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

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
