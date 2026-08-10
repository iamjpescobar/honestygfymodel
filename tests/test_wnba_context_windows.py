"""A context column's HEADER must match the window of the data in it.

WHAT HAPPENED. The Volume and Stocks tabs carried bare "FTA", "TO",
"STL", "BLK" columns holding SEASON averages, sitting immediately to the
right of four columns explicitly labelled Season / L5 / L10 / vs OPP.
Read left to right, a season FTA lands one column after an L10 FGA and
inherits its window in the reader's head. On a props page the window IS
the claim — "6 free throw attempts" means something completely different
over five games than over a season — so a column whose header does not
carry its window is not a smaller version of the right answer, it is a
wrong one.

The headers were fixed to say "szn". This test stops them drifting back,
and stops the opposite drift: a column labelled L5 that is quietly fed
the season key.

WHY IT ASSERTS THE PAIRING AND NOT THE SPELLING (rule 11). It does not
check that any particular column exists — columns are a product decision
and this file has no business freezing them. It checks the PROPERTY: for
every context column added to a row, the window named in the header and
the window of the key it reads must agree. Add a column, rename one,
drop one — this test stays quiet. Feed "FTA L5" the season key and it
goes red, which is the only thing it is here to catch.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "app" / "views" / "WNBA.py").read_text()

failures = []

# row["<header>"] = p.get("<key>") — the context columns only. The four
# primary columns are built from variables (season_k, l5_k, ...) rather
# than literals and are not what drifted.
PAIRS = re.findall(r'row\[\s*"([^"]+)"\s*\]\s*=\s*p\.get\(\s*"([^"]+)"\s*\)', SRC)

if not PAIRS:
    failures.append("found no row[...] = p.get(...) pairs at all — the "
                    "table construction moved and this test is now blind")

# header token -> the prefix the key must carry. "" means a bare
# season key with no window prefix.
WINDOWS = {"szn": "", "l5": "l5_", "l10": "l10_"}


def _window_in(header: str):
    """Which window the HEADER claims, or None if it claims none."""
    h = header.lower()
    for token in ("l10", "l5", "szn"):
        # Word-ish match so a header like "BLKL5X" doesn't count and,
        # more importantly, so "vs OPP" isn't read as claiming one.
        if re.search(rf"(^|[^a-z0-9]){token}([^a-z0-9]|$)", h):
            return token
    return None


checked = 0
for header, key in PAIRS:
    claimed = _window_in(header)
    if claimed is None:
        # No window claimed. That is allowed for a genuinely
        # window-less column (FG%, GP, Status) but NOT for one whose key
        # is windowed — a column reading l5_fta while saying only "FTA"
        # is the original bug with the label removed instead of fixed.
        if re.match(r"^l\d+_", key):
            failures.append(
                f'column "{header}" reads windowed key {key!r} but its '
                f'header names no window — the reader inherits the '
                f'window of whatever column sits to its left')
        continue

    checked += 1
    want = WINDOWS[claimed]
    if want:
        if not key.startswith(want):
            failures.append(
                f'column "{header}" claims {claimed.upper()} but reads '
                f'{key!r}, which is not a {claimed} key')
    else:
        if re.match(r"^l\d+_", key):
            failures.append(
                f'column "{header}" says season but reads {key!r}, '
                f'which is a windowed key')

if checked == 0 and not failures:
    failures.append("no column claimed a window at all — either the "
                    "labels lost their suffixes or the pattern above "
                    "stopped matching; both are the bug this catches")

# THE PAIR IS THE POINT. A recent-form column is unreadable without its
# baseline: "6 FTA over five games" only means something next to the
# season figure, because the reader is looking for the CHANGE. Asserted
# as a property of the tab, not as a list of column names — if Volume
# stops carrying FTA entirely this stays quiet, and it only bites when a
# windowed column is shipped orphaned.
_stems = {}
for header, key in PAIRS:
    claimed = _window_in(header)
    if claimed is None:
        continue
    stem = re.sub(r"^l\d+_", "", key)
    _stems.setdefault(stem, set()).add(claimed)

for stem, windows in sorted(_stems.items()):
    if "szn" not in windows and windows:
        failures.append(
            f"{stem!r} ships a recent-form column ({', '.join(sorted(windows))}) "
            f"with no season column beside it — a recent number with no "
            f"baseline cannot be read as high or low")

print("=" * 60)
if failures:
    for f in failures:
        print(f"FAIL: {f}")
    sys.exit(1)

print(f"PASS: {checked} windowed context column(s), header and key agree")
print(f"PASS: every recent-form column keeps its season baseline")
print()
print("A column header that hides its window is a wrong number, not a "
      "smaller right one.")
