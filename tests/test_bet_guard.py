"""
The guard on every bet call (10-11) — model_view.guarded_tier.

Plain script — exits non-zero on failure. Calls carry value.assess's
shape; curves carry calibration_map's — rule 5.

THE CASE IT EXISTS FOR: Brissett passing yards, 10-11. The model
projected ~200 yards, the book 266.5 (Detroit's pass defense, a big
underdog throwing), and the Bet Finder would have called UNDER 266.5 at
-113 STRONG. It must be CHECK.

Negative controls, confirmed red by exit code when written (rule 4):
  - guarded_tier without the book-disagrees rule
    -> "a 10+ point gap with one price is CHECK" fails
  - market_chance ignoring the other side's price
    -> "with both prices the book's chance is de-vigged" fails
  - guarded_tier ignoring the tested range
    -> "STRONG past the graded range is capped at VALUE" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import model_math as mm  # noqa: E402
from engines import model_view as mv  # noqa: E402
from engines import value as vl  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


GOOD = {"measured": True, "in_range": True, "n": 500, "untested": False}

# --- 1. the measured threshold -------------------------------------------
check("the gap threshold is the measured 10 points", abs(mv.GAP_CHECK - 0.10) < 1e-12)
check("STRONG needs the site's 30-call floor", mv.STRONG_MIN_N == 30)

# --- 2. book disagrees -> CHECK -------------------------------------------
a = vl.assess(0.45, 200)                         # break-even 33.3%: edge 11.7
t, why = mv.guarded_tier(a, 200, None, GOOD)
check("a 10+ point gap with one price is CHECK", t == "check" and "Book disagrees" in why)
a = vl.assess(0.42, 200)                         # edge 8.7
check("an 8.7-point edge, measured, stays STRONG", mv.guarded_tier(a, 200, None, GOOD)[0]
      == "strong")
a = vl.assess(0.61, -113)                        # vs break-even 53.1%: edge 7.9
t, _ = mv.guarded_tier(a, -113, -113, GOOD)      # vs the book's de-vigged 50%: gap 11
check("with both prices the book's chance is de-vigged", t == "check")
check("...and the market chance reads 50% at -113 / -113",
      abs(mv.market_chance(-113, -113)[0] - 0.5) < 1e-12 and mv.market_chance(-113, -113)[1])
check("one price: the book's chance is its break-even",
      abs(mv.market_chance(-113)[0] - 113 / 213) < 1e-12 and not mv.market_chance(-113)[1])

# --- 3. untested / unmeasured / out of range ------------------------------
a = vl.assess(0.42, 200)
check("an untested chance is at most THIN",
      mv.guarded_tier(a, 200, None, {"measured": False, "in_range": False, "n": 0,
                                     "untested": True})[0] == "thin")
check("STRONG past the graded range is capped at VALUE",
      mv.guarded_tier(a, 200, None, dict(GOOD, in_range=False))[0] == "value")
check("STRONG in a thin band (under 30 calls) is capped at VALUE",
      mv.guarded_tier(a, 200, None, dict(GOOD, n=12))[0] == "value")
check("no curve attached: STRONG is capped at VALUE", mv.guarded_tier(a, 200)[0] == "value")
check("VALUE is not touched by the range rule",
      mv.guarded_tier(vl.assess(0.37, 200), 200, None, dict(GOOD, in_range=False))[0]
      == "value")
check("no edge is no edge", mv.guarded_tier(vl.assess(0.30, 200), 200, None, GOOD)[0] == "none")

# --- 4. the support reader -------------------------------------------------
bins = [{"band": "30-39%", "n": 14, "predicted": 0.359, "actual": 0.5},
        {"band": "40-49%", "n": 56, "predicted": 0.448, "actual": 0.482},
        {"band": "50-59%", "n": 12, "predicted": 0.517, "actual": 0.75}]
s = mv.curve_support(0.165, bins)
check("a call below the lowest graded call is out of range", s["measured"] and not s["in_range"])
s = mv.curve_support(0.45, bins)
check("a call inside the curve reads its nearest band's count", s["in_range"] and s["n"] == 56)
check("no curve is untested", mv.curve_support(0.4, None)["untested"])
m = (("g1", "Goal O0.5", "g", 1),)
cal = {"g1": bins}
check("support_for reads the same curve delivered_over reads",
      mv.curve_for("g", 0.5, m, cal) == (bins, "exact")
      and mv.support_for(0.45, "g", 0.5, m, cal)["n"] == 56)
check("delivered_over is unchanged by the refactor",
      mv.delivered_over(0.45, "g", 0.5, m, cal)[1] == "exact"
      and mv.delivered_over(0.45, "x", 0.5, m, cal) == (0.45, "raw"))

# --- 5. the Brissett under, end to end ------------------------------------
pmf = [0.0] * 600
for y in range(600):
    pmf[y] = mm.normal_cdf(y + 0.5, 200.0, 60.0) - mm.normal_cdf(y - 0.5, 200.0, 60.0)
over = mm.over_prob_pmf(pmf, 266.5)
under = 1 - over
a = vl.assess(under, -113)
t, why = mv.guarded_tier(a, -113, -113, mv.curve_support(over, bins))
check("Brissett UNDER 266.5 at -113 / -113 is CHECK, never STRONG", t == "check" and why)

# --- 6. every prop checker on the site uses it ----------------------------
for path in ("app/engines/model_view.py", "app/engines/bet_finder.py", "app/views/Top_Plays.py",
             "app/views/NHL_Player_Of_The_Day.py", "app/views/NHL_Goal_Edge.py",
             "app/views/NFL_TD_Edge.py", "app/views/NFL_Projections.py"):
    src = (ROOT / path).read_text(encoding="utf-8")
    check(f"{path.split('/')[-1]} decides prop calls through the guard", "guarded_tier(" in src)
for path in ("app/views/Top_Plays.py", "app/views/NHL_Player_Of_The_Day.py",
             "app/views/NHL_Goal_Edge.py", "app/views/NFL_TD_Edge.py",
             "app/views/NFL_Projections.py"):
    src = (ROOT / path).read_text(encoding="utf-8")
    check(f"{path.split('/')[-1]} no longer tiers a prop with the bare edge",
          "edge_tier(" not in src)
check("CHECK has its own colour and label", mv.TIER_STYLE["check"][0] == "CHECK")

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall guard checks passed")
