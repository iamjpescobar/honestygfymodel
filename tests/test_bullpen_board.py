"""The bullpen board must aggregate honestly and never invent a split.

This page exists because a single pooled bullpen HR/9 cannot answer the
question that matters late in a game: what does THIS reliever allow to
THIS hand of hitter. Two things have to hold for it to be worth trusting.

A four-inning mop-up man must not move the pen line the way the setup man
does — a plain mean across relievers lets him, and produces a number
that's wrong by a factor of two.

And a reliever with almost no innings against a hand must report NOTHING,
not a number. A 2-inning .000 SLG allowed renders as the most dominant
arm in the pen, which is the exact opposite of the truth.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

st = types.ModuleType("streamlit")
st.session_state = {}
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, str(ROOT / "app"))

from engines.bullpen_board import (  # noqa: E402
    pen_totals, worst_matchup, PEN_STATS, MIN_SPLIT_IP,
)

PEN = [
    {"name": "Setup",  "throws": "R", "overall": {"IP": 40.0, "HR/9": 1.0, "SLG": 0.380},
     "vs_rhb": {"IP": 26.0, "SLG": 0.350}, "vs_lhb": {"IP": 14.0, "SLG": 0.430}},
    {"name": "Closer", "throws": "R", "overall": {"IP": 38.0, "HR/9": 0.8, "SLG": 0.310},
     "vs_rhb": {"IP": 25.0, "SLG": 0.290}, "vs_lhb": {"IP": 13.0, "SLG": 0.350}},
    {"name": "Lefty",  "throws": "L", "overall": {"IP": 22.0, "HR/9": 1.4, "SLG": 0.450},
     "vs_rhb": {"IP": 9.0, "SLG": 0.520}, "vs_lhb": {"IP": 13.0, "SLG": 0.360}},
    {"name": "Mop-up", "throws": "R", "overall": {"IP": 4.0, "HR/9": 9.0, "SLG": 0.900},
     "vs_rhb": {}, "vs_lhb": {}},
]

# --- 1. innings weighting, not a plain mean --------------------------
tot = pen_totals(PEN)
plain = sum(r["overall"]["HR/9"] for r in PEN) / len(PEN)
assert tot["HR/9"] < plain / 2, (
    f"pen HR/9 came out {tot['HR/9']} against a plain mean of {plain:.2f}. A "
    f"four-inning mop-up man is dominating the pen line — weight by innings, "
    f"or the number describes an arm nobody uses in a close game")
assert 1.0 < tot["HR/9"] < 1.6, f"weighted HR/9 {tot['HR/9']} is outside a sane band"
print(f"PASS: pen line is innings-weighted ({tot['HR/9']} vs {plain:.2f} unweighted)")

# --- 2. handedness mix is measured in INNINGS, not arms --------------
assert abs(tot["lhp_ip_share"] - 22.0 / 104.0) < 0.001, (
    "LHP share must be a share of INNINGS. One lefty out of four arms is 25% "
    "by headcount but 21% by innings, and it's innings a hitter actually faces")
assert tot["lhp_arms"] == 1
print(f"PASS: LHP share measured by innings ({tot['lhp_ip_share']:.1%}), not headcount")

# --- 3. empty pen degrades, doesn't crash ----------------------------
assert pen_totals([]) == {}
assert pen_totals([{"name": "x", "throws": "R", "overall": {}}]) == {}
print("PASS: an empty or IP-less pen returns nothing rather than dividing by zero")

# --- 4. worst matchup ranks on SLUGGING ------------------------------
w = worst_matchup(PEN, "R")
assert w["name"] == "Lefty", (
    f"expected the arm with the highest SLG allowed to RHB, got {w['name']}")
w = worst_matchup(PEN, "L")
assert w["name"] == "Setup", (
    f"expected the arm with the highest SLG allowed to LHB, got {w['name']}")
print("PASS: worst matchup ranks on slugging allowed, per hand")

# The mop-up man has NO qualifying split, so despite the worst overall
# numbers he must never be named as the matchup.
assert worst_matchup(PEN, "R")["name"] != "Mop-up"
print("PASS: an arm with no qualifying split is never named as the matchup")

# No qualifying samples at all -> None, not a fabricated pick.
_bare = [{"name": "A", "throws": "R", "overall": {"IP": 10.0}, "vs_rhb": {}, "vs_lhb": {}}]
assert worst_matchup(_bare, "R") is None, (
    "with no qualifying split the honest answer is None — naming an arm "
    "anyway invents a read the data doesn't support")
print("PASS: no qualifying split yields None, not a guess")

# --- 5. the view must not fill blanks with zeros ---------------------
VIEW = (ROOT / "app" / "views" / "Bullpen_Board.py").read_text()
_code = "\n".join(l.split("#")[0] for l in VIEW.split("\n"))
assert "split.get(key)" in _code and "split.get(key, 0)" not in _code, (
    "a missing split must render as None/N-A. Defaulting to 0 shows a "
    "reliever with no sample as .000 SLG allowed — the most dominant arm on "
    "the board, and completely fictional")
print("PASS: the view renders missing splits as N/A, never as zero")

# --- 6. eligibility matches the edge module --------------------------
ENG = (ROOT / "app" / "engines" / "bullpen_board.py").read_text()
for rule, why in [
    ('p.get("active") is False', "IL and optioned arms can't pitch tonight"),
    ('get_pitcher_role(p["id"]) != "RP"', "the rotation isn't the bullpen"),
    ('p["id"] == starter_pid', "tonight's starter isn't a reliever"),
]:
    assert rule in ENG, (
        f"bullpen board is missing the {rule!r} filter — {why}. It must match "
        f"the edge module's pen exactly, or the page and the score will "
        f"disagree about who is even in the bullpen")
print("PASS: eligibility rules match the edge module's bullpen")


# ----------------------------------------------------------------------
# get_todays_games_with_weather returns a (games, error) TUPLE.
#
# This shipped broken twice in this codebase now — once as
# `df = _get_pitcher_df(pid)` and once here as
# `games = get_todays_games_with_weather()`. Binding the pair to a single
# name makes the first loop element the LIST itself, and the page dies on
# load with "'list' object has no attribute 'get'". Every other caller
# unpacks it; a new one that doesn't is a page that never renders.
# ----------------------------------------------------------------------
import re

for _v in (ROOT / "app" / "views").glob("*.py"):
    _src = _v.read_text()
    for _i, _line in enumerate(_src.split("\n"), 1):
        if "get_todays_games_with_weather(" not in _line:
            continue
        if _line.strip().startswith(("#", "from", "import")):
            continue
        # Must destructure into two names.
        assert re.search(r"\w+\s*,\s*\w+\s*=\s*get_todays_games_with_weather\(", _line), (
            f"{_v.name}:{_i} does not unpack the (games, error) tuple:\n"
            f"    {_line.strip()}\n"
            f"  Binding the pair to one name makes each 'game' the whole list, "
            f"and the page dies on load.")
print("PASS: every view unpacks the (games, error) tuple correctly")
