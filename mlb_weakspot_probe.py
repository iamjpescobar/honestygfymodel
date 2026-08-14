"""ONE-SHOT PROBE — is 0.550 really "hitters do real damage here"?

    python mlb_weakspot_probe.py

THE SYMPTOM. On a real pitcher card, fifteen of nineteen weak-spot
buckets render red. By pitch type, by zone band, by times through the
order, by lineup slot — almost everything says "hitters do real damage
here". A panel whose job is to show WHERE a pitcher gets hurt cannot do
it if three quarters of it is flagged.

THE SUSPECT. `XSLG_HOT = 0.550` and `XSLG_COLD = 0.380` in
engines/pitcher_weakspots.py, both absolute and both chosen by eye.

xSLG measured ON CONTACT excludes strikeouts, so it sits far higher than
the xSLG people quote per plate appearance. If the league's typical
contact xSLG is around .550-.600, then 0.550 flags roughly HALF of
everything as damage and the colour stops discriminating.

This is the fifth scale on this site chosen by eye. The other four —
Clears%, FB95%, HRWindow%, and an EV floor — were all measured and all
wrong, three of them unreachable at one end. Measure before re-setting.

WHAT IT REPORTS
---------------
The distribution of xSLG allowed on contact across every pitcher and
every bucket the panel actually draws, using the engine's own
get_weak_spots so the numbers are the ones on screen and not a parallel
calculation.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd  # noqa: E402

MIN_APPEARANCES = 3


def main() -> int:
    import types, glob
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        st.cache_data = lambda **kw: (lambda f: f)
        sys.modules["streamlit"] = st
    sys.modules.setdefault("pybaseball", types.ModuleType("pybaseball"))

    from engines.pitcher_weakspots import get_weak_spots, XSLG_HOT, XSLG_COLD

    roots = [ROOT / "build_data" / "data" / "statcast" / "pitchers",
             ROOT / "app" / "data" / "statcast" / "pitchers"]
    root = next((r for r in roots if r.exists()), None)
    if root is None:
        print("No pitcher files. Run `python app/fetch_data.py` first.")
        return 1

    ids = [int(Path(f).stem) for f in glob.glob(str(root / "*.parquet"))]
    print(f"Reading {len(ids):,} pitchers from {root.name}/\n")

    rows, failed = [], 0
    for pid in ids:
        try:
            spots = get_weak_spots(pid)
        except Exception:
            failed += 1
            continue
        if not spots:
            continue
        # get_weak_spots returns grouped buckets; walk whatever shape it
        # has rather than assuming one, so this keeps working if the
        # panel gains a section.
        stack = [spots]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                v = node.get("xslg") if "xslg" in node else None
                if isinstance(v, (int, float)):
                    rows.append({"pid": pid, "group": node.get("group"),
                                 "label": node.get("label"), "xslg": float(v)})
                stack.extend(x for x in node.values()
                             if isinstance(x, (dict, list)))
            elif isinstance(node, list):
                stack.extend(x for x in node if isinstance(x, (dict, list)))

    if not rows:
        print("No buckets found. get_weak_spots' return shape may have "
              "changed — inspect it before trusting this probe.")
        return 1

    d = pd.DataFrame(rows)
    print(f"{len(d):,} buckets across {d['pid'].nunique():,} pitchers "
          f"({failed} errored)\n")

    print("=" * 70)
    print("xSLG ALLOWED ON CONTACT — every bucket the panel draws")
    print("=" * 70)
    q = d["xslg"].quantile
    print(f"{'10th':>9}{'25th':>9}{'median':>9}{'75th':>9}{'90th':>9}")
    print(f"{q(.10):>9.3f}{q(.25):>9.3f}{d['xslg'].median():>9.3f}"
          f"{q(.75):>9.3f}{q(.90):>9.3f}")

    hot = (d["xslg"] >= XSLG_HOT).mean() * 100
    cold = (d["xslg"] <= XSLG_COLD).mean() * 100
    print(f"\nWITH TODAY'S THRESHOLDS ({XSLG_COLD} / {XSLG_HOT}):")
    print(f"  {hot:5.1f}% of buckets flagged 'real damage'")
    print(f"  {cold:5.1f}% flagged 'he wins here'")
    print(f"  {100 - hot - cold:5.1f}% middling")

    print(f"""
HOW TO READ IT
==============
A threshold meant to mark the DANGEROUS buckets should flag roughly the
top quarter — call it the 75th percentile. If the 'real damage' share
above is far past 25%, 0.550 is sitting near the middle of the
distribution and the colour has stopped discriminating: a panel where
three quarters of the bars are red says nothing about WHERE he gets hurt.

Suggested, straight off this run:
  XSLG_HOT  = {q(.75):.3f}   (75th — the genuinely dangerous quarter)
  XSLG_COLD = {q(.25):.3f}   (25th — where he genuinely wins)

Check the same thing per GROUP before settling. Zone bands and pitch
types may sit at different levels, and one shared pair of thresholds
across groups that differ would flatten one and saturate the other —
the same mistake the WNBA form band made across five inputs.
""")
    for g, sub in d.groupby("group", dropna=True):
        if len(sub) < 30:
            continue
        print(f"  {str(g):<22} n={len(sub):>5}  median {sub['xslg'].median():.3f}"
              f"  75th {sub['xslg'].quantile(.75):.3f}"
              f"  flagged hot {(sub['xslg'] >= XSLG_HOT).mean()*100:.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
