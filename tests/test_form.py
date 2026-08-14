"""FORM — the numbers must be REAL, and they must stay real.

WHAT THIS FILE REPLACED. tests/test_hr_form.py asserted the behaviour of
a 0-100 index: that a hitter at his own baseline read exactly 50, that
the bands put one in ten at an extreme, that the scale was monotonic.
Every one of those assertions was correct about a number that should not
have existed. The index was a real deviation clamped and mapped onto a
hundred-point scale — and it sat on the board beside HR Score, HRThreat
and the Savant percentiles, which are LEAGUE-relative, looking exactly
like one of them. The one self-relative signal on the page was dressed
as the thing it was built to not be.

So the assertions here are the opposite shape. They do not check that a
derived number lands where a formula says it should. They check that
NOTHING IS DERIVED: that what reaches the reader is recent minus season,
in the stat's own units, and that no future edit quietly reintroduces a
scale, a clamp, a weight or a blend.

WHY ONLY TWO INPUTS is still the measured argument, unchanged — L15 vs
season across 373 hitters at 150+ PA:

    input        10th    25th   median    75th    90th   |dev| 90th
    Brl/PA     -100.0  -100.0    -26.8    33.7   101.3       101.3
    PullAir %  -100.0   -39.1     -0.9    51.1   102.3       102.3
    HH %        -43.2   -26.1     -4.4    14.0    35.9        48.0
    AvgEV        -6.1    -3.4     -0.6     2.1     4.4         7.3
    Blast %     -56.0   -32.0     -5.6    18.5    42.1        67.2

A quarter of hitters sit at exactly -100% on Brl/PA — zero barrels in
fifteen games, a wall rather than a measurement.
"""
import inspect
import sys
import types

sys.path.insert(0, "app")
sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))
from engines import form  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print(f"PASS: {msg}")
    else:
        failures.append(msg)
        print(f"FAIL: {msg}")


SEASON = {"AvgEV": 89.4, "HH %": 41.2, "Brl/PA": 6.0, "PullAir %": 12.0}
RECENT = {"AvgEV": 91.2, "HH %": 48.1, "Brl/PA": 9.0, "PullAir %": 20.0}


# ------------------------------------------------------------------ 1
# THE NUMBERS ARE SUBTRACTION. Nothing else.
#
# Asserted against arithmetic done here in the test, not against a
# fixture copied out of the engine — if the engine ever starts scaling,
# these are the lines that go red.
d = form.form_deltas(SEASON, RECENT)
check(d.get("\u0394EV") == round(91.2 - 89.4, 1),
      "the EV delta is exactly recent minus season, in mph")
check(d.get("\u0394HH%") == round(48.1 - 41.2, 1),
      "the HH% delta is exactly recent minus season, in points")

# A hitter doing exactly what he always does reads ZERO, not 50 and not
# some midpoint of a range. Zero is the anchor the whole thing rests on.
flat = form.form_deltas(SEASON, dict(SEASON))
check(flat == {"\u0394EV": 0.0, "\u0394HH%": 0.0},
      "a hitter at his own baseline reads exactly 0.0, not a midpoint")

# Sign survives. A cold hitter must come back negative — the direction
# IS the reading, and an abs() anywhere in here would destroy it.
cold = form.form_deltas(SEASON, {"AvgEV": 87.0, "HH %": 35.0})
check(cold["\u0394EV"] < 0 and cold["\u0394HH%"] < 0,
      "a hitter below his own baseline reads negative")


# ------------------------------------------------------------------ 2
# NOTHING IS CLAMPED, AND THE UNITS DO NOT MIX.
#
# The old index clamped to a band, so an extreme hitter and a merely hot
# one printed the same number. A delta has no ceiling because a
# measurement has no ceiling.
huge = form.form_deltas(SEASON, {"AvgEV": 120.0, "HH %": 41.2})
check(huge["\u0394EV"] == round(120.0 - 89.4, 1),
      "an extreme delta is reported at full size, not clamped to a band")

# The two must never be averaged into one headline. AvgEV and HH% move
# on scales an order of magnitude apart (|dev| 90th of 7.3 against
# 48.0), so a blend would call a 4% EV swing — near-extreme — equal to a
# 4% HH% swing, which is noise. That is the exact defect the old
# per-input bands existed to prevent, and it would come back wearing the
# costume of a more honest number.
check(len(form.FORM_COLUMNS) == len(set(form.FORM_COLUMNS)) >= 2,
      "Form publishes one column per input, never a blended headline")
_src = inspect.getsource(form)
for _banned, _why in [
    ("/ sum(", "a weighted mean is a blend"),
    ("max(-1.0", "a clamp to a band"),
    ("* 100.0", "a rescale onto a hundred-point range"),
]:
    check(_banned not in _src,
          f"no {_why} in the engine \u2014 the output must stay a raw stat")


# ------------------------------------------------------------------ 3
# MISSING IS MISSING. Never a fabricated zero.
#
# This matters more here than anywhere else in the app: 0.0 is a REAL
# and meaningful value in a delta column — it means measured, and
# exactly at his baseline. So a zero standing in for "we could not tell"
# is not merely wrong, it is indistinguishable from the most specific
# thing the column can say.
check(form.form_deltas(None, RECENT) == {},
      "no season baseline yields no deltas, not zeros")
check(form.form_deltas(SEASON, None) == {},
      "no recent window yields no deltas, not zeros")
check(form.form_deltas(SEASON, {}) == {},
      "an empty recent profile yields no deltas")
check("\u0394HH%" not in form.form_deltas(SEASON, {"AvgEV": 90.0}),
      "one measurable input does not fabricate the other")
check(form.form_deltas(SEASON, {"AvgEV": 90.0}).get("\u0394EV") is not None,
      "and the one that IS measurable still reports")


# ------------------------------------------------------------------ 4
# THE WORKING IS SHOWN. A delta with the numbers it came from is
# checkable against Savant; a delta alone is one more figure to trust.
lines = form.form_lines(SEASON, RECENT)
check(len(lines) == 2, "form_lines reports both inputs")
for ln in lines:
    # TO THE DISPLAYED PRECISION, which is the only claim the card
    # makes. A raw float compare fails here on 91.2 - 89.4 = 1.79999...
    # and that is the test being wrong, not the engine: what has to hold
    # is that a reader subtracting the two numbers HE CAN SEE gets the
    # third one. The engine rounds before subtracting for exactly that
    # reason.
    check(round(ln["recent"] - ln["season"], ln["dp"]) == ln["delta"],
          f'{ln["key"]}: a reader subtracting the two shown figures gets '
          f'the shown change')
    check(ln["unit"] in ("mph", "pts"),
          f'{ln["key"]}: carries a real unit, so two deltas are not read '
          f'on one scale')

note = form.form_note(SEASON, RECENT)
check(note and "89.4" in note and "91.2" in note,
      "the note names both sides, not just the answer")
check(form.form_note(SEASON, None) is None,
      "no note rather than an empty one when nothing is measurable")


# ------------------------------------------------------------------ 5
# ONLY THE TWO BEHAVED INPUTS. Adding Brl/PA or PullAir% puts a wall
# back on the board: a quarter of the league would read maximum-cold for
# a reason having nothing to do with form.
keys = [k for k, _c, _u, _dp in form.FORM_INPUTS]
check(keys == ["AvgEV", "HH %"],
      "the inputs are AvgEV and HH% only \u2014 the two that are not sparse "
      "at fifteen games")
check(form.FORM_WINDOW == "l15" and form.FORM_UNIT == "bbe",
      "the window the measurement was justified over is the window used")


# ------------------------------------------------------------------ 6
# THE COMPONENT DRAWS NOTHING WHEN THERE IS NOTHING.
#
# A heading with blank values under it reads as "measured, and he has
# none" — the same defect as a fabricated zero, one layer up.
_emitted = []
_st = types.ModuleType("streamlit")
_st.markdown = lambda h, **k: _emitted.append(h)
sys.modules["streamlit"] = _st
_theme = types.ModuleType("styles.kc_theme")

check(form.render_form(None, RECENT) is False and not _emitted,
      "the component renders nothing, and says so, when it has nothing")

print()
if failures:
    print(f"FAILED {len(failures)} check(s):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All Form checks passed.")
