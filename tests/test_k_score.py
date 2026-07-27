"""Guards the Savant percentile orientation.

Savant publishes every percentile as a percentile of GOODNESS: 100 is
best in the league, even for stats where a low raw value is the good
outcome (whiff%, K%, chase%). Reading those straight through inverted
both K Score and the xBH K penalty and put Luis Arraez at the top of
the Strikeout Targets board. These tests fail if that ever comes back.
"""
import sys, types
import pandas as pd
st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
pb.statcast_batter_percentile_ranks = lambda *a, **k: None
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

from engines.top_plays import k_score
from engines.xbh_engine import xbh_skill

ARRAEZ, JUDGE = "100001", "100002"
# Real-world shape: Arraez whiffs least in the league (~99th pct of
# goodness); Judge whiffs more than ~90% of it (10th pct).
savant = pd.DataFrame(
    {"whiff_percent": [99.0, 10.0], "k_percent": [99.0, 12.0],
     "xslg": [30.0, 99.0], "brl_percent": [5.0, 100.0],
     "hard_hit_percent": [20.0, 99.0], "exit_velocity": [25.0, 99.0]},
    index=pd.Index([ARRAEZ, JUDGE], name="player_id"),
)

a, j = k_score(ARRAEZ, savant), k_score(JUDGE, savant)
assert a == 1, f"Arraez K Score should be ~1, got {a}"
assert j == 90, f"Judge K Score should be ~90, got {j}"
assert a < j, "the league's best contact hitter outranked its biggest whiffer"
print(f"PASS: K Score — Arraez {a}, Judge {j} (higher = more strikeout-prone)")

# The board takes the TOP 5 by K Score. Arraez must not be near it.
board = sorted([("Arraez", a), ("Judge", j)], key=lambda r: -r[1])
assert board[0][0] == "Judge", board
print(f"PASS: Strikeout Targets ranks {board[0][0]} first, not {board[-1][0]}")

# The "elevated strikeout risk" flag fires at >= 70 in two views.
assert a < 70 and j >= 70
print("PASS: risk flag (>=70) fires on Judge and not on Arraez")

# xBH engine: elite contact must be a bonus, not a penalty.
_, pa = xbh_skill(ARRAEZ, savant)
_, pj = xbh_skill(JUDGE, savant)
assert pa["_k_adj"] > 0, f"contact hitter penalized: {pa['_k_adj']}"
assert pj["_k_adj"] < 0, f"high-K hitter rewarded: {pj['_k_adj']}"
print(f"PASS: xBH K adjustment — Arraez {pa['_k_adj']:+}, Judge {pj['_k_adj']:+}")

assert k_score("999999", savant) is None
print("PASS: unknown player returns None, not a fabricated 0")
