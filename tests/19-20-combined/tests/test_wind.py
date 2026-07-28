"""Wind resolved against real park orientations.

The geometry is the whole thing: a southwest wind blows OUT at a park
facing northeast and IN at one facing southwest. Getting the sign
backwards would be worse than ignoring wind entirely, so these check
direction explicitly, in both hemispheres of the compass.
"""
import sys, types
st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, "app")

from engines.wind_engine import (
    wind_hr_adj, _parse_wind, PARK_CF_BEARING, WIND_CAP, _POINTS)
from engines.team_abbreviations import TEAM_ABBREVIATIONS

# --- coverage: every abbreviation must be one the rest of the app uses -
known = set(TEAM_ABBREVIATIONS.values())
unknown = set(PARK_CF_BEARING) - known
assert not unknown, f"bearings keyed by abbreviations nothing else uses: {unknown}"
print(f"PASS: all {len(PARK_CF_BEARING)} park keys match team_abbreviations")

missing = known - set(PARK_CF_BEARING)
assert missing == {"ATH"}, f"expected only ATH missing, got {missing}"
print("PASS: 29 of 30 parks covered; ATH absent (Sutter Health Park not in source)")

# All bearings must be real compass points.
assert all(v in _POINTS.values() for v in PARK_CF_BEARING.values())
print("PASS: every bearing is an exact compass point")

# --- parsing ----------------------------------------------------------
assert _parse_wind("SW 12 mph") == (12.0, 225.0)
assert _parse_wind("Wind 8 mph out of the NNE") == (8.0, 22.5)
# SSW must not be mis-parsed as S.
assert _parse_wind("SSW 10 mph") == (10.0, 202.5)
print("PASS: compass parsing handles ordering and 3-letter points")

for bad in (None, "", "Out To CF", "calm", "12 mph"):
    assert _parse_wind(bad) == (None, None), bad
print("PASS: field-relative and unparseable strings yield nothing")

# --- the geometry that matters ----------------------------------------
# Wrigley (CHC) faces NE. A SW wind travels toward NE -> straight OUT.
out_adj, out_note = wind_hr_adj("CHC", "SW 15 mph")
assert out_adj > 0, out_adj
assert "blowing out" in out_note, out_note
print(f"PASS: Wrigley faces NE, SW wind blows OUT -> {out_adj:+} ({out_note})")

# The SAME wind at Comerica (DET), which faces SSE, blows IN.
in_adj, in_note = wind_hr_adj("DET", "SW 15 mph")
assert in_adj < 0, in_adj
print(f"PASS: same SW wind at Comerica (faces SSE) blows IN -> {in_adj:+}")

# A NE wind at Wrigley is the reverse of a SW wind at Wrigley.
rev_adj, _ = wind_hr_adj("CHC", "NE 15 mph")
assert rev_adj < 0
assert abs(rev_adj + out_adj) < 0.2, (rev_adj, out_adj)
print(f"PASS: reversing the wind reverses the sign exactly "
      f"({out_adj:+} vs {rev_adj:+})")

# Crosswind is near-neutral.
cross_adj, _ = wind_hr_adj("CHC", "SE 15 mph")
assert abs(cross_adj) < 1.0, cross_adj
print(f"PASS: perpendicular wind is ~neutral ({cross_adj:+})")

# Speed scales the effect.
slow, _ = wind_hr_adj("CHC", "SW 5 mph")
fast, _ = wind_hr_adj("CHC", "SW 25 mph")
assert 0 < slow < out_adj <= fast
assert fast <= WIND_CAP
print(f"PASS: scales with speed — 5mph {slow:+}, 15mph {out_adj:+}, "
      f"25mph {fast:+} (capped at {WIND_CAP})")

# --- honest degradation -----------------------------------------------
assert wind_hr_adj("CHC", "SW 15 mph", roof_closed=True) == (0, None)
assert wind_hr_adj("ATH", "SW 15 mph") == (0, None), "unknown park must not guess"
assert wind_hr_adj(None, "SW 15 mph") == (0, None)
assert wind_hr_adj("CHC", "Out To CF 12 mph") == (0, None), \
    "field-relative strings belong to the other code path"
assert wind_hr_adj("CHC", None) == (0, None)
print("PASS: roof, unknown park, and unparseable input all yield no adjustment")
