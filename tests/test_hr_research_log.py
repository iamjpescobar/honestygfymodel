"""hr_research_log's writing, its grading, and the guard that matters.

THE CASE THIS FILE EXISTS FOR is the coverage check. "No rows for this
batter on this date" is ambiguous — either he did not play, or the
nightly Statcast pull has not reached that date yet. Reading the second
as the first would close a whole night of bats as DNP with a 0 against
each of them, permanently, and the file would look complete.

That exact mistake has already been made once in this repo, against a
stale WNBA slate, and it closed 45 picks as DNP for games that had
already been played. So it gets a test before it gets a first run.
"""
import json, sys, types, tempfile
from pathlib import Path
import pandas as pd

# pyarrow isn't available everywhere; shim parquet with pickle so the
# reader under test still runs. Production keeps real parquet. **kw
# because _homered passes columns=[...] and the shim must accept it.
pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))

sys.path.insert(0, ".")

# --- stub the board so `log` needs no network and no lineups ---------
# Both NYY bats share game 10 — the same park, starter, wind and pen.
# That is the correlation the 2-per-game cap exists for, and the log
# cannot see it at all unless game_pk is stored.
BOARD = [
    {"id": 1, "name": "A", "team": "NYY", "opponent": "BOS", "edge": 100,
     "edge_raw": 115.2, "hr_score": 80, "bats": "R", "game_pk": 10,
     "floors_met": 9, "floors_total": 9},
    {"id": 2, "name": "B", "team": "NYY", "opponent": "BOS", "edge": 100,
     "edge_raw": 100.4, "hr_score": 66, "bats": "L", "game_pk": 10,
     "floors_met": 4, "floors_total": 9},
    {"id": 3, "name": "C", "team": "BOS", "opponent": "NYY", "edge": 55,
     "edge_raw": 55.3, "hr_score": 50, "bats": "R", "game_pk": 11,
     "floors_met": 6, "floors_total": 9},
]
_board_mod = types.ModuleType("engines.hr_edge_board")
_board_mod.get_hr_edge_board = lambda confirmed_only=True: (
    list(BOARD), {"games": 1, "rated": len(BOARD)})
_sc_mod = types.ModuleType("engines.statcast_engine")
_sc_mod.get_batter_profile_windowed = lambda pid, **kw: {
    "Brl %": 12.0, "Brl/PA": 8.5, "ISO": 0.240, "PA": 400,
    "AvgEV": 91.4, "Blast %": 22.0, "ClearsAnywhere %": 0.7}
_pkg = types.ModuleType("engines"); _pkg.__path__ = []
sys.modules.setdefault("engines", _pkg)
sys.modules["engines.hr_edge_board"] = _board_mod
sys.modules["engines.statcast_engine"] = _sc_mod

import hr_research_log as hrl  # noqa: E402

tmp = Path(tempfile.mkdtemp())
hrl.OUT_DIR = tmp / "research"
hrl.BATTER_DIR = tmp / "batters"
hrl.BATTER_DIR.mkdir(parents=True)

DATE = "2026-08-11"
TODAY = "2026-08-12"

# --- 1. log writes one row per RATED bat, not per published pick -----
assert hrl.log(DATE) == 3
rows = [r for r in hrl._read_month(DATE) if r["date"] == DATE]
assert len(rows) == 3, rows
assert {r["id"] for r in rows} == {1, 2, 3}
assert all(r["hr"] is None and r["graded"] is None for r in rows), (
    "a freshly logged bat must be UNGRADED, not zero")
assert rows[0]["Brl/PA"] == 8.5, "the floor metrics did not come through"
print("PASS: every rated bat logged, all three, ungraded")

# --- 2. idempotent per (date, batter) --------------------------------
assert hrl.log(DATE) == 0, "a second run duplicated the night"
assert len([r for r in hrl._read_month(DATE) if r["date"] == DATE]) == 3
print("PASS: a second run the same evening leaves the night alone")


def batter_file(pid, dates, hr_dates=()):
    """A batter's season file covering `dates`, homering on `hr_dates`."""
    pd.DataFrame({
        "game_date": list(dates),
        "events": ["home_run" if d in hr_dates else "field_out" for d in dates],
    }).to_parquet(hrl.BATTER_DIR / f"{pid}.parquet")


# --- 3. THE COVERAGE GUARD -------------------------------------------
#
# The pull is behind: only batter 1 has any row for that date. If the
# grader read the other two as DNP it would write two permanent zeros
# for a night that simply has not been pulled yet.
batter_file(1, [DATE], hr_dates=[DATE])
batter_file(2, ["2026-08-09"])
batter_file(3, ["2026-08-09"])
hrl.grade(TODAY)
rows = [r for r in hrl._read_month(DATE) if r["date"] == DATE]
assert all(r["graded"] is None for r in rows), (
    "the grader closed a night the Statcast pull had not reached")
assert all(r["hr"] is None for r in rows), "and it wrote results anyway"
print("PASS: pull behind -> the whole night is left ungraded, not zeroed")

# --- 4. Once the pull covers the date, it grades ----------------------
batter_file(2, [DATE])                       # played, no home run
batter_file(3, ["2026-08-09"])               # genuinely did not play
assert hrl.grade(TODAY) == 3
rows = {r["id"]: r for r in hrl._read_month(DATE) if r["date"] == DATE}
assert rows[1]["hr"] == 1 and rows[1]["graded"] == "played"
assert rows[2]["hr"] == 0 and rows[2]["graded"] == "played"
assert rows[3]["graded"] == "dnp", "a bench night must be distinguishable"
print("PASS: graded 1 homer, 1 played-no-homer, 1 DNP — and they differ")

# --- 5. Tonight is never graded --------------------------------------
#
# THE BATTER FILES ALREADY COVER TODAY, and that is the realistic case:
# a 1 PM game lands in the Statcast pull hours before the 7 PM games
# finish. So the coverage guard is satisfied and the ONLY thing standing
# between the grader and closing tonight's board at 4 PM is the date
# check. Without these two lines this case passed on the coverage guard
# instead, and a control that removed the date check stayed green.
batter_file(1, [DATE, TODAY], hr_dates=[DATE])
batter_file(2, [DATE, TODAY])
hrl.log(TODAY)
hrl.grade(TODAY)
_tonight = [r for r in hrl._read_month(TODAY) if r["date"] == TODAY]
assert _tonight and all(r["graded"] is None for r in _tonight), (
    "tonight's games were graded before they were played")
print("PASS: the current date is never graded")

# --- 6. Re-grading does not double count or overwrite -----------------
assert hrl.grade(TODAY) == 0
assert [r for r in hrl._read_month(DATE) if r["date"] == DATE][0]["hr"] == 1
print("PASS: re-running the grader changes nothing already closed")

# --- 7. A corrupt line costs one line, not the month -----------------
path = hrl._month_path(DATE)
path.write_text(path.read_text() + "{not json\n", encoding="utf-8")
assert len(hrl._read_month(DATE)) == 6, "one bad line took the whole file down"
print("PASS: an unreadable line is reported and skipped, month survives")

# --- 8. THE FIELDS ADDED AFTER THIS LOGGER WAS WRITTEN ---------------
#
# Four of them were missing for a full night of real logging, and each
# one silently removes a question the log was built to answer. The
# regression control is that a stored row can still answer it.
row = [r for r in hrl._read_month(DATE) if r["date"] == DATE][0]

# game_pk — without it, every row reads as its own game and the cap can
# never be evaluated against outcomes.
by_game = {}
for r in hrl._read_month(DATE):
    if r["date"] == DATE:
        by_game.setdefault(r.get("game_pk"), []).append(r)
assert None not in by_game, "a logged bat has no game key"
assert len(by_game) == 2 and len(by_game[10]) == 2, (
    f"same-game bats are not groupable: {by_game.keys()}")

# edge_raw — both NYY bats display 100 and the log has to keep them apart.
_pinned = sorted(by_game[10], key=lambda r: r["edge_raw"], reverse=True)
assert _pinned[0]["id"] == 1, "two bats clamped to 100 are indistinguishable"
assert row["edge"] != row["edge_raw"], (
    "edge_raw stored as the clamped value — the clamp is back inside the "
    "measurement")

# AvgEV — the floor set names it, so the tier is not reconstructable
# without it.
assert row.get("AvgEV") == 91.4, "AvgEV is not captured"

# floors_met — recorded against the thresholds IN FORCE THAT NIGHT,
# which move as the league does.
assert row.get("floors_met") == 9 and row.get("floors_total") == 9
print("PASS: game_pk, edge_raw, AvgEV and floors_met all reach the file")
