"""
Every workflow push retries (10-22): two runs saving to main within a
minute of each other (or a run and a manual push) turned the late one
away ("cannot lock ref"), and the nightly stopped at its first commit
step without publishing. Each push now pulls and retries up to five
times, then fails loudly.

Plain script — exits non-zero on failure. Reads the workflow files only.

Negative control, confirmed red by exit code when written (rule 4):
  - one workflow's push put back to a single pull + push
    -> "every push in every workflow is inside the retry loop" fails
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


bad, n = [], 0
for f in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
    for line in f.read_text(encoding="utf-8").splitlines():
        if re.search(r"\bgit push\b", line) and not line.lstrip().startswith("#"):
            n += 1
            if "&& break" not in line or "git pull --rebase --autostash" not in line:
                bad.append(f"{f.name}: {line.strip()[:80]}")
check(f"every push in every workflow is inside the retry loop ({n} pushes) {bad[:3]}",
      n >= 10 and not bad)
ng = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the loop gives up loudly after five tries",
      ng.count('echo "::error::push failed 5 times"; exit 1') >= 5
      and ng.count("for _try in 1 2 3 4 5; do") >= 5)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall workflow push-retry checks passed")
