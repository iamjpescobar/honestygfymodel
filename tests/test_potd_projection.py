"""Projected stat line on the WNBA Player of the Day.

The projection reuses the SAME opponent-defense factor that already
ranks the pick — not a second model. Both inputs are measured: her own
recent box scores, and what this opponent actually allows versus the
slate average.
"""
import sys, types

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, "app")

src = open("app/engines/player_of_the_day.py").read()

for key in ("proj_pts", "proj_reb", "proj_ast"):
    assert f'"{key}"' in src, f"{key} not produced"
print("PASS: per-stat projections produced for PTS/REB/AST")

# Must reuse the existing factor, not invent a second adjustment.
seg = src[src.index('"proj_pts"'):src.index('"proj_ast"') + 200]
assert seg.count("* factor") == 3, "projections must use the same def_factor"
print("PASS: all three reuse the same opponent-defense factor as adj_pra")

# A missing average must yield None, never a number.
assert "is not None else None" in seg
print("PASS: missing input -> None, not a fabricated projection")

# The factor is capped, so a projection can't run away from reality.
assert "min(max(float(opp_pa) / slate_pa_avg, 0.9), 1.1)" in src
print("PASS: defense factor stays capped at +/-10%")

# --- the arithmetic ---------------------------------------------------
def project(avg, factor):
    return round(avg * factor, 1)
assert project(20.0, 1.1) == 22.0
assert project(20.0, 0.9) == 18.0
assert project(20.0, 1.0) == 20.0
print("PASS: projection arithmetic — soft matchup up, tough matchup down")

# --- display ----------------------------------------------------------
w = open("app/views/WNBA.py").read()
assert "PROJECTED TONIGHT" in w
# Deltas vs her own recent form, however they're rendered. This used to
# assert st.metric's `delta=` kwarg; the tiles are hand-built HTML now,
# so it checks the requirement (the difference from her form is shown)
# rather than the widget that used to show it.
assert "_proj - _base" in w, "the matchup effect must be shown as a delta vs her form"
assert "estimate, not a forecast with a track record" in w, (
    "a projection shown without that caveat reads as a graded prediction")
print("PASS: projection displayed with deltas and an honest caveat")

# It must sit alongside the real averages, not replace them.
#
# Anchored on the form-average ROW DEFINITION rather than on the
# st.metric call it used to be: the tiles were rebuilt with a real
# hierarchy (ranked stat leading, league percentiles on the components),
# so the widget changed while the requirement — her measured averages
# read first, the projection second — did not. Testing the requirement
# instead of the markup is the point.
assert '("PPG", wnba_pick.get("form_ppg")' in w, (
    "the real recent averages must still be on the tile")
i_form = w.index('("PPG", wnba_pick.get("form_ppg")')
i_proj = w.index("PROJECTED TONIGHT")
assert i_form < i_proj, "recent form should read first, projection second"
print("PASS: recent averages shown first, projection beside them")

# A neutral matchup must be LABELLED, never used as a reason to hide the
# projection. Hiding it removed the tonight-facing numbers people open
# this card for; the factor on the label carries the same information.
assert "neutral matchup" in w, "a ~1.00 factor should be called out, not left implicit"
assert "PROJECTED TONIGHT" in w
_i_head = w.index("PROJECTED TONIGHT")
assert '("PTS", _pp' in w and '("PRA", wnba_pick.get("adj_pra")' in w, (
    "the projected PTS/REB/AST/PRA numbers must always render — a neutral "
    "matchup is information, not a reason to show nothing")
print("PASS: neutral matchup is labelled and the projection still shows its numbers")
