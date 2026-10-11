"""
Long Shots (10-11) — engines/long_shots and views/Long_Shots.py.

Plain script — exits non-zero on failure. Player rows carry the board's
shape ({"_name", "_probs": {market_key: raw}}), curves calibration_map's,
NHL prop rows nhl_model's (ice, pp) — rule 5.

Negative controls, confirmed red by exit code when written (rule 4):
  - rows_from_markets without the graded-range gate
    -> "a call past its curve's graded range is not listed" fails
  - rows_from_markets listing the raw chance instead of the delivered one
    -> "the chance listed is the DELIVERED one" fails
  - in_band ignoring the +2000 end
    -> "a 3% call (+3200) is not a listed long shot" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import long_shots as ls  # noqa: E402
from engines import model_math as mm  # noqa: E402
from engines import model_view as mv  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- 1. the band ------------------------------------------------------------
check("+300 .. +2000 is 25% .. 1/21", abs(ls.HI_P - 0.25) < 1e-12 and abs(ls.LO_P - 1 / 21) < 1e-12)
check("a 10% call is a long shot", ls.in_band(0.10))
check("a 30% call (+233) is not a long shot", not ls.in_band(0.30))
check("a 3% call (+3200) is not a listed long shot", not ls.in_band(0.03))

# --- 2. rows from a board ------------------------------------------------------
markets = (("g1", "Goal O0.5", "g", 1), ("g2", "Goal O1.5", "g", 2))
# goals: a curve that pulls calls DOWN (12% called -> ~9% delivered), well
# populated from 5% to 30%; 2+ goals: graded only up to 11.5%
cal = {"g1": [{"band": "0-9%", "n": 400, "predicted": 0.06, "actual": 0.05},
              {"band": "10-19%", "n": 400, "predicted": 0.15, "actual": 0.12},
              {"band": "20-29%", "n": 400, "predicted": 0.25, "actual": 0.22},
              {"band": "30-39%", "n": 400, "predicted": 0.35, "actual": 0.33}],
       "g2": [{"band": "0-9%", "n": 900, "predicted": 0.02, "actual": 0.02},
              {"band": "10-19%", "n": 92, "predicted": 0.115, "actual": 0.065}]}
players = [{"_name": "Depth (X)", "_probs": {"g1": 0.12, "g2": 0.14}, "team": "X", "opp": "Y",
            "_signals": "ice time up"},
           {"_name": "Star (X)", "_probs": {"g1": 0.40, "g2": 0.08}, "team": "X", "opp": "Y"},
           {"_name": "Untested (X)", "_probs": {"a1": 0.10}, "team": "X", "opp": "Y"}]
rows = ls.rows_from_markets(players, markets, cal, "X @ Y", "NHL")
names = {(r["player"], r["key"]) for r in rows}
d = next(r for r in rows if r["player"] == "Depth (X)" and r["key"] == "g1")
want, _b = mv.delivered_over(0.12, "g", 0.5, markets, cal)
check("the chance listed is the DELIVERED one", abs(d["chance"] - want) < 1e-12
      and d["chance"] < d["raw"])
check("worth it at is that chance's fair price", d["worth"] == mm.fair_american(d["chance"]))
check("a star's anytime goal (37% delivered) is not a long shot", ("Star (X)", "g1") not in names)
check("a call past its curve's graded range is not listed", ("Depth (X)", "g2") not in names)
check("a well-graded 2+ goal long shot is listed", ("Star (X)", "g2") in names)
check("an untested market is never listed", not any(r["player"] == "Untested (X)" for r in rows))
check("the reasons ride along", d["signals"] == "ice time up")
check("ranked most likely first", [r["chance"] for r in ls.rank(rows)]
      == sorted((r["chance"] for r in rows), reverse=True))

# --- 3. one chance + its curve (NFL TD) ---------------------------------------
td = [{"band": "10-19%", "n": 300, "predicted": 0.15, "actual": 0.14},
      {"band": "20-29%", "n": 300, "predicted": 0.25, "actual": 0.23}]
x = ls.row_from_chance("RB (X)", "Anytime TD", 0.18, 0.20, td, "X vs Y", "NFL")
check("a graded TD long shot is listed", x and x["support"]["n"] == 300)
check("an ungraded one is not", ls.row_from_chance("RB (X)", "Anytime TD", 0.18, 0.40, td,
                                                   "X vs Y", "NFL") is None)

# --- 4. why it's live -----------------------------------------------------------
sig = ls.nhl_signals({"ice": {"recent": 15.0, "base": 13.0}, "pp": {"unit": "PP1"}},
                     {"goal_ratio": 1.09}, 0.892, 0.905)
check("signals name ice time, PP1, the team's goals and a weak goalie",
      all(s in sig for s in ("ice time up", "PP1", "+9%", "weak goalie (.892)")))
check("no signal is invented when nothing stands out",
      ls.nhl_signals({"ice": {"recent": 13.0, "base": 13.0}, "pp": {}}, {"goal_ratio": 1.0},
                     0.91, 0.905) == "")

# --- 5. the page -----------------------------------------------------------------
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("Long Shots is in the MLB, NHL and NFL navs",
      app.count('("Long Shots", "views/Long_Shots.py")') == 3)
page = (ROOT / "app" / "views" / "Long_Shots.py").read_text(encoding="utf-8")
check("prices are judged by the site's one guard", 'bf.judge(r["chance"]' in page
      and 'r["support"]' in page)
check("BETs go on the same card as the Bet Finder", 'ss["bf_card"]' in page)
home = (ROOT / "app" / "views" / "Home.py").read_text(encoding="utf-8")
check("Home has a route to it", '("Long Shots", "MLB"' in home)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall Long Shots checks passed")
