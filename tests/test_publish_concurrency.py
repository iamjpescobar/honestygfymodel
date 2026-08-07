"""Every workflow that republishes the release archive shares one lock.

WHY THIS EXISTS

`nightly-data` and `intl-late-refresh` both download the published
archive, repack it, and upload it back to the same release asset. None
of that is atomic. If two runs overlap, the second upload silently
replaces the first's work, and the repack's `data/statcast/` check
cannot help: it catches an archive that is GUTTED, not one that is
STALE.

The guard that existed protected the nightly from itself and nothing
else — `group: nightly-data` scoped it to one workflow, so a late
refresh could still land on top of a nightly mid-publish. On
2026-08-06 that nearly happened twice: the nightly was running while a
refresh sat queued, and then a GitHub Actions outage left two of EACH
queued to fire the moment capacity returned. Nothing protected the
asset but luck.

WHAT THIS ASSERTS, AND WHY IT IS A PROPERTY (rule 11)

Not "the file contains the string publish-archive". It reads every
workflow, finds the ones that actually touch the release asset — by
looking for the upload verbs in their steps, not by name — and requires
that all of them declare the SAME concurrency group with
`cancel-in-progress: false`. Add a third publisher and this fails until
it joins the group; rename the group everywhere and it still passes.

`cancel-in-progress` must be false: a half-finished publish is worse
than a delayed one.
"""
import os
import sys

try:
    import yaml
except ImportError:                       # pragma: no cover
    print("  skip  PyYAML not installed in this environment")
    print("FAILING: none")
    sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")

failures = []


def check(label, ok):
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def steps_text(doc):
    """All run/with text in a workflow, flattened."""
    out = []
    for job in (doc.get("jobs") or {}).values():
        for step in (job.get("steps") or []):
            if not isinstance(step, dict):
                continue
            out.append(str(step.get("run") or ""))
            out.append(str(step.get("uses") or ""))
            out.append(str(step.get("with") or ""))
    return "\n".join(out)


# A workflow publishes if it uploads to a release. Keyed on the verbs,
# not on the workflow's name — a rename must not silently exempt it.
PUBLISH_MARKERS = ("gh release upload", "gh release create",
                   "softprops/action-gh-release", "actions/upload-release")

publishers = {}
for fn in sorted(os.listdir(WF)):
    if not fn.endswith((".yml", ".yaml")):
        continue
    doc = yaml.safe_load(open(os.path.join(WF, fn), encoding="utf-8"))
    if not isinstance(doc, dict):
        continue
    body = steps_text(doc)
    if any(m in body for m in PUBLISH_MARKERS):
        publishers[fn] = doc.get("concurrency")

print(f"  workflows that publish the archive: {sorted(publishers)}")

check("at least two publishers found (else this test proves nothing)",
      len(publishers) >= 2)

for fn, conc in publishers.items():
    check(f"{fn} declares a concurrency block", isinstance(conc, dict))

groups = {fn: (c or {}).get("group") for fn, c in publishers.items()}
distinct = {g for g in groups.values() if g}
check(f"all publishers share ONE group (found: {sorted(distinct)})",
      len(distinct) == 1 and len(groups) == len(publishers)
      and all(groups.values()))

for fn, conc in publishers.items():
    if isinstance(conc, dict):
        check(f"{fn} does not cancel a publish in progress",
              conc.get("cancel-in-progress") is False)

print("FAILING:" + (" " + ", ".join(failures) if failures else " none"))
sys.exit(1 if failures else 0)
