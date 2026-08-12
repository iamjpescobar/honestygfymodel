"""The board's ORDERING, its per-game cap, and the floors tier.

Separate from test_hr_edge_board.py, which asserts the board spans the
slate and matches each side to the right starter. This file is about
what happens to those rows afterwards.

THREE THINGS THAT WERE WRONG IN THE SAME PLACE.

1. The board sorted on `edge` — an INTEGER clamped to 0-100, across
   ~270 bats sharing 101 possible values — with a stable sort. Ties
   resolved by the order the build loop happened to produce rows in:
   game order, away before home, lineup order. So the top of a ranked
   board was partly the schedule. Teammates tie far more often than
   strangers because they share ctx_adj EXACTLY (same park, temperature,
   wind, opposing arsenal), which is why one lineup could appear to take
   the board over.

2. The clamp erased separation exactly where the reader looks: the
   adjustments span +/-67, so a strong bat in a strong spot pins at 100
   beside one several points behind it.

3. The board never passed batting_order, so the slot term was on the
   Game Card and absent here — while the module docstring promised the
   two agreed, and while THIS is the board that gets logged.
"""
import sys, types
import pandas as pd  # noqa: F401

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache; sys.modules["streamlit"] = st
sys.path.insert(0, "app")

from engines.hr_edge_board import cap_per_game, GAME_CAP  # noqa: E402
from engines import hr_floors  # noqa: E402

SORT_KEY = lambda r: (r.get("edge_raw") if r.get("edge_raw") is not None
                      else (r.get("edge") or 0),
                      r.get("hr_score") or 0,
                      r.get("hr_threat") or 0)

# --- 1. THE CAP IS PER GAME, NOT PER TEAM ----------------------------
board = [
    {"name": "a", "team": "COL", "game_pk": 1},
    {"name": "b", "team": "COL", "game_pk": 1},
    {"name": "c", "team": "LAD", "game_pk": 1},   # other side, SAME game
    {"name": "d", "team": "LAD", "game_pk": 1},
    {"name": "e", "team": "NYY", "game_pk": 2},
]
kept, overflow = cap_per_game(board, cap=2)
assert [r["name"] for r in kept] == ["a", "b", "e"], [r["name"] for r in kept]
assert [r["name"] for r in overflow] == ["c", "d"]
assert len({r["team"] for r in board[:4]}) == 2, (
    "fixture no longer has two teams in one game — per-game vs per-team "
    "is the whole point of this case")
print("PASS: cap is per GAME — COL and LAD bats both count against game 1")

# --- 2. ORDER IS PRESERVED, never re-ranked --------------------------
ranked = [{"name": f"{i:02d}", "game_pk": i // 3} for i in range(9)]
kept, _ = cap_per_game(ranked, cap=2)
assert [r["name"] for r in kept] == sorted(r["name"] for r in kept), (
    "the cap re-ordered the board instead of filtering it")
print("PASS: survivors keep board order — it filters, it never re-ranks")

# --- 3. NOTHING IS DISCARDED -----------------------------------------
kept, overflow = cap_per_game(board, cap=1)
assert len(kept) + len(overflow) == len(board), "a bat vanished"
print("PASS: every capped-out bat comes back in the overflow")

# --- 4. AN UNKNOWN GAME KEY FAILS OPEN -------------------------------
nokey = [{"name": "x"}, {"name": "y"}, {"name": "z"}]
kept, overflow = cap_per_game(nokey, cap=1)
assert len(kept) == 3 and not overflow
print("PASS: a row with no game key is never capped away")

# --- 5. ...AND THE BOARD REALLY CARRIES THE KEY ----------------------
#
# Case 4's fail-open is only safe if the key is actually there. From the
# outside a cap that silently does nothing looks exactly like a cap that
# is working, so this is asserted against the source.
src = open("app/engines/hr_edge_board.py", encoding="utf-8").read()
assert 'r["game_pk"] = game.get("game_pk")' in src, (
    "the board stopped carrying game_pk — the cap would fail open on "
    "every row and cap nothing, silently")
print("PASS: the board carries game_pk, so the cap has a key to work on")

# --- 6. THE SORT USES THE UNCLAMPED VALUE ----------------------------
assert 'r.get("edge_raw")' in src, "the board reverted to sorting on the integer"
rows = [{"name": "lo", "edge": 100, "edge_raw": 100.4, "hr_score": 90},
        {"name": "hi", "edge": 100, "edge_raw": 115.2, "hr_score": 70}]
rows.sort(key=SORT_KEY, reverse=True)
assert rows[0]["name"] == "hi", (
    "two bats clamped to 100 sorted by something other than their real edge")
print("PASS: bats pinned at 100 still separate on the unclamped value")

# --- 7. THE TIEBREAK IS DECLARED, not inherited ----------------------
tied = [{"name": "worse", "edge": 80, "edge_raw": 80.0, "hr_score": 50},
        {"name": "better", "edge": 80, "edge_raw": 80.0, "hr_score": 88}]
tied.sort(key=SORT_KEY, reverse=True)
assert tied[0]["name"] == "better", (
    "a genuine tie fell back to iteration order instead of HR Score")
print("PASS: a real tie breaks on HR Score, not on the schedule")

# --- 8. batting_order reaches edge_components, on confirmed cards only
assert 'batting_order=(r.get("batting_order") if confirmed else None)' in src, (
    "the slot term is missing again — the board and the Game Card would "
    "disagree by up to five points, and this is the board that is logged")
assert '"batting_order": b.get("battingOrder")' in src, (
    "the order is never read off the lineup, so the line above passes None")
print("PASS: batting order reaches the edge layer, confirmed lineups only")

# --- 9. FLOORS ARE A TIER, AND UNMEASURED IS NOT A PASS --------------
th = hr_floors.resolve(None)          # fallbacks, no archive
elite = {"Brl %": 20.0, "Brl/PA": 12.0, "HH %": 55.0, "FB %": 40.0,
         "AvgEV": 95.0, "Blast %": 30.0, "PullAir %": 25.0, "ISO": 0.400,
         "ClearsAnywhere %": 2.0}
met, total, missed = hr_floors.evaluate(elite, th)
assert met == total and not missed, (met, missed)

# Same hitter, bat tracking unavailable. None must FAIL — a bat nobody
# measured has not cleared the floor — and the DENOMINATOR must not
# move, or a 9/9 that quietly became 8/8 would be one number meaning
# two different things.
untracked = {**elite, "Blast %": None}
met, total, missed = hr_floors.evaluate(untracked, th)
assert met == total - 1 and missed == ["Blast %"], (met, missed)
assert total == 9, "the denominator moved when a metric went missing"

met, _t, missed = hr_floors.evaluate({k: 0.0 for k in elite}, th)
assert met == 0 and len(missed) == 9
print(f"PASS: floors read as N/{total} — unmeasured fails, and is named")

# --- 10. THE FLOORS ARE MEASURED, the literals are only a fallback ---
measured = hr_floors.resolve({"hr_floors": {"brl_pa": 9.75}})
assert measured["brl_pa"] == 9.75, measured["brl_pa"]
assert measured["iso"] == hr_floors.resolve(None)["iso"], (
    "a partial measurement wiped the floors it did not cover")
# Junk is refused. An empty pool that produced a 0 is not a measurement,
# and a floor of 0 passes the entire league.
assert hr_floors.resolve({"hr_floors": {"brl_pa": 0}})["brl_pa"] > 0
assert hr_floors.resolve({"hr_floors": "not a dict"})["brl_pa"] > 0
print("PASS: measured floors win, partials merge, a zero floor is refused")

# --- 11. EV90 IS NOT THE EV FLOOR ------------------------------------
#
# The regression control for the finding that started this batch. A "91
# EV minimum" applied to EV90 cleared 373 of 373 hitters, because EV90
# is the 90th percentile of a hitter's batted balls (league median
# 104.2), not his average. If the floor ever points back at EV90 it will
# once again exclude nobody while looking strict.
_keys = [pkey for _k, pkey, _p, _f in hr_floors.FLOOR_SPECS]
assert "AvgEV" in _keys and "EV90" not in _keys, _keys
assert GAME_CAP == 2, f"the game cap moved to {GAME_CAP} — say so in a commit"
print("PASS: the EV floor reads average EV, not the 90th percentile")

# --- 12. THE PAGE CAPS TOO, not just the logged top 5 ----------------
#
# top_hr_edge() caps the record. This view called get_hr_edge_board
# directly and did not, so for one commit the graded record and the
# board on screen were two different lists — the exact divergence the
# cap decision was made to prevent, reintroduced one layer above where
# it was fixed. Asserted against the source because the view needs a
# Streamlit runtime to execute.
view = open("app/views/HR_Edge_Board.py", encoding="utf-8").read()
assert "cap_per_game(rows)" in view, (
    "the HR Edge page is not capped — it would show a different list "
    "from the one calibration grades")
assert "_overflow" in view and "Held back by the" in view, (
    "capped-out bats are not rendered anywhere — a hidden pick is worse "
    "than the stacking the cap exists to fix")
assert '"Floors"' in view and '"PA": r.get("hr_pa")' in view, (
    "the floors tier and the sample column are computed but not shown")
print("PASS: the page caps, shows the overflow, and renders floors + PA")
