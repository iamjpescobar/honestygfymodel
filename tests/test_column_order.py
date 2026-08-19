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
# Brl/PA and Clears% are promoted into the head by name, so the
# weight-order check covers the four that remain in the tail. The two
# promoted ones are pinned by _HEAD instead.
W = {
    "EV90": _num("_W_POWER") * 0.30,
    "FB95%": _num("_W_CONVERGE") * 0.60,
    "HRWindow%": _num("_W_LAUNCH") * 0.50,
    "PullAir%": _num("_W_LAUNCH") * 0.50,
}
_ALL_W = dict(W, **{"Brl/PA": _num("_W_POWER") * 0.70,
                    "Clears%": _num("_W_CONVERGE") * 0.40})
assert abs(sum(_ALL_W.values()) + _num("_W_PROCESS") - 1.0) < 1e-9, (
    f"the axis weights no longer sum to 1: {_ALL_W}")
print("PASS: effective weights read from top_plays and sum to 1")

# --- 2. SCORED INPUTS ARE ORDERED HEAVIEST FIRST ---------------------
# The whole tuple, not up to the first blank line — the list is grouped
# into commented tiers now, so a blank line lands inside it.
_blk = gc[gc.index("_COL_ORDER = ("):]
_blk = _blk[:_blk.index("\n                    )")]
_pos = {k: _blk.rindex(f'"{k}"') for k in W}
_by_order = sorted(W, key=lambda k: _pos[k])
_by_weight = sorted(W, key=lambda k: -W[k])
assert _by_order == _by_weight, (
    f"scored inputs are not in weight order.\n"
    f"  on screen: {_by_order}\n"
    f"  by weight: {_by_weight}")
print(f"PASS: scored inputs run heaviest first — {' > '.join(_by_weight)}")

# --- 3. THE OWNER'S READING ORDER IS THE HEAD ------------------------
#
# THIS CASE CHANGED, DELIBERATELY. It used to assert Brl/PA preceded
# every outcome column, which was right when the whole order came from
# the weights. The owner then gave an explicit head — identity, the
# verdicts, the slash line, contact quality — and Brl/PA now sits behind
# BA / xwOBA / xSLG / ISO on purpose. That is how a baseball person
# scans a row, and this table is read by a person every night.
#
# The trade is real and worth failing on if it drifts silently: pinned
# here so the head cannot be quietly rearranged back.
_HEAD = ["HR Edge", "HR Score", "Hit Score", "SLAM",
         # Cross-board standing sits with the verdicts because it IS a
         # verdict — one made on another page. "HR13 · H4" means 13th on
         # HR Edge and 4th on Daily 13, so a bat the whole site likes is
         # visible without opening three tabs.
         "Boards",
         # Form beside its own MAGNITUDE. The percentile says he is
         # hotter than 96 percent of the league; the delta says by how
         # much. 96% with +1.7 mph is a real move and 96% with +0.2 is a
         # technicality, and nobody can separate those with twenty
         # columns in between. Only dEV rides along — measured band
         # +/-7.3% against dHH%'s +/-48%, so it is the one that means
         # something at a glance.
         # Career vs tonight's starter, with the other verdicts. It is a
         # history rather than a rate, and it is the only column on the
         # table about THIS pitcher specifically.
         "BvP",
         "Form", "\u0394EV",
         # THE THREE DENOMINATORS, widening left to right. They were
         # buried with the volume stats, and PA was worse than buried:
         # _COL_ORDER named it but _stat_row never emitted the key, so
         # _ordered's membership filter dropped it and the column this
         # test has been pinning never actually rendered. A .300 ISO on
         # 65 PA and on 543 PA are not the same claim.
         #
         # All three, not just PA, because PA is the WRONG denominator
         # for most of this table: Brl%, HH%, FB%, GB%, LD%, SweetSpot%,
         # HRWindow%, PullAir%, FB95% and Clears% are per ball in play,
         # and SwStr% is per pitch.
         "Pitches", "PA", "BIP",
         # ISO first (SLG minus BA — power with singles removed), BA
         # last (a hitter can bat .320 entirely on singles). ISO beside
         # xSLG on purpose: the gap is the luck still owed.
         "ISO", "xSLG", "xwOBA", "BA",
         # The two least redundant power inputs. Brl/PA is 28% of HR
         # Score; Clears% has a league median of 0.00, so it is the one
         # column able to disagree with everything else.
         "Brl/PA", "Clears%",
         # Cashed against owed, read while deciding if the power above
         # is real.
         "HR", "NearHR",
         # Contact quality, as given.
         "Brl%", "HH%", "FB%", "GB%", "LD%", "AvgEV", "PullBrl%"]
# GameCard writes the delta columns as the escape \\u0394EV, so the
# source text carries the escape and not the character. Normalise both
# sides rather than comparing a decoded name against a literal one — a
# test that fails on an encoding difference teaches people to ignore it.
def _norm(name):
    return name.encode().decode("unicode_escape")


_got = [_norm(c) for c in re.findall(r'"([^"]+)"', _blk)[:len(_HEAD)]]
assert _got == _HEAD, f"the given reading order changed:\n  {_got}\n  {_HEAD}"
print(f"PASS: the head is the owner's given order ({len(_HEAD)} columns)")

# Brl/PA leads every redundant or descriptive column, wherever it sits.
for lighter in ("Brl%", "HH%", "HR", "AvgDist", "300+", "L5 PA/G", "HRThreat"):
    if f'"{lighter}"' in _blk:
        assert _blk.index('"Brl/PA"') < _blk.index(f'"{lighter}"'), (
            f"{lighter} is ahead of Brl/PA, which is 28% of the score")
# And Clears% precedes the contact run it was pulled ahead of.
for lighter in ("Brl%", "HH%", "FB%", "AvgEV"):
    assert _blk.index('"Clears%"') < _blk.index(f'"{lighter}"'), (
        f"{lighter} is ahead of Clears%, the one column nothing else "
        f"on this table duplicates")
print("PASS: Brl/PA and Clears% lead the contact run")

# --- 3b. THE PAIRS THAT DO THE WORK ----------------------------------
#
# ADJACENCY IS THE POINT OF THIS ORDER. Two columns side by side are
# read as a pair whether or not that was intended, so each of these
# neighbours qualifies the column before it. Separate them and the
# question each pair answers stops being askable at a glance.
for _a, _b, _why in (
        ("HR Edge", "HR Score",
         "the GAP is the read — close means the hitter is the pick, Edge "
         "far above Score means the SPOT is, and a spot-driven bat "
         "evaporates on a lineup change"),
        ("Form", "\u0394EV",
         "the percentile ranks, the delta SIZES it — 96% with +1.7 is a "
         "real move and 96% with +0.2 is a technicality"),
        ("ISO", "xSLG",
         "actual against expected power — the gap is the luck still owed"),
        ("Brl/PA", "Clears%",
         "the two least redundant power inputs, read together"),
):
    _sa = _a.encode("unicode_escape").decode()
    _sb = _b.encode("unicode_escape").decode()
    _ia, _ib = _blk.index(f'"{_sa}"'), _blk.index(f'"{_sb}"')
    assert 0 < _ib - _ia < 260, f"{_a} and {_b} were separated: {_why}"
print("PASS: the four checking pairs are still adjacent")

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
# Ord before Bats: the slot is what you scan for when you already know
# the lineup; the hand is the second check.
assert '_ident = ["Player", "Ord", "Bats"]' in gc, (
    "identity order changed — Player / Ord / Bats was chosen deliberately")
print("PASS: Player / Ord / Bats always lead")

# --- 7. THE ORDER IS APPLIED, NOT JUST DEFINED -----------------------
assert "display_df = display_df[" in gc and "_ordered(list(display_df.columns))" in gc, (
    "_COL_ORDER is defined but never applied to the frame")
print("PASS: the order is applied to the rendered frame")
