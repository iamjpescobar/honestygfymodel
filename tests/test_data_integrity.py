"""Data-integrity guards — the "no fake numbers" rules, enforced.

Every number on this site is meant to trace to a real source. These
assert the two ways that quietly stops being true:
  1. a number that IS real but no longer describes what it's labelled
  2. two writers filling the same record with different things
"""
import re, sys, types

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from engines.park_factors import PARK_FACTORS, get_park_factor

# --- 1. Unverified factors must be unusable, not just annotated -------
# Downstream code gates on `verified`. A real Savant number that
# describes a different building is more dangerous than a missing one,
# because nothing about it looks wrong.
for team, info in PARK_FACTORS.items():
    if not info["verified"]:
        assert get_park_factor(team)["verified"] is False, \
            f"{team} is unverified but reads as verified downstream"
print(f"PASS: {sum(1 for v in PARK_FACTORS.values() if not v['verified'])} "
      f"unverified park factor(s) stay unverified through the accessor")

# The Rays played 2025 entirely at Steinbrenner Field, so a 2024-2026
# rolling factor labelled "Tropicana Field" blends three buildings.
assert PARK_FACTORS["Tampa Bay Rays"]["verified"] is False, \
    "Tampa Bay's factor spans a venue change and must not be trusted"
print("PASS: Tampa Bay's venue-blended factor is flagged")

# A missing team must degrade to None, never to a neutral-looking 100.
missing = get_park_factor("Athletics")
assert missing["park_factor"] is None and missing["verified"] is False, missing
assert missing["park_factor"] != 100, "absent data must not masquerade as neutral"
print("PASS: absent park data returns None, not a neutral-looking default")

# --- 2. One writer per calibration board ------------------------------
# calibration_picks.py owns every board it logs. A view writing the same
# key would overwrite the model's real board with whatever the user
# happened to be looking at — and neither is graded early in the day, so
# which one survived the merge would be arbitrary.
import calibration_picks as cp
ci_boards = set(cp.BUILDERS)

view_writes = {}
import glob, os
for path in glob.glob("app/views/*.py"):
    src = open(path).read()
    for board in re.findall(r'log_picks\(\s*"([a-z0-9_]+)"', src):
        view_writes.setdefault(board, []).append(os.path.basename(path))

shared = {b: v for b, v in view_writes.items() if b in ci_boards}

# daily13 and potd are written by BOTH a view and CI, and that's safe
# ONLY because log_picks is genuinely idempotent — both compute the same
# slate-wide board, so first-writer-wins yields the same picks.
# hr_edge is different: the Game Card's version ranked ONE game, so a
# view writing it would record a different thing under the same name.
assert "hr_edge" not in shared, (
    f"hr_edge is written by a view ({shared.get('hr_edge')}) as well as CI. "
    f"The view's version ranks one game, not the slate — same key, "
    f"different meaning."
)
print(f"PASS: hr_edge has a single writer (CI owns {sorted(ci_boards)}); "
      f"shared boards: {sorted(shared)}")

# The safety of those shared boards rests entirely on idempotency.
src = open("app/engines/calibration.py").read()
body = src[src.index("def log_picks"):src.index("def log_picks") + 2200]
assert "existing.get(\"picks\")" in body and "return True" in body, (
    "log_picks must refuse to overwrite an existing entry — otherwise a "
    "page re-render resets every result to None and wipes that day's grades."
)
print("PASS: log_picks refuses to overwrite an existing day (grades survive)")
