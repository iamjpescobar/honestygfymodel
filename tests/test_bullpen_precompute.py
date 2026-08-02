"""The nightly bullpen profile must equal what the live path computes.

_pen_profile_json is the heaviest thing on a cold Game Card: a roster
HTTPS call plus a role/splits/hand derive for every arm, run for all ~30
teams on the slate before the first render. precompute.build_bullpen_
profiles moves that off the user's first load.

"Faster" is only acceptable if it's the SAME NUMBER. These assert the
two paths can't drift:

  - the out-event set behind the IP estimate is identical in both files
  - pooling the stored arms reproduces HR/9 and the lefty innings share
  - tonight's starter is still excluded (an opener classified RP is rare
    but real, and on the night he opens he isn't part of the late pen)
  - the sample floors still apply, so a thin pen reports None rather
    than a rate built on four arms
  - a missing file falls through to the live build instead of erroring
"""
import json
import re
import sys
import tempfile
import types
from pathlib import Path

import pandas as pd

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter", "statcast_pitcher", "playerid_lookup"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

import engines.edge as edge
from engines.statcast_engine import _OUT_EVENTS as ENGINE_OUT_EVENTS

# ---------------------------------------------------------------
# 1. The IP definition must be the same in both files.
#
# precompute.py can't be imported here (it pulls pybaseball's bulk
# statcast at module scope in some environments), so this reads the
# literal set out of the source — which is exactly the thing that would
# silently drift if someone edited one copy.
# ---------------------------------------------------------------
src = Path("precompute.py").read_text()
block = re.search(r"_OUT_EVENTS = \{(.*?)\}", src, re.S)
assert block, "precompute.py no longer defines _OUT_EVENTS"
precompute_events = set(re.findall(r'"([a-z_]+)"', block.group(1)))
assert precompute_events == ENGINE_OUT_EVENTS, (
    "IP definitions have drifted — the precomputed pen and the live pen "
    "would produce different innings for the same pitcher:\n"
    f"  only in precompute: {sorted(precompute_events - ENGINE_OUT_EVENTS)}\n"
    f"  only in engine:     {sorted(ENGINE_OUT_EVENTS - precompute_events)}")
print(f"PASS: both files agree on all {len(ENGINE_OUT_EVENTS)} out events")

# ---------------------------------------------------------------
# 2. Pooling the stored arms reproduces the live arithmetic.
# ---------------------------------------------------------------
tmp = Path(tempfile.mkdtemp())
pen_path = tmp / "bullpen_profiles.json"

# 6 arms, 60 IP total, 8 HR -> 8 * 9 / 60 = 1.20 HR/9.
# 20 of those innings are left-handed -> 0.333 share.
relievers = [
    {"id": "101", "hr": 2, "ip": 10.0, "hand": "L"},
    {"id": "102", "hr": 1, "ip": 10.0, "hand": "L"},
    {"id": "103", "hr": 2, "ip": 10.0, "hand": "R"},
    {"id": "104", "hr": 1, "ip": 10.0, "hand": "R"},
    {"id": "105", "hr": 1, "ip": 10.0, "hand": "R"},
    {"id": "106", "hr": 1, "ip": 10.0, "hand": "R"},
]
pen_path.write_text(json.dumps(
    {"Test Team": {"relievers": relievers, "unknown_role": 3}}))
edge._PEN_PATH = pen_path

got = json.loads(edge._pen_from_precomputed("Test Team", None))
assert got["arms"] == 6, got
assert got["ip"] == 60.0, got
assert got["hr9"] == 1.20, got
assert got["lhp_ip_share"] == 0.333, got
assert got["unknown_role"] == 3, got
print("PASS: pooled HR/9 and lefty innings share match the live formula")

# ---------------------------------------------------------------
# 3. Tonight's starter is excluded, not baked in.
# ---------------------------------------------------------------
without = json.loads(edge._pen_from_precomputed("Test Team", "101"))
assert without["arms"] == 5, without
assert without["ip"] == 50.0, without
# 6 HR over 50 IP once the 2-HR arm is out.
assert without["hr9"] == 1.08, without
assert without["lhp_ip_share"] == 0.2, without
print("PASS: the starter is excluded at read time, exactly as the live path does")

# ---------------------------------------------------------------
# 4. Sample floors still apply — a thin pen reports None, not a rate.
# ---------------------------------------------------------------
pen_path.write_text(json.dumps({"Thin Team": {
    "relievers": [{"id": "201", "hr": 3, "ip": 5.0, "hand": "R"}],
    "unknown_role": 0}}))
thin = json.loads(edge._pen_from_precomputed("Thin Team", None))
assert thin["hr9"] is None, thin
assert thin["lhp_ip_share"] is None, thin
print("PASS: pens under the arm/innings floor report None, never a thin rate")

# ---------------------------------------------------------------
# 5. No file, or a team not in it -> fall through to the live build.
# ---------------------------------------------------------------
assert edge._pen_from_precomputed("Nonexistent Team", None) is None
edge._PEN_PATH = tmp / "does_not_exist.json"
assert edge._pen_from_precomputed("Test Team", None) is None
print("PASS: a missing file or team falls through to the live build")

print("PASS: precomputed bullpen path verified end to end")
