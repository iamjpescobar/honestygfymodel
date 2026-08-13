"""The batter's platoon split against the STARTING pitcher.

WHY IT EXISTS. pen_context has priced the bullpen's hand mix since it
was written. The starter — whom a hitter faces two or three times — had
no platoon term at all, so a hitter with a .300 ISO against righties was
scored on his blended .205 when he faced one.

MEASURED, 340 batters clearing 40 AB against BOTH hands:

    |ISO vs RHP - ISO vs LHP|   median 0.058 · 75th 0.094
                                90th 0.138 · max 0.300
    188 of 340 (55%) gap >= 0.050 · 78 (23%) >= 0.100

League median ISO is ~.150, so the median gap is about 39% of a typical
ISO. The signed median is +0.012 — essentially zero, because righties
and lefties cancel, which is the check that says this is a platoon
effect and not a systematic bias.

THE FLOOR IS THE POINT. Only 340 of 1,390 batters qualify. A hitter
measured against one hand has ONE NUMBER, not a split, and inventing the
other side is how a thin sample becomes a confident adjustment. The term
stays silent for him — silence is the correct output, not a cost.
"""
import sys, types
import pandas as pd  # noqa: F401

st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks", "statcast"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

import engines.edge as edge  # noqa: E402

SPLITS = {}


def _iso(batter_id, throws):
    return SPLITS.get((batter_id, throws))


edge.get_batter_iso_vs_hand = _iso

# A hitter who mashes righties and cannot touch lefties — roughly the
# largest real split in the league (0.300 max measured).
SPLITS[(1, "R")] = 0.300
SPLITS[(1, "L")] = 0.100
# The median hitter: a real but ordinary gap of ~0.058.
SPLITS[(2, "R")] = 0.180
SPLITS[(2, "L")] = 0.122
# No split at all.
SPLITS[(3, "R")] = 0.150
SPLITS[(3, "L")] = 0.150
# Measured against righties only — 40 AB floor unmet vs lefties.
SPLITS[(4, "R")] = 0.300

# --- 1. The extreme split moves the score, in both directions --------
up, note = edge.platoon_context(1, "R")
down, _ = edge.platoon_context(1, "L")
assert up == edge.PLATOON_CAP, f"biggest split did not reach the cap: {up}"
assert down == -edge.PLATOON_CAP, f"reverse split did not reach -cap: {down}"
assert "0.300" in note and "0.100" in note, note
print(f"PASS: a .300/.100 split reads {up:+d} vs RHP and {down:+d} vs LHP")

# --- 2. THE MEDIAN HITTER MOVES, BUT NOT MUCH ------------------------
#
# The case against a term is "it does nothing for most of the board".
# The median gap must produce a real but modest adjustment — if it
# reached the cap the band would be too narrow, and if it rounded to
# zero the term would only ever fire for outliers.
mid, _ = edge.platoon_context(2, "R")
assert 0 < mid < edge.PLATOON_CAP, (
    f"the median hitter's gap produced {mid} — the band is mis-sized")
print(f"PASS: the median split ({0.058:.3f} gap) reads {mid:+d}, real but modest")

# --- 3. No split, no adjustment --------------------------------------
flat, _ = edge.platoon_context(3, "R")
assert flat == 0, flat
print("PASS: a hitter with no platoon split gets no adjustment")

# --- 4. ONE-SIDED IS NOT A SPLIT -------------------------------------
one, note = edge.platoon_context(4, "R")
assert one == 0 and note is None, (
    "a batter measured against only one hand received an adjustment — "
    "the other side was invented")
print("PASS: a one-sided sample yields no adjustment and no note")

# --- 5. Unknown pitcher hand -----------------------------------------
#
# get_pitcher_hand returns None for an unannounced or unknown starter.
# Guessing a hand would apply a real adjustment off a coin flip.
for hand in (None, "", "S", "?"):
    adj, note = edge.platoon_context(1, hand)
    assert adj == 0 and note is None, (hand, adj)
print("PASS: an unknown pitcher hand yields no adjustment")

# --- 6. THE BAND MATCHES THE MEASUREMENT -----------------------------
#
# A pinned constant, not derived from the code under test — widening the
# band by eye is exactly what produced three broken colour scales and a
# saturating WNBA form column this week.
assert edge.PLATOON_BAND == 0.45, (
    f"the platoon band moved to {edge.PLATOON_BAND}; the 90th-percentile "
    f"gap of 0.138 off a .150 neutral is a ~46% swing, so 0.45 is what "
    f"puts one hitter in ten at an extreme")
assert edge.PLATOON_CAP == 8
print("PASS: band and cap still match the measured distribution")

# --- 7. It reaches the edge total ------------------------------------
src = open("app/engines/edge.py", encoding="utf-8").read()
assert "+ plat_adj" in src, (
    "platoon_context is computed but never added to the edge total")
assert '"platoon_adj": plat_adj' in src, (
    "the adjustment is not returned, so no view can explain it")
print("PASS: the platoon term reaches the total and the returned dict")
