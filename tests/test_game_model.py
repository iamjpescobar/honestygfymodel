"""
The shared game model (engines/game_model, engines/model_math) and the
MLB builder/reader (mlb_model_precompute, engines/mlb_game_model).

Plain script — exits non-zero on failure. Fixtures are simulated seasons
with KNOWN team and starter strengths, delivered in statsapi's real
response shape (dates[].games[] with teams.home.team.name, score,
linescore.currentInning, probablePitcher) so the parser is exercised the
way production calls it (rule 5).

Negative controls, confirmed red by exit code when written (rule 4):
  - clean_finals rebuilt from five fields again -> section 2 fails
    (that exact defect shipped in the first draft: "with starters"
    scored identical to team-only to four decimals)
  - walk_forward reading the game's own result into the team totals
    before predicting it -> section 3's look-ahead check fails
  - project() falling back to league average for an unknown team ->
    section 5 fails
"""
import math
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import model_math as mm      # noqa: E402
from engines import game_model as gm      # noqa: E402
from engines import mlb_game_model as mgm  # noqa: E402
import mlb_model_precompute as mpc        # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# ---------------------------------------------------------------- 1. math
p_even = mm.win_prob(4.5, 4.5, None, 0.5)
check("equal teams, fair tie-break -> exactly 50%", abs(p_even - 0.5) < 1e-9)
check("better offense wins more", mm.win_prob(5.0, 4.0) > 0.5)
check("tie-break rate moves the number in its direction",
      mm.win_prob(4.5, 4.5, None, 0.6) > mm.win_prob(4.5, 4.5, None, 0.4))
check("fair odds: 60% -> -150, 40% -> +150",
      mm.fair_american(0.6) == -150 and mm.fair_american(0.4) == 150)
h, a = mm.no_vig_pair(-150, 130)
check("no-vig pair sums to 1 and favours the favourite", abs(h + a - 1) < 1e-9 and h > a)
check("an impossible score expectation returns None, not a truncated pmf",
      mm.score_pmf(60.0) is None)
o = mm.total_over_prob(4.5, 4.5, 9)
check("whole-number total excludes the push from both sides", o is not None and 0.4 < o < 0.6)

# A fitter that cannot recover a known answer measures nothing (rule 3).
rng = random.Random(7)
obs = []
for _ in range(400):
    p = rng.betavariate(25, 75)
    n = rng.randint(80, 600)
    obs.append((sum(rng.random() < p for _ in range(n)), n))
mu, s = mm.fit_beta_prior(obs)
check(f"beta prior recovers mean .25 / strength 100 (got {mu:.3f} / {s:.0f})",
      abs(mu - 0.25) < 0.01 and 60 < s < 160)


# --------------------------------------------------- fixtures: a season
def _nb(mu, r, g):
    lam = g.gammavariate(r, mu / r)
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= g.random()
        if p < L:
            return k
        k += 1


def statsapi_season(seed=3, days=120, sp_sd=0.35):
    g = random.Random(seed)
    teams = [f"Club {i}" for i in range(20)]
    st = {t: (math.exp(g.gauss(0, .12)), math.exp(g.gauss(0, .10))) for t in teams}
    rot = {t: [str(1000 + i * 10 + j) for j in range(5)] for i, t in enumerate(teams)}
    spq = {p: math.exp(g.gauss(0, sp_sd)) for t in teams for p in rot[t]}
    nxt = {t: 0 for t in teams}
    games, logs = [], {}
    for d in range(days):
        day = (date(2026, 4, 1) + timedelta(d)).isoformat()
        ts = teams[:]
        g.shuffle(ts)
        for i in range(0, len(ts), 2):
            h, a = ts[i], ts[i + 1]
            hp, ap = rot[h][nxt[h] % 5], rot[a][nxt[a] % 5]
            nxt[h] += 1
            nxt[a] += 1
            dh = st[h][1] * (1 / 3 + 2 / 3 * spq[hp])
            da = st[a][1] * (1 / 3 + 2 / 3 * spq[ap])
            hs, as_ = _nb(4.5 * st[h][0] * da * 1.03, 4, g), _nb(4.5 * st[a][0] * dh / 1.03, 4, g)
            inn = 9
            while hs == as_:
                inn += 1
                hs += g.random() < .3
                as_ += g.random() < .28
            games.append({
                "gamePk": len(games), "officialDate": day,
                "status": {"abstractGameState": "Final", "detailedState": "Final"},
                "linescore": {"currentInning": inn, "scheduledInnings": 9},
                "teams": {"home": {"team": {"name": h}, "score": hs,
                                   "probablePitcher": {"id": int(hp), "fullName": "P" + hp}},
                          "away": {"team": {"name": a}, "score": as_,
                                   "probablePitcher": {"id": int(ap), "fullName": "P" + ap}}}})
            for p, ra in ((hp, as_), (ap, hs)):
                outs = g.randint(12, 21)
                logs.setdefault(p, []).append({"date": day, "stat": {
                    "gamesStarted": 1, "inningsPitched": f"{outs // 3}.{outs % 3}",
                    "runs": max(0, round(ra * outs / 27 * g.uniform(.7, 1.3)))}})
    games.append({"gamePk": -1, "officialDate": "2026-05-01",
                  "status": {"abstractGameState": "Final", "detailedState": "Postponed"},
                  "teams": {"home": {"team": {"name": "Club 0"}}, "away": {"team": {"name": "Club 1"}}}})
    games.append({"gamePk": -2, "officialDate": "2026-05-02",
                  "status": {"abstractGameState": "Final", "detailedState": "Final"},
                  "teams": {"home": {"team": {"name": "Club 0"}, "score": 3},
                            "away": {"team": {"name": "Club 1"}, "score": 3}}})

    def get(url):
        m = re.search(r"startDate=([\d-]+)&endDate=([\d-]+)", url)
        if m:
            s_, e_ = m.groups()
            return {"dates": [{"games": [x for x in games if s_ <= x["officialDate"] <= e_]}]}
        m = re.search(r"people/(\d+)/stats", url)
        if m:
            return {"stats": [{"splits": logs.get(m.group(1), [])}]}
        return None
    return get, games


# ---------------------------------------------------- 2. parse + carry
get, raw_games = statsapi_season()
parsed = mpc.parse_schedule({"dates": [{"games": raw_games}]})
check("postponed and tied games are excluded (missing is not zero)",
      len(parsed) == len(raw_games) - 2)
check("extra innings read from the linescore",
      any(f["extra"] for f in parsed) and any(f["extra"] is False for f in parsed))
check("innings pitched '5.2' is 17 outs", mpc._ip_to_outs("5.2") == 17)
cleaned = gm.clean_finals(parsed)
check("clean_finals CARRIES starter ids through (the first-draft defect)",
      all(f.get("home_sp") and f.get("away_sp") for f in cleaned))

# ----------------------------------------------- 3. walk-forward honesty
small = cleaned[:300]
wf = gm.walk_forward(small, 20.0)
first_date = small[0]["date"]
check("nothing is predicted on the first date (no earlier games exist)",
      all(p["date"] > first_date for p in wf))
# Look-ahead check: flip every result ON ONE DATE and the predictions FOR
# that date must not move — they may only depend on earlier dates.
target = sorted({f["date"] for f in small})[5]
flipped = [dict(f, hs=f["as"], **{"as": f["hs"]}) if f["date"] == target else f for f in small]
wf2 = gm.walk_forward(flipped, 20.0)
same = [(a["p_home"], b["p_home"]) for a, b in zip(wf, wf2) if a["date"] == target]
check("a game's own result cannot leak into its prediction",
      same and all(abs(x - y) < 1e-12 for x, y in same))

# ----------------------------------------------- 4. the full MLB builder
out_path = Path(__file__).resolve().parent / "_tmp_model.json"
mpc.OUT = out_path
try:
    rc = mpc.main(today=date(2026, 10, 3), _get_json=get)
    import json
    model = json.loads(out_path.read_text())
finally:
    if out_path.exists():
        out_path.unlink()
check("builder exits 0", rc == 0)
v = model["validation"]
check(f"beats the coin flip walk-forward ({v['model']['log_loss']} vs {v['coin_flip']['log_loss']})",
      v["beats_coin"])
check("dispersion is measured, finite and in the neighbourhood of the truth (4)",
      model["params"]["dispersion"] and 2.0 < model["params"]["dispersion"] < 8.0)
wt, ws = model["validation_team_only"], model["validation_with_starters"]
check("with-starters is a DIFFERENT walk-forward from team-only",
      ws and abs(ws["model"]["log_loss"] - wt["model"]["log_loss"]) > 1e-4)
check("use_starters is exactly the comparison, not a default",
      model["use_starters"] == (ws["model"]["log_loss"] < wt["model"]["log_loss"]))
check("starters genuinely matter in this fixture and the model finds it", model["use_starters"])
cal = [c for c in v["calibration"] if c["n"] >= 100]
check("calibrated: every well-populated band within 6 points",
      cal and all(abs(c["predicted"] - c["actual"]) < 0.06 for c in cal))

# ---------------------------------------------------- 5. the reader side
pj = mgm.project_game("Club 0", "Club 1", "1000", "1010", model=model)
check("projection has the fields the card draws",
      pj and {"home_score", "away_score", "p_home", "fair_home", "total"} <= set(pj))
check("probabilities sum to 1", abs(pj["p_home"] + pj["p_away"] - 1) < 1e-9)
check("an unknown team gets NO projection, not a league-average one",
      mgm.project_game("Nobody FC", "Club 1", model=model) is None)
one = mgm.project_game("Club 0", "Club 1", "1000", None, model=model)
check("one starter known and one not -> neither used (no lopsided layer)",
      one and one["starters_used"] is False)
check("market gap computed only when both prices are present",
      "edge_home" in mgm.project_game("Club 0", "Club 1", model=model,
                                      market={"home_ml": -140, "away_ml": 120})
      and "edge_home" not in mgm.project_game("Club 0", "Club 1", model=model,
                                              market={"home_ml": -140}))

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
