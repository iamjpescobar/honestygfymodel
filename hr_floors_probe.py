"""ONE-SHOT PROBE — what do the proposed HR floors actually exclude?

Not a repo file in the sense of shipping behaviour: nothing imports it,
nothing runs it on a schedule. It answers one question and then you
decide.

    python hr_floors_probe.py

THE QUESTION
------------
Nine floors were proposed as an AND gate on the HR board:

    Brl% >= 11 · Brl/PA >= 8 · HH% >= 40 · FB% >= 26 · EV90 >= 91
    Blast% >= 18 · PullAir% >= 10 · ISO >= .200 · ClearsAnywhere > 0

Nobody knows what that leaves. If it leaves sixty hitters it is a gate;
if it leaves four, a top-15 board cannot be built from it and the answer
is tiers, not a filter. Guessing costs nothing to be wrong about right
up until the board is empty on a Tuesday.

WHAT IT PRINTS
--------------
  1. THE DISTRIBUTION of each metric across the league — median, 75th,
     90th. This is the part that matters most. A floor set at the league
     median excludes nobody while looking strict, and two of the nine
     look like they may be there.
  2. How many hitters clear each floor ALONE.
  3. The AND cascade, in order, so you can see which floor is actually
     doing the cutting. Highly correlated floors will each look
     powerful alone and add nothing on top of the one before.
  4. How many clear all nine, and how many miss by exactly one — the
     near-miss count decides whether a hard gate or a "floors met: 8/9"
     tier is the right shape.

It reads app/data/statcast/batters/*.parquet, the files the nightly
already writes, and computes every metric by calling the ENGINE'S OWN
_compute_batted_ball_metrics. It does not reimplement a single rate —
a probe that computes its own Brl% would be measuring a stat the site
does not have.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd  # noqa: E402

BATTER_DIR = ROOT / "app" / "data" / "statcast" / "batters"

# Minimum PA to count as a hitter for this exercise. Not a proposal —
# just "is this a regular", so the distributions below describe the
# players who actually appear in lineups rather than 400 September
# call-ups sitting on twelve plate appearances.
MIN_PA = 150

# (label, profile key, floor, direction). Direction is always ">=" here;
# it is spelled out so a future one-sided floor cannot be misread.
FLOORS = [
    ("Brl %",            "Brl %",            11.0),
    ("Brl/PA",           "Brl/PA",            8.0),
    ("HH %",             "HH %",             40.0),
    ("FB %",             "FB %",             26.0),
    ("EV90",             "EV90",             91.0),
    ("Blast %",          "Blast %",          18.0),
    ("PullAir %",        "PullAir %",        10.0),
    ("ISO",              "ISO",               0.200),
    ("ClearsAnywhere %", "ClearsAnywhere %",  0.001),
]


def main() -> int:
    if not BATTER_DIR.exists():
        print(f"No batter files at {BATTER_DIR}.")
        print("Run the nightly (or fetch_data.py) first — this probe reads "
              "what the nightly writes and computes nothing from the network.")
        return 1

    from engines.statcast_engine import _compute_batted_ball_metrics

    files = sorted(BATTER_DIR.glob("*.parquet"))
    print(f"Reading {len(files):,} batter files from {BATTER_DIR}...\n")

    profiles = []
    skipped = 0
    for path in files:
        try:
            df = pd.read_parquet(path)
        except Exception:
            skipped += 1
            continue
        try:
            prof = _compute_batted_ball_metrics(df)
        except Exception as exc:
            # Report rather than swallow. A metric that throws on real
            # data is a finding, not a file to skip quietly.
            print(f"  {path.stem}: {type(exc).__name__}: {exc}")
            skipped += 1
            continue
        if not prof or (prof.get("PA") or 0) < MIN_PA:
            continue
        prof["id"] = int(path.stem)
        profiles.append(prof)

    if not profiles:
        print(f"No batter cleared {MIN_PA} PA. Either the pull is early in "
              f"the season or the files are partial.")
        return 1

    p = pd.DataFrame(profiles)
    print(f"{len(p):,} hitters at {MIN_PA}+ PA "
          f"({skipped} file(s) unreadable or errored)\n")

    # ---- 1. THE DISTRIBUTION -----------------------------------------
    print("=" * 74)
    print("DISTRIBUTION — where each proposed floor sits in the real league")
    print("=" * 74)
    print(f"{'metric':<20}{'floor':>8}{'median':>10}{'75th':>10}"
          f"{'90th':>10}{'floor is':>16}")
    for label, key, floor in FLOORS:
        s = pd.to_numeric(p.get(key), errors="coerce").dropna()
        if s.empty:
            print(f"{label:<20}{floor:>8}{'—':>10}{'—':>10}{'—':>10}"
                  f"{'NOT MEASURED':>16}")
            continue
        med, q75, q90 = s.median(), s.quantile(0.75), s.quantile(0.90)
        # Where the floor sits as a percentile of the league. THIS is the
        # number that says whether a floor is strict or decorative.
        pct = (s < floor).mean() * 100
        verdict = ("BELOW MEDIAN" if pct < 50 else
                   "top half" if pct < 75 else
                   "top quarter" if pct < 90 else "top decile")
        print(f"{label:<20}{floor:>8.3f}{med:>10.2f}{q75:>10.2f}{q90:>10.2f}"
              f"{verdict:>16}")
    print("\nA floor BELOW MEDIAN excludes fewer than half the league. That "
          "is not a filter,\nit is a label — and it will not change what the "
          "board shows.\n")

    # ---- 2. EACH FLOOR ALONE -----------------------------------------
    print("=" * 74)
    print("EACH FLOOR ALONE")
    print("=" * 74)
    masks = {}
    for label, key, floor in FLOORS:
        s = pd.to_numeric(p.get(key), errors="coerce")
        if s is None or s.dropna().empty:
            continue
        # NaN fails the floor. An unmeasured bat is not a qualifying bat,
        # and it is not a disqualified one either — it is counted here
        # so the gap is visible rather than assumed away.
        m = s >= floor
        masks[label] = m.fillna(False)
        n_missing = int(s.isna().sum())
        print(f"  {label:<20} {int(m.sum()):>4} of {len(p)} clear "
              f"({m.mean() * 100:>5.1f}%)"
              + (f"   [{n_missing} unmeasured]" if n_missing else ""))

    # ---- 3. THE AND CASCADE ------------------------------------------
    print("\n" + "=" * 74)
    print("THE AND CASCADE — which floor is actually doing the cutting")
    print("=" * 74)
    running = pd.Series(True, index=p.index)
    prev = len(p)
    for label in masks:
        running = running & masks[label]
        n = int(running.sum())
        print(f"  + {label:<20} {n:>4} remain   ({n - prev:+d})")
        prev = n

    # ---- 4. ALL NINE, AND THE NEAR MISSES ----------------------------
    if masks:
        met = sum(m.astype(int) for m in masks.values())
        total = len(masks)
        print("\n" + "=" * 74)
        print(f"HOW MANY OF THE {total} FLOORS EACH HITTER CLEARS")
        print("=" * 74)
        for k in range(total, max(total - 4, -1), -1):
            n = int((met == k).sum())
            tag = "  <- the gate" if k == total else ""
            print(f"  {k}/{total} floors: {n:>4} hitter(s){tag}")
        qualified = int((met == total).sum())
        near = int((met == total - 1).sum())
        print(f"\n  {qualified} hitters clear all {total}.")
        print(f"  {near} more miss by exactly one.")
        if qualified:
            names = p.loc[met == total].head(25)
            print("\n  Qualifying (first 25 by Brl/PA):")
            for _i, row in names.sort_values("Brl/PA", ascending=False).iterrows():
                print(f"    {int(row['id']):>7}  Brl/PA {row.get('Brl/PA')}  "
                      f"ISO {row.get('ISO')}  Blast% {row.get('Blast %')}")
        print("\nREAD IT LIKE THIS. Roughly a third of qualifying hitters are "
              "in any given\nnight's confirmed lineups. If the number above "
              "is under ~45, a hard gate\ncannot fill a top-15 board and the "
              "answer is a 'floors met: N/9' tier instead.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
