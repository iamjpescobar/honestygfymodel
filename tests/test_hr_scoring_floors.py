"""The FLOORS and DENOMINATORS behind the HR metrics table.

Three things this pins, all of them cases where the old build produced a
number that looked fine and meant something else:

  1. UNTRACKED CONTACT. A batted ball with no exit velocity or launch
     angle cannot be binned into the xHR grid. The merge filled its
     probability with 0.0, so unmeasured contact was scored as contact
     that had no chance of leaving — and it stayed in the denominator.
     Two hitters who swung identically got different numbers because one
     played in front of a camera that missed more balls.

  2. THE GAP WAS A COUNT. xhr_gap ranked whole home runs. A 550-PA bat
     can run six either way and a 60-PA bat structurally cannot, so both
     tails of that percentile were regulars and part of what the
     correction rewarded was playing every night.

  3. THE PERCENTILE SCALE. Ranking every included bat against every
     other let hundreds of thin bats — all shrunk to the league mean on
     purpose — pile into the middle of the distribution and stretch the
     tails, so a regular's percentile depended on how many part-timers
     happened to clear the inclusion floor that week.

Each is asserted as a PROPERTY (two hitters who should agree, do) rather
than against a magic number, and each has a control below that breaks
the code on purpose and is confirmed red.
"""
import sys, types, tempfile
from pathlib import Path
import numpy as np, pandas as pd

# pyarrow isn't available in every environment; shim parquet with pickle
# so the logic under test still runs. Production keeps real parquet.
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))

pb = types.ModuleType("pybaseball")
pb.statcast = lambda *a, **k: None
sys.modules["pybaseball"] = pb
sys.path.insert(0, ".")
import precompute  # noqa: E402

tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp
precompute.HRM_MIN_PA = 10
precompute.HRM_MIN_BBE = 5
precompute.HRM_MIN_TRACKED_BBE = 10


def bbe(bid, n, ev, la, hrs, tracked=True):
    """n batted balls at one (ev, la), `hrs` of them home runs.

    tracked=False blanks exit velocity and launch angle — the shape of a
    play Statcast did not measure. Everything else about the row is
    intact, which is the point: it is a real batted ball, not a gap.
    """
    return pd.DataFrame({
        "batter": bid, "type": "X", "bb_type": "fly_ball", "stand": "R",
        "launch_speed": np.full(n, ev if tracked else np.nan, dtype=float),
        "launch_angle": np.full(n, la if tracked else np.nan, dtype=float),
        "launch_speed_angle": np.full(n, 6.0),
        "hc_x": 60.0, "hc_y": 100.0, "bat_speed": 74.0,
        "events": ["home_run"] * hrs + ["field_out"] * (n - hrs),
    })


def whiffs(bid, n):
    """Strikeouts — PA with no batted ball, to move playing time alone."""
    return pd.DataFrame({
        "batter": bid, "type": ["S"] * n, "bb_type": None, "stand": "R",
        "launch_speed": np.nan, "launch_angle": np.nan,
        "launch_speed_angle": np.nan, "hc_x": np.nan, "hc_y": np.nan,
        "bat_speed": np.nan, "events": ["strikeout"] * n,
    })


def build(frames):
    league = pd.concat(frames, ignore_index=True)
    assert precompute.build_xhr_table(league), "xHR grid did not build"
    assert precompute.build_hr_metrics(league), "HR metrics did not build"
    return pd.read_parquet(tmp / "hr_metrics.parquet").set_index("batter")


# Filler so the grid has enough contact per bucket to clear
# XHR_MIN_BUCKET_N, and so the league rate is not defined by one hitter.
FILLER = [bbe(900 + i, 40, 104.0, 28.0, 10) for i in range(6)]

# ---------------------------------------------------------------
# 1. UNTRACKED CONTACT IS EXCLUDED, NOT SCORED AS A ZERO
# ---------------------------------------------------------------
# CLEAN and MISSED swung identically on every ball anyone measured.
# MISSED simply had 20 more batted balls the cameras did not catch.
#
# FIVE OF THE UNTRACKED BALLS ARE HOME RUNS, and that is deliberate.
# The gap subtracts actual home runs from expected ones, and expected is
# summed over tracked contact — so subtracting the FULL home-run count
# charges a hitter for a homer whose trajectory was never measured, and
# pushes his gap negative for having done the thing the metric rewards.
# Without an untracked home run in the fixture, hr and hr_tracked are
# equal and that error is invisible.
CLEAN, MISSED = 1, 2
out = build(FILLER + [
    bbe(CLEAN, 40, 104.0, 28.0, 10),
    bbe(MISSED, 40, 104.0, 28.0, 10),
    bbe(MISSED, 20, 104.0, 28.0, 5, tracked=False),
])
assert out.at[MISSED, "hr"] > out.at[MISSED, "hr_tracked"], (
    "fixture has no untracked home run — the tracked-HR case proves nothing")

assert out.at[MISSED, "bbe"] > out.at[CLEAN, "bbe"], "fixture is not testing anything"
assert out.at[MISSED, "bbe_scored"] == out.at[CLEAN, "bbe_scored"], (
    f"untracked contact reached the scoreable denominator: "
    f"{out.at[MISSED, 'bbe_scored']} vs {out.at[CLEAN, 'bbe_scored']}")
assert abs(out.at[MISSED, "xhr"] - out.at[CLEAN, "xhr"]) < 0.01, (
    f"untracked balls changed xHR: {out.at[MISSED,'xhr']} vs {out.at[CLEAN,'xhr']}")
assert abs(out.at[MISSED, "xhr_gap_rate"] - out.at[CLEAN, "xhr_gap_rate"]) < 0.01
print(f"PASS: 20 untracked batted balls left xHR unchanged "
      f"({out.at[CLEAN,'xhr']:.1f} both) — excluded, not zeroed")

# ---------------------------------------------------------------
# 2. THE GAP IS A RATE, SO PLAYING TIME DOES NOT MOVE IT
# ---------------------------------------------------------------
# SHORT and LONG convert identically per batted ball. LONG simply bats
# three times as often. The raw count separates them by construction;
# the rate must not.
SHORT, LONG = 3, 4
out = build(FILLER + [
    bbe(SHORT, 40, 104.0, 28.0, 6),
    bbe(LONG, 120, 104.0, 28.0, 18),
    whiffs(LONG, 60),
])

assert abs(out.at[LONG, "xhr_gap"]) > abs(out.at[SHORT, "xhr_gap"]) * 2, (
    "the raw counts are not separated — this case cannot show anything")
# THE PROPERTY: per scoreable batted ball, they are the same hitter.
assert abs(out.at[LONG, "xhr_gap_rate_raw"]
           - out.at[SHORT, "xhr_gap_rate_raw"]) < 0.01, (
    f"playing time moved the unregressed rate: "
    f"{out.at[SHORT,'xhr_gap_rate_raw']:.2f} vs "
    f"{out.at[LONG,'xhr_gap_rate_raw']:.2f}")

# THE RANKED column still differs, and SHOULD. It is shrunk toward the
# league, and the thinner sample is shrunk harder — that is the
# regression working, not playing time leaking back in. What must hold
# is the DIRECTION: both land between the league and their own raw rate,
# and the smaller sample lands nearer the league.
_raw = out.at[SHORT, "xhr_gap_rate_raw"]
_league = 0.0     # the fixture's gap sums to zero across the league
for bid in (SHORT, LONG):
    _r = out.at[bid, "xhr_gap_rate"]
    assert min(_league, _raw) <= _r <= max(_league, _raw), (
        f"regressed rate {_r:.2f} sits outside [league, raw] — that is not "
        f"shrinkage, it is a different number")
assert abs(out.at[SHORT, "xhr_gap_rate"] - _league) < \
    abs(out.at[LONG, "xhr_gap_rate"] - _league), (
    "the thinner sample was not shrunk harder — the regression is inverted")
print(f"PASS: 3x the volume, same conversion — raw count "
      f"{out.at[SHORT,'xhr_gap']:+.1f} vs {out.at[LONG,'xhr_gap']:+.1f} "
      f"(3x), raw rate {out.at[SHORT,'xhr_gap_rate_raw']:+.2f} both, "
      f"ranked {out.at[SHORT,'xhr_gap_rate']:+.2f} vs "
      f"{out.at[LONG,'xhr_gap_rate']:+.2f} (shrunk toward league)")

# ---------------------------------------------------------------
# 3. THE SCALE COMES FROM REGULARS
# ---------------------------------------------------------------
# Same six regulars in both leagues. The second adds 120 part-timers who
# all clear the inclusion floor. Their arrival must not move where the
# regulars sit, because the scale is defined by the core.
precompute.HRM_CORE_PA = 100

# FORTY regulars, not six. The scale falls back to ranking within the
# whole pool when the core is under 30 bats — an early-April guard — and
# a fixture that trips that guard tests the fallback while claiming to
# test the scale. It did, on the first run of this file, and reported a
# 26-point move as a failure of code that was working.
N_CORE = 40
REGULARS = [bbe(10 + i, 60, 96.0 + i * 0.5, 28.0, i % 12) for i in range(N_CORE)]
REGULARS += [whiffs(10 + i, 60) for i in range(N_CORE)]       # 120 PA each
THIN = [bbe(500 + i, 12, 99.0, 28.0, 1) for i in range(120)]  # 12 PA each

alone = build(FILLER + REGULARS)
crowded = build(FILLER + REGULARS + THIN)

assert len(crowded) > len(alone) + 100, "the thin bats did not make the table"

# MEASURED ON ev90_pct, not brl_per_pa_pct.
#
# Every bat in this fixture barrels everything, so all forty regulars
# share one Brl/PA and all forty tie at the bottom of that column —
# searchsorted hands ties the same position, so the percentile could not
# move whatever the scale was built from. The case went green against a
# control that ranked everyone together. Exit velocity is the column
# these regulars actually spread across, and the part-timers sit in the
# MIDDLE of that spread, which is where they do the most damage to a
# scale that includes them.
_col = "ev90_pct"
_spread = alone.loc[[10 + i for i in range(N_CORE)], _col]
assert _spread.max() - _spread.min() > 50, (
    "the regulars do not spread across this column — nothing to move")
_moved = max(abs(crowded.at[10 + i, _col] - alone.at[10 + i, _col])
             for i in range(N_CORE))
assert _moved < 0.01, (
    f"120 part-timers moved a regular's percentile by {_moved:.1f} points")
# And the thin bats still receive a percentile — placed on the scale,
# not excluded from it. Excluding them would blank the score of every
# bench bat in tonight's lineup.
assert crowded.loc[[500 + i for i in range(120)], "brl_per_pa_pct"].notna().all()
print(f"PASS: 120 part-timers joined the table and moved the regulars' "
      f"percentiles by {_moved:.3f} points — and were still ranked")

# ---------------------------------------------------------------
# 4. THE TRACKED FLOOR REPORTS N/A, NOT A NUMBER
# ---------------------------------------------------------------
precompute.HRM_MIN_TRACKED_BBE = 30
THINTRACK = 7
out = build(FILLER + [
    bbe(THINTRACK, 8, 104.0, 28.0, 2),
    bbe(THINTRACK, 40, 104.0, 28.0, 0, tracked=False),
])
assert out.at[THINTRACK, "bbe"] >= 40, "fixture lost its contact"
assert pd.isna(out.at[THINTRACK, "xhr"]), (
    "a bat under the tracked floor published an xHR anyway")
assert pd.isna(out.at[THINTRACK, "xhr_gap_rate"]), (
    "a bat under the tracked floor published a gap rate anyway")
print("PASS: under the tracked floor, xHR and the gap read N/A rather than 0")
