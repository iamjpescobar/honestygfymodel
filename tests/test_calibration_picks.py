"""calibration_picks.py — the headless slate-time pick logger.

The record it writes is the ONLY thing standing between this model and
"the board looks about right", so the failure modes that matter are the
quiet ones: silently erasing graded history, overwriting a real board
with an empty one, or letting one broken engine cost the whole day.
"""
import json, sys, types, importlib, tempfile
from pathlib import Path

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache; sys.modules["streamlit"] = st
sys.path.insert(0, ".")

import calibration_picks as cp
from datetime import datetime
TODAY = datetime.now(cp.EASTERN).strftime("%Y-%m-%d")

tmp = Path(tempfile.mkdtemp())
cp.RECORD_PATH = tmp / "calibration.json"

# --- 1. Happy path: both boards logged ---
cp.BUILDERS = {
    "daily13": lambda: [{"id": i, "name": f"B{i}", "team": "NYY"} for i in range(1, 14)],
    "potd": lambda: [{"id": 99, "name": "Star", "team": "LAD"}],
}
assert cp.main() == 0
rec = json.loads(cp.RECORD_PATH.read_text())
assert len(rec["daily13"][TODAY]["picks"]) == 13
assert len(rec["potd"][TODAY]["picks"]) == 1
assert rec["potd"][TODAY]["graded"] is False
assert all(p["result"] is None for p in rec["daily13"][TODAY]["picks"])
print("PASS: both boards logged, ungraded, results empty")

# --- 2. Idempotent: a later run must NOT overwrite a logged board ---
cp.BUILDERS = {"daily13": lambda: [{"id": 1, "name": "DIFFERENT", "team": "X"}],
               "potd": lambda: []}
cp.main()
rec = json.loads(cp.RECORD_PATH.read_text())
assert len(rec["daily13"][TODAY]["picks"]) == 13, "re-run overwrote a logged board"
assert rec["daily13"][TODAY]["picks"][0]["name"] == "B1"
print("PASS: re-run leaves an already-logged board untouched")

# --- 3. Empty board (lineups not posted) must not blank an existing one ---
assert rec["potd"][TODAY]["picks"], "empty build erased a real board"
print("PASS: empty build doesn't erase previously logged picks")

# --- 4. One engine crashing must not cost the other board ---
cp.RECORD_PATH = tmp / "b.json"
def boom(): raise RuntimeError("engine exploded")
cp.BUILDERS = {"daily13": boom, "potd": lambda: [{"id": 7, "name": "S", "team": "SF"}]}
assert cp.main() == 0, "a crashing engine failed the whole run"
rec2 = json.loads(cp.RECORD_PATH.read_text())
assert "daily13" not in rec2 and len(rec2["potd"][TODAY]["picks"]) == 1
print("PASS: one engine crashing still logs the other board")

# --- 5. Graded history from earlier days must survive a new write ---
cp.RECORD_PATH = tmp / "c.json"
cp.RECORD_PATH.write_text(json.dumps({
    "daily13": {"2026-07-01": {"picks": [{"id": 5, "name": "Old",
                                          "result": "hit"}], "graded": True}}}))
cp.BUILDERS = {"daily13": lambda: [{"id": 1, "name": "New", "team": "NYY"}],
               "potd": lambda: []}
cp.main()
rec3 = json.loads(cp.RECORD_PATH.read_text())
assert rec3["daily13"]["2026-07-01"]["picks"][0]["result"] == "hit", "graded history lost"
assert rec3["daily13"]["2026-07-01"]["graded"] is True
assert TODAY in rec3["daily13"]
print("PASS: prior graded days survive a new day's write")

# --- 6. A corrupt record must RAISE, never silently start from {} ---
cp.RECORD_PATH = tmp / "d.json"
cp.RECORD_PATH.write_text("{ this is not json")
try:
    cp.main()
    raise AssertionError("corrupt record was silently overwritten")
except Exception as exc:
    assert not isinstance(exc, AssertionError), exc
print("PASS: corrupt record raises instead of erasing history")

# --- 7. Nothing to log leaves no file behind ---
cp.RECORD_PATH = tmp / "e.json"
cp.BUILDERS = {"daily13": lambda: [], "potd": lambda: []}
assert cp.main() == 0
assert not cp.RECORD_PATH.exists()
print("PASS: an empty slate writes nothing and still exits clean")

# --- 8. get_daily_13 returns a (rows, meta) TUPLE ---------------------
# _rows_daily13 assumed a bare list, so each element was handed to
# r.get() and every run died with "AttributeError: 'list' object has no
# attribute 'get'". The board never logged once.
import types
mod = types.ModuleType("engines.daily_13")
mod.get_daily_13 = lambda: ([{"id": 1, "name": "A", "team": "NYY"},
                             {"id": 2, "name": "B", "team": "BOS"}],
                            {"scanned": 50})
sys.modules["engines.daily_13"] = mod
rows = cp._rows_daily13()
assert len(rows) == 2 and rows[0]["name"] == "A", rows
print("PASS: (rows, meta) tuple unpacked correctly")

mod.get_daily_13 = lambda: ([], {"warning": "cache error"})
assert cp._rows_daily13() == []
print("PASS: empty board with a warning yields no picks, no crash")

mod.get_daily_13 = lambda: [{"id": 3, "name": "C", "team": "SF"}]
assert len(cp._rows_daily13()) == 1
print("PASS: bare-list return still handled (shape-tolerant)")

mod.get_daily_13 = lambda: ([["not", "a", "dict"], {"id": 4, "name": "D"}], {})
assert len(cp._rows_daily13()) == 1, "non-dict rows should be skipped, not crash"
print("PASS: malformed rows skipped rather than crashing the board")

def _commands_only(text):
    """The workflow with comment lines removed.

    A substring search over the whole file matches the long explanatory
    comments this repo puts above every tricky step — so an assertion
    that `data/mlb/games.json` appears passed even after the path was
    deleted from the git-add, because the comment ABOVE it still named
    the file. Caught by deleting the path on purpose and watching the
    test stay green. Anything asserting what a workflow DOES has to read
    what it runs.
    """
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("#"))


# --- 9. The workflow guard must detect an UNTRACKED file --------------
#
# ASSERTS THE PROPERTY, NOT THE SPELLING (rule 11). This used to pin the
# exact string `git status --porcelain -- data/calibration.json`, which
# went red the moment slate-picks started committing a second file and
# moved the paths into a shell variable — a correct change failing a
# test that was checking the wording of the guard rather than the guard.
#
# The property is what matters and is unchanged: git STATUS, never git
# diff, because git diff only compares TRACKED files and both of these
# were new untracked files on their first run. That is the bug that kept
# the record frozen at one day while the log said picks had been written.
for wf in ("slate-picks", "nightly-data"):
    y = _commands_only(open(f".github/workflows/{wf}.yml").read())
    assert "git status --porcelain" in y, \
        f"{wf}.yml must use git status, not git diff"
    assert "git diff --quiet" not in y, \
        f"{wf}.yml still uses git diff, which ignores untracked files"
    assert "data/calibration.json" in y, \
        f"{wf}.yml no longer commits the pick record at all"
print("PASS: both workflows detect a first-time (untracked) record file")

# The MLB slate must be committed too, and ONLY slate-picks writes it.
#
# Home's hero card reads the repository copy: Render gets the repo in its
# checkout but gets app/data/ only from the nightly release archive, and
# this job publishes no archive. Uncommitted, the slate would live on the
# Actions runner and die with it — a green run, a log line saying the
# file was written, and a card that never once sees it. That is the same
# shape as every other silent-outage bug in this repo's history, one
# layer further out.
_sp = _commands_only(open(".github/workflows/slate-picks.yml").read())
assert "data/mlb/games.json" in _sp, (
    "slate-picks.yml must commit data/mlb/games.json — calibration_picks "
    "writes it and nothing else publishes it, so an uncommitted slate "
    "never reaches production")
assert "git add" in _sp and "git push" in _sp, \
    "slate-picks.yml must still commit and push what it wrote"
print("PASS: slate-picks commits the MLB slate the hero card reads")
