"""Context (park + temperature) inside edge_components.

Park belongs in the MATCHUP layer, not in HR Score: the xHR grid behind
the skill number pools all 30 parks so a hitter's rating doesn't change
when he travels. These assert the wiring is additive, bounded, backwards
compatible, and that switch hitters get the right side.
"""
import re, sys, types, tempfile
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
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))
sys.path.insert(0, "app")

import engines.edge as edge
import engines.hr_context as ctx

# Neutral matchup so only context moves the number.
edge.bvp_component = lambda b, p: (0, None)
edge.zone_fit_component = lambda b, p: (0, None)

tmp = Path(tempfile.mkdtemp())
pd.DataFrame({"park": ["NYY", "NYY"], "hand": ["L", "R"],
              "hr_index": [150.0, 60.0], "count": [500, 500]}
             ).to_parquet(tmp / "park_hr_factors.parquet", index=False)
ctx._PARK_PATH = tmp / "park_hr_factors.parquet"

base = 50
plain = edge.edge_components(1, 2, base, 0, None)
assert plain["edge"] == base, plain
assert plain["ctx_adj"] == 0 and plain["ctx_notes"] == []
print("PASS: existing callers unchanged — no context args, no adjustment")

lhb = edge.edge_components(1, 2, base, 0, None, home_team="NYY", bats="L")
rhb = edge.edge_components(1, 2, base, 0, None, home_team="NYY", bats="R")
assert lhb["edge"] > base > rhb["edge"], (lhb["edge"], rhb["edge"])
print(f"PASS: same park, opposite hands — LHB {lhb['edge']}, RHB {rhb['edge']} "
      f"(base {base})")

sw = edge.edge_components(1, 2, base, 0, None, home_team="NYY", bats="S")
assert sw["ctx_adj"] == 0, "an unresolved switch hitter got a park adjustment"
print("PASS: raw 'S' yields no park adjustment — caller must resolve the hand")

hot = edge.edge_components(1, 2, base, 0, None, temp="95 degrees")
cold = edge.edge_components(1, 2, base, 0, None, temp="40 degrees")
assert hot["edge"] > base > cold["edge"]
assert edge.edge_components(1, 2, base, 0, None, temp="95 degrees",
                            roof_closed=True)["ctx_adj"] == 0
print(f"PASS: temperature moves edge ({hot['edge']} hot / {cold['edge']} cold); "
      f"closed roof ignores it")

both = edge.edge_components(1, 2, base, 0, None, home_team="NYY", bats="L",
                            temp="95 degrees")
assert abs(both["ctx_adj"] - (lhb["ctx_adj"] + hot["ctx_adj"])) < 0.01
assert len(both["ctx_notes"]) == 2
print(f"PASS: park + temp combine additively ({both['ctx_adj']:+}) with 2 notes")

# Bounded, and never rescues an unratable bat.
assert 0 <= both["edge"] <= 100
extreme = edge.edge_components(1, 2, 99, 0, None, home_team="NYY", bats="L",
                               temp="110 degrees")
assert extreme["edge"] <= 100
assert edge.edge_components(1, 2, None, 0, None, home_team="NYY",
                            bats="L")["edge"] is None
print("PASS: edge stays 0-100 and stays None when skill is unrateable")

# The call site must resolve switch hitters, and must not call the
# out-of-scope _side_for() helper.
gc = open("app/views/GameCard.py").read()
block = gc[gc.index("pen_context(_pitcher_team, pitcher_id)"):]
block = block[:block.index("_r[\"iso_vs_hand\"]")]
assert "_side_for(_r)" not in block, "_side_for is defined later — NameError"
assert '_b == "S"' in block, "call site doesn't resolve switch hitters"
assert "team_abbr(game[\"home\"])" in block, "park key must be the team abbreviation"
print("PASS: call site resolves handedness inline and abbreviates the park key")

# --- wind through the full chain --------------------------------------
# Wrigley faces NE, so a SW wind blows straight out; the identical wind
# at Comerica (SSE) blows in. If this sign ever flips, wind is worse
# than useless.
import engines.wind_engine as we
w_out = edge.edge_components(1, 2, base, 0, None, home_team="CHC", wind="SW 15 mph")
w_in = edge.edge_components(1, 2, base, 0, None, home_team="DET", wind="SW 15 mph")
assert w_out["edge"] > base > w_in["edge"], (w_out["edge"], w_in["edge"])
print(f"PASS: same SW wind — Wrigley {w_out['edge']} vs Comerica {w_in['edge']} "
      f"(base {base})")

assert edge.edge_components(1, 2, base, 0, None, home_team="CHC",
                            wind="SW 15 mph", roof_closed=True)["ctx_adj"] == 0
print("PASS: closed roof ignores wind")

# Wind must stack with park and temperature, and be explained.
stacked = edge.edge_components(1, 2, base, 0, None, home_team="NYY", bats="L",
                               temp="90 degrees", wind="SW 12 mph")
assert len(stacked["ctx_notes"]) >= 2, stacked["ctx_notes"]
print(f"PASS: park + temp + wind combine with {len(stacked['ctx_notes'])} "
      f"explained components")

# Callers that never pass wind must be unaffected.
assert edge.edge_components(1, 2, base, 0, None, home_team="CHC")["ctx_adj"] == \
       edge.edge_components(1, 2, base, 0, None, home_team="CHC", wind=None)["ctx_adj"]
print("PASS: omitting wind changes nothing for existing callers")

# Both call sites must actually pass it, or the engine is dead code.
gc = open("app/views/GameCard.py").read()
hb = open("app/engines/hr_edge_board.py").read()
assert "wind=_wind" in gc, "GameCard doesn't pass wind to edge_components"
assert 'game.get("weather_wind")' in gc, "GameCard doesn't read the wind field"
assert "wind=wind" in hb, "hr_edge_board doesn't pass wind"
assert 'game.get("weather_wind")' in hb, "hr_edge_board doesn't read the wind field"
print("PASS: both call sites read and pass the wind string")
