"""A hit rate is not a profit. The two routinely disagree.

65% sounds excellent and loses money all season at -200, which needs
66.7% just to break even. 30% sounds terrible and prints at +400, which
needs 20%. A board that reports only its hit rate is telling someone the
less important half of the story while they size real bets off it.

These tests cover the arithmetic and, more importantly, the refusals:
never assume a price, never count a DNP as a loss.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

st = types.ModuleType("streamlit")
st.session_state = {}
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
sys.path.insert(0, str(ROOT / "app"))

from engines.calibration import (  # noqa: E402
    american_to_decimal, breakeven_pct, _profit_summary,
)

# --- 1. odds conversion ----------------------------------------------
assert abs(american_to_decimal(-200) - 1.5) < 1e-9, "risk 200 to win 100 = 1.5x"
assert abs(american_to_decimal(+200) - 3.0) < 1e-9, "risk 100 to win 200 = 3.0x"
assert abs(american_to_decimal(-110) - 1.909) < 0.001
assert abs(american_to_decimal(+100) - 2.0) < 1e-9
for bad in (None, "", "abc", 0):
    assert american_to_decimal(bad) is None, f"{bad!r} must not convert"
print("PASS: American odds convert correctly, junk returns None")

# --- 2. break-even is the number that decides everything -------------
assert breakeven_pct(-200) == 66.7, "a -200 price needs 66.7% to break even"
assert breakeven_pct(+100) == 50.0
assert breakeven_pct(+400) == 20.0
assert breakeven_pct(-110) == 52.4
print("PASS: break-even percentages are correct")

# The headline case: the same hit rate, opposite outcomes.
_rate = 0.652
_lose = (_rate * american_to_decimal(-200) - 1) * 100
_win = (_rate * american_to_decimal(-150) - 1) * 100
assert _lose < 0 < _win, (
    f"65.2% must LOSE at -200 ({_lose:.1f}%) and WIN at -150 ({_win:.1f}%). If "
    f"this ever stops being true the whole point of the feature is gone")
print(f"PASS: 65.2% loses at -200 ({_lose:+.1f}%) and profits at -150 ({_win:+.1f}%)")

# --- 3. profit summary arithmetic ------------------------------------
picks = [
    {"result": "hit", "odds": -200},    # +0.50
    {"result": "hit", "odds": -200},    # +0.50
    {"result": "miss", "odds": -200},   # -1.00
]
r = _profit_summary(picks)
assert r["priced"] == 3 and r["wins"] == 2
assert abs(r["units"]) < 1e-9, (
    f"2 wins and 1 loss at -200 is exactly break-even, got {r['units']}")
assert r["hit_rate"] == 66.7 and r["breakeven"] == 66.7
print("PASS: profit arithmetic is correct (66.7% at -200 = break-even)")

# --- 4. unpriced picks are EXCLUDED, never assumed -------------------
mixed = [
    {"result": "hit", "odds": -150},
    {"result": "miss", "odds": None},
    {"result": "hit"},
]
r = _profit_summary(mixed)
assert r["priced"] == 1, (
    f"counted {r['priced']} priced picks out of 1. Assuming a price for the "
    f"others would manufacture a profit figure out of nothing — the exact "
    f"kind of invented number this whole system exists to avoid")
print("PASS: picks without a price are excluded, not assumed even money")

# --- 5. DNP is a returned stake, not a loss --------------------------
r = _profit_summary([{"result": "dnp", "odds": -150},
                     {"result": "hit", "odds": -150}])
assert r["priced"] == 1 and r["wins"] == 1, (
    "a scratched player was counted as a bet. A DNP is a void, not a loss — "
    "counting it would understate every board's real performance")
print("PASS: DNPs are excluded from profit, not scored as losses")

# --- 6. nothing priced -> no fabricated figures ----------------------
r = _profit_summary([{"result": "hit"}, {"result": "miss"}])
assert r == {"priced": 0}, (
    f"got {r} with no priced picks. Returning zeros here would render as "
    f"'0.00 units, 0.0% ROI', which reads as a measured break-even result "
    f"rather than an absence of data")
assert _profit_summary([]) == {"priced": 0}
print("PASS: with no prices, nothing is reported rather than a fake zero")

# --- 7. underdogs: low hit rate can still print ----------------------
dogs = [{"result": "hit", "odds": 400}] + [{"result": "miss", "odds": 400}] * 3
r = _profit_summary(dogs)
assert r["hit_rate"] == 25.0 and r["units"] > 0, (
    f"25% at +400 must be PROFITABLE ({r['units']} units). If a board's hit "
    f"rate alone drove the verdict, this winning board would read as a "
    f"disaster")
print(f"PASS: 25% at +400 is correctly profitable ({r['units']:+.2f} units)")


# ----------------------------------------------------------------------
# Entered odds must SURVIVE being saved.
#
# _save() drops any day the published record already holds with an equal
# grade count — correct for keeping the local log from accumulating the
# whole published history, but it silently threw away every hand-entered
# price: set_odds returned True, the number vanished on the next read,
# and the profit columns stayed empty with nothing reporting an error.
# The pipeline never writes odds, so local is the ONLY place they live.
# ----------------------------------------------------------------------
import json as _json
import pathlib as _pathlib
import tempfile as _tempfile

from engines import calibration as _cal  # noqa: E402

_tmp = _pathlib.Path(_tempfile.mkdtemp())
_cal._LOG_PATH = _tmp / "local.json"
_cal._published_path = lambda: _tmp / "pub.json"
(_tmp / "pub.json").write_text(_json.dumps({
    "daily13": {"2026-07-30": {"picks": [
        {"id": "1", "name": "A", "result": "hit"},
        {"id": "2", "name": "B", "result": "miss"},
        {"id": "3", "name": "C", "result": "hit"}], "graded": True}}}))

for _pid, _o in (("1", -150), ("2", -150), ("3", -150)):
    assert _cal.set_odds("daily13", "2026-07-30", _pid, _o), f"set_odds failed for {_pid}"

_picks = _cal._load()["daily13"]["2026-07-30"]["picks"]
assert [p.get("odds") for p in _picks] == [-150, -150, -150], (
    f"odds did not persist: {[p.get('odds') for p in _picks]}. A price that "
    f"reports saved and then vanishes is worse than no feature at all — the "
    f"profit columns stay blank and nothing says why")
print("PASS: hand-entered odds survive a save/load round trip")

_r = _profit_summary(_picks)
assert _r["priced"] == 3 and _r["units"] > 0 and _r["breakeven"] == 60.0
print(f"PASS: profit computes from stored odds ({_r['units']:+.2f} units)")

assert [p["result"] for p in _picks] == ["hit", "miss", "hit"], (
    "editing odds changed a grade — pricing a pick must never reopen or "
    "alter its result")
print("PASS: editing odds never touches a graded result")
