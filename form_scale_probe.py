"""ONE-SHOT PROBE — what do the Form deltas actually look like, in units?

Not a repo file in the sense of shipping behaviour: nothing imports it,
nothing runs it on a schedule. It answers one question and then you
decide.

    python form_scale_probe.py

THE QUESTION
------------
`styles/stat_scales.py` colours the two Form columns from cut points
that are **DERIVED, NOT MEASURED**, and the file says so:

    ΔEV     (-3.0, -0.5,  1.9,  3.9)   mph
    ΔHH%   (-10.4, -1.8,  5.6, 14.4)   points

They come from hr_floors_probe's percent-of-own-baseline table (25th
-3.4, median -0.6, 75th +2.1, 90th +4.4 for AvgEV; -26.1, -4.4, +14.0,
+35.9 for HH%) converted to units at the LEAGUE-AVERAGE baseline — about
89 mph and about 40%. That makes them roughly right for a typical hitter
and progressively wrong for the tails: a 3% swing is 2.7 mph for an
86 mph contact hitter and 3.2 mph for a 106 mph one, and the scale
grades both the same.

This measures the deltas directly, in mph and in points, so the numbers
can stop being a conversion of somebody else's numbers.

WHY IT MATTERS RATHER THAN BEING TIDY
-------------------------------------
A cut point that nobody reaches paints the whole column one colour and
the board silently stops saying anything — that has happened twice here
already (Clears% at (10,20,30,40) when the league median is 0.00, and
Brl% at (15,25,35,45) when the 90th percentile is 18.66). A signed
column has the same failure at BOTH ends and a third in the middle: set
the inner cuts too wide and every hitter reads neutral, too narrow and
everyone reads extreme.

WHAT IT PRINTS
--------------
  1. The distribution of each delta in its own units — 10th, 25th,
     median, 75th, 90th — which is what the scale should be cut from.
  2. THE MEDIAN SANITY CHECK. A form measurement on comparable footing
     has a median near zero, because half a league is above its own
     baseline and half below. A median far off zero means the window is
     measuring something other than form (the whole league's contact
     drifting with the weather, say) and the column needs a caveat, not
     a scale.
  3. What share of hitters each proposed tier would hold, against the
     20/25/25/20/10-ish spread a five-tier scale wants. A tier holding
     two thirds of the league is not a tier.
  4. How many hitters have no measurable recent window at all — the
     em-dash rate the column will actually show.

It reads app/data/statcast/batters/*.parquet, the files the nightly
already writes, and computes both profiles by calling the ENGINE'S OWN
_compute_batted_ball_metrics through the ENGINE'S OWN apply_window. It
reimplements nothing: a probe that computed its own AvgEV would be
measuring a stat the site does not have, and the deltas it reported
would not be the deltas on the board.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd  # noqa: E402

BATTER_DIR = ROOT / "app" / "data" / "statcast" / "batters"

# Same 150 PA as hr_floors_probe, and for the same reason: "is this a
# regular", so the distribution describes players who appear in lineups
# rather than 400 call-ups on twelve plate appearances.
MIN_PA = 150


def _pct(series, q):
    return series.quantile(q) if len(series) else float("nan")


def main() -> int:
    if not BATTER_DIR.exists():
        print(f"No batter files at {BATTER_DIR}.")
        print("Run the nightly (or fetch_data.py) first — this probe reads "
              "what the nightly writes and computes nothing from the network.")
        return 1

    # INPUTS AND WINDOW COME FROM THE COMPONENT, never from a list typed
    # here. hr_floors_probe carried its own copy of the thresholds once
    # and spent a run reporting on a set the board did not use — the
    # exact failure a probe exists to catch, committed by the probe.
    from engines.form import FORM_INPUTS, FORM_WINDOW, FORM_UNIT, form_deltas
    from engines.statcast_engine import _compute_batted_ball_metrics
    from engines.recency_windows import apply_window

    files = sorted(BATTER_DIR.glob("*.parquet"))
    print(f"Reading {len(files):,} batter files from {BATTER_DIR}...")
    print(f"Window: {FORM_WINDOW} by {FORM_UNIT}, against season.\n")

    rows, skipped, no_recent = [], 0, 0
    for path in files:
        try:
            df = pd.read_parquet(path)
            season = _compute_batted_ball_metrics(df)
        except Exception as exc:
            # Report rather than swallow. A metric that throws on real
            # data is a finding, not a file to skip quietly.
            print(f"  {path.stem}: {type(exc).__name__}: {exc}")
            skipped += 1
            continue
        if not season or (season.get("PA") or 0) < MIN_PA:
            continue
        try:
            recent = _compute_batted_ball_metrics(
                apply_window(df, FORM_WINDOW, FORM_UNIT))
        except Exception:
            recent = None
        d = form_deltas(season, recent)
        if not d:
            no_recent += 1
            continue
        rows.append(d)

    if not rows:
        print(f"No batter cleared {MIN_PA} PA with a measurable "
              f"{FORM_WINDOW} window.")
        return 1

    p = pd.DataFrame(rows)
    n = len(p)
    print(f"{n:,} hitters at {MIN_PA}+ PA with a measurable window "
          f"({no_recent} had none, {skipped} file(s) unreadable)\n")

    # ---- 1. THE DISTRIBUTION, IN UNITS -------------------------------
    print("=" * 74)
    print("DISTRIBUTION — cut the scale from THESE, not from a conversion")
    print("=" * 74)
    print(f"{'column':<10}{'unit':>6}{'10th':>9}{'25th':>9}{'median':>9}"
          f"{'75th':>9}{'90th':>9}{'n':>7}")
    for _key, col, unit, _dp in FORM_INPUTS:
        if col not in p:
            continue
        s = p[col].dropna()
        print(f"{col:<10}{unit:>6}{_pct(s, .10):>9.2f}{_pct(s, .25):>9.2f}"
              f"{_pct(s, .50):>9.2f}{_pct(s, .75):>9.2f}{_pct(s, .90):>9.2f}"
              f"{len(s):>7}")
    print()
    print("Suggested cut points are the 25th, median, 75th and 90th above.")

    # ---- 2. THE MEDIAN SANITY CHECK ----------------------------------
    print()
    print("=" * 74)
    print("MEDIAN AT ZERO? — the check that catches a broken measurement")
    print("=" * 74)
    print("Half a league is above its own baseline and half below, so a")
    print("median far from zero means this window is measuring something")
    print("other than form. That is a finding, not a scale to draw.")
    for _key, col, unit, _dp in FORM_INPUTS:
        if col not in p:
            continue
        s = p[col].dropna()
        med, share = _pct(s, .50), (s > 0).mean() * 100
        flag = "  <-- LOOK" if abs(share - 50) > 12 else ""
        print(f"  {col:<8} median {med:+7.2f} {unit:<4} "
              f"· {share:5.1f}% of hitters above their own baseline{flag}")

    # ---- 3. WOULD THE SHIPPED SCALE HOLD ANYONE? ---------------------
    print()
    print("=" * 74)
    print("TIER OCCUPANCY under the cut points currently shipped")
    print("=" * 74)
    print("A tier holding two thirds of the league is not a tier, and one")
    print("holding nobody paints the column a single colour. Compare to a")
    print("roughly 20/25/25/20/10 spread.")
    from styles.stat_scales import SCALES
    for _key, col, unit, _dp in FORM_INPUTS:
        if col not in p or col not in SCALES:
            print(f"  {col:<8} NO SCALE DEFINED — colour falls back to "
                  f"column-relative, which changes tier when a filter moves")
            continue
        cuts = SCALES[col]
        s = p[col].dropna()
        edges = [float("-inf"), *cuts, float("inf")]
        print(f"  {col} ({unit})  cuts {tuple(cuts)}")
        for lo, hi in zip(edges, edges[1:]):
            held = ((s > lo) & (s <= hi)).mean() * 100
            bar = "#" * int(round(held / 2))
            lo_s = "  -inf" if lo == float("-inf") else f"{lo:+6.1f}"
            hi_s = "  +inf" if hi == float("inf") else f"{hi:+6.1f}"
            print(f"    {lo_s} .. {hi_s}  {held:5.1f}%  {bar}")

    print()
    print("Replace the cut points in styles/stat_scales.py with the")
    print("measured figures above, and change the DERIVED note to say what")
    print("they were measured against and when. Do not tune them by eye —")
    print("the two scales this repo has already had to fix were both wrong")
    print("because somebody assumed a range instead of looking at one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
