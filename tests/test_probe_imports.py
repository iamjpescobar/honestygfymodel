"""The probes reach into engine internals. Guard the names.

hr_floors_probe and wnba_props_probe deliberately import private
helpers — `_compute_batted_ball_metrics`, `_line_for`, `_clear_rate`,
`_floor_rate`, `_scale` — and the weight and floor constants beside
them. That is the correct design: a probe that reimplemented clear-rate
would be measuring a stat the board does not have, which is the exact
failure hr_floors_probe was written to catch and later committed itself
by carrying its own copy of the thresholds.

The cost of that design is that a rename in an engine breaks a probe
SILENTLY. Nothing imports these files, no page renders them, and the
break only surfaces the next time someone runs one by hand — which is
every few weeks, long after the commit that caused it.

So this asserts the names still resolve. It does not run the probes;
they need a data archive that is not in the repo.
"""
import sys, types

st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
sys.modules.setdefault("pybaseball", types.ModuleType("pybaseball"))
sys.path.insert(0, "app")

from engines.wnba_props import (  # noqa: E402,F401
    STATS, MIN_GP, MIN_MPG, MIN_LOG,
    _line_for, _clear_rate, _floor_rate, _scale,
    W_CONSISTENCY, W_FORM, W_MATCHUP, W_PACE,
)
print("PASS: wnba_props_probe's imports all resolve")

# The weights must still sum to 1, or the "60% of the score" claim the
# probe prints — and the guide repeats — is wrong.
_total = W_CONSISTENCY + W_FORM + W_MATCHUP + W_PACE
assert abs(_total - 1.0) < 1e-9, f"props weights sum to {_total}, not 1.0"
assert abs((W_CONSISTENCY + W_FORM) - 0.60) < 1e-9, (
    "the player-intrinsic share moved off 60% — wnba_props_probe reports "
    "that fraction to the reader and would now be misstating it")
print(f"PASS: props weights sum to 1.0, {(W_CONSISTENCY + W_FORM) * 100:.0f}% measurable without a slate")

from engines.statcast_engine import _compute_batted_ball_metrics  # noqa: E402,F401
from engines.hr_floors import FLOOR_SPECS, resolve  # noqa: E402
assert callable(_compute_batted_ball_metrics)
assert len(FLOOR_SPECS) == 9 and len(resolve(None)) == 9
print("PASS: hr_floors_probe's imports resolve, 9 floors defined")


# --- THE PAYLOAD SHAPE -----------------------------------------------
#
# players.json is keyed BY PLAYER ID, not a list. wnba_props_probe
# iterated it directly, got the id STRINGS, and died on the first
# p.get("gp") with AttributeError: 'str' object has no attribute 'get'.
#
# league_percentiles() in the same engine does the unwrap three lines
# from where it reads the same file. The probe was written without
# copying it. So this asserts the engine still owns that unwrap — if it
# ever stops, the probe's copy is the only one left and it will rot.
import inspect  # noqa: E402
from engines import wnba_props  # noqa: E402

_src = inspect.getsource(wnba_props.league_percentiles)
assert "isinstance(players, dict)" in _src, (
    "the engine stopped unwrapping the dict-keyed players.json — check "
    "whether the file shape changed, and fix wnba_props_probe to match")

_probe = open("wnba_props_probe.py", encoding="utf-8").read()
assert "list(players.values())" in _probe, (
    "wnba_props_probe iterates players.json directly again — it will "
    "crash on the id strings the moment it is run")
print("PASS: both readers unwrap the dict-keyed player payload")


# --- mlb_form_probe's imports ----------------------------------------
#
# Same exposure as the other probes: it reaches into the engine by name,
# nothing imports it, and a rename breaks it silently until someone runs
# it by hand weeks later.
from engines.statcast_engine import get_batter_profile_windowed  # noqa: E402,F401

_fp = open("mlb_form_probe.py", encoding="utf-8").read()
assert "window=\"l15\"" in _fp and "window=\"season\"" in _fp, (
    "the form probe stopped comparing two windows — it would report a "
    "deviation of zero for everyone")
for _k in ("Brl/PA", "PullAir %", "AvgEV"):
    assert _k in _fp, f"the form probe lost {_k}"
print("PASS: mlb_form_probe's imports and windows resolve")


# --- mlb_platoon_probe's imports -------------------------------------
from engines.statcast_engine import get_batter_iso_vs_hand  # noqa: E402,F401

_pp = open("mlb_platoon_probe.py", encoding="utf-8").read()
assert 'get_batter_iso_vs_hand(pid, "L")' in _pp and \
       'get_batter_iso_vs_hand(pid, "R")' in _pp, (
    "the platoon probe stopped reading both hands — a one-sided split is "
    "not a split")
assert "if iso_l is None or iso_r is None" in _pp, (
    "the probe no longer requires BOTH sides to clear the 40-AB floor; a "
    "hitter measured against one hand would be reported as having a gap")
print("PASS: mlb_platoon_probe reads both hands and requires both")
