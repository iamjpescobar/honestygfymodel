"""Exercises precompute.build_hr_metrics end to end.

This test exists because it didn't. build_hr_metrics shipped with a bare
`np.` reference while precompute.py imported only pandas — a NameError
that killed the entire nightly workflow AFTER the 500k-pitch fetch had
already completed. test_xhr.py covered build_xhr_table and gave false
confidence that the precompute additions were tested.

Any function this file adds to precompute.py must be CALLED here, not
merely imported: import alone won't surface a missing global inside a
function body.
"""
import sys, types, tempfile
from pathlib import Path
import numpy as np, pandas as pd

# pyarrow isn't available in every environment; shim parquet with pickle
# so the logic under test still runs. Production keeps real parquet.
_orig = pd.DataFrame.to_parquet
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))

pb = types.ModuleType("pybaseball")
pb.statcast = lambda *a, **k: None
sys.modules["pybaseball"] = pb
sys.path.insert(0, ".")
import precompute

tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp
precompute.HRM_MIN_PA = 10
precompute.HRM_MIN_BBE = 5

rng = np.random.default_rng(7)
def bat(bid, n, ev, la, hc_x, barrel, hrs):
    """n plate appearances, all balls in play, with `hrs` home runs."""
    ev_ = np.full(n, ev, dtype=float)
    return pd.DataFrame({
        "batter": bid, "type": "X", "bb_type": "fly_ball", "stand": "R",
        "launch_speed": ev_, "launch_angle": np.full(n, la, dtype=float),
        "launch_speed_angle": np.full(n, 6 if barrel else 3),
        "hc_x": np.full(n, hc_x, dtype=float), "hc_y": 100.0,
        "bat_speed": 75.0 if barrel else 65.0,
        "events": ["home_run"]*hrs + ["field_out"]*(n-hrs),
    })

SLUG, FLAT = 101, 102
# SLUG: barrels, launches into the 20-40 window, pulls (hc_x < 125.42).
# FLAT: same exit velocity, but 12 degrees — outside the HR window.
league = pd.concat([bat(SLUG, 40, 103.0, 28.0, 90.0, True, 10),
                    bat(FLAT, 40, 103.0, 12.0, 160.0, False, 0)],
                   ignore_index=True)

assert precompute.build_xhr_table(league)
assert precompute.build_hr_metrics(league), "build_hr_metrics returned False"
print("PASS: build_hr_metrics runs (this is the NameError guard)")

out = pd.read_parquet(tmp / "hr_metrics.parquet").set_index("batter")
assert set(out.index) == {SLUG, FLAT}, out.index.tolist()

assert out.at[SLUG, "hr_window_pct"] == 100.0, out.at[SLUG, "hr_window_pct"]
assert out.at[FLAT, "hr_window_pct"] == 0.0, out.at[FLAT, "hr_window_pct"]
print("PASS: 28-deg flies count in the HR window, 12-deg liners do not")

assert out.at[SLUG, "pull_air_pct"] == 100.0, out.at[SLUG, "pull_air_pct"]
assert out.at[FLAT, "pull_air_pct"] == 0.0, out.at[FLAT, "pull_air_pct"]
print("PASS: spray angle resolves pull vs oppo the same way the engine does")

assert out.at[SLUG, "brl_per_pa"] == 100.0
assert out.at[FLAT, "brl_per_pa"] == 0.0
print("PASS: Brl/PA computed off plate appearances")

for col in ("brl_per_pa_pct", "hr_window_pct_pct", "pull_air_pct_pct",
            "ev90_pct", "hr_intent_pct", "xhr_gap_pct"):
    assert col in out.columns, f"missing percentile column {col}"
    assert out[col].between(0, 100).all(), f"{col} out of 0-100"
print("PASS: all six league-percentile columns present and in range")

assert out.at[SLUG, "hr_intent_pct"] > out.at[FLAT, "hr_intent_pct"]
print("PASS: HR Intent separates the launcher from the flat swing")

# xHR gap: SLUG hit 10 HRs off 40 identical high-probability trajectories.
assert not pd.isna(out.at[SLUG, "xhr_gap"]), "xHR gap not computed"
print(f"PASS: xHR gap computed (SLUG {out.at[SLUG,'xhr_gap']:+.1f})")

# Sample floor must exclude thin samples rather than publish noise.
precompute.HRM_MIN_PA, precompute.HRM_MIN_BBE = 500, 500
assert precompute.build_hr_metrics(league) is False
print("PASS: batters under the sample floor are excluded, not published")
