"""
The nightly restores any tracked file the test suite touched BEFORE its
first commit step.

2026-10-03: a test rewrote data/mlb/games.json during "Run tests"; a
later commit step's `git pull --rebase --autostash` conflicted on it and
the following commit died on an unmerged file (exit 128), after the
models were built and before the archive was published. The leaking
test is fixed (test_calibration_picks); this pins the workflow-level
guard so the next leak is a warning, not an outage.

Plain script — exits non-zero on failure. Negative control, confirmed
red by exit code when written: deleting the restore step, or moving it
below "Commit graded calibration record", fails this.
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
wf = yaml.safe_load((ROOT / ".github/workflows/nightly-data.yml").read_text())
steps = wf["jobs"]["build-data"]["steps"]
names = [s.get("name", "") for s in steps]
failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


def idx(pred):
    return next((i for i, s in enumerate(steps) if pred(s)), None)


tests_i = idx(lambda s: s.get("name") == "Run tests")
restore_i = idx(lambda s: "git checkout -- ." in (s.get("run") or "")
                and "git status --porcelain" in (s.get("run") or ""))
first_commit_i = idx(lambda s: "git commit" in (s.get("run") or ""))
check("there is a Run tests step", tests_i is not None)
check("there is a restore step (status + checkout)", restore_i is not None)
check("it runs AFTER the tests", restore_i is not None and tests_i is not None
      and restore_i > tests_i)
check("it runs BEFORE the first commit step", restore_i is not None
      and first_commit_i is not None and restore_i < first_commit_i)

def _code(text):
    """Shell or YAML text with comment lines dropped. Every check below
    reads CODE, never prose: the first draft of this test failed on its
    own explanatory comments ("never `git clean`", "mlb.json belongs to
    slate-picks") — a check that matches a comment proves nothing (the
    08-12 na_rep lesson)."""
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


restore_run = _code(steps[restore_i].get("run") or "") if restore_i is not None else ""
check("the restore step also removes NEW files tests created under data/",
      "ls-files" in restore_run and "--others" in restore_run and "-- data" in restore_run)
check("...and never uses git clean (standing rule 7)", "git clean" not in restore_run)

# ---- 2. every test that runs calibration_picks.main() sandboxes BOTH
# files main() writes. 10-03: test_calibration_picks sandboxed only the
# record; then test_calibration_lines sandboxed neither — each leaked in
# turn, so this is checked across the whole suite, not per file.
import re
import ast
for t in sorted((ROOT / "tests").glob("*.py")):
    if t.name == Path(__file__).name:
        continue
    src = t.read_text()
    if "import calibration_picks" not in src:
        continue
    alias = re.search(r"import calibration_picks as (\w+)", src)
    name = alias.group(1) if alias else "calibration_picks"
    if f"{name}.main(" not in src:
        continue
    check(f"{t.name}: runs main() with the slate AND picks paths sandboxed",
          f"{name}.MLB_SLATE_PATH =" in src and f"{name}.PICKS_ROOT =" in src)

# ---- 3. every writer of the picks log goes through a sandboxable root
for f in ("calibration_picks.py", "nhl_precompute.py", "nfl_precompute.py"):
    tree = ast.parse((ROOT / f).read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", getattr(n.func, "id", None)) == "log_picks"]
    ok = calls and all(any(k.arg == "root" and isinstance(k.value, ast.Name)
                           and k.value.id == "PICKS_ROOT" for k in c.keywords) for c in calls)
    check(f"{f}: log_picks always passes root=PICKS_ROOT ({len(calls)} call(s))", bool(ok))

# ---- 4. one owner per picks file
nightly_txt = _code((ROOT / ".github/workflows/nightly-data.yml").read_text())
slate_txt = _code((ROOT / ".github/workflows/slate-picks.yml").read_text())
check("the nightly grades NHL and NFL only, never MLB",
      "model_picks_grade.py nhl nfl" in nightly_txt
      and "model_picks_grade.py mlb" not in nightly_txt
      and "model_picks/mlb.json" not in nightly_txt)
check("the nightly never adds the whole data/model_picks directory",
      "git add data/model_picks\n" not in nightly_txt and "git add data/model_picks;" not in nightly_txt)
check("slate-picks grades MLB (it is the workflow that logs MLB)",
      "model_picks_grade.py mlb" in slate_txt)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
