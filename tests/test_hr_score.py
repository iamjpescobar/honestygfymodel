"""hr_score's axis structure, its coverage floor, and its degradation.

The score has been wrong in this same shape twice. First it averaged
Barrel%, Hard-Hit% and Exit Velocity as three axes, which are three
measurements of one thing. Then the replacement fed hr_intent_pct into
an "INTENT" axis while HR window % and pull air % — two of the three
columns HRIntent is built from — already made up the LAUNCH axis, so the
same two columns entered the score twice on two different scales while
the docstring said the axes were independent.

So these tests assert the PROPERTY that keeps failing: an axis must be
able to move the score on its own, and no column may reach the score
through two doors. Case 4 is the one that goes red if the second bug is
ever reintroduced.
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

from engines.top_plays import hr_score  # noqa: E402
import engines.top_plays as tp  # noqa: E402

# NOTE the two key types. The Savant leaderboard is indexed by STRING
# player_id; the nightly HR metrics table by INT batter id (that's how
# Statcast stores it, and how precompute writes it). get_percentile and
# get_hr_metric each cast accordingly, so a caller can pass either form
# — but a test has to build both frames the way the real ones arrive.
SLUG = 1
savant = pd.DataFrame(
    {"brl_percent": [95.0], "hard_hit_percent": [95.0],
     "exit_velocity": [95.0]},
    index=pd.Index([str(SLUG)], name="player_id"))


def metrics(**cols):
    df = pd.DataFrame.from_dict({str(SLUG): cols}, orient="index")
    df.index = [SLUG]
    return df


# A fully measured bat, every axis mid-scale. Each case moves ONE axis
# off this, so the thing under test is the only thing that changed.
FULL = dict(brl_per_pa_pct=60.0, ev90_pct=60.0,
            fb95_pct_pct=60.0, clears_anywhere_pct_pct=60.0,
            hr_window_pct_pct=60.0, pull_air_pct_pct=60.0,
            bat_speed_pct=60.0, xhr_gap_rate_pct=50.0)

# --- 1. No metrics table at all -> Savant path, nothing breaks -------
#
# This path is not a nicety. The metrics reader pointed at the wrong
# directory for weeks, and the only reason the site did not go blank is
# that this fallback held. It must keep holding.
assert hr_score(SLUG, savant, hr_df=None) == 95, hr_score(SLUG, savant, hr_df=None)
print("PASS: no nightly table -> falls back to Savant percentiles, no crash")

# --- 2. Unknown player is None, never a fabricated 0 -----------------
assert hr_score(999, savant, hr_df=None) is None
print("PASS: unmeasurable batter returns None, not 0")

# --- 3. Each axis moves the score on its own -------------------------
for axis, cols in (("power", ("brl_per_pa_pct", "ev90_pct")),
                   ("convergence", ("fb95_pct_pct", "clears_anywhere_pct_pct")),
                   ("launch", ("hr_window_pct_pct", "pull_air_pct_pct")),
                   ("process", ("bat_speed_pct",))):
    lo = metrics(**{**FULL, **{c: 5.0 for c in cols}})
    hi = metrics(**{**FULL, **{c: 95.0 for c in cols}})
    a, b = hr_score(SLUG, savant, hr_df=lo), hr_score(SLUG, savant, hr_df=hi)
    assert b > a, f"{axis} axis does not move the score: {a} -> {b}"
print("PASS: power, convergence, launch and process each move the score alone")

# --- 4. NO COLUMN REACHES THE SCORE TWICE ----------------------------
#
# The regression control for the bug this batch fixed. Asserted against
# the source rather than an output because a double-count is invisible
# in any single score: it changes the WEIGHTING, and no one bat's number
# can show you a weighting.
src = open("app/engines/top_plays.py", encoding="utf-8").read()
_body = src[src.index("def hr_score"):src.index("def hit_score")]
_reads = [ln for ln in _body.splitlines()
          if "get_hr_metric(" in ln and not ln.strip().startswith("#")]
_cols = [ln.split('"')[-2] for ln in _reads]
assert _cols, "no metric reads found — the parse above is wrong, not the code"
assert "hr_intent_pct" not in _cols, (
    "hr_score reads hr_intent_pct, which is built from hr_window_pct and "
    "pull_air_pct — the launch inputs would be counted twice")
assert len(_cols) == len(set(_cols)), f"a column is read twice: {_cols}"
assert "bat_speed_pct" in _cols, "process axis lost its only independent input"
print(f"PASS: {len(_cols)} distinct metric columns, none entering twice")

# --- 5. xHR gap is a BOUNDED correction, not a weight ----------------
unlucky = metrics(**{**FULL, "xhr_gap_rate_pct": 100.0})
lucky = metrics(**{**FULL, "xhr_gap_rate_pct": 0.0})
u, l = hr_score(SLUG, savant, hr_df=unlucky), hr_score(SLUG, savant, hr_df=lucky)
assert u > l, "owed home runs should score higher than over-performed ones"
# THE BOUND IS A LITERAL HERE, NOT tp._XHR_MAX_ADJ.
#
# The first version of this line read `2 * tp._XHR_MAX_ADJ + 1`, which
# is an assertion that cannot fail: widening the constant from 8 to 30
# widened the bound with it and the case stayed green through a control
# that turned a bounded correction into the largest term in the score.
# A test that derives its expectation from the thing under test is
# measuring nothing. Same lesson as the KBO rounds.
assert (u - l) <= 17, f"xHR correction exceeded its +/-8 bound: spread {u - l}"
assert tp._XHR_MAX_ADJ == 8.0, (
    f"the correction bound moved to {tp._XHR_MAX_ADJ} — that is a real "
    f"decision, but it belongs in a commit that says so")
print(f"PASS: xHR gap corrects within bounds — unlucky {u}, lucky {l} (spread {u-l})")

# --- 6. It reads the RATE, not the count -----------------------------
#
# xhr_gap_pct ranked whole home runs, so playing time sat inside a
# correction that has nothing to do with playing time. If the name ever
# reverts, the adjustment silently stops firing — the new nightly does
# not publish that column — and every score shifts with no error.
assert "xhr_gap_rate_pct" in _cols, "conversion adjustment must read the RATE"
assert "xhr_gap_pct" not in _cols, "reverted to the count-based gap column"
count_based = metrics(**{**FULL, "xhr_gap_pct": 100.0})
assert hr_score(SLUG, savant, hr_df=count_based) == \
    hr_score(SLUG, savant, hr_df=metrics(**FULL)), \
    "the old count column still moves the score"
print("PASS: conversion reads the per-batted-ball rate, not the raw count")

# --- 7. COVERAGE FLOOR: one axis is not a score ----------------------
thin = metrics(brl_per_pa_pct=90.0, ev90_pct=90.0)     # power alone, w=0.40
assert hr_score(SLUG, savant, hr_df=thin) == 95, (
    "an under-covered bat should fall back to the complete Savant path")
# ...and with no Savant sample either, nothing. Never a number built on
# a single measurement.
assert hr_score(SLUG, savant.iloc[0:0], hr_df=thin) is None, (
    "under-covered with no fallback must be None, not a one-axis score")
print("PASS: coverage floor — one axis falls back, and scores nothing with no fallback")

# --- 8. A MISSING axis above the floor is still not a zero -----------
missing_process = metrics(**{k: v for k, v in FULL.items() if k != "bat_speed_pct"})
assert abs(hr_score(SLUG, savant, hr_df=missing_process) - 60) <= 1, (
    "a missing axis dragged the score down like a zero")
print("PASS: a measurable-but-incomplete bat renormalises, it is not penalised")

# --- 9. Score stays in range -----------------------------------------
for df in (unlucky, lucky, thin, missing_process, metrics(**FULL)):
    s = hr_score(SLUG, savant, hr_df=df)
    assert s is None or 0 <= s <= 100, s
print("PASS: score stays within 0-100 across every input shape")
