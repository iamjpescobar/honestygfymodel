"""
NFL props on last season + this one (10-11): the 2025 box scores in this
season's shape (nfl_precompute.load_or_fetch_prior_logs), the defense
strength FITTED and TESTED (nfl_prop_check.fit_strength / split_rows),
and the strength applied in the projection (nfl_projection).

Plain script — exits non-zero on failure. Walk-forward rows carry the
shape nfl_prop_check.walk_forward returns; summaries carry ESPN's
boxscore shape (the parser's own fixture shape) — rule 5. Temp dirs only.

Negative controls, confirmed red by exit code when written (rule 4):
  - fit_strength adopting the fitted strength without the test
    -> "a world where the defense means nothing: not adopted" fails
  - split_rows testing on the weeks it fitted on
    -> "the test never sees a week the fit saw" fails
  - project_player ignoring matchup_strength
    -> "half strength moves the projection by the square root" fails
"""
import json
import math
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

import nfl_precompute as npc  # noqa: E402
import nfl_prop_check as pck  # noqa: E402
from engines import nfl_projection as nproj  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def sig(x):
    return 1 / (1 + math.exp(-x))


# --- 1. the strength fit, on simulated rows ---------------------------------
def world(true_s, n=4000, seed=5, weeks=(2, 18)):
    """Rows where each player-game's over chance moves with the defense by
    true_s (0 = the defense means nothing)."""
    g = random.Random(seed)
    rows = []
    for i in range(n):
        base = g.uniform(-0.6, 0.6)
        d = g.gauss(0, 0.8)                  # how soft the defense is, in log-odds
        by_s = {s: sig(base + s * d) for s in pck.STRENGTH_GRID}
        y = 1 if g.random() < sig(base + true_s * d) else 0
        wk = g.randint(*weeks)
        rows.append(("pass_yds", wk, str(i), by_s[1.0], by_s[0.0], 0.5, y, by_s))
    return rows


real = world(0.5)
train, test = pck.split_rows(real, [])
fit = pck.fit_strength(train, test)["pass"]
check("a defense that matters at half strength: fitted near half", fit["fitted"] in (0.25, 0.5, 0.75))
check("...tested on weeks it had not seen, and adopted", fit["in_number"] and fit["n"] > 0
      and fit["verdict"]["verdict"] == "beats")
# The fitting weeks LOOK like the defense matters (a fluke of those weeks);
# the later weeks say it does not. The fit finds a strength, the test must
# throw it out.
fluke = world(0.5, seed=9, weeks=(2, 9)) + world(0.0, seed=11, weeks=(10, 18))
train0, test0 = pck.split_rows(fluke, [])
f0 = pck.fit_strength(train0, test0)["pass"]
check("fixture: the fit weeks really do suggest a strength", f0["fitted"] and f0["fitted"] > 0)
check("a world where the defense means nothing: not adopted", not f0["in_number"]
      and f0["strength"] == 0.0)
check("families with no rows stay out", not pck.fit_strength(train, test)["rush"]["in_number"])

# --- 2. which weeks fit, which test ---------------------------------------
prior = [("rec", w, "p", .5, .5, .5, 1, None) for w in range(2, 19)]
cur = [("rec", w, "c", .5, .5, .5, 1, None) for w in range(2, 6)]
tr, te = pck.split_rows(prior, cur)
check("the test never sees a week the fit saw",
      max(r[1] for r in tr) < min(r[1] for r in te if r[2] == "p"))
check("this season is always in the test, never in the fit",
      all(r[2] == "p" for r in tr) and sum(1 for r in te if r[2] == "c") == len(cur))
tr2, te2 = pck.split_rows([], cur)
check("no last season: this season's own weeks split the same way",
      tr2 and te2 and max(r[1] for r in tr2) < min(r[1] for r in te2))

# --- 3. the projection reads the strength ---------------------------------
p = {"role": "QB", "gp": 5, "pass_yds": 220.0, "pass_att": 33.0, "pass_gp": 5}
team = {"targets_pg": 33.0, "carries_pg": 25.0}
opp = {"ypt_allowed": 8.46, "ypc_allowed": 4.3}
league = {"yards_per_target": 6.0, "ypc": 4.3, "td_per_point": 0.11,
          "matchup_in_number": {"rush": True, "rec": True, "pass": True}}
full = nproj.project_player(p, team, opp, league, 21.0)["pass_yds"]
half = nproj.project_player(p, team, opp, dict(league, matchup_strength={"pass": 0.5}),
                            21.0)["pass_yds"]
plain = 33.0 * (220.0 / 33.0)
check("half strength moves the projection by the square root",
      abs(half - plain * (8.46 / 6.0) ** 0.5) < 0.6 and full > half > plain)
off = nproj.project_player(p, team, opp, dict(league, matchup_strength={"pass": 0.0}),
                           21.0)["pass_yds"]
check("strength 0 is no defense at all", abs(off - plain) < 0.11)

# --- 4. last season's box scores, once -----------------------------------
def summ(home, away, h_ab, a_ab):
    def team(nm, ab):
        return {"team": {"displayName": nm, "abbreviation": ab},
                "statistics": [{"name": "totalYards", "displayValue": "350"}]}

    def players(nm):
        return {"team": {"displayName": nm}, "statistics": [{
            "name": "passing", "labels": ["C/ATT", "YDS", "TD", "INT"],
            "athletes": [{"athlete": {"id": nm[:2] + "qb", "displayName": nm + " QB"},
                          "stats": ["20/30", "250", "2", "0"]}]}]}
    return {"boxscore": {"teams": [team(away, a_ab), team(home, h_ab)],
                         "players": [players(away), players(home)]}}


pf = [{"date": "2025-09-04", "event_id": "e1", "home": "Home A", "away": "Away B",
       "home_id": "1", "away_id": "2", "home_score": 24, "away_score": 20},
      {"date": "2025-09-14", "event_id": "e2", "home": "Away B", "away": "Home A",
       "home_id": "2", "away_id": "1", "home_score": 10, "away_score": 13}]
calls = []


def fake_summary(eid):
    calls.append(eid)
    f = next(x for x in pf if x["event_id"] == eid)
    return summ(f["home"], f["away"], f["home"][:3].upper(), f["away"][:3].upper())


with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "prior_logs.json"
    got = npc.load_or_fetch_prior_logs(pf, fake_summary, path=path, sleep=0)
    check("2025 finals come back in this season's shape",
          got and all(k in got["finals"][0] for k in ("week", "event_id", "home_abbr", "home_box",
                                                      "away_score")))
    check("weeks are 2025 weeks (opener = week 1, Sep 14 = week 2)",
          [f["week"] for f in got["finals"]] == [1, 2])
    check("players come back through this season's parser", len(got["logs"]) == 2)
    n_calls = len(calls)
    again = npc.load_or_fetch_prior_logs(pf, fake_summary, path=path, sleep=0)
    check("fetched once: the second run reads the file", again == got and len(calls) == n_calls)
    short = npc.load_or_fetch_prior_logs(pf + [dict(pf[0], event_id="bad")] * 3,
                                         lambda e: {} if e == "bad" else fake_summary(e),
                                         path=Path(td) / "short.json", sleep=0)
    check("a short fetch is not saved (the test runs on this season, and says so)",
          short == {} and not (Path(td) / "short.json").exists())

# --- 5. wiring --------------------------------------------------------------
src = (ROOT / "nfl_precompute.py").read_text(encoding="utf-8")
check("the nightly hands last season to the prop test", "prior=_plogs or None" in src)
check("the adopted strengths reach the page's projections",
      'league["matchup_strength"] = res["matchup_strength"]' in src)
wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the nightly commits the 2025 box scores", "data/nfl/prior_logs.json" in wf)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall two-season NFL checks passed")
