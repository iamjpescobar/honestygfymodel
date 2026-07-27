"""Pitcher-side HR vulnerability metrics.

_compute_batted_ball_metrics runs on a pitcher's own rows, so Brl%, HH%,
FB%, HRWindow% and EV90 are ALREADY "allowed" figures — they describe
contact made against him. They were computed and never surfaced, leaving
the pitcher half of the HR model invisible. These assert the aliases
resolve, carry the same values, and that xHR-allowed works on that side.
"""
import sys, types, tempfile
from pathlib import Path
import numpy as np, pandas as pd

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter", "statcast_pitcher", "playerid_lookup"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
_orig = pd.DataFrame.to_parquet
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))
sys.path.insert(0, "app")

import engines.statcast_engine as se
from engines.statcast_engine import _compute_batted_ball_metrics, compute_xhr

def rows(n, ev, la, hrs=0, barrel=True):
    return pd.DataFrame({
        "type": "X", "bb_type": "fly_ball", "stand": "R",
        "launch_speed": float(ev), "launch_angle": float(la),
        "launch_speed_angle": 6 if barrel else 3,
        "hc_x": 90.0, "hc_y": 100.0, "bat_speed": 72.0, "release_speed": 93.0,
        "events": ["home_run"]*hrs + ["field_out"]*(n-hrs),
    })

# A pitcher who gives up loud contact in the HR window.
hittable = rows(40, 104.0, 28.0, hrs=6)
m = _compute_batted_ball_metrics(hittable)

# The "Allowed" aliases are what a view would read.
for src, dst in (("Brl %", "Brl % Allowed"), ("HH %", "HH % Allowed"),
                 ("FB %", "FB % Allowed"), ("HRWindow %", "HRWindow % Allowed"),
                 ("EV90", "EV90 Allowed")):
    assert src in m, f"{src} missing from metrics — alias would silently vanish"
print("PASS: every aliased source metric exists on the pitcher's own rows")

assert m["Brl %"] == 100.0 and m["FB %"] == 100.0
assert m["HRWindow %"] == 100.0
print(f"PASS: allowed contact quality reads through — Brl {m['Brl %']}%, "
      f"HR window {m['HRWindow %']}%, EV90 {m['EV90']}")

# xHR allowed uses the same grid as hitters.
tmp = Path(tempfile.mkdtemp())
grid = pd.DataFrame({"ev_bin": [104.0], "la_bin": [28.0], "hr_prob": [0.55]})
grid.to_parquet(tmp / "xhr_table.parquet", index=False)
se._DATA_DIR = tmp
xhr, actual = compute_xhr(hittable)
assert actual == 6, actual
assert abs(xhr - 40*0.55) < 0.1, xhr
gap = round(xhr - actual, 1)
assert gap > 0, "pitcher who got away with it should show a positive gap"
print(f"PASS: xHR allowed {xhr} vs {actual} actual — gap {gap:+.1f} (luck to regress)")

# A groundball pitcher must not look vulnerable.
worm = _compute_batted_ball_metrics(rows(40, 88.0, 2.0, barrel=False))
assert worm["HRWindow %"] == 0.0 and worm["Brl %"] == 0.0
print("PASS: groundball pitcher shows zero HR-window contact allowed")
