"""
NBA double-doubles / triple-doubles (11-02) — engines/nba_doubles and the
"Double-double / Triple-double" card on NBA Trends.

Izzy (11-02): "how can I research double doubles and triple doubles?"

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - a missing stat read as 0 -> "a game missing a stat is left out" fails
  - the chance as two stats' chances multiplied -> "the chance counts the
    SAME simulated game" fails
  - the blend without his record (weight 0) -> "same simulator chance: the
    player who keeps getting them reads higher" fails
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nba_doubles as dd  # noqa: E402
from engines import nba_sim as ns  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


check("10+ in two stats = 2 (a double-double), named",
      dd.game_cats({"pts": 22, "reb": 10, "ast": 4}) == (2, "PTS+REB"))
check("three at 10+ = a triple-double", dd.game_cats({"pts": 10, "reb": 12, "ast": 11})[0] == 3)
check("a game missing a stat is left out (missing is never zero)",
      dd.game_cats({"pts": 22, "reb": 10}) == (None, None))
row = {"opp": "BOS", "trend": [
    {"date": "2026-03-01", "opp": "BOS", "tag": "LAST", "pts": 20, "reb": 11, "ast": 3},
    {"date": "2026-10-10", "opp": "NYK", "tag": "PRE", "pts": 30, "reb": 15, "ast": 2},
    {"date": "2026-10-22", "opp": "NYK", "tag": "REG", "pts": 15, "reb": 8, "ast": 4},
    {"date": "2026-10-28", "opp": "BOS", "tag": "REG", "pts": 12, "reb": 3, "ast": 10},
    {"date": "2026-10-30", "opp": "MIA", "tag": "REG", "pts": 9, "reb": None, "ast": 1}]}
h = dd.history(row)
check("history: regular games, oldest first, preseason left out, incomplete games out",
      [x[1] for x in h] == [2, 1, 2] and h[0][0] == "03/01 BOS")
check("preseason when asked", len(dd.history(row, include_pre=True)) == 4)
check("how he got them", dd.how_he_got_them(h) == {"PTS+REB": 1, "PTS+AST": 1})
a = np.r_[np.full(50, 20), np.full(50, 5)]
check("the chance counts the SAME simulated game (stats that rise together)",
      dd.sim_chance({"pts": a, "reb": a.copy(), "ast": np.zeros(100)}) == {"dd": 0.5, "td": 0.0})
check("no assists array: no chance invented", dd.sim_chance({"pts": a, "reb": a}) is None)
s = ns.simulate(112, 110, 13, 19, [{"pid": "x", "side": "home", "min": 34,
                                    "mu": {"pts": 25, "reb": 12, "ast": 9, "tpm": 1}}],
                {"pts": 8, "reb": 6, "ast": 5, "tpm": 4}, None, n=20000)
c = dd.sim_chance(s["stats"]["x"])
check("a 25 / 12 / 9 projection: a likely double-double, a live triple-double",
      0.6 < c["dd"] < 0.9 and 0.1 < c["td"] < 0.4)
import math  # noqa: E402
none = []
check("no record yet: his rate is the league's", dd.record_rate(none) == (dd.DD_LEAGUE, 0))
p0 = dd.dd_chance(0.10, none)
x = dd.DD_A + dd.DD_B * math.log(0.1 / 0.9) + dd.DD_C * math.log(dd.DD_LEAGUE / (1 - dd.DD_LEAGUE))
check("the blend is the measured logit formula", abs(p0 - 1 / (1 + math.exp(-x))) < 1e-9)
often = [("g", 2, "PTS+REB", "REG", "X")] * 20 + [("g", 1, "PTS", "REG", "X")] * 10
rare = [("g", 1, "PTS", "REG", "X")] * 30
check("same simulator chance: the player who keeps getting them reads higher",
      dd.dd_chance(0.10, often) > 0.25 > dd.dd_chance(0.10, rare))
check("his record counts his last 30 regular games, preseason out",
      dd.record_rate(often + [("g", 2, "PTS+REB", "PRE", "X")] * 5)[1] == 30
      and dd.record_rate([("g", 2, "x", "REG", "X")] * 40 + rare)[0]
      == dd.record_rate(rare)[0])
check("no simulator chance: no blend invented", dd.dd_chance(None, often) is None)
src = (ROOT / "app" / "engines" / "nba_doubles.py").read_text()
check("the measurement is written beside the weights",
      "z 2.94 vs the sim, 3.01 vs the record" in src and "DD_A, DD_B, DD_C = 0.3, 0.3, 0.8" in src)
page = (ROOT / "app" / "views" / "NBA_Trends.py").read_text()
check("NBA Trends shows the card: the tested blend, triple-double THIN, chips, how, chart",
      '"Double-double", "tested"' in page and '"THIN · runs low"' in page
      and "_dd.dd_chance(_ddc[\"dd\"], _dd.history(r))" in page and "_dd.history(r, pre)" in page and "_dd.sim_chance(" in page
      and "_dd_sim(" in page and "_dd.how_he_got_them(" in page)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
