#!/usr/bin/env python3
"""E2: give the WNBA slate a mid-day rebuild path.

Edits accumulate per file; verifies what landed ON DISK.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
buf = {}
applied = []


def edit(relpath, old, new, label):
    s = buf.get(relpath)
    if s is None:
        s = (ROOT / relpath).read_text()
    if old not in s:
        sys.exit(f"ANCHOR NOT FOUND ({label}) - nothing written.")
    if s.count(old) != 1:
        sys.exit(f"ANCHOR NOT UNIQUE ({label}) - nothing written.")
    buf[relpath] = s.replace(old, new, 1)
    applied.append(label)


W = ".github/workflows/intl-late-refresh.yml"
GATE_OLD = "if: steps.npb.outcome == 'success' || steps.kbo.outcome == 'success'"
GATE_NEW = ("if: steps.npb.outcome == 'success' || steps.kbo.outcome == 'success'"
            "\n          || steps.wnba.outcome == 'success'")

# ----------------------------------------------------------------------
# 1. The name stops lying. WNBA is not "intl".
# ----------------------------------------------------------------------
edit(W, "name: intl-late-refresh",
     "name: Late slate refresh (KBO, NPB, WNBA)", "workflow display name")

# ----------------------------------------------------------------------
# 2. The WNBA step.
# ----------------------------------------------------------------------
edit(W, '''      - name: Re-fetch KBO slate
        id: kbo
        continue-on-error: true
        run: python kbo_precompute.py''', '''      - name: Re-fetch KBO slate
        id: kbo
        continue-on-error: true
        run: python kbo_precompute.py

      # WNBA HAS NO OTHER WAY BACK.
      #
      # The WNBA slate is built solely inside nightly-data.yml, downstream
      # of the ~15-minute Statcast pull. When the nightly failed on
      # Aug 5 the site showed "No WNBA slate on disk for 2026-08-05" for
      # the rest of the day — slate_guard correctly refusing to pass an
      # older night's games off as tonight's — and there was no way to
      # recover short of a full nightly run. "Sync latest" cannot help
      # either: it re-downloads the same release asset and honestly
      # reports that nothing changed.
      #
      # This job already downloads, swaps, repacks, verifies and
      # publishes. wnba_precompute.py writes to build_data/data/wnba,
      # exactly the convention kbo_precompute and npb_precompute use, and
      # needs nothing the install step does not already provide. So the
      # recovery path costs one step.
      - name: Re-fetch WNBA slate
        id: wnba
        continue-on-error: true
        run: python wnba_precompute.py''', "WNBA fetch step")

# ----------------------------------------------------------------------
# 3. Three gates: repack, publish, deploy.
# ----------------------------------------------------------------------
for i, label in enumerate(("gate: repack", "gate: publish", "gate: deploy")):
    s = buf.get(W) or (ROOT / W).read_text()
    idx = s.find(GATE_OLD)
    if idx == -1:
        sys.exit(f"ANCHOR NOT FOUND ({label}) - nothing written.")
    buf[W] = s[:idx] + GATE_NEW + s[idx + len(GATE_OLD):]
    applied.append(label)

# ----------------------------------------------------------------------
# 4. Verify and report the third league too.
# ----------------------------------------------------------------------
edit(W, '''          for lg in ("kbo", "npb"):''',
     '''          for lg in ("kbo", "npb", "wnba"):''', "verify includes wnba")

edit(W, '''        env:
          NPB_OUTCOME: ${{ steps.npb.outcome }}
          KBO_OUTCOME: ${{ steps.kbo.outcome }}''',
     '''        env:
          NPB_OUTCOME: ${{ steps.npb.outcome }}
          KBO_OUTCOME: ${{ steps.kbo.outcome }}
          WNBA_OUTCOME: ${{ steps.wnba.outcome }}''', "report env")

edit(W, '''          if [ "$KBO_OUTCOME" = "failure" ]; then
            echo "::error::KBO refresh failed - the archive kept the nightly's KBO slate."
          fi''', '''          if [ "$KBO_OUTCOME" = "failure" ]; then
            echo "::error::KBO refresh failed - the archive kept the nightly's KBO slate."
          fi
          if [ "$WNBA_OUTCOME" = "failure" ]; then
            echo "::error::WNBA refresh failed - the archive kept the nightly's WNBA slate."
          fi''', "report wnba failure")

edit(W, '''        if: steps.npb.outcome == 'failure' || steps.kbo.outcome == 'failure' ''' .rstrip() + "\n",
     '''        if: steps.npb.outcome == 'failure' || steps.kbo.outcome == 'failure'
          || steps.wnba.outcome == 'failure'
''', "report gate")

for relpath, content in buf.items():
    (ROOT / relpath).write_text(content)
for label in applied:
    print(f"patched: {label}")

_w = (ROOT / W).read_text()
checks = {
    "wnba step added": "id: wnba" in _w,
    "runs wnba_precompute": "run: python wnba_precompute.py" in _w,
    "3 success gates widened": _w.count("|| steps.wnba.outcome == 'success'") == 3,
    "failure gate widened": "|| steps.wnba.outcome == 'failure'" in _w,
    "verify loop includes wnba": '("kbo", "npb", "wnba")' in _w,
    "failure message added": "WNBA refresh failed" in _w,
    "name updated": "Late slate refresh" in _w,
}
try:
    import yaml
    d = yaml.safe_load(_w)
    steps = d["jobs"]["refresh"]["steps"]
    checks["YAML parses"] = True
    checks["step count 11"] = len(steps) == 11
except Exception as exc:  # pragma: no cover
    checks["YAML parses"] = False
    print(f"  yaml error: {exc}")

print()
for name, ok in checks.items():
    print(f"  {'OK  ' if ok else 'FAIL'} {name}")
print("done" if all(checks.values()) else "INCOMPLETE - tell Claude")
