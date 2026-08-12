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
