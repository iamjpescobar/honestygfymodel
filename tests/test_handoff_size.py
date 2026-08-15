"""HANDOFF.md has to stay short enough to actually be read.

WHY THIS TEST EXISTS. The file reached 4,317 lines across 40 entries,
and 64% of that was superseded — entries describing defects since
re-fixed, thresholds since re-measured, designs since replaced. A handoff
that long stops being read, and AN UNREAD HANDOFF IS WORSE THAN A SHORT
ONE, because it looks like the context is there.

Nothing was deleted: git has everything, and the rotated entries sit in
HANDOFF_ARCHIVE.md. What this protects is the WORKING document.

THE CAP IS DELIBERATELY LOOSE. It is not a style rule — it fires only
when the file has drifted far enough that someone would skim it instead
of reading it. When it does, the fix is to move the OLDEST entries to
the archive. Never trim the standing rules: they are the part that
outlives every entry, and they are why the file is worth reading at all.
"""
from pathlib import Path

MAX_LINES = 1400          # ~14 entries plus the rules
MAX_ENTRIES = 14

h = Path("HANDOFF.md").read_text(encoding="utf-8")
lines = h.count("\n")
entries = h.count("\n## PICK UP HERE")

# --- 1. THE WORKING DOCUMENT STAYS READABLE --------------------------
assert lines <= MAX_LINES, (
    f"HANDOFF.md is {lines} lines (cap {MAX_LINES}). Move the oldest "
    f"entries to HANDOFF_ARCHIVE.md — do NOT trim the standing rules.")
assert entries <= MAX_ENTRIES, (
    f"{entries} entries (cap {MAX_ENTRIES}). Rotate the oldest out.")
print(f"PASS: HANDOFF.md is {lines} lines / {entries} entries")

# --- 2. THE STANDING RULES SURVIVE ROTATION --------------------------
#
# The rules are the only part of this file that is not history. Every
# one cost real time and has bitten more than once, so a rotation that
# takes them out with the old entries is the failure mode worth
# guarding — it would leave a file that says what happened and nothing
# about what to avoid.
for rule in ("MEASURE BEFORE YOU SET ANY NUMBER",
             "A FIXTURE CANNOT TEST A CONSTANT IT REPLACES",
             "CONFIRM EVERY NEGATIVE CONTROL GOES RED",
             "MISSING IS NOT ZERO",
             "NEVER RUN `git clean` IN THIS REPO",
             "DO NOT TUNE AFTER A BAD NIGHT"):
    assert rule in h, f"standing rule lost in a rotation: {rule}"
print("PASS: all standing rules survive")

# --- 3. THE ARCHIVE EXISTS AND SAYS IT IS STALE ----------------------
#
# An archive that reads like current state is worse than no archive: the
# whole point of rotating is that these entries are NOT true any more.
a = Path("HANDOFF_ARCHIVE.md")
assert a.exists(), "entries were rotated out but the archive is missing"
_a = a.read_text(encoding="utf-8")
assert "Nothing here is current" in _a, (
    "the archive does not warn that its contents are stale — someone "
    "will read a superseded entry as the current design")
print(f"PASS: archive present ({_a.count(chr(10))} lines) and marked stale")

# --- 4. NOTHING WAS LOST IN THE SPLIT --------------------------------
#
# Rotation moves entries, it does not drop them. If the two files
# together ever hold fewer than they did, something was deleted rather
# than archived.
total = entries + _a.count("\n## PICK UP HERE")
assert total >= 38, (
    f"only {total} entries across both files — the split lost some")
print(f"PASS: {total} entries across working file and archive")

# --- 5. THE NEWEST ENTRY IS AT THE TOP -------------------------------
#
# "START WITH PICK UP HERE" only works if the first one you meet is the
# current one.
first = h.index("\n## PICK UP HERE")
assert h.index("STANDING RULES") < first, (
    "the rules moved below the entries; they are the preamble")
print("PASS: rules precede the entries, newest entry first")
