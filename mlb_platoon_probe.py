"""ONE-SHOT PROBE — how big is the platoon split, really?

    python mlb_platoon_probe.py

WHY THIS EXISTS BEFORE A PLATOON TERM DOES
------------------------------------------
HR Score is hand-neutral. `get_batter_iso_vs_hand` exists and is already
used to price the BULLPEN's hand mix in pen_context — but the STARTING
pitcher, whom a hitter faces two or three times, gets no platoon term at
all. So a hitter with a .300 ISO against right-handers is scored on his
blended .205 when he faces a righty.

That is a real hole. What is NOT yet known is how much it is worth, and
that decides whether it belongs in the score at all:

  * If the median hitter's L/R ISO gap is small, a platoon term is a
    rounding error dressed up as insight, and adding it makes the score
    look smarter without predicting better.

  * If the gap is large and the TAIL is large, it matters enormously for
    the hitters at the extremes — which is exactly who ends up on a
    home-run board.

Four things chosen by eye this week were wrong: three colour scales, an
EV floor, and a form band. So the number gets measured before the term
gets built, and the CAP gets set from the distribution rather than from
whatever looks tidy.

WHAT IT REPORTS
---------------
Per batter, ISO vs LHP and vs RHP from his own Statcast rows, using the
engine's own function (40-AB floor per side, so both sides are real).
Then the distribution of the gap, and how much of the league is at the
extremes where a platoon term would actually change a ranking.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd  # noqa: E402


def main() -> int:
    import types, glob
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        st.cache_data = lambda **kw: (lambda f: f)
        sys.modules["streamlit"] = st
    sys.modules.setdefault("pybaseball", types.ModuleType("pybaseball"))

    from engines.statcast_engine import (get_batter_iso_vs_hand,
                                         get_batter_profile_windowed)

    roots = [ROOT / "build_data" / "data" / "statcast" / "batters",
             ROOT / "app" / "data" / "statcast" / "batters"]
    root = next((r for r in roots if r.exists()), None)
    if root is None:
        print("No batter files. Run `python app/fetch_data.py` first.")
        return 1

    ids = [int(Path(f).stem) for f in glob.glob(str(root / "*.parquet"))]
    print(f"Reading {len(ids):,} batters from {root.name}/\n")

    rows, one_sided = [], 0
    for pid in ids:
        # BOTH sides must clear the 40-AB floor. A hitter measured
        # against righties and not lefties has no split, he has one
        # number — and pretending otherwise is how a thin sample becomes
        # a confident adjustment.
        iso_l = get_batter_iso_vs_hand(pid, "L")
        iso_r = get_batter_iso_vs_hand(pid, "R")
        if iso_l is None or iso_r is None:
            one_sided += 1
            continue
        prof = get_batter_profile_windowed(pid, window="season", unit="bbe") or {}
        rows.append({"id": pid, "iso_l": iso_l, "iso_r": iso_r,
                     "iso": prof.get("ISO"), "pa": prof.get("PA") or 0,
                     "gap": iso_r - iso_l})

    if not rows:
        print("No batter cleared 40 AB against BOTH hands.")
        return 1

    d = pd.DataFrame(rows)
    d["abs_gap"] = d["gap"].abs()
    print(f"{len(d):,} batters with a real split on both sides "
          f"({one_sided} had only one)\n")

    print("=" * 72)
    print("ISO vs RHP minus ISO vs LHP")
    print("=" * 72)
    q = d["gap"].quantile
    print(f"{'10th':>9}{'25th':>9}{'median':>9}{'75th':>9}{'90th':>9}")
    print(f"{q(.10):>9.3f}{q(.25):>9.3f}{d['gap'].median():>9.3f}"
          f"{q(.75):>9.3f}{q(.90):>9.3f}")
    print(f"\nABSOLUTE gap — median {d['abs_gap'].median():.3f} · "
          f"75th {d['abs_gap'].quantile(.75):.3f} · "
          f"90th {d['abs_gap'].quantile(.90):.3f} · "
          f"max {d['abs_gap'].max():.3f}")

    # How much of the league would a platoon term actually move? A gap
    # smaller than the spacing between adjacent board ranks changes
    # nothing, however real it is.
    for thr in (0.050, 0.100, 0.150, 0.200):
        n = int((d["abs_gap"] >= thr).sum())
        print(f"  {n:>4} of {len(d)} ({n/len(d)*100:>4.1f}%) have a gap of "
              f"{thr:.3f} or more")

    print("\n" + "=" * 72)
    print("THE BIGGEST SPLITS — who a platoon term would actually move")
    print("=" * 72)
    top = d.reindex(d["abs_gap"].sort_values(ascending=False).index).head(20)
    print(f"{'id':>8}{'PA':>6}{'ISO':>8}{'vs L':>8}{'vs R':>8}{'gap':>8}")
    for _i, r in top.iterrows():
        _iso = f"{r['iso']:.3f}" if pd.notna(r["iso"]) else "  —  "
        print(f"{int(r['id']):>8}{int(r['pa']):>6}{_iso:>8}"
              f"{r['iso_l']:>8.3f}{r['iso_r']:>8.3f}{r['gap']:>+8.3f}")

    print("""
HOW TO READ IT
==============
The MEDIAN gap is the case against a platoon term: if half the league
sits inside a few ISO points, the term does nothing for most of the
board and adds a component that has to be explained, maintained and
eventually validated.

The 90th percentile and the table above are the case FOR it. A board
that surfaces fifteen bats out of 270 is selecting from the tail, and
the tail is where splits live. If the top twenty here are routinely on
the board, the score is pricing them wrong against a hand it never
looks at.

FOR THE CAP: pen_context maps a +/-40% ISO swing to its full cap. If
that number does not match the distribution above, it was chosen by eye
too — and it is already live in the bullpen term today.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
