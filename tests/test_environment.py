"""
Today's scoring environment (10-25) — engines/game_model.environment and
its wiring into every game model (MLB and NHL through game_model.build,
NBA and NFL through nfl_game_model.build).

Izzy: "make sure simulators and model are adaptive to today's game style
... for all of the sports that have a simulator and a model". Measured on
last season's finals before building: the NBA's league scoring moved ~10
points inside the season and a recency-weighted rate beat the flat one
(half-life 100, z 2.04); NHL / MLB / NFL did not drift (z <= 0.9). So it
is tested per sport every night and used only where it wins.

Plain script — exits non-zero on failure. Synthetic finals. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - environment applying on the prior-season test alone (ignoring this
    season's test) -> "not used when this season's test does not beat" fails
  - _ewma_errors adding a game to the rate BEFORE scoring it
    -> "each game is priced before it is played" fails
  - build() ignoring an applied environment
    -> "the build scales the league by the environment" fails
"""
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import game_model as gm  # noqa: E402
from engines import nfl_game_model as ngm  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def season(start, n, level, seed, drift=0.0, period=400.0, teams=12):
    """n finals; each side scores normal(level/2 x (1 + drift x sin)) ."""
    r = random.Random(seed)
    out = []
    for i in range(n):
        d = (start + timedelta(days=i // 6)).isoformat()
        m = level / 2.0 * (1 + drift * math.sin(2 * math.pi * i / period))
        h, a = r.sample(range(teams), 2)
        out.append({"date": d, "home": f"T{h}", "away": f"T{a}",
                    "hs": max(0, int(round(r.gauss(m * 1.01, 11)))),
                    "as": max(0, int(round(r.gauss(m * 0.99, 11))))})
    return gm.clean_finals(out)


# --- the pieces -----------------------------------------------------------------------
tot = [("d", 10.0), ("d", 20.0), ("d", 40.0)]
check("each game is priced before it is played (first error is game 2 vs game 1)",
      gm._ewma_errors(tot, None, 1) == [(20 - 10) ** 2, (40 - 15) ** 2])
check("the recency-weighted rate leans to the latest games",
      gm._ewma_rate([("d", 200.0)] * 50 + [("d", 240.0)] * 50, 20) > 115)

# --- a drifting league whose new season runs hotter ------------------------------------
prior = season(date(2025, 10, 21), 1200, 230, 1, drift=0.05)
hot = season(date(2026, 10, 21), 140, 250, 2)
E = gm.environment(prior, hot)
print("    ", gm.env_line("TEST", E))
check("a drifting league: the half-life beats flat on last season",
      (E["prior_test"] or {}).get("verdict") == "beats" and E["half_life"] in gm.ENV_HALF_LIVES)
check("a hotter season: the environment beats last season's average and is used",
      E["applied"] and (E["test"] or {}).get("verdict") == "beats")
check("the rate in use moves toward this season's scoring",
      E["used_rate"] < E["rate"] <= E["season_rate"] + 1)

# --- a steady league: nothing to follow -------------------------------------------------
steady = season(date(2025, 10, 21), 1200, 230, 3)
E2 = gm.environment(steady, season(date(2026, 10, 21), 140, 250, 4))
check("a steady league fails the first test and keeps its rate",
      not E2["applied"] and E2["rate"] == E2["used_rate"])

# --- drifting last season, but this season sits on last season's average ----------------
same = season(date(2026, 10, 21), 140, 230, 6)
E3 = gm.environment(prior, same)
print("    ", gm.env_line("TEST", E3))
check("not used when this season's test does not beat",
      (E3["prior_test"] or {}).get("verdict") == "beats"
      and (E3["test"] or {}).get("verdict") != "beats" and not E3["applied"]
      and E3["rate"] == E3["used_rate"])
check("too little of either season -> not measured, rate unchanged",
      not gm.environment(prior[:100], hot)["applied"]
      and not gm.environment(prior, hot[:10])["applied"])

# --- the builds -------------------------------------------------------------------------
B = gm.build(hot, prior_finals=prior)
check("the build scales the league by the environment",
      B and B["environment"]["applied"] and B["league"]["league_rate"] == E["rate"]
      and B["league"]["from"].endswith("+environment"))
B2 = gm.build(same, prior_finals=prior)
check("...and leaves it alone when the environment is not used",
      B2 and not B2["environment"]["applied"]
      and B2["league"]["league_rate"] == gm.league_constants(prior)["league_rate"])


def nfl_rows(fs):
    return [{"date": f["date"], "home_id": f["home"], "away_id": f["away"],
             "home_score": f["hs"], "away_score": f["as"] + (1 if f["hs"] == f["as"] else 0)}
            for f in fs]


N = ngm.build(nfl_rows(hot), nfl_rows(prior))
check("the NBA / NFL model carries the environment too",
      N and "environment" in N and (N["league"]["from"].endswith("+environment")
                                    == bool(N["environment"]["applied"])))

# --- wiring: one verify line per sport ---------------------------------------------------
src = {p: (ROOT / p).read_text(encoding="utf-8") for p in
       ("nba_precompute.py", "nfl_precompute.py", "mlb_model_precompute.py",
        "app/engines/nhl_model.py")}
for p, sport in (("nba_precompute.py", "NBA"), ("nfl_precompute.py", "NFL"),
                 ("mlb_model_precompute.py", "MLB"), ("app/engines/nhl_model.py", "NHL")):
    check(f"{sport} nightly prints its environment line", f'env_line("{sport}"' in src[p])

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall environment checks passed")
