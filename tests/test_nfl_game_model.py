"""
NFL game model — engines/nfl_game_model.py and nfl_prior_season.py.

Plain script — exits non-zero on failure. Fixture: a simulated 2025
season (32 teams, 272 games) and four weeks of 2026 with KNOWN team
strengths, the 2025 slate served through ESPN's header shape with every
game repeated on each day of its week (the 09-27 lesson: the NFL
scoreboard answers a date with its whole week).

Negative controls, confirmed red by exit code when written (rule 4):
  - collector keyed by list append instead of event id -> "each 2025
    game collected once" fails (seven copies of every week)
  - the cover probability reading the spread with the wrong sign ->
    "a home favourite laying more points covers less often" fails
  - fitting on 2026's four weeks instead of 2025 -> "fitted on 2025
    while 2026 is young" fails
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import nfl_precompute as npc               # noqa: E402
import nfl_prior_season as nps             # noqa: E402
from engines import nfl_game_model as ngm  # noqa: E402

failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


nps.time.sleep = lambda *_a: None   # the collector's politeness pause
G = random.Random(23)
TEAMS = {str(i + 1): f"T{i + 1:02d}" for i in range(32)}
OFF = {t: G.gauss(0, 3.5) for t in TEAMS}
DEF = {t: G.gauss(0, 3.0) for t in TEAMS}


def play(h, a, g):
    mh = 22.5 + OFF[h] - DEF[a] + 1.2
    ma = 22.5 + OFF[a] - DEF[h] - 1.2
    hs = max(0, int(round(g.gauss(mh, 9.5))))
    as_ = max(0, int(round(g.gauss(ma, 9.5))))
    if hs == as_:
        hs += 3
    return hs, as_


def season(start, weeks, g, prefix):
    out = []
    for w in range(weeks):
        ids = list(TEAMS)
        g.shuffle(ids)
        day = start + timedelta(days=7 * w)
        for k in range(16):
            h, a = ids[2 * k], ids[2 * k + 1]
            hs, as_ = play(h, a, g)
            out.append({"event_id": f"{prefix}{w:02d}{k:02d}", "date": day.isoformat(),
                        "home_id": h, "away_id": a, "home": TEAMS[h], "away": TEAMS[a],
                        "home_score": hs, "away_score": as_})
    return out


PRIOR = season(date(2025, 9, 7), 17, G, "P")
CUR = season(date(2026, 9, 13), 4, G, "C")


# -------------------------------------------- 1. the 2025 collector
def header_event(f, status="STATUS_FINAL"):
    def comp(tid, side, score):
        return {"homeAway": side, "score": str(score), "id": tid,
                "displayName": TEAMS[tid], "abbreviation": TEAMS[tid]}
    return {"id": f["event_id"], "date": f"{f['date']}T17:00Z",
            "fullStatus": {"type": {"name": status, "completed": True, "shortDetail": "Final"}},
            "competitors": [comp(f["away_id"], "away", f["away_score"]),
                            comp(f["home_id"], "home", f["home_score"])]}


by_week = {}
for f in PRIOR:
    by_week.setdefault(f["date"], []).append(f)


def sb_fn(d):
    # The WHOLE week for any date inside it — ESPN's real behaviour.
    for sunday, games in by_week.items():
        s = date.fromisoformat(sunday)
        if s - timedelta(days=3) <= d <= s + timedelta(days=3):
            from engines.espn_wnba import _normalize_header_events
            return _normalize_header_events({"events": [header_event(x) for x in games]})
    return {"events": []}


got = nps.collect(sb_fn, npc.slate_game, sleep=0)
check(f"each 2025 game collected once ({len(got)} of {len(PRIOR)})", len(got) == len(PRIOR))
check("ids and scores carried", all(f["home_id"] in TEAMS and f["home_score"] is not None for f in got))
tmp = Path(__file__).resolve().parent / "_tmp_nfl_prior.json"
try:
    loaded = nps.load_or_fetch(sb_fn, npc.slate_game, path=tmp)
    check("a full season is saved once", tmp.exists() and len(loaded) == len(PRIOR))
    again = nps.load_or_fetch(lambda d: (_ for _ in ()).throw(RuntimeError("no fetch")),
                              npc.slate_game, path=tmp)
    check("...and then READ, never refetched", len(again) == len(PRIOR))
finally:
    if tmp.exists():
        tmp.unlink()
short = nps.load_or_fetch(lambda d: {"events": []}, npc.slate_game, path=tmp)
check("a short season is refused, not written", not tmp.exists() and short == [])

# ---------------------------------------------------- 2. build + fit
model = ngm.build(CUR, got)
check("model built", model is not None)
p = model["params"]
check("fitted on 2025 while 2026 is young", p["fit_on"] == "prior")
check(f"margin SD measured near the fixture's ~13.4 (got {p['sd_margin']})",
      11.0 < p["sd_margin"] < 16.0)
check("home edge measured above 1", model["league"]["home_mult"] > 1.0)
v = model["validation"]
check(f"beats the coin flip ({v['model']['log_loss']} vs {v['coin_flip']['log_loss']})",
      v["beats_coin"])
check("margin beats the plain home-edge guess", v["margin_beats_home_edge"])
check("carryover measured between 0 and 1",
      p["carryover"] is not None and 0 <= p["carryover"] <= 1)

# ----------------------------------------------------- 3. projection
best = max(TEAMS, key=lambda t: OFF[t] - DEF[t])
worst = min(TEAMS, key=lambda t: OFF[t] - DEF[t])
pj = ngm.project(model, best, worst, {"spread": -7.0, "total": 44.5,
                                      "details": f"{TEAMS[best]} -7.0",
                                      "home_ml": -320, "away_ml": 260},
                 home_abbr=TEAMS[best], away_abbr=TEAMS[worst])
check("the best team at home over the worst is a clear favourite", pj["p_home"] > 0.7)
check("fair spread is the negative of the projected margin",
      abs(pj["fair_spread_home"] + pj["margin"]) < 0.11)
lay7 = pj["p_home_cover"]
lay14 = ngm.project(model, best, worst, {"spread": -14.0, "total": 44.5,
                                         "details": f"{TEAMS[best]} -14.0"},
                    home_abbr=TEAMS[best], away_abbr=TEAMS[worst])["p_home_cover"]
check("a home favourite laying more points covers less often", lay14 < lay7 < pj["p_home"])
check("over/under and no-vig market gap computed",
      "p_over" in pj and "edge_home" in pj and abs(pj["market_home"] + pj["market_away"] - 1) < 1e-9)
bad = ngm.project(model, best, worst, {"spread": -7.0, "total": 44.5,
                                       "details": f"{TEAMS[worst]} -7.0"},
                  home_abbr=TEAMS[best], away_abbr=TEAMS[worst])
check("a line that contradicts itself gives NO cover probability, and says why",
      "p_home_cover" not in bad and bad.get("market_note"))
check("an unknown team gets no projection", ngm.project(model, "999", best) is None)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
