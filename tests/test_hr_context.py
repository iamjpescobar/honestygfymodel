"""Park-by-hand and temperature HR context adjustments."""
import sys, types, tempfile
from pathlib import Path
import numpy as np, pandas as pd

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball"); pb.statcast = lambda *a, **k: None
sys.modules["pybaseball"] = pb
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))
sys.path.insert(0, "."); sys.path.insert(0, "app")

import precompute
import engines.hr_context as ctx

tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp
precompute.PARK_MIN_BBE = 50

def park(team, hand, n, hrs):
    return pd.DataFrame({"home_team": team, "stand": hand, "type": "X",
                         "events": ["home_run"]*hrs + ["field_out"]*(n-hrs)})

# NYY: lefties homer far more than righties (short right-field porch,
# deep left-centre). DET: suppresses both. BOS: middling.
#
# NOTE the league baseline is computed PER HAND across all parks in this
# fixture, so "below 100" means below the league rate FOR THAT HAND —
# not below the other hand. An earlier version of this test had NYY
# righties at 16/200 and expected an index under 100; they were actually
# above the synthetic league rate, and the code was right.
league = pd.concat([
    park("NYY", "L", 200, 40), park("NYY", "R", 200, 6),
    park("DET", "L", 200, 10), park("DET", "R", 200, 12),
    park("BOS", "L", 200, 20), park("BOS", "R", 200, 14),
], ignore_index=True)

assert precompute.build_park_hr_factors(league)
ctx._PARK_PATH = tmp / "park_hr_factors.parquet"
print("PASS: park factors build from batted-ball data")

t = pd.read_parquet(ctx._PARK_PATH)
nyy_l = t[(t.park == "NYY") & (t.hand == "L")].hr_index.iloc[0]
nyy_r = t[(t.park == "NYY") & (t.hand == "R")].hr_index.iloc[0]
det_l = t[(t.park == "DET") & (t.hand == "L")].hr_index.iloc[0]
assert nyy_l > 100 and nyy_r < 100, (nyy_l, nyy_r)
assert nyy_l > det_l
print(f"PASS: same park splits by hand — NYY LHB {nyy_l:.0f} vs RHB {nyy_r:.0f}")

l_adj, l_note = ctx.park_hr_adj("NYY", "L")
r_adj, r_note = ctx.park_hr_adj("NYY", "R")
assert l_adj > 0 and r_adj < 0, (l_adj, r_adj)
assert abs(l_adj) <= ctx.PARK_CAP and abs(r_adj) <= ctx.PARK_CAP
print(f"PASS: adjustment follows hand — LHB {l_adj:+}, RHB {r_adj:+}, both within cap")
assert "LHB" in l_note and "NYY" in l_note
print(f"PASS: note explains itself: {l_note!r}")

# Switch hitters must NOT be guessed at.
assert ctx.park_hr_adj("NYY", "S") == (0, None)
print("PASS: switch hitter returns 0 — caller must resolve the effective hand")

# Unknown park / missing table degrade to zero, never a fabricated number.
assert ctx.park_hr_adj("XXX", "L") == (0, None)
assert ctx.park_hr_adj(None, "L") == (0, None)
ctx._PARK_PATH = Path("/nonexistent.parquet")
assert ctx.park_hr_adj("NYY", "L") == (0, None)
ctx._PARK_PATH = tmp / "park_hr_factors.parquet"
print("PASS: unknown park and missing table both yield no adjustment")

# Temperature: direction is settled physics.
hot, hot_note = ctx.temp_hr_adj("95 degrees")
cold, _ = ctx.temp_hr_adj("42 degrees")
mild, _ = ctx.temp_hr_adj("71 degrees")
assert hot > 0 and cold < 0 and mild == 0, (hot, cold, mild)
assert abs(hot) <= ctx.TEMP_CAP and abs(cold) <= ctx.TEMP_CAP
print(f"PASS: temperature — 95F {hot:+}, 42F {cold:+}, 71F {mild} (capped at "
      f"+/-{ctx.TEMP_CAP})")

assert ctx.temp_hr_adj("95 degrees", roof_closed=True) == (0, None)
print("PASS: closed roof ignores outside temperature")

assert ctx.temp_hr_adj(None) == (0, None)
assert ctx.temp_hr_adj("unavailable") == (0, None)
assert ctx.temp_hr_adj("900 degrees") == (0, None)
print("PASS: unparseable or absurd temperature yields no adjustment")

# Combined
total, notes = ctx.context_hr_adj("NYY", "L", "95 degrees")
assert abs(total - (l_adj + hot)) < 0.01
assert len(notes) == 2
print(f"PASS: combined park+temp = {total:+} with {len(notes)} notes")

total0, notes0 = ctx.context_hr_adj(None, "S", None)
assert total0 == 0 and notes0 == []
print("PASS: nothing measurable -> 0 with no invented notes")
