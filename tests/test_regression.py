"""Sample-size regression on the league-wide HR metrics.

A raw rate off 55 plate appearances is not comparable to one off 450,
but percentile ranking treats them identically. These assert that thin
samples get pulled toward the league mean, that the ORDER of the board
changes as a result, and that a real track record still wins.
"""
import sys, types, tempfile
from pathlib import Path
import numpy as np, pandas as pd

pb = types.ModuleType("pybaseball"); pb.statcast = lambda *a, **k: None
sys.modules["pybaseball"] = pb
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))
sys.path.insert(0, ".")
import precompute

tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp
precompute.HRM_MIN_PA = 40
precompute.HRM_MIN_BBE = 20

def bat(bid, n_bbe, barrels, n_k=0):
    """n_bbe batted balls of which `barrels` are barrels, plus strikeouts."""
    rows = pd.DataFrame({
        "batter": bid, "type": "X", "bb_type": "fly_ball", "stand": "R",
        "launch_speed": 103.0, "launch_angle": 28.0,
        "launch_speed_angle": [6]*barrels + [3]*(n_bbe-barrels),
        "hc_x": 90.0, "hc_y": 100.0, "bat_speed": 72.0,
        "events": ["field_out"]*n_bbe,
    })
    if n_k:
        ks = pd.DataFrame({
            "batter": bid, "type": "S", "bb_type": None, "stand": "R",
            "launch_speed": np.nan, "launch_angle": np.nan,
            "launch_speed_angle": np.nan, "hc_x": np.nan, "hc_y": np.nan,
            "bat_speed": np.nan, "events": ["strikeout"]*n_k,
        })
        rows = pd.concat([rows, ks], ignore_index=True)
    return rows

# FLUKE: 50 BBE, 40 barrels (80%) — a hot two weeks.
# GRINDER: 500 BBE, 250 barrels (50%) — half the rate, ten times the proof.
# FILLER: league mass so the mean isn't set by these two alone.
FLUKE, GRINDER = 1, 2
league = pd.concat(
    [bat(FLUKE, 50, 40), bat(GRINDER, 500, 250)] +
    [bat(100 + i, 200, 40) for i in range(8)],
    ignore_index=True)
league["launch_speed_angle"] = league["launch_speed_angle"].astype("Int8")

assert precompute.build_xhr_table(league)
assert precompute.build_hr_metrics(league)
out = pd.read_parquet(tmp / "hr_metrics.parquet").set_index("batter")

raw_f = out.at[FLUKE, "brl_per_pa_raw"]
raw_g = out.at[GRINDER, "brl_per_pa_raw"]
reg_f = out.at[FLUKE, "brl_per_pa"]
reg_g = out.at[GRINDER, "brl_per_pa"]

assert raw_f > raw_g, "fixture wrong — fluke should have the higher raw rate"
print(f"PASS: raw rates — fluke {raw_f:.1f}% vs grinder {raw_g:.1f}% "
      f"(fluke looks better)")

# The whole point: regression must REORDER them.
assert reg_g > reg_f, (
    f"regression didn't reorder: fluke {reg_f:.1f} still >= grinder {reg_g:.1f}")
print(f"PASS: regressed — grinder {reg_g:.1f}% now ABOVE fluke {reg_f:.1f}% "
      f"(order flipped)")

# Thin samples move a lot, deep samples barely move.
move_f = abs(reg_f - raw_f)
move_g = abs(reg_g - raw_g)
assert move_f > move_g * 3, (move_f, move_g)
print(f"PASS: fluke pulled {move_f:.1f} pts, grinder only {move_g:.1f} "
      f"(regression scales with sample size)")

# Raw values are preserved for display, not overwritten.
for col in ("brl_per_pa_raw", "hr_window_pct_raw", "pull_air_pct_raw"):
    assert col in out.columns, f"{col} missing — raw rate must stay visible"
print("PASS: unregressed rates kept alongside for display")

# Percentiles rank the REGRESSED value.
assert out.at[GRINDER, "brl_per_pa_pct"] > out.at[FLUKE, "brl_per_pa_pct"]
print("PASS: league percentiles rank the regressed rate, not the raw one")

# Regression must never invent a rate outside what's possible.
assert (out["brl_per_pa"] >= 0).all() and (out["brl_per_pa"] <= 100).all()
assert (out["hr_window_pct"] >= 0).all() and (out["hr_window_pct"] <= 100).all()
print("PASS: all regressed rates stay within 0-100")
