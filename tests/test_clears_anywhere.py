"""The launch floor that clears all 30 fences, and the composite on top.

WHY THIS IS MEASURED AND NOT MODELLED

There is no single launch angle that leaves every park: the angle needed
falls as exit velocity rises (~28 degrees at 95 mph, ~18 at 110). The
honest options were a hand-built table of fence distances and wall
heights driven through a drag-and-lift trajectory model — which produces
an ESTIMATE — or reading the contour off the league's own outcomes,
which produces a measurement. This site does not ship estimates on its
boards, so it is the second.

The subtle failure this guards against: a bucket can record one home run
in each of 30 parks while most of its contact stays in the yard. Park
coverage ALONE would call that "clears anywhere" and be badly wrong.
Both conditions are required — most of the bucket leaves, AND every park
that saw it also saw it go out.
"""
import sys, types
import numpy as np
import pandas as pd

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter", "statcast_pitcher", "playerid_lookup", "statcast"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, ".")

_orig_to_parquet = pd.DataFrame.to_parquet
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))

import precompute
from pathlib import Path
import tempfile
tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp

PARKS = [f"P{i:02d}" for i in range(30)]
rng = np.random.default_rng(7)
failures = []


def _rows(n, ev, la, hr_mask, parks):
    return pd.DataFrame({
        "launch_speed": ev, "launch_angle": la, "type": "X",
        "events": np.where(hr_mask, "home_run", "field_out"),
        "home_team": parks,
    })


# --- the league ------------------------------------------------------
# A: 108 mph / 29 deg — leaves everywhere, seen in all 30 parks.
n = 900
a = _rows(n, 108.0, 29.0, np.ones(n, bool), [PARKS[i % 30] for i in range(n)])

# B: THE TRAP. 101 mph / 25 deg. Exactly one homer in each of the 30
# parks, and 20 outs in each. Full park coverage, 4.8% HR rate. If the
# metric trusted coverage alone this would qualify, and the column would
# be a lie.
b_parks, b_hr = [], []
for pk in PARKS:
    b_parks += [pk] * 21
    b_hr += [True] + [False] * 20
b = _rows(len(b_parks), 101.0, 25.0, np.array(b_hr), b_parks)

# C: 104 mph / 27 deg, leaves 95% of the time but only ever hit in 6
# parks. High probability, thin coverage — must not qualify either.
n = 300
c = _rows(n, 104.0, 27.0, rng.random(n) < 0.95, [PARKS[i % 6] for i in range(n)])

# D: grounders.
n = 400
d = _rows(n, 92.0, 4.0, np.zeros(n, bool), [PARKS[i % 30] for i in range(n)])

league = pd.concat([a, b, c, d], ignore_index=True)
assert precompute.build_xhr_table(league)

sys.path.insert(0, "app")
import engines.statcast_engine as se
se._DATA_DIR = tmp
from engines.statcast_engine import clears_anywhere_pct, _clears_anywhere_buckets

buckets = _clears_anywhere_buckets()
if buckets is None:
    failures.append("no clears_anywhere column was written at all")
else:
    if (108.0, 28.0) not in buckets:
        failures.append(f"the all-parks trajectory did not qualify: {buckets}")
    else:
        print("PASS: a trajectory that left all 30 parks qualifies")

    if (100.0, 24.0) in buckets:
        failures.append(
            "THE TRAP FIRED: a bucket with one homer in each of 30 parks "
            "and a 4.8% HR rate was called 'clears anywhere'. Park coverage "
            "alone is not the test")
    else:
        print("PASS: full park coverage at a low HR rate does NOT qualify")

    if (104.0, 26.0) in buckets:
        failures.append("a 95% bucket seen in only 6 parks qualified — the "
                        "all-parks claim is not supported by 6 parks")
    else:
        print("PASS: a high-probability bucket with thin park coverage does "
              "not qualify")

# --- the rate on a hitter --------------------------------------------
# Six no-doubters and fourteen grounders -> 30%.
hitter = pd.concat([
    _rows(6, 108.0, 29.0, np.zeros(6, bool), PARKS[:6]),
    _rows(14, 92.0, 4.0, np.zeros(14, bool), PARKS[:14]),
], ignore_index=True)
pct = clears_anywhere_pct(hitter)
if pct is None or abs(pct - 30.0) > 0.01:
    failures.append(f"expected 30.0% clears-anywhere, got {pct}")
else:
    print(f"PASS: hitter rate computes to {pct}% of batted balls")

# Outcome must not enter it: the same trajectories that were CAUGHT
# still count. That is the whole point of a trajectory metric.
caught = _rows(6, 108.0, 29.0, np.zeros(6, bool), PARKS[:6])
homered = _rows(6, 108.0, 29.0, np.ones(6, bool), PARKS[:6])
if clears_anywhere_pct(caught) != clears_anywhere_pct(homered):
    failures.append("the rate changed with the outcome — it is supposed to "
                    "describe the trajectory, not what happened to it")
else:
    print("PASS: identical trajectories score identically, caught or not")

# --- absence is N/A, never 0.0 ---------------------------------------
# A parquet from before this shipped has no clears_anywhere column. That
# means "we cannot tell", and 0.0 would read as the worst hitter on the
# board — a fabricated stat.
old = pd.read_pickle(str(tmp / "xhr_table.parquet")).drop(columns=["clears_anywhere"])
old.to_pickle(str(tmp / "xhr_table.parquet"))
if clears_anywhere_pct(hitter) is not None:
    failures.append("an older table without the column produced a number "
                    "instead of N/A")
else:
    print("PASS: a table predating the metric reports N/A, not 0.0")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nThe launch floor is read off the league, not off a fence diagram.")
