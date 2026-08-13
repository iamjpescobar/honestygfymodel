"""ONE-SHOT PROBE — what does a real MLB form deviation look like?

    python mlb_form_probe.py

WHY THIS EXISTS BEFORE THE FORM COLUMN DOES
-------------------------------------------
Form means "how far is he from his own baseline right now", and turning
that deviation into a 0-100 score needs a BAND: how big a deviation
counts as maximum hot. Pick that band by eye and you get what the WNBA
props board has — a fixed +/-25% band applied to a stat whose typical
value is 1.0, which measured out at a 75th percentile of 94.9 and a 90th
of exactly 100. A quarter of the league pinned at the ceiling, and a
component that had stopped separating anyone.

Three colour scales, an EV floor and that form band were all chosen by
eye this week and all four were wrong. So: measure first, then set the
band from the distribution.

WHAT IT MEASURES
----------------
For every batter with enough recent contact, the L15-vs-season deviation
in the batted-ball inputs that actually drive home runs — not in home
runs themselves. A hitter gets 0-2 homers in fifteen games; that number
is far too noisy to call form. Barrel rate and pull-air rate over the
same window rest on 40-60 batted balls and move for real reasons.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd  # noqa: E402

# The inputs HR Score already weights, so form measures deviation in the
# same things the score is built from rather than in a parallel universe.
FORM_KEYS = ("Brl/PA", "PullAir %", "HH %", "AvgEV", "Blast %")
MIN_PA = 150


def main() -> int:
    import types, glob
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        st.cache_data = lambda **kw: (lambda f: f)
        sys.modules["streamlit"] = st
    sys.modules.setdefault("pybaseball", types.ModuleType("pybaseball"))

    from engines.statcast_engine import get_batter_profile_windowed

    roots = [ROOT / "build_data" / "data" / "statcast" / "batters",
             ROOT / "app" / "data" / "statcast" / "batters"]
    root = next((r for r in roots if r.exists()), None)
    if root is None:
        print("No batter files. Run `python app/fetch_data.py` first.")
        return 1

    ids = [int(Path(f).stem) for f in glob.glob(str(root / "*.parquet"))]
    print(f"Reading {len(ids):,} batters from {root.name}/\n")

    rows, thin = [], 0
    for pid in ids:
        season = get_batter_profile_windowed(pid, window="season", unit="bbe")
        if not season or (season.get("PA") or 0) < MIN_PA:
            thin += 1
            continue
        recent = get_batter_profile_windowed(pid, window="l15", unit="bbe")
        if not recent:
            thin += 1
            continue
        rec = {"id": pid}
        for k in FORM_KEYS:
            s, r = season.get(k), recent.get(k)
            # Deviation as a PERCENT of his own baseline, which is what
            # makes it comparable across a rate and a velocity.
            rec[k] = ((r - s) / s * 100.0) if (s and r is not None) else None
        rows.append(rec)

    if not rows:
        print(f"No batter cleared {MIN_PA} PA with a readable L15 window.")
        return 1

    d = pd.DataFrame(rows)
    print(f"{len(d):,} batters at {MIN_PA}+ PA ({thin} skipped)\n")
    print("=" * 74)
    print("L15 vs SEASON, as a percent of the player's own baseline")
    print("=" * 74)
    print(f"{'input':<14}{'10th':>9}{'25th':>9}{'median':>9}"
          f"{'75th':>9}{'90th':>9}{'|dev| 90th':>12}")
    for k in FORM_KEYS:
        s = pd.to_numeric(d[k], errors="coerce").dropna()
        if s.empty:
            print(f"{k:<14}{'— not measured':>50}")
            continue
        print(f"{k:<14}{s.quantile(.10):>9.1f}{s.quantile(.25):>9.1f}"
              f"{s.median():>9.1f}{s.quantile(.75):>9.1f}"
              f"{s.quantile(.90):>9.1f}{s.abs().quantile(.90):>12.1f}")

    print("""
HOW TO READ IT
==============
The last column is the band. Set form's +/- limit to roughly the 90th
percentile of the ABSOLUTE deviation: at that width, about one batter in
ten reaches an extreme, which is what an extreme should mean. Anything
much narrower saturates — that is exactly how the WNBA 3PM form column
ended up with a quarter of the league pinned at 100.

Expect the bands to DIFFER per input. Exit velocity is a stable quantity
and will move a few percent; barrel rate over fifteen games will swing
far more. One shared band across all five would flatten the stable ones
and saturate the volatile ones, which is the same mistake in a new place.

The MEDIAN should sit near zero. If it does not, L15 and season are not
being computed on comparable footing and the deviation is measuring
something other than form.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
