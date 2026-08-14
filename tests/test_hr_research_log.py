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
def _profile(pid, window="season", **kw):
    """Season and short windows must differ, or case 11 proves nothing."""
    base = {"Brl %": 12.0, "Brl/PA": 8.5, "ISO": 0.240, "PA": 400,
            "AvgEV": 91.4, "Blast %": 22.0, "ClearsAnywhere %": 0.7,
            "PullAir %": 15.0, "HH %": 45.0, "FB %": 30.0, "EV90": 106.0,
            "HRWindow %": 27.0}
    if window == "l15":
        return {**base, "Brl/PA": 11.2, "PullAir %": 19.4}   # hot
    if window == "l5":
        return {**base, "Brl/PA": 3.1, "PullAir %": 8.0}     # cold
    return base


_sc_mod.get_batter_profile_windowed = _profile
_pkg = types.ModuleType("engines"); _pkg.__path__ = []
sys.modules.setdefault("engines", _pkg)
sys.modules["engines.hr_edge_board"] = _board_mod
sys.modules["engines.statcast_engine"] = _sc_mod

import hr_research_log as hrl  # noqa: E402

tmp = Path(tempfile.mkdtemp())
hrl.OUT_DIR = tmp / "research"
# TWO ROOTS, and the reason is the bug that cost a day of grading.
#
# precompute writes into build_data/; app/data/ only exists after
# fetch_data.py unpacks the release asset, which never happens on the CI
# runner. The grader read app/data/ alone, found nothing on the nightly,
# and the coverage guard correctly refused to close 270 rows — for a
# reason nobody could see. The fixture uses a fake first root so the
# FALLBACK is what these cases exercise.
_ABSENT = tmp / "build_data_that_does_not_exist"
hrl.BATTER_DIRS = (_ABSENT, tmp / "batters")
(tmp / "batters").mkdir(parents=True)

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

# --- 1b. SHORT WINDOWS ARE LOGGED BESIDE THE SEASON FIGURES ----------
#
# Season alone cannot answer whether season is the right basis. If only
# the season value is on disk, then in three weeks the log can say
# whether an 88 beats a 71 and STILL not say whether L15 pull-air beats
# season pull-air — and there is no way to backfill, because the windows
# move every night.
#
# The fixture deliberately makes l15 hot and l5 cold, so a row that
# merely copied the season value would fail here.
row = [r for r in hrl._read_month(DATE) if r["date"] == DATE][0]
assert row.get("Brl/PA") == 8.5, "the season value was overwritten"
assert row.get("l15_Brl/PA") == 11.2, f"l15 not logged: {row.get('l15_Brl/PA')}"
assert row.get("l5_Brl/PA") == 3.1, f"l5 not logged: {row.get('l5_Brl/PA')}"
assert row.get("l15_PullAir %") == 19.4 and row.get("l5_PullAir %") == 8.0
assert len({row["Brl/PA"], row["l15_Brl/PA"], row["l5_Brl/PA"]}) == 3, (
    "the three windows returned the same number — the window argument is "
    "not reaching the profile call")
print("PASS: season, L15 and L5 are all logged and are all different")

# --- 2. idempotent per (date, batter) --------------------------------
assert hrl.log(DATE) == 0, "a second run duplicated the night"
assert len([r for r in hrl._read_month(DATE) if r["date"] == DATE]) == 3
print("PASS: a second run the same evening leaves the night alone")


def batter_file(pid, dates, hr_dates=()):
    """A batter's season file covering `dates`, homering on `hr_dates`."""
    pd.DataFrame({
        "game_date": list(dates),
        "events": ["home_run" if d in hr_dates else "field_out" for d in dates],
    }).to_parquet(hrl.BATTER_DIRS[1] / f"{pid}.parquet")


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


# --- 9. A MISSING ROOT IS NOT A MISSING GAME -------------------------
#
# The regression control for the day of grading that was lost. With no
# readable root at all, every bat looks like "did not play" — and closing
# a night on that would write 270 permanent zeros against games that were
# played. The guard must hold, and the reason must be reported.
hrl.BATTER_DIRS = (_ABSENT, tmp / "also_missing")
LATER = "2026-08-13"
BOARD[:] = [{"id": 1, "name": "A", "team": "NYY", "opponent": "BOS",
             "edge": 90, "edge_raw": 90.1, "hr_score": 80, "bats": "R",
             "game_pk": 10, "floors_met": 9, "floors_total": 9}]
hrl.log(LATER)
hrl.grade("2026-08-14")
_after = [r for r in hrl._read_month(LATER) if r["date"] == LATER]
assert _after and all(r["graded"] is None for r in _after), (
    "a night was closed with no batter files readable at all")
print("PASS: no readable data root -> the night stays ungraded, not zeroed")


# --- 10. THE ROOTS MUST MATCH WHERE PRECOMPUTE WRITES ----------------
#
# THE CASE THAT WOULD HAVE CAUGHT THE REAL BUG, and none of the above
# can: every case here monkeypatches BATTER_DIRS, so a wrong hardcoded
# path is invisible to them. The defect was never in the logic — it was
# that the logger read app/data/ while precompute writes build_data/,
# and app/data/ does not exist on the CI runner at all.
#
# A fixture cannot test a constant it replaces. Only comparing the two
# modules' own constants can.
import importlib, re as _re  # noqa: E402

# Read precompute's OUT_ROOT from SOURCE rather than importing it —
# precompute pulls in engines.hr_floors, which needs app/ on sys.path and
# a streamlit shim. This case is about two literals agreeing; dragging a
# whole import graph in to compare them is how a test starts failing for
# reasons that have nothing to do with what it checks.
_src = open("precompute.py", encoding="utf-8").read()
_root = _re.search(r'^OUT_ROOT = Path\("([^"]+)"\)', _src, _re.M).group(1)
_datadir = _re.search(r'^DATA_DIR = OUT_ROOT / "([^"]+)" / "([^"]+)"', _src, _re.M)
_real = list(importlib.reload(hrl).BATTER_DIRS)
_want = (Path(_root) / _datadir.group(1) / _datadir.group(2) / "batters").resolve()
assert any(p.resolve() == _want for p in _real), (
    f"none of the grader's roots {[str(p) for p in _real]} is where "
    f"precompute writes batter files ({_want}) — grading will find no "
    f"data on the nightly runner and silently refuse every night")
print(f"PASS: a grader root matches precompute's output ({_want.name})")


# --- 12. EVERY ADJUSTMENT edge_components RETURNS MUST BE LOGGED -----
#
# THE GUARD FOR A MISTAKE MADE FOUR TIMES. game_pk, edge_raw, AvgEV and
# platoon_adj were each added to the model after EDGE_KEYS was written.
# Each reached the board rows (the board does r.update(edge_components(
# ...))) and none reached the log, so for as long as it went unnoticed
# the log could not measure the thing that had just been built. There is
# no backfill: the board state that produced those nights is gone.
#
# Asserted against edge.py's SOURCE rather than by importing it —
# edge.py pulls in most of the engine layer, and a test that drags an
# import graph in to compare two lists starts failing for reasons
# unrelated to what it checks.
import re as _re2  # noqa: E402

_edge_src = open("app/engines/edge.py", encoding="utf-8").read()
_ret = _edge_src[_edge_src.rindex("return {\"edge\":"):]
_ret = _ret[:_ret.index("}") + 1]
_returned = set(_re2.findall(r'"(\w+_adj)"', _ret))
_logged = set(hrl.EDGE_KEYS)
_missing = _returned - _logged
assert not _missing, (
    f"edge_components returns {sorted(_missing)} and hr_research_log does "
    f"not record it — the log cannot measure a term the model just "
    f"gained. Add it to EDGE_KEYS.")
print(f"PASS: all {len(_returned)} edge adjustments reach the log "
      f"({', '.join(sorted(_returned))})")
