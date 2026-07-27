"""hr_score's four-axis structure and its graceful degradation.

The old score averaged Barrel%, Hard-Hit% and Exit Velocity percentiles
with equal weight — three measurements of one underlying thing. These
tests assert that power is now ONE axis, that the launch/intent axes can
actually move the score independently of power, and that everything
still works when the nightly metrics table is missing.
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

from engines.top_plays import hr_score

# NOTE the two key types. The Savant leaderboard is indexed by STRING
# player_id; the nightly HR metrics table by INT batter id (that's how
# Statcast stores it, and how precompute writes it). get_percentile and
# get_hr_metric each cast accordingly, so a caller can pass either form
# — but a test has to build both frames the way the real ones arrive.
SLUG, SWING = 1, 2
savant = pd.DataFrame(
    {"brl_percent": [95.0, 50.0], "hard_hit_percent": [95.0, 50.0],
     "exit_velocity": [95.0, 50.0]},
    index=pd.Index([str(SLUG), str(SWING)], name="player_id"))

def metrics(**rows):
    return pd.DataFrame.from_dict(rows, orient="index")

# --- 1. No metrics table at all -> old Savant path, nothing breaks ---
assert hr_score(SLUG, savant, hr_df=None) == 95, hr_score(SLUG, savant, hr_df=None)
print("PASS: no nightly table -> falls back to Savant percentiles, no crash")

# --- 2. Unknown player is None, never a fabricated 0 ---
assert hr_score(999, savant, hr_df=None) is None
print("PASS: unmeasurable batter returns None, not 0")

# --- 3. Launch axis moves the score with power held IDENTICAL ---
flat = metrics(**{str(SLUG): dict(brl_per_pa_pct=80.0, ev90_pct=80.0,
                                  hr_window_pct_pct=10.0, pull_air_pct_pct=10.0,
                                  hr_intent_pct=50.0, xhr_gap_pct=50.0)})
lofty = metrics(**{str(SLUG): dict(brl_per_pa_pct=80.0, ev90_pct=80.0,
                                   hr_window_pct_pct=95.0, pull_air_pct_pct=95.0,
                                   hr_intent_pct=50.0, xhr_gap_pct=50.0)})
flat.index = lofty.index = [SLUG]
a, b = hr_score(SLUG, savant, hr_df=flat), hr_score(SLUG, savant, hr_df=lofty)
assert b > a + 15, f"launch axis barely moved the score: {a} -> {b}"
print(f"PASS: same power, different swing plane -> {a} vs {b} (launch is independent)")

# --- 4. xHR gap is a BOUNDED correction, not a weight ---
base = dict(brl_per_pa_pct=60.0, ev90_pct=60.0, hr_window_pct_pct=60.0,
            pull_air_pct_pct=60.0, hr_intent_pct=60.0)
unlucky = metrics(**{str(SLUG): {**base, "xhr_gap_pct": 100.0}}); unlucky.index=[SLUG]
lucky   = metrics(**{str(SLUG): {**base, "xhr_gap_pct": 0.0}});   lucky.index=[SLUG]
u, l = hr_score(SLUG, savant, hr_df=unlucky), hr_score(SLUG, savant, hr_df=lucky)
assert u > l, "owed home runs should score higher than over-performed ones"
assert (u - l) <= 17, f"xHR correction exceeded its +/-8 bound: spread {u-l}"
print(f"PASS: xHR gap corrects within bounds — unlucky {u}, lucky {l} (spread {u-l})")

# --- 5. Partial data renormalises instead of scoring a missing axis 0 ---
partial = metrics(**{str(SLUG): dict(brl_per_pa_pct=90.0, ev90_pct=90.0)})
partial.index = [SLUG]
sc = hr_score(SLUG, savant, hr_df=partial)
assert sc >= 85, f"missing axes dragged the score down like zeros: {sc}"
print(f"PASS: only power measurable -> {sc}, weights renormalised (not treated as 0)")

# --- 6. Score stays in range ---
for df in (flat, lofty, unlucky, lucky, partial):
    s = hr_score(SLUG, savant, hr_df=df)
    assert 0 <= s <= 100, s
print("PASS: score stays within 0-100 across every input shape")
