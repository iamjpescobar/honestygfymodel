"""End-to-end: build the xHR table the way the pipeline does, then read
it back through the engine and check the luck gap comes out right."""
import sys, types
import numpy as np, pandas as pd
st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data=_cache; sys.modules["streamlit"]=st
pb=types.ModuleType("pybaseball")
for n in ("statcast_batter","statcast_pitcher","playerid_lookup","statcast"): setattr(pb,n,lambda *a,**k:None)
sys.modules["pybaseball"]=pb
sys.path.insert(0, ".")


import pandas as _pd
_orig_df_to_parquet = _pd.DataFrame.to_parquet
def _fake_to_parquet(self, path, **kw): self.to_pickle(str(path))
_pd.DataFrame.to_parquet = _fake_to_parquet
_pd.read_parquet = lambda path, **kw: _pd.read_pickle(str(path))

import precompute
from pathlib import Path
import tempfile
tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp

# Synthetic league: 100-102mph / 28-30deg leaves the yard 60% of the time,
# 88-90mph / 10-12deg never does.
rng = np.random.default_rng(0)
hot = pd.DataFrame({"launch_speed":101.0,"launch_angle":29.0,"type":"X",
                    "events":np.where(rng.random(200)<0.6,"home_run","field_out")})
cold = pd.DataFrame({"launch_speed":89.0,"launch_angle":11.0,"type":"X","events":"field_out"} ,index=range(200)).reset_index(drop=True)
league = pd.concat([hot,cold],ignore_index=True)
assert precompute.build_xhr_table(league)

sys.path.insert(0,"app")
import engines.statcast_engine as se
se._DATA_DIR = tmp
from engines.statcast_engine import compute_xhr

# A hitter with 10 of the hot trajectories who got ZERO homers — unlucky.
unlucky = pd.DataFrame({"launch_speed":101.0,"launch_angle":29.0,"type":"X","events":"field_out"},index=range(10)).reset_index(drop=True)
xhr, actual = compute_xhr(unlucky)
assert actual == 0, actual
assert 5.0 <= xhr <= 7.0, xhr
print(f"PASS: unlucky bat — xHR {xhr} vs {actual} actual, gap {xhr-actual:+.1f} (regression signal)")

# Same 10 trajectories, all left the yard — lucky.
lucky = unlucky.copy(); lucky["events"]="home_run"
xhr2, actual2 = compute_xhr(lucky)
assert actual2 == 10 and xhr2 == xhr
print(f"PASS: lucky bat — xHR {xhr2} vs {actual2} actual, gap {xhr2-actual2:+.1f}")

# Ground balls must contribute ~nothing
gb = pd.DataFrame({"launch_speed":89.0,"launch_angle":11.0,"type":"X","events":"field_out"},index=range(50)).reset_index(drop=True)
xhr3,_ = compute_xhr(gb)
assert xhr3 == 0.0, xhr3
print(f"PASS: 50 grounders produce xHR {xhr3}")

# Missing table must degrade honestly, not fabricate
se._DATA_DIR = Path("/nonexistent")
se._xhr_table.__wrapped__ if hasattr(se._xhr_table,"__wrapped__") else None
assert compute_xhr(unlucky) == (None, None)
print("PASS: no table present -> (None, None), never a fake zero")
