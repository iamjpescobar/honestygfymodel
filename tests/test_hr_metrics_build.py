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

def non_bbe(bid, n):
    """Strikeouts, walks, and called pitches — the majority of real rows.

    Every batted-ball column is NaN here. This is what broke the nightly
    run: launch_speed_angle is NaN on all of these, and with a NULLABLE
    dtype the comparison `== 6` yields pd.NA rather than False. NA
    survives `&`, so the integer cast blew up with "cannot convert NA to
    integer". A synthetic frame of clean batted balls never reproduces
    it — this block is the whole point of the test.
    """
    return pd.DataFrame({
        "batter": bid, "type": ["S"]*n, "bb_type": [None]*n, "stand": "R",
        "launch_speed": np.nan, "launch_angle": np.nan,
        "launch_speed_angle": np.nan,
        "hc_x": np.nan, "hc_y": np.nan, "bat_speed": np.nan,
        "events": [None]*(n-1) + ["strikeout"],
    })

def untracked(bid, n):
    """Batted balls with NO tracking data — the exact production case.

    This is the row that broke the nightly run, and it's subtle: type=="X"
    (it IS a batted ball) while launch_speed_angle is missing. Bunts,
    weak contact, and tracking dropouts all produce it.

    Why it matters: with a nullable dtype, `launch_speed_angle == 6`
    gives pd.NA here, and `is_bbe & NA` is `True & NA` = NA. The NA
    SURVIVES the `&` and blows up the integer cast. On a non-batted-ball
    row the same NA is harmless, because `False & NA` is False — which
    is why a frame of clean batted balls plus clean strikeouts passes
    even against the broken code. It has to be a batted ball WITH
    missing tracking to reproduce.
    """
    return pd.DataFrame({
        "batter": bid, "type": ["X"]*n, "bb_type": ["ground_ball"]*n,
        "stand": "R", "launch_speed": np.nan, "launch_angle": np.nan,
        "launch_speed_angle": np.nan, "hc_x": np.nan, "hc_y": np.nan,
        "bat_speed": np.nan, "events": ["field_out"]*n,
    })

SLUG, FLAT = 101, 102
# SLUG: barrels, launches into the 20-40 window, pulls (hc_x < 125.42).
# FLAT: same exit velocity, but 12 degrees — outside the HR window.
league = pd.concat([bat(SLUG, 40, 103.0, 28.0, 90.0, True, 10),
                    non_bbe(SLUG, 25), untracked(SLUG, 5),
                    bat(FLAT, 40, 103.0, 12.0, 160.0, False, 0),
                    non_bbe(FLAT, 25), untracked(FLAT, 5)],
                   ignore_index=True)

# Force the NULLABLE dtypes real Statcast data arrives with. Plain
# float64 silently turns NA into NaN and hides the bug; Int8/Float64
# propagate pd.NA through the mask exactly like production does.
league["launch_speed_angle"] = league["launch_speed_angle"].astype("Int8")
league["launch_speed"] = league["launch_speed"].astype("Float64")
league["launch_angle"] = league["launch_angle"].astype("Float64")
league["hc_x"] = league["hc_x"].astype("Float64")
league["hc_y"] = league["hc_y"].astype("Float64")

assert precompute.build_xhr_table(league)
assert precompute.build_hr_metrics(league), "build_hr_metrics returned False"
print("PASS: build_hr_metrics runs (this is the NameError guard)")

out = pd.read_parquet(tmp / "hr_metrics.parquet").set_index("batter")
assert set(out.index) == {SLUG, FLAT}, out.index.tolist()

# Exact rates now live in the *_raw columns; the unsuffixed ones are
# REGRESSED toward the league mean by sample size (see _regress in
# precompute), so they deliberately no longer equal the raw fraction.
# 40 of 45 batted balls in the window (the 5 untracked ones aren't).
assert abs(out.at[SLUG, "hr_window_pct_raw"] - 40/45*100) < 0.01, out.at[SLUG, "hr_window_pct_raw"]
assert out.at[FLAT, "hr_window_pct_raw"] == 0.0, out.at[FLAT, "hr_window_pct_raw"]
# Regression must pull both toward the middle, never past each other.
assert out.at[SLUG, "hr_window_pct"] < out.at[SLUG, "hr_window_pct_raw"]
assert out.at[FLAT, "hr_window_pct"] > out.at[FLAT, "hr_window_pct_raw"]
assert out.at[SLUG, "hr_window_pct"] > out.at[FLAT, "hr_window_pct"], \
    "regression must not reorder two equally-sized samples"
print("PASS: 28-deg flies count in the HR window, 12-deg liners do not")

assert abs(out.at[SLUG, "pull_air_pct_raw"] - 40/45*100) < 0.01, out.at[SLUG, "pull_air_pct_raw"]
assert out.at[FLAT, "pull_air_pct_raw"] == 0.0, out.at[FLAT, "pull_air_pct_raw"]
print("PASS: spray angle resolves pull vs oppo the same way the engine does")

# 40 barrels over 41 plate appearances (40 in play + 1 strikeout).
# The strikeout row MUST land in the denominator — that's the whole
# reason Brl/PA is used instead of Brl%.
assert out.at[SLUG, "pa"] == 46, out.at[SLUG, "pa"]   # 40 in play + 1 K + 5 untracked
assert abs(out.at[SLUG, "brl_per_pa_raw"] - 40/46*100) < 0.01, out.at[SLUG, "brl_per_pa_raw"]
assert out.at[FLAT, "brl_per_pa_raw"] == 0.0
print(f"PASS: Brl/PA raw {out.at[SLUG,'brl_per_pa_raw']:.1f}% "
      f"(regressed {out.at[SLUG,'brl_per_pa']:.1f}%) — strikeouts in the denominator")

for col in ("brl_per_pa_raw", "hr_window_pct_raw", "pull_air_pct_raw"):
    assert col in out.columns, f"raw rate {col} must stay available for display"
print("PASS: unregressed rates preserved alongside the regressed ones")

for col in ("brl_per_pa_pct", "hr_window_pct_pct", "pull_air_pct_pct",
            "ev90_pct", "bat_speed_pct", "hr_intent_pct", "xhr_gap_rate_pct"):
    assert col in out.columns, f"missing percentile column {col}"
    assert out[col].dropna().between(0, 100).all(), f"{col} out of 0-100"
print("PASS: all seven league-percentile columns present and in range")

# bat_speed is ranked in its own right now. hr_score's process axis reads
# it directly instead of reading HRIntent, which is two thirds the same
# columns the launch axis already carries.
assert "bat_speed_pct" in out.columns, "process axis has no ranked column to read"

# The COUNT-based gap column must NOT be published as a percentile any
# more — hr_score would read a ranking of whole home runs, i.e. of
# playing time. The raw count stays for display.
assert "xhr_gap" in out.columns, "raw gap should stay available for display"
assert "xhr_gap_pct" not in out.columns, (
    "xhr_gap_pct is back — that column ranks a count, not a rate")
print("PASS: the gap is ranked as a rate; the raw count stays for display only")

assert out.at[SLUG, "hr_intent_pct"] > out.at[FLAT, "hr_intent_pct"]
print("PASS: HR Intent separates the launcher from the flat swing")

# xHR gap: SLUG hit 10 HRs off 40 identical high-probability trajectories.
assert not pd.isna(out.at[SLUG, "xhr_gap"]), "xHR gap not computed"
print(f"PASS: xHR gap computed (SLUG {out.at[SLUG,'xhr_gap']:+.1f})")

# UNTRACKED CONTACT IS EXCLUDED, NOT ZEROED.
#
# The fixture gives SLUG five batted balls with no launch_speed and no
# launch_angle. Those cannot be binned into the xHR grid; the merge used
# to fill their probability with 0.0 and leave them in the denominator,
# so a hitter was charged for contact nobody measured. bbe_scored is the
# denominator every xHR-derived rate now divides by.
assert out.at[SLUG, "bbe_tracked"] < out.at[SLUG, "bbe"], (
    "fixture no longer contains untracked contact — this case proves nothing")
assert out.at[SLUG, "bbe_scored"] <= out.at[SLUG, "bbe_tracked"]
print(f"PASS: {out.at[SLUG,'bbe']} batted balls, "
      f"{out.at[SLUG,'bbe_scored']} scoreable — the rest excluded, not zeroed")

# Sample floor must exclude thin samples rather than publish noise.
precompute.HRM_MIN_PA, precompute.HRM_MIN_BBE = 500, 500
assert precompute.build_hr_metrics(league) is False
print("PASS: batters under the sample floor are excluded, not published")
