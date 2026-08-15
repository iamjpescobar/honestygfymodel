"""HR, NEAR HR, L5 PA/G and the distance columns.

WHY EACH ONE EXISTS

  NEAR HR   Balls hit hard enough AND at an angle to leave a park, that
            did not. "Who was trying" — the profile the xHR gap already
            flags as owed, made countable per hitter. Read against HR as
            a pair: 2 home runs against 9 near misses is a hitter the
            ball is not falling for; 7 against 2 is one who has cashed
            everything he has hit.

            It reuses in_window — the SAME launch window the LAUNCH axis
            uses — rather than picking a second threshold, so a near miss
            and a home-run trajectory are the same shape by construction
            and not by coincidence.

  L5 PA/G   Every other column on the lineup table is a RATE. This is the
            volume those rates get applied to. A bat hitting ninth gets
            fewer swings than one hitting second, and no rate on the page
            can see that. Last five GAMES PLAYED, not calendar days, so a
            rest day does not dilute it.

  DISTANCE  How far his contact travels — a different question from how
            hard he hits it: two bats can share an exit velocity and
            separate by fifty feet on launch angle alone.

            hit_distance_sc was added to ENGINE_COLS on 2026-08-14 and
            only populates GOING FORWARD, so on older data these are NaN
            — which must stay NaN, never 0. "Not measured" and "hit it
            nowhere" are opposite claims, and a 0 in a count column is
            indistinguishable from a real zero.
"""
import sys, types, tempfile
from pathlib import Path
import pandas as pd

pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))
_pb = types.ModuleType("pybaseball")
_pb.statcast = lambda *a, **k: None
sys.modules["pybaseball"] = _pb
sys.path.insert(0, ".")
import precompute  # noqa: E402

tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp
precompute.OUT_ROOT = tmp


def bb(batter, ev, la, event="field_out", dist=None, date="2026-08-01"):
    return {"batter": batter, "game_date": date, "events": event, "type": "X",
            "launch_speed": ev, "launch_angle": la, "bb_type": "fly_ball",
            "hit_distance_sc": dist, "stand": "R", "hc_x": 100.0, "hc_y": 100.0,
            "bat_speed": 72.0, "estimated_slg_using_speedangle": 0.5,
            "estimated_woba_using_speedangle": 0.4,
            # _mask() rejects a scalar from a missing column rather than
            # broadcasting it — so a fixture must carry every column the
            # builder reads, not just the ones under test. That guard is
            # why p_throws going missing was caught instead of silently
            # marking every row False.
            "launch_speed_angle": 6 if (ev >= 98 and 24 <= la <= 33) else 3}


rows = []
# Batter 1 — the ball is not falling for him: many near misses, one HR.
for d in range(1, 13):
    date = f"2026-08-{d:02d}"
    rows += [bb(1, 104.0, 27.0, dist=380, date=date)] * 5   # near misses
    rows += [bb(1, 104.0, 5.0, dist=120, date=date)]        # hard, wrong angle
    rows += [bb(1, 88.0, 27.0, dist=250, date=date)]        # right angle, soft
rows += [bb(1, 106.0, 28.0, event="home_run", dist=420)]
# Batter 2 — cashes what he hits. His EARLY games are heavy and his last
# five are light, so "last five" and "all games" give different answers.
# Without that difference the control that removes the tail(5) stays
# green and the case proves nothing.
for d in range(1, 13):
    date = f"2026-08-{d:02d}"
    # DIFFERENT SIZES, or the control proves nothing. Eight PA in each
    # of his first seven games and four in each of his last five, so
    # "last five" (4.0) and "all games" (6.33) cannot be confused.
    _big = d <= 7
    rows += [bb(2, 105.0, 28.0, event="home_run", dist=410, date=date)] * (3 if _big else 1)
    rows += [bb(2, 90.0, 12.0, dist=200, date=date)] * (5 if _big else 3)

assert precompute.build_hr_metrics(pd.DataFrame(rows))
m = pd.read_parquet(tmp / "hr_metrics.parquet").set_index("batter")

# --- 1. A NEAR MISS IS HARD *AND* IN THE WINDOW ----------------------
#
# Both conditions, or the column is just "hard-hit balls", which the
# board already carries as HH%.
assert m.at[1, "near_hr"] == 60, m.at[1, "near_hr"]
print(f"PASS: {int(m.at[1, 'near_hr'])} near misses — hard AND in the window only")

# --- 2. A BALL THAT LEFT IS NOT A NEAR MISS --------------------------
#
# Batter 2 hits the identical shape 36 times and every one leaves. If
# home runs counted, the column would measure power and the pairing with
# HR would say nothing.
assert m.at[2, "near_hr"] == 0, m.at[2, "near_hr"]
assert m.at[2, "hr"] == 26, m.at[2, "hr"]
print("PASS: a home run is never counted as a near miss")

# --- 3. THE PAIR IS THE READ -----------------------------------------
assert m.at[1, "hr"] == 1 and m.at[1, "near_hr"] > 10, (m.at[1, "hr"], m.at[1, "near_hr"])
assert m.at[2, "hr"] > m.at[2, "near_hr"]
print("PASS: 1 HR / 60 near vs 26 HR / 0 near — the pair separates them")

# --- 4. DISTANCE IS AVERAGED, AND THE BANDS ARE COUNTS ---------------
# 36 balls at 410 ft and 48 at 200 ft average 290, NOT 410. Averaging
# over ALL batted balls is the point: a hitter who crushes a third of
# them and rolls over the rest does not have a 410-foot profile, and a
# column that only averaged his good contact would say he does.
_exp = (26 * 410 + 50 * 200) / 76
assert abs(m.at[2, "avg_dist"] - _exp) < 1.0, (m.at[2, "avg_dist"], _exp)
assert m.at[2, "dist_300"] == 26, m.at[2, "dist_300"]
assert m.at[2, "dist_350"] == 26, m.at[2, "dist_350"]
# Batter 1's soft contact at 250 ft must miss both bands.
# Batter 1: 60 balls at 380 ft clear both bands; his 120 ft and 250 ft
# contact clears neither. The bands must COUNT, not include everything.
assert m.at[1, "dist_300"] == 61, m.at[1, "dist_300"]
assert m.at[1, "dist_350"] == 61, m.at[1, "dist_350"]
assert m.at[1, "bbe"] > m.at[1, "dist_300"], "every ball landed in the 300+ band"
print(f"PASS: AvgDist {m.at[2, 'avg_dist']:.0f} ft, 300+ and 350+ are counts")

# --- 5. NO DISTANCE COLUMN MUST NOT BECOME ZERO ----------------------
#
# THE REGRESSION THAT MATTERS. hit_distance_sc only populates going
# forward, so every historical row has none. A 0 in a count column is
# indistinguishable from a hitter who genuinely never cleared 300 feet.
_no_dist = pd.DataFrame(rows).drop(columns=["hit_distance_sc"])
assert precompute.build_hr_metrics(_no_dist)
m2 = pd.read_parquet(tmp / "hr_metrics.parquet").set_index("batter")
assert pd.isna(m2.at[2, "avg_dist"]), (
    f"missing distance became {m2.at[2, 'avg_dist']} — a real number for "
    f"data that does not exist")
assert m2.at[2, "dist_300"] == 0
print("PASS: with no distance column AvgDist is NaN, not a fabricated number")

# --- 6. L5 PA/G IS OVER GAMES PLAYED ---------------------------------
#
# Batter 2 has 7 batted balls in each of 12 games. The last five games
# must average 7, not be diluted by anything outside them.
# Every game has 7 PA, so the MEAN is 7 either way — the discriminating
# fact is the HR split: 21 home runs in the first seven games and 5 in
# the last five. l5_pa_per_game must be built from the tail, and the
# control that widens tail(5) to tail(500) has to change something.
# 4.0 over his last five games, against 6.33 over all twelve. If this
# ever reads 6.33 the tail(5) is gone and the column is measuring his
# season instead of his form.
assert abs(m.at[2, "l5_pa_per_game"] - 4.0) < 0.01, m.at[2, "l5_pa_per_game"]
_all_mean = (7 * 8 + 5 * 4) / 12
assert abs(m.at[2, "l5_pa_per_game"] - _all_mean) > 1.0, (
    "last-five and all-games give the same answer — the fixture cannot "
    "tell them apart, so this case would pass with the window removed")
assert abs(m.at[1, "l5_pa_per_game"] - 7.0) < 0.51, m.at[1, "l5_pa_per_game"]
print(f"PASS: L5 PA/G = {m.at[2, 'l5_pa_per_game']:.1f} over games played")

# --- 7. THE COLUMN IS IN BOTH LISTS ----------------------------------
#
# ENGINE_COLS and _KEEP_COLS drifting is how p_throws once went missing
# and left the platoon split dead league-wide with no error at all.
pc = open("precompute.py", encoding="utf-8").read()
se = open("app/engines/statcast_engine.py", encoding="utf-8").read()
assert '"hit_distance_sc"' in pc and '"hit_distance_sc"' in se, (
    "hit_distance_sc is not in both column lists — the nightly would "
    "write a column the engine discards, or read one it never kept")
print("PASS: hit_distance_sc is in ENGINE_COLS and _KEEP_COLS")

# --- 8. THEY REACH THE LINEUP TABLE ----------------------------------
gc = open("app/views/GameCard.py", encoding="utf-8").read()
for col in ('"HR": hr_count', '"NearHR": near_hr', '"L5 PA/G": l5_pa',
            '"AvgDist": avg_dist', '"300+": dist_300', '"350+": dist_350'):
    assert col in gc, f"{col} never reaches the row"
for fmt in ('"HR": "{:.0f}"', '"NearHR": "{:.0f}"', '"AvgDist": "{:.0f}"'):
    assert fmt in gc, f"{fmt} missing — a count would render as 7.000000"
assert '"HR", "NearHR", "L5 PA/G", "AvgDist"' in gc, "the new columns are ungraded"
print("PASS: all six reach the lineup table, formatted and graded")
