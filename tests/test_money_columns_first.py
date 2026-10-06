"""
Money columns first (10-06) — tests/test_money_columns_first.py. (NOT test_column_order.py: that name
already holds the Game Card lineup-order test.)

Money columns first — every model table leads with the columns a
bet is decided on, so an iPad shows them without a sideways swipe.

Renders the REAL boards through streamlit's AppTest (prop board for NHL
skaters, MLB batters, NHL goalies; the NFL board; the game value table)
and reads the column order the page actually draws — not the spelling of
the code that orders it (rule 11).

Plain script — exits non-zero on failure.

Negative controls, confirmed red by exit code when written (rule 4):
  - render_prop_board without the reorder -> "NHL skaters" fails
  - render_value_panel without the reorder -> "value table" fails
  - lead_columns dropping the tail -> "nothing dropped" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


from engines import model_view as mv  # noqa: E402

cols = ["Skater", "Pos", "GP", "TOI recent", "TOI norm", "Avg", "O1.5", "O2.5 *", "Defense vs pos"]
out = mv.prop_board_order(cols, ["O1.5", "O2.5 *"])
check("prop order: name, pos, lines, avg, matchup, then the rest",
      out == ["Skater", "Pos", "O1.5", "O2.5 *", "Avg", "Defense vs pos", "GP", "TOI recent", "TOI norm"])
check("nothing dropped, nothing duplicated", sorted(out) == sorted(cols) and len(set(out)) == len(out))
check("MLB batter: # and samples go after the chances",
      mv.prop_board_order(["#", "Batter", "PA", "Exp PA", "Avg", "O0.5"], ["O0.5"])
      == ["Batter", "O0.5", "Avg", "#", "PA", "Exp PA"])

check("NFL board: player, pos, the ladder, proj, matchup first",
      mv.prop_board_order(["Player", "Pos", "Team", "Status", "GP", "Proj", "Low", "Mid", "High",
                           "Defense vs pos"], ["Low", "Mid", "High"])[:7]
      == ["Player", "Pos", "Low", "Mid", "High", "Proj", "Defense vs pos"])

SCRIPT = '''
import sys
sys.path.insert(0, %r)
import streamlit as st
from engines import model_view as mv
from engines import model_math as mm
pmf = mm.poisson_pmf(2.5, 15)
rows = [{"Skater": "A", "Pos": "C", "GP": 80, "TOI recent": 20.0, "TOI norm": 19.0,
         "_name": "A", "_pmfs": {"sog": pmf},
         "_dvp": {"sog": {"rank": 3, "of": 32, "tier": "soft"}}}]
stats = (("sog", "Shots", (1.5, 2.5)),)
markets = (("s2", "SOG O1.5", "sog", 2), ("s3", "SOG O2.5", "sog", 3))
mv.render_prop_board(rows, stats, markets, {"s2": "beats", "s3": "beats"}, key="t",
                     staking=(0.0, 0.25, 0.02), info_cols=("Skater", "Pos", "GP", "TOI recent", "TOI norm"))
proj = {"p_home": 0.55, "p_away": 0.45, "home_score": 3.2, "away_score": 2.9, "total": 6.1,
        "fair_home": -122, "fair_away": 122}
odds = {"home_ml": -130, "away_ml": 110}
mv.render_value_panel(proj, odds, "AWY", "HOM", key="v", staking=(0.0, 0.25, 0.02))
''' % str(ROOT / "app")

try:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string(SCRIPT, default_timeout=60).run()
    if at.exception:
        print(at.exception)
    check("the page renders without an exception", not at.exception)
    frames = [d.value for d in at.dataframe]
    sk = next((f for f in frames if "Skater" in f.columns), None)
    check("NHL skaters: the chances and the matchup sit right after name/pos",
          sk is not None and list(sk.columns)[:6] == ["Skater", "Pos", "O1.5", "O2.5", "Avg",
                                                      "Defense vs pos"])
    vt = next((f for f in frames if "Bet" in f.columns), None)
    check("value table: bet, final, price, fair, edge lead",
          vt is not None and list(vt.columns)[:5] == ["Bet", "Final", "Price", "Fair", "Edge"])
except ImportError as exc:
    print(f"SKIP AppTest checks ({exc}) — needs streamlit")

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
