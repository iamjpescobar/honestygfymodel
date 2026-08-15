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
    # Ord before Bats: the slot is what you scan for when you already
    # know the lineup, and the hand is the second check. Changed with the
    # column reorder — the RULE (identity leads every group) is
    # unchanged, only which two of the three come second and third.
    assert cols[:3] == ["Player", "Ord", "Bats"], (
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


# ----------------------------------------------------------------------
# The HTML tables must SCROLL inside their card, never overflow it.
#
# These render two-up in st.columns. A flex item defaults to
# min-width:auto, so it refuses to shrink below its content width and
# overflow-x:auto never engages — the table spills out of its card and
# paints on top of the neighbouring one, producing overlapping digits
# where the two collide. Every property below is what prevents that.
# ----------------------------------------------------------------------
TS = (Path(__file__).resolve().parent.parent / "app" / "styles" / "table_style.py").read_text()
_css = TS[TS.index("_HTML_TABLE_CSS"):TS.index("def render_html_table")]

for prop, why in [
    ("min-width: 0",
     "the wrapper can't shrink below content width, so it overflows the card "
     "instead of scrolling"),
    ("max-width: 100%",
     "the wrapper is free to grow past its card and overlap the next column"),
    ('stColumn"]:has(.lc-tbl-wrap)',
     "Streamlit's own column wrapper is a flex item with the same "
     "min-width:auto default — without it the wrapper constraint never applies"),
    ("width: max-content",
     "forcing width:100% makes columns compress instead of scrolling"),
    ("overflow-x: auto",
     "no scroll container at all"),
]:
    assert prop in _css, f"{prop} missing from the HTML table CSS — {why}"
print("PASS: table overflow is contained and scrolls inside its card")

assert "!important" in _css[_css.index("td:first-child"):], (
    "the sticky label cell needs an opaque background: gradient-filled cells "
    "scroll UNDERNEATH it and would bleed through a transparent one")
print("PASS: sticky label column is opaque over scrolling cells")

assert "@media (max-width: 900px)" in _css, (
    "mobile sizing gone — desktop-sized padding on a phone is what made these "
    "tables unusable in the first place")
print("PASS: mobile media query retained, desktop sizing untouched")


# ----------------------------------------------------------------------
# The table CSS must be emitted on EVERY render, not once per session.
#
# This shipped broken. render_html_table guarded the <style> block with a
# session_state flag, but Streamlit rebuilds the DOM on every rerun: the
# flag survives, the style tag does not. So the tables looked right on
# first load and lost ALL their CSS the moment any filter was touched —
# no scroll container, no sticky column, default layout spilling out of
# the card and colliding with the table next to it.
# ----------------------------------------------------------------------
import sys as _sys
import types as _types

_st = _types.ModuleType("streamlit")
_st.session_state = {}
_emitted = []
_st.markdown = lambda h, **k: _emitted.append(h)
_st.cache_data = lambda **kw: (lambda f: f)
_sys.modules["streamlit"] = _st
_sys.path.insert(0, "app")
from styles.table_style import style_stat_table, render_html_table  # noqa: E402

_t = pd.DataFrame([{"Split": "Overall", "BB%": 13.2},
                   {"Split": "vs RHB", "BB%": 10.5}])

# Three renders sharing one session_state — an initial load followed by
# two reruns, which is what changing a filter produces.
for _run in (1, 2, 3):
    _emitted.clear()
    render_html_table(style_stat_table(_t, favor_low=["BB%"], gradient=True), key="t")
    _joined = "".join(_emitted)
    assert "lc-tbl-wrap {" in _joined, (
        f"render {_run} emitted no CSS. A once-per-session guard leaves every "
        f"rerun after the first with unstyled tables that overflow their card "
        f"and paint over the neighbouring one")
    assert "overflow-x: auto" in _joined and "position: sticky" in _joined
print("PASS: table CSS is re-emitted on every rerun, not once per session")

assert "_lc_html_tbl_css" not in TS, (
    "the once-only session flag is back — it makes the tables break on the "
    "first filter change, which is how this bug originally shipped")
print("PASS: no once-only CSS guard present")
