"""FORM — recent vs the player's OWN baseline.

WHAT FORM IS NOT. Not last season vs this season — that is career
trajectory, it breaks for rookies and for anyone whose role changed, and
it is stale by August.

WHY ONLY TWO INPUTS. Measured L15 vs season across 373 hitters at
150+ PA:

    input        10th    25th   median    75th    90th   |dev| 90th
    Brl/PA     -100.0  -100.0    -26.8    33.7   101.3       101.3
    PullAir %  -100.0   -39.1     -0.9    51.1   102.3       102.3
    HH %        -43.2   -26.1     -4.4    14.0    35.9        48.0
    AvgEV        -6.1    -3.4     -0.6     2.1     4.4         7.3
    Blast %     -56.0   -32.0     -5.6    18.5    42.1        67.2

A QUARTER OF HITTERS SIT AT EXACTLY -100% ON Brl/PA — zero barrels in
fifteen games. A wall, not a measurement. Brl/PA's median of -26.8 is
the tell: a form metric on comparable footing has a median at zero,
because half a league is above its own baseline and half below.

Had this shipped on all five inputs, a quarter of the board would have
read maximum-cold for a reason having nothing to do with form. Same
defect as the WNBA 3PM band, at the opposite end of the scale.
"""
import sys, types
sys.path.insert(0, "app")
sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))
from engines import hr_form  # noqa: E402

BASE = {"AvgEV": 89.0, "HH %": 40.0, "Brl/PA": 6.0, "PullAir %": 12.0}

# --- 1. AT HIS OWN BASELINE READS 50 ---------------------------------
#
# The anchor the whole scale rests on. A hitter doing exactly what he
# always does is neither hot nor cold.
assert hr_form.form_score(BASE, dict(BASE)) == 50.0
print("PASS: a hitter at his own baseline reads exactly 50")

# --- 2. THE BAND PUTS ONE IN TEN AT AN EXTREME -----------------------
#
# +7.3% on AvgEV is the measured 90th percentile of absolute deviation.
# It must reach the ceiling — no further, or the band is too wide; no
# sooner, or it saturates.
hot = {**BASE, "AvgEV": 89.0 * 1.073, "HH %": 40.0 * 1.48}
cold = {**BASE, "AvgEV": 89.0 * 0.927, "HH %": 40.0 * 0.52}
assert hr_form.form_score(BASE, hot) == 100.0, hr_form.form_score(BASE, hot)
assert hr_form.form_score(BASE, cold) == 0.0, hr_form.form_score(BASE, cold)
print("PASS: the measured 90th-percentile deviation reaches the extremes")

# --- 3. A TYPICAL SWING IS NOT AN EXTREME ----------------------------
#
# The saturation check. A hitter 2% up on exit velocity — around the
# 75th percentile of real deviation — must read warm, not maximum.
mild = {**BASE, "AvgEV": 89.0 * 1.021, "HH %": 40.0 * 1.14}
mid = hr_form.form_score(BASE, mild)
assert 50 < mid < 80, f"a 75th-percentile swing read {mid} — the band is wrong"
print(f"PASS: a 75th-percentile swing reads {mid}, warm rather than pinned")

# --- 4. THE SPARSE INPUTS ARE NOT USED -------------------------------
#
# The regression control for the column that was NOT shipped. Barrels
# and pull-air are too sparse over fifteen games; a quarter of hitters
# are at exactly -100% on Brl/PA. If either reappears in FORM_INPUTS,
# that quarter of the board reads maximum-cold for no reason.
_keys = [k for k, _b, _w in hr_form.FORM_INPUTS]
for banned in ("Brl/PA", "PullAir %", "Blast %"):
    assert banned not in _keys, (
        f"{banned} is back in FORM_INPUTS — it hits a -100% wall for a "
        f"quarter of hitters over a 15-game window")
assert _keys == ["AvgEV", "HH %"], _keys
print(f"PASS: form reads only {_keys} — the sparse inputs stay out")

# --- 5. BANDS ARE PER INPUT ------------------------------------------
#
# One shared band would flatten the stable input and saturate the
# volatile one, which is the same mistake in a new place.
_bands = {k: b for k, b, _w in hr_form.FORM_INPUTS}
assert _bands["AvgEV"] == 7.3 and _bands["HH %"] == 48.0, _bands
assert _bands["AvgEV"] != _bands["HH %"], (
    "the two inputs share a band — exit velocity moves a few percent and "
    "hard-hit rate swings far more; one band cannot serve both")
print("PASS: each input carries its own measured band")

# --- 6. UNMEASURABLE IS None, NOT 50 ---------------------------------
#
# A neutral 50 and "we could not tell" look identical on a board and
# mean opposite things.
assert hr_form.form_score(BASE, None) is None
assert hr_form.form_score(BASE, {}) is None
assert hr_form.form_score({}, BASE) is None
# PROFILES PRESENT, NOTHING READABLE. The case the three above miss:
# they all trip the empty-profile guard, so a `return 50.0` further down
# stayed green through a control that made unmeasurable look neutral.
assert hr_form.form_score(BASE, {"Foo": 1, "Bar": 2}) is None, (
    "a profile with no readable input returned a score — 50 and "
    "'could not tell' look identical on a board and mean opposites")
# One input readable, the other not: still a score, from what exists.
assert hr_form.form_score(BASE, {"AvgEV": 89.0}) == 50.0
print("PASS: unmeasurable returns None; a partial read still scores")

# --- 7. It reaches the board -----------------------------------------
tp = open("app/engines/top_plays.py", encoding="utf-8").read()
assert '"form": _form_for(b)' in tp and '"avg_ev"' in tp, (
    "rank_batters does not carry form or avg_ev, so no view can show them")
view = open("app/views/HR_Edge_Board.py", encoding="utf-8").read()
assert '"Form": r.get("form")' in view and '"AvgEV": r.get("avg_ev")' in view
assert '"AvgEV", "Form"' in view, "the new columns are not colour-graded"
print("PASS: AvgEV and Form reach the board and are graded")
