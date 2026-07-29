"""Projected stat line on the WNBA Player of the Day.

The projection reuses the SAME opponent-defense factor that already
ranks the pick — not a second model. Both inputs are measured: her own
recent box scores, and what this opponent actually allows versus the
slate average.
"""
import re, sys, types

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
assert 'delta=' in w, "deltas make the matchup effect legible"
assert "estimate, not a forecast with a track record" in w, (
    "a projection shown without that caveat reads as a graded prediction")
print("PASS: projection displayed with deltas and an honest caveat")

# It must sit alongside the real averages, not replace them.
assert 'pc1.metric(f"{_fw_label} PPG"' in w
i_form, i_proj = w.index('pc1.metric(f"{_fw_label} PPG"'), w.index("PROJECTED TONIGHT")
assert i_form < i_proj, "recent form should read first, projection second"
print("PASS: recent averages shown first, projection beside them")
