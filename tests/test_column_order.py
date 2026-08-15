"""Lineup column order, derived from the model's own weights.

THE PROBLEM. Order was whatever _stat_row happened to insert first. Six
volume and distance columns went in after Form and pushed Brl/PA — THE
SINGLE HEAVIEST INPUT IN HR SCORE — out past ten others, so a reader
scanning left to right met batted-ball distance before the thing the
score is mostly made of.

THE NON-ARBITRARY ANSWER. engines/top_plays multiplies out to:

    Brl/PA     28%   POWER    .40 x .70
    FB95%      18%   CONVERGE .30 x .60
    EV90       12%   POWER    .40 x .30
    Clears%    12%   CONVERGE .30 x .40
    HRWindow%  11%   LAUNCH   .22 x .50
    PullAir%   11%   LAUNCH   .22 x .50

Scored inputs lead, heaviest first. A reader going left to right is then
reading the score's own reasoning in its own order.

AND IT MOVES WITH THE WEIGHTS. When the research log has enough graded
outcomes to refit them, this order follows — which is the whole reason
it is derived from them rather than typed out by preference.
"""
import re
import sys, types

sys.path.insert(0, "app")
_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = _st
for _m in ("pybaseball",):
    sys.modules.setdefault(_m, types.ModuleType(_m))

gc = open("app/views/GameCard.py", encoding="utf-8").read()
tp = open("app/engines/top_plays.py", encoding="utf-8").read()


def _num(name):
    return float(re.search(rf"^{name} = ([\d.]+)", tp, re.M).group(1))


# --- 1. THE WEIGHTS THE ORDER CLAIMS TO FOLLOW -----------------------
W = {
    "Brl/PA": _num("_W_POWER") * 0.70,
    "EV90": _num("_W_POWER") * 0.30,
    "FB95%": _num("_W_CONVERGE") * 0.60,
    "Clears%": _num("_W_CONVERGE") * 0.40,
    "HRWindow%": _num("_W_LAUNCH") * 0.50,
    "PullAir%": _num("_W_LAUNCH") * 0.50,
}
assert abs(sum(W.values()) + _num("_W_PROCESS") - 1.0) < 1e-9, (
    f"the axis weights no longer sum to 1: {W}")
print("PASS: effective weights read from top_plays and sum to 1")

# --- 2. SCORED INPUTS ARE ORDERED HEAVIEST FIRST ---------------------
_blk = gc[gc.index("_COL_ORDER = ("):]
_blk = _blk[:_blk.index("\n\n")]
_pos = {k: _blk.index(f'"{k}"') for k in W}
_by_order = sorted(W, key=lambda k: _pos[k])
_by_weight = sorted(W, key=lambda k: -W[k])
assert _by_order == _by_weight, (
    f"scored inputs are not in weight order.\n"
    f"  on screen: {_by_order}\n"
    f"  by weight: {_by_weight}")
print(f"PASS: scored inputs run heaviest first — {' > '.join(_by_weight)}")

# --- 3. THE HEAVIEST INPUT LEADS THE STATS ---------------------------
#
# Brl/PA is 28% of HR Score on its own. It was sitting past ten other
# columns; whatever else moves, it does not go back there.
for lighter in ("HR", "ISO", "BA", "AvgDist", "300+", "L5 PA/G", "AvgEV"):
    if f'"{lighter}"' in _blk:
        assert _blk.index('"Brl/PA"') < _blk.index(f'"{lighter}"'), (
            f"{lighter} is ahead of Brl/PA, which is 28% of the score")
print("PASS: Brl/PA precedes every descriptive and outcome column")

# --- 4. HR AND NEARHR STAY ADJACENT ----------------------------------
#
# The PAIR is the read: 3 home runs against 12 near misses is a
# different hitter from 12 against 3, and splitting them across the
# table destroys the comparison that makes NearHR worth having.
_hr, _near = _blk.index('"HR"'), _blk.index('"NearHR"')
assert 0 < _near - _hr < 20, "HR and NearHR were separated"
print("PASS: HR and NearHR render side by side")

# --- 5. NOTHING IS SILENTLY DROPPED ----------------------------------
#
# A column missing from _COL_ORDER must still RENDER. Dropping one
# quietly is how a stat vanishes from the site and nobody notices for a
# month.
assert "rest = [c for c in cols if c not in _COL_ORDER" in gc, (
    "unknown columns are no longer appended — one missing from the list "
    "would disappear from the table entirely")
assert "return _ident + known + rest" in gc
print("PASS: a column absent from the order still renders, at the end")

# --- 6. IDENTITY COLUMNS LEAD ----------------------------------------
#
# Player/Bats/Ord tell you whose row you are reading; losing them while
# scrolling sideways was the original complaint about this table.
assert 'return _ident + known + rest' in gc
assert '_ident = ["Player", "Bats", "Ord"]' in gc
print("PASS: Player / Bats / Ord always lead")

# --- 7. THE ORDER IS APPLIED, NOT JUST DEFINED -----------------------
assert "display_df = display_df[" in gc and "_ordered(list(display_df.columns))" in gc, (
    "_COL_ORDER is defined but never applied to the frame")
print("PASS: the order is applied to the rendered frame")
