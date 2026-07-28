"""Pitch-type HR matchup — the interaction, not the raw rate.

The naive version (a pitcher's own HR rate per pitch type) is a two-event
coin flip over ~250 sliders. These assert the implementation uses the
three large-sample quantities instead, and degrades honestly.
"""
import sys, types, tempfile
from pathlib import Path
import pandas as pd

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball"); pb.statcast = lambda *a, **k: None
sys.modules["pybaseball"] = pb
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))
sys.path.insert(0, "."); sys.path.insert(0, "app")

import precompute
import engines.pitch_matchup as pm

tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp
precompute.PITCH_TYPE_MIN_BBE = 10

# Fastballs get hit out far more often than sinkers, in this fixture.
league_rows = []
for pt, n, hrs in (("FF", 1000, 60), ("SL", 1000, 30), ("SI", 1000, 10)):
    league_rows.append(pd.DataFrame({
        "pitch_type": pt, "type": "X",
        # ~6.5% of batted balls are barrels league-wide; the build now
        # measures this per pitch type so nothing assumes a constant.
        "launch_speed_angle": ([6]*int(n*0.065) + [3]*(n-int(n*0.065))),
        "events": ["home_run"]*hrs + ["field_out"]*(n-hrs)}))
league = pd.concat(league_rows, ignore_index=True)
assert precompute.build_pitch_type_hr(league)
pm._LEAGUE_PATH = tmp / "pitch_type_hr.parquet"
print("PASS: league HR-by-pitch-type table builds from batted balls")

t = pd.read_parquet(pm._LEAGUE_PATH).set_index("pitch_type")
assert t.at["FF", "hr_rate"] > t.at["SI", "hr_rate"]
print(f"PASS: FF {t.at['FF','hr_rate']*100:.1f}% > SI {t.at['SI','hr_rate']*100:.1f}%")

# A fastball-heavy arsenal should read more homer-prone than a sinkerballer.
ff_heavy, _ = pm.pitch_matchup_adj(1, {"FF": 70.0, "SL": 30.0})
si_heavy, _ = pm.pitch_matchup_adj(1, {"SI": 70.0, "SL": 30.0})
assert ff_heavy > si_heavy, (ff_heavy, si_heavy)
print(f"PASS: fastball-heavy {ff_heavy:+} vs sinkerballer {si_heavy:+}")

for adj in (ff_heavy, si_heavy):
    assert abs(adj) <= pm.PITCH_MATCH_CAP
print(f"PASS: adjustment bounded at +/-{pm.PITCH_MATCH_CAP}")

# A hitter who crushes fastballs must add to a fastball-heavy matchup.
#
# NOTE the arsenal below is mostly sinkers. An all-fastball arsenal
# saturates the +/-8 cap on the mix term alone, so both a crusher and a
# fluke come back at exactly +8.0 and the hitter term is invisible — an
# earlier version of this test compared two capped values and reported a
# regression failure that wasn't real. A mixed arsenal leaves headroom
# for the hitter term to actually show.
ARSENAL = {"SI": 75.0, "FF": 25.0}
# league_brl is no longer passed in — it comes from the nightly table.
crusher = {"FF": {"barrels": 60, "bbe": 200}}
weak = {"FF": {"barrels": 2, "bbe": 200}}
a_crush, _ = pm.pitch_matchup_adj(1, ARSENAL, batter_vs_pitch=crusher)
a_weak, _ = pm.pitch_matchup_adj(1, ARSENAL, batter_vs_pitch=weak)
assert a_crush > a_weak, (a_crush, a_weak)
print(f"PASS: hitter term moves it — crusher {a_crush:+} vs weak {a_weak:+}")

# ...but a TINY sample must be regressed almost away.
tiny_hot = {"FF": {"barrels": 3, "bbe": 4}}
a_tiny, _ = pm.pitch_matchup_adj(1, ARSENAL, batter_vs_pitch=tiny_hot)
assert a_tiny < a_crush, "4 batted balls outweighed 200 — regression failed"
print(f"PASS: 3-for-4 on fastballs ({a_tiny:+}) stays well below a 200-BBE "
      f"crusher ({a_crush:+})")

# Unreadable / missing inputs must yield nothing, never a guess.
assert pm.pitch_matchup_adj(1, {}) == (0, None)
assert pm.pitch_matchup_adj(1, {"XX": 100.0}) == (0, None), \
    "unknown pitch types should not produce an adjustment"
print("PASS: empty or unreadable arsenal yields no adjustment")

pm._LEAGUE_PATH = Path("/nonexistent.parquet")
pm._league_pitch_hr.__dict__.pop("_cache", None)
assert pm.pitch_matchup_adj(1, {"FF": 100.0}) == (0, None)
print("PASS: missing league table degrades to zero, not a fabricated number")

# The pitcher's OWN per-pitch HR rate must never appear in the module.
src = open("app/engines/pitch_matchup.py").read()
assert "pitcher_hr_by_pitch" not in src and "pitcher_pitch_hr" not in src
assert "K_HITTER_PITCH" in src, "hitter term must be regressed"
print("PASS: pitcher's own per-pitch HR rate never used; hitter term regressed")

# --- league barrel rate is measured, not assumed ----------------------
# An earlier assertion above deliberately points _LEAGUE_PATH at a
# missing file to test degradation; restore it before reading.
pm._LEAGUE_PATH = tmp / "pitch_type_hr.parquet"
t2 = pd.read_parquet(pm._LEAGUE_PATH).set_index("pitch_type")
assert "brl_rate" in t2.columns, "league barrel rate per pitch type missing"
assert 0 < t2.at["FF", "brl_rate"] < 1
src2 = open("app/engines/pitch_matchup.py").read()
assert "0.065" not in src2, "an assumed barrel rate constant is back in the module"
print(f"PASS: league barrel rate measured per pitch type "
      f"(FF {t2.at['FF','brl_rate']*100:.1f}%), no constant in the module")

# --- the arsenal key must match what the engine actually produces -----
eng = open("app/engines/statcast_engine.py").read()
assert 'metrics["Pitch Arsenal"]' in eng
for path in ("app/engines/hr_edge_board.py", "app/views/GameCard.py"):
    src = open(path).read()
    assert '"Pitch Arsenal"' in src, f'{path} reads the wrong arsenal key'
    assert '.get("arsenal")' not in src, f'{path} still uses the guessed key'
print("PASS: both call sites read the real \"Pitch Arsenal\" key")

# --- slate board stays mix-only (perf) --------------------------------
hb = open("app/engines/hr_edge_board.py").read()
# Check the ARGUMENT, not the word — the module explains in a comment
# why it omits this, and matching prose made the assertion fail against
# correct code.
assert "batter_vs_pitch=" not in hb, \
    "slate board must not fetch per-batter pitch profiles (~270 hitters)"
assert "batter_pitch_profile" not in hb, \
    "slate board must not call the per-pitch profile helper"
gc = open("app/views/GameCard.py").read()
assert "batter_vs_pitch=" in gc, "Game Card should use the full interaction"
print("PASS: full interaction on the Game Card, mix-only on the slate board")
