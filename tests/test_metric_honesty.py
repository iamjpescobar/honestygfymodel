"""Every stat is measured or absent — never estimated, never mislabelled.

Three real defects covered here:

1. Barrel% used a FLAT 26-30 degree band at every exit velocity. A barrel
   band widens as EV rises (98 -> 26-30, 116 -> 8-50), so the flat
   version discarded every hard-hit barrel outside that narrow window —
   a systematic undercount feeding HR Score.

2. SwStr% counted only "swinging_strike" while Whiff% counted
   "swinging_strike" AND "swinging_strike_blocked", and zone-contact left
   blocked whiffs out of its swing denominator. Three rates, three
   different opinions about what a swing and a miss is.

3. All three returned 0.0 when there was no data. 0.00 SwStr% reads as
   the best possible value, so a player we know nothing about rendered as
   elite.
"""
import sys
import types

import pandas as pd

st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
# statcast_engine imports all three of these at module level, so every
# one has to exist on the stub or the import fails.
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

from engines import statcast_engine as se

# --- 1. Barrels are measured, never estimated ------------------------
# No launch_speed_angle column => nothing to measure => None, NOT a
# derived estimate. This previously fell back to a launch-angle band.
bbe = pd.DataFrame({
    "type": ["X"] * 5,
    "launch_speed": [97.0, 98.0, 105.0, 116.0, 116.0],
    "launch_angle": [28.0, 28.0, 20.0, 9.0, 55.0],
    "events": ["field_out"] * 5,
})
m = se._compute_batted_ball_metrics(bbe)
assert m["Brl %"] is None, (
    f"Brl% was {m['Brl %']!r} with no launch_speed_angle column. A barrel is "
    f"MLB's classification of a batted ball; anything we compute ourselves "
    f"is a different number wearing the same name")
assert m["Brl/PA"] is None, "Brl/PA is derived from barrels and must be None too"
assert m["PullBrl %"] is None, (
    "a pulled barrel is a barrel first — PullBrl% cannot be real when "
    "barrels are unmeasurable")
assert m["_barrel_measured"] is False
# Everything NOT dependent on barrels still computes from real data.
assert m["HH %"] is not None and m["SweetSpot %"] is not None, (
    "unmeasurable barrels must not take down the metrics that don't depend "
    "on them")
print("PASS: barrels are None, not estimated, when the column is absent")

# Statcast's own bucket is the only source of a barrel.
exact = pd.DataFrame({
    "type": ["X"] * 4,
    "launch_speed": [100.0, 100.0, 116.0, 97.0],
    "launch_angle": [28.0, 28.0, 9.0, 28.0],
    "launch_speed_angle": [6, 3, 6, 6],
    "events": ["home_run", "field_out", "home_run", "field_out"],
})
me = se._compute_batted_ball_metrics(exact)
assert me["Brl %"] == 75.0, (
    f"three of four rows carry launch_speed_angle == 6, so Brl% is 75.0, got "
    f"{me['Brl %']} — the bucket is authoritative even where a hand-rolled "
    f"launch-angle rule would disagree (row 3 is 9 degrees, row 4 is 97 mph)")
assert me["_barrel_measured"] is True
print("PASS: Statcast's launch_speed_angle bucket is the only barrel source")

# --- 2. One definition of a swing and a miss --------------------------
# 4 pitches: 1 blocked whiff, 1 plain whiff, 1 foul (swing+contact),
# 1 called strike (not a swing).
df = pd.DataFrame({"description": [
    "swinging_strike_blocked", "swinging_strike", "foul", "called_strike"]})

assert se._compute_swstr_pct(df) == 50.0, (
    f"SwStr% = 2 whiffs / 4 pitches = 50.0, got {se._compute_swstr_pct(df)} — "
    f"dropping swinging_strike_blocked understates every pitcher who gets "
    f"swings in the dirt")
assert se._compute_whiff_pct(df) == round(2 / 3 * 100, 2), (
    f"Whiff% = 2 whiffs / 3 swings, got {se._compute_whiff_pct(df)}")
print("PASS: SwStr% and Whiff% agree on what a swing and a miss is")

zdf = pd.DataFrame({
    "description": ["swinging_strike_blocked", "foul", "hit_into_play"],
    "zone": [5, 5, 5],
})
assert se._compute_zone_contact_pct(zdf) == round(2 / 3 * 100, 2), (
    f"zone contact = 2 contacts / 3 in-zone swings, got "
    f"{se._compute_zone_contact_pct(zdf)} — omitting blocked whiffs from the "
    f"denominator inflates contact rate")
print("PASS: zone contact counts blocked whiffs as swings")

# --- 3. Absent data returns None, never a flattering zero -------------
empty = pd.DataFrame({"description": []})
for name, fn, arg in (
    ("SwStr%", se._compute_swstr_pct, empty),
    ("Whiff%", se._compute_whiff_pct, empty),
    ("ZoneContact%", se._compute_zone_contact_pct,
     pd.DataFrame({"description": [], "zone": []})),
):
    got = fn(arg)
    assert got is None, (
        f"{name} returned {got!r} for a player with no data. 0.0 in these "
        f"columns reads as the BEST possible value, so absent data would "
        f"render as elite — the same rule test_data_integrity enforces for "
        f"park factors")
print("PASS: no-data returns None rather than a flattering 0.0")

# Taking zero swings is also not a 0% whiff rate.
no_swings = pd.DataFrame({"description": ["called_strike", "ball"]})
assert se._compute_whiff_pct(no_swings) is None, \
    "no swings means Whiff% is unknown, not 0.0"
print("PASS: zero swings yields None, not a 0.0 whiff rate")

# --- 4. x-stats are expected stats or nothing -------------------------
# No estimated_* columns => None. This previously backfilled REAL
# wOBA/SLG into these columns, which are a different statistic.
frame = pd.DataFrame({
    "type": ["X", "X", "X"],
    "events": ["single", "home_run", "field_out"],
    "launch_speed": [95.0, 105.0, 80.0],
    "launch_angle": [12.0, 28.0, 5.0],
})
out = se._add_expected_stats({}, frame)
assert out["xwOBA"] is None and out["xSLG"] is None, (
    f"got xwOBA={out['xwOBA']!r} xSLG={out['xSLG']!r}. Expected stats strip "
    f"out defence, park and luck; actuals contain all three. Filling an 'x' "
    f"column with an actual tells the user they're reading a stat they "
    f"aren't")
assert "_expected_actual" not in out, \
    "the substitution flag should be gone, not merely unused"
# The real versions are still available, under their own honest names.
real = se._compute_batted_ball_metrics(frame)
assert real["SLG"] is not None and real["ISO"] is not None, (
    "removing the fallback must not lose the real slugging line — it is "
    "still reported as SLG/ISO")
print("PASS: x-stats are None when Statcast's expected columns are absent")

# When the real expected columns ARE present, they're used as-is.
with_x = frame.assign(
    estimated_woba_using_speedangle=[0.35, 0.90, 0.10],
    estimated_slg_using_speedangle=[0.50, 1.60, 0.10],
)
out2 = se._add_expected_stats({}, with_x)
assert out2["xwOBA"] == 0.45 and out2["xSLG"] == 0.733, (
    f"expected the mean of the real expected-stat columns, got "
    f"xwOBA={out2['xwOBA']} xSLG={out2['xSLG']}")
print("PASS: genuine Statcast expected stats are used as-is")
