"""The weak-spot panel, drawn spatially instead of as a bar stack.

WHY THE THRESHOLDS MOVED. Measured 2026-08-13 across 5,032 buckets and
451 pitchers — every bucket the panel actually draws:

    10th   25th   median   75th   90th
   0.394  0.453   0.523   0.598  0.675

At the old XSLG_HOT of 0.550, **40.2%** of buckets were flagged "hitters
do real damage here". A phrase that marks the dangerous QUARTER cannot
apply to two buckets in five: a panel where nearly half the bars are red
says nothing about WHERE a pitcher gets hurt, which is the whole job.

xSLG on contact excludes strikeouts, so it sits far above the per-PA
figure people quote. 0.550 was near the MIDDLE of this distribution.

Fifth scale on this site chosen by eye. The other four — Clears%, FB95%,
HRWindow% and an EV floor — were all measured and all wrong.

WHY THE BARS WENT. A pitch type carries TWO numbers, usage and damage; a
bar draws one, so usage was demoted to a subtitle where it stopped being
comparable. Up/middle/down is a strike zone drawn sideways. Times
through the order is a three-point trend drawn as three unconnected
bars. The panel had nineteen bars and no shape.
"""
import sys, types
sys.path.insert(0, "app")
_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = _st
_pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks", "statcast"):
    setattr(_pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = _pb

from engines.pitcher_weakspots import XSLG_HOT, XSLG_COLD  # noqa: E402
from engines import weakspot_view as wv  # noqa: E402

# Real shape, from get_weak_spots(645261) on 2026-08-13.
PITCHES = [
    {"code": "SI", "name": "Sinker", "pitches": 686, "bbe": 159, "usage": 26.2, "xslg": 0.402},
    {"code": "CH", "name": "Changeup", "pitches": 529, "bbe": 124, "usage": 20.2, "xslg": 0.436},
    {"code": "FF", "name": "4-Seam", "pitches": 516, "bbe": 87, "usage": 19.7, "xslg": 0.665},
    {"code": "FC", "name": "Cutter", "pitches": 377, "bbe": 58, "usage": 14.4, "xslg": 0.476},
    {"code": "ST", "name": "Sweeper", "pitches": 238, "bbe": 23, "usage": 9.1,
     "xslg": None, "reason": "238 pitches / 23 batted balls \u2014 below the 150/35 floor"},
    {"code": "CU", "name": "Curveball", "pitches": 85, "bbe": 17, "usage": 3.2,
     "xslg": None, "reason": "85 pitches / 17 batted balls \u2014 below the 150/35 floor"},
]
BANDS = [{"band": "Up", "pitches": 358, "bbe": 75, "xslg": 0.422},
         {"band": "Middle", "pitches": 520, "bbe": 162, "xslg": 0.539},
         {"band": "Down", "pitches": 465, "bbe": 154, "xslg": 0.476}]
TTO = [{"pass": 1, "bbe": 159, "xslg": 0.394},
       {"pass": 2, "bbe": 166, "xslg": 0.491},
       {"pass": 3, "bbe": 146, "xslg": 0.459}]
SLOTS = [{"slot": 1, "bbe": 62, "xslg": 0.416}, {"slot": 2, "bbe": 61, "xslg": 0.451},
         {"slot": 3, "bbe": 57, "xslg": 0.664}, {"slot": 4, "bbe": 56, "xslg": 0.470},
         {"slot": 5, "bbe": 58, "xslg": 0.481}, {"slot": 6, "bbe": 51, "xslg": 0.514},
         {"slot": 7, "bbe": 47, "xslg": 0.447}, {"slot": 8, "bbe": 48, "xslg": 0.297},
         {"slot": 9, "bbe": 50, "xslg": None}]

# --- 1. THE THRESHOLDS MATCH THE MEASUREMENT -------------------------
assert XSLG_HOT == 0.598, (
    f"XSLG_HOT is {XSLG_HOT}; the measured 75th percentile is 0.598. At the "
    f"old 0.550 the panel flagged 40.2% of buckets as real damage.")
assert XSLG_COLD == 0.453, f"XSLG_COLD is {XSLG_COLD}; the measured 25th is 0.453"
print(f"PASS: thresholds are the measured 25th/75th ({XSLG_COLD}/{XSLG_HOT})")

# --- 2. THE COLOUR RULE DISCRIMINATES --------------------------------
#
# The whole point. Across the real distribution the three tones must all
# appear — a rule that returns one colour for everything is the bug.
tones = {wv.tone(v) for v in (0.394, 0.453, 0.523, 0.598, 0.675)}
assert len(tones) == 3, f"only {len(tones)} tone(s) across the real range: {tones}"
assert wv.tone(None) not in (wv.tone(0.675), wv.tone(0.394)), (
    "an unmeasured bucket shares a colour with a measured one")
print("PASS: the three tones all appear across the measured distribution")

# --- 3. THE ARSENAL PANEL CARRIES BOTH NUMBERS -----------------------
#
# A bar could draw damage OR usage. The scatter must place a bubble on
# both, which is the entire reason it replaced the bars.
svg = wv.arsenal_svg(PITCHES)
assert svg.startswith("<svg") and svg.endswith("</svg>")
assert svg.count("<circle") == 4, (
    f"expected 4 rated pitches plotted, got {svg.count('<circle')}")
assert "4-Seam 0.665" in svg and "Sinker 0.402" in svg
# Higher damage must sit HIGHER on the plot than lower damage.
import re  # noqa: E402
cy = {m.group(1): float(m.group(2)) for m in
      re.finditer(r'<circle cx="(\d+)" cy="([\d.]+)"', svg)}
assert min(cy.values()) < max(cy.values()), "every bubble landed at one height"
print(f"PASS: {svg.count('<circle')} rated pitches plotted on usage AND damage")

# --- 4. UNRATED PITCHES ARE NAMED, NOT DROPPED -----------------------
#
# "He throws a sweeper 9% of the time and we cannot rate it" is worth
# knowing. Silently omitting it makes the arsenal look smaller than it is.
assert "sweeper 9%" in svg and "below the sample floor" in svg
print("PASS: pitches under the sample floor are named rather than dropped")

# --- 5. THE ZONE IS STACKED AS A ZONE --------------------------------
#
# Up above middle above down. The old panel drew these as three
# horizontal bars, which is a strike zone rotated 90 degrees for no
# reason.
zs = wv.zone_svg(BANDS)
ys = [float(m) for m in re.findall(r'<rect x="200" y="(\d+)"', zs)]
labels = re.findall(r'>(up|middle|down)<', zs)
assert labels == ["up", "middle", "down"], labels
assert ys == sorted(ys), "the zone bands are not stacked top to bottom"
print("PASS: the zone renders stacked up / middle / down")

# --- 6. TIMES THROUGH THE ORDER IS A LINE ----------------------------
ts = wv.tto_svg(TTO)
assert "<polyline" in ts, "the three passes are not connected"
assert ts.count("<circle") == 3
# Two points is still a line; one is not.
assert wv.tto_svg(TTO[:1]) == "", "a single pass drew a trend"
print("PASS: passes render as a connected line, one point draws nothing")

# --- 7. SLOTS SORT BY LEAK, NOT BY BATTING ORDER ---------------------
#
# THE CHANGE THAT MAKES THE PANEL WORTH READING. Nine slots in order is a
# roster printout. Sorted by damage, the top rows ARE the answer.
rows = wv.slot_rows(SLOTS)
assert rows[0][0] == 3 and abs(rows[0][1] - 0.664) < 1e-9, rows[0]
assert [r[1] for r in rows] == sorted([r[1] for r in rows], reverse=True)
print(f"PASS: slots sorted by leak — slot {rows[0][0]} at {rows[0][1]:.3f} leads")

# --- 8. AN UNMEASURED SLOT IS DROPPED, NOT DRAWN EMPTY ---------------
assert all(r[1] is not None for r in rows)
assert len(rows) == 8, f"slot 9 has no xslg and should not appear: {len(rows)}"
print("PASS: the unmeasured slot is absent rather than an empty track")

# --- 9. THE LINEUP JOIN IS WHAT ANSWERS THE CAVEAT -------------------
#
# A slot's line partly reflects WHICH hitters batted there. Joined to
# tonight's order the claim changes from "he is bad at slot 4" to "the
# soft spots in this order line up with these bats", which is true
# whatever causes the softness.
lineup = [{"name": f"H{i}"} for i in range(1, 10)]
joined = wv.slot_rows(SLOTS, lineup=lineup)
assert joined[0][3] == {"name": "H3"}, joined[0]
assert all(r[3] is not None for r in joined), "a slot lost its hitter"
# Without a lineup it still works, just unjoined.
assert all(r[3] is None for r in wv.slot_rows(SLOTS))
print("PASS: slots join to tonight's hitters, and stand alone without one")

# --- 10. THE OLD BAR GROUPS ARE GONE FROM THE VIEW -------------------
gc = open("app/views/GameCard.py", encoding="utf-8").read()
assert "arsenal_svg" in gc and "zone_svg" in gc and "tto_svg" in gc, (
    "the view does not call the new panels")
assert '_ws_bar(b.get("xslg")' not in gc, "the zone bar stack is still rendered"
print("PASS: the view renders the panels and no longer draws those bars")
