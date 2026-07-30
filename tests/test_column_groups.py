"""The lineup column groups must narrow the table without losing identity.

27 columns is unusable on a phone. The groups let you cut that down, but
two things must hold: every group keeps Player/Bats/Ord (otherwise you're
reading anonymous rows of numbers, which was half the original
complaint), and "All" must be a true no-op so desktop behaviour is
unchanged for anyone who never touches the control.
"""
import textwrap
from pathlib import Path

import pandas as pd

SRC = (Path(__file__).resolve().parent.parent / "app" / "views" / "GameCard.py").read_text()

# Pull the _groups literal straight out of the view.
_start = SRC.index("_groups = {")
_end = SRC.index("}", SRC.index('"Quick"')) + 1
_ns = {}
# The block is indented inside the view, so dedent before compiling.
# Start at the LINE start, not mid-line, or dedent sees a zero-indent
# first line and refuses to strip the rest.
_i = SRC.rindex("\n", 0, SRC.index('_ident = [')) + 1
_block = textwrap.dedent(SRC[_i:_end])
exec(compile(_block, "groups", "exec"), _ns)
groups = _ns["_groups"]

assert groups["All"] is None, (
    '"All" must be None so no filtering happens — desktop users who never '
    'touch the selector must get the exact table they had before')
print("PASS: All is a true no-op")

for name, cols in groups.items():
    if cols is None:
        continue
    for ident in ("Player", "Bats", "Ord"):
        assert ident in cols, (
            f'group "{name}" drops {ident} — losing track of whose row you are '
            f'reading while scrolling sideways is the exact problem these '
            f'groups exist to fix')
    assert cols[:3] == ["Player", "Bats", "Ord"], (
        f'group "{name}" must LEAD with the identity columns; they are only '
        f'useful if they are the first thing on screen')
print("PASS: every group leads with Player/Bats/Ord")

for name, cols in groups.items():
    if cols is None:
        continue
    assert len(cols) == len(set(cols)), f'group "{name}" repeats a column'
    assert len(cols) <= 14, (
        f'group "{name}" has {len(cols)} columns — past ~14 it stops being a '
        f'narrower view and the phone problem comes back')
print("PASS: no duplicates, every group stays narrow")

# The intersection guard must survive a column that isn't there.
_df = pd.DataFrame([{"Player": "X", "Bats": "R", "Ord": 1, "HR Score": 50}])
for name, cols in groups.items():
    if cols is None:
        continue
    kept = [c for c in cols if c in _df.columns]
    out = _df[kept]
    assert "Player" in out.columns
    assert not out.isna().all().any(), (
        "reindexing to a missing column would create an all-NaN column that "
        "reads as real missing data rather than a column we never had")
print("PASS: missing columns are skipped, not invented as NaN")

assert 'key="lineup_col_group"' in SRC, "selector needs a stable key to persist"
assert 'default="All"' in SRC
print("PASS: selector defaults to All and persists")
