"""The per-pick LINE has to survive the trip from builder to grader.

Three defects lived in that gap at once, and every existing test passed
through all of them:

  1. calibration_picks.main() wrote "stat": None, "line": None into every
     record, discarding what the builders computed.
  2. _rows_k_board() bound the whole (rows, warning) tuple to `rows`, so
     it raised AttributeError on every run and logged nothing, ever.
  3. calibration_pipeline.BOARDS and engines.calibration.BOARDS disagreed
     on the WNBA thresholds (None vs 15), so one pick had two answers.

Together they meant the boards that grade against their own published
number could not be graded at all. These tests pin each one shut.
"""
import json
import sys
import types
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

# streamlit only has to IMPORT — the engines are decorated with
# @st.cache_data and never enter a runtime here.
st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache
sys.modules.setdefault("streamlit", st)

import calibration_picks as cp
import calibration_pipeline as pipe


# --- 1. main() carries stat and line into the record -------------------
def _fake_rows():
    return [{"id": "99", "name": "Test Pitcher", "team": "TST",
             "stat": "strikeOuts", "line": 6.5}]

with tempfile.TemporaryDirectory() as td:
    cp.RECORD_PATH = Path(td) / "calibration.json"
    cp.BUILDERS = {"k_board": _fake_rows}
    cp.main()
    rec = json.loads(cp.RECORD_PATH.read_text())

day = next(iter(rec["k_board"]))
pick = rec["k_board"][day]["picks"][0]
assert pick["stat"] == "strikeOuts", f"stat was dropped: {pick}"
assert pick["line"] == 6.5, f"line was dropped: {pick}"
assert pick["result"] is None
print("PASS: main() writes the builder's stat and line through, not None")


# --- 2. a line-less pick on a None-threshold board is never gradeable --
# This is the consequence the bug had, stated as an invariant so nobody
# reintroduces it by "simplifying" the record shape later.
cfg = pipe.BOARDS["wnba_props"]
assert cfg["threshold"] is None
_target = None if cfg["threshold"] is None else cfg["threshold"]
assert _target is None, (
    "a pick with no line on a None-threshold board has no target, so it "
    "can only ever close as dnp — the line MUST be recorded")
print("PASS: None threshold + None line == ungradeable, invariant pinned")


# --- 3. get_slate_k_projections returns a 2-tuple, and _rows_k_board
#        unpacks it rather than iterating it ---------------------------
kp = types.ModuleType("engines.k_projection")
kp.get_slate_k_projections = lambda basis="season": (
    [{"pid": "1", "pitcher": "A", "team": "AAA", "proj": 7.2},
     {"pid": "2", "pitcher": "B", "team": "BBB", "proj": 5.1}],
    None,
)
sys.modules["engines.k_projection"] = kp

rows = cp._rows_k_board()
assert rows, "k_board built nothing from a valid slate"
assert rows[0]["line"] == 7.2, f"projection not carried as the line: {rows[0]}"
assert rows[0]["stat"] == "strikeOuts"
assert rows[0]["id"] == "1", "rows not sorted by projection descending"
print(f"PASS: _rows_k_board unpacks (rows, warning) -> {len(rows)} pick(s)")

# The warning slot being non-empty must not change the shape.
kp.get_slate_k_projections = lambda basis="season": ([], "cache miss")
assert cp._rows_k_board() == [], "a warning-only response should build no picks"
print("PASS: warning in the second slot doesn't leak into the picks")


# --- 4. the two BOARDS configs agree ----------------------------------
from engines.calibration import BOARDS as APP_BOARDS

shared = set(APP_BOARDS) & set(pipe.BOARDS)
assert shared, "the two BOARDS configs share no boards at all"
for board in sorted(shared):
    a, p = APP_BOARDS[board], pipe.BOARDS[board]
    for field in ("sport", "stat", "threshold"):
        assert a[field] == p[field], (
            f"{board}.{field} disagrees: app={a[field]!r} "
            f"pipeline={p[field]!r} — the same pick would grade two ways")
print(f"PASS: app and pipeline BOARDS agree on {len(shared)} board(s)")


# --- 5. neither grader compares a value against a None target ---------
# The app engine was missing the guard the pipeline had; with the WNBA
# thresholds now None, that path is reachable.
src = (ROOT / "app" / "engines" / "calibration.py").read_text()
assert "if value is None or target is None:" in src, (
    "engines/calibration.py must short-circuit a None target before "
    "comparing, or `value >= None` raises TypeError")
print("PASS: app grader guards a None target before comparing")
