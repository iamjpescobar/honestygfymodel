"""The long windows slice real data, and every label the UI offers works.

WHY THESE EXIST. A 25-game window is about 110 plate appearances. HR
rate needs ~170 PA and ISO ~160 AB to carry real signal, so the longest
window the Game Card offered sat UNDER both — every power read on the
lineup table was taken on a sample too thin for the stat. l50 / l75 and
l200 / l250 / l300 were added 2026-08-17 to get past that, and L15/L20/
L25 on the pitcher splits for the same reason on the other side.

THE WAYS THIS GOES WRONG ARE ALL SILENT:

  1. A label in the dropdown maps to a window key apply_window does not
     know. Unknown keys return the frame UNCHANGED — so the control
     would show "Last 250 PA" and quietly render the full season. No
     error, no empty table, just a wrong label on a right number.
  2. A window returns MORE rows than a shorter one, meaning the slice
     is not actually nested.
  3. Asking for more than a hitter has silently returns less than the
     label claims — real, unavoidable with a tail(), and the reason the
     control carries help text saying so.
"""
import ast
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines.recency_windows import (          # noqa: E402
    apply_window, WINDOW_LABELS, LONG_WINDOWS, THIN_WINDOWS)


def frame(n_games=90, pa_per_game=4, pitches_per_pa=4):
    """A season-shaped frame: real dates, real PA keys, real BBE rows."""
    rows = []
    for g in range(n_games):
        for ab in range(pa_per_game):
            for pitch in range(pitches_per_pa):
                rows.append({
                    "game_date": pd.Timestamp("2026-04-01") + pd.Timedelta(days=g),
                    "game_pk": 700000 + g,
                    "at_bat_number": ab + 1,
                    "pitch_number": pitch + 1,
                    # last pitch of each PA is a batted ball
                    "type": "X" if pitch == pitches_per_pa - 1 else "S",
                })
    return pd.DataFrame(rows)


DF = frame()

# --- 1. EVERY LABEL THE GAME CARD OFFERS RESOLVES ---------------------
#
# Parsed out of the view rather than retyped here. A list copied into a
# test agrees with itself forever and with the app never — this reads
# the same dict the dropdown reads.
gc_src = (ROOT / "app" / "views" / "GameCard.py").read_text(encoding="utf-8")
gc = ast.parse(gc_src)

offered = set()
controls = 0
for node in ast.walk(gc):
    if not isinstance(node, ast.Dict):
        continue
    keys = [k.value for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    if "Season" not in keys:
        continue
    controls += 1
    for k, v in zip(node.keys, node.values):
        if not isinstance(k, ast.Constant):
            continue
        # pitcher control maps label -> "l15"; lineup maps label -> tuple
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            offered.add(v.value)
        elif isinstance(v, ast.Tuple) and v.elts:
            first = v.elts[0]
            if isinstance(first, ast.Constant):
                offered.add(first.value)

# Count the CONTROLS, not the deduped keys: the three window pickers
# share most of their keys, so a key count is a weak guard and was wrong
# the first time it ran. Three dicts = grade window, pitcher splits,
# lineup window.
assert controls >= 3, (
    f"found {controls} window control(s) in GameCard, expected 3 (grade, "
    f"pitcher splits, lineup) — the AST walk is not finding them, so every "
    f"check below is vacuous")
assert {"l75", "l250", "l20"} <= offered, (
    f"the windows added 2026-08-17 are not reaching any control: "
    f"{sorted({'l75', 'l250', 'l20'} - offered)} missing")

known = set(WINDOW_LABELS) | {"season"}
unknown = {w for w in offered if w not in known}
assert not unknown, (
    f"GameCard offers window key(s) {sorted(unknown)} that recency_windows "
    f"does not know. apply_window returns the frame UNCHANGED for an "
    f"unrecognised key, so the control would read 'Last 250 PA' and render "
    f"the full season — a wrong label on a right number, which nothing "
    f"downstream can catch.")
print(f"PASS: all {len(offered)} window keys offered by the Game Card resolve")

# Every offered key must actually SLICE, not fall through the n lookup.
#
# Measured against a frame LONGER than the largest window in any unit —
# 90 games is only 360 PA, so a PA key like l300 would look like a
# no-op here for the wrong reason and the test would fail on a correct
# engine. The first version of this check did exactly that.
BIG = frame(n_games=320)
for w in sorted(offered - {"season"}):
    got = apply_window(BIG, w, "games")
    assert len(got) < len(BIG), (
        f"{w} returned the whole frame from a 320-game history — it is "
        f"missing from apply_window's n map and is silently a no-op, so the "
        f"control offering it renders the season under a shorter label")
print("PASS: every non-season key actually narrows the frame")

# --- 2. THE NEW WINDOWS ARE NESTED AND CORRECTLY SIZED ---------------
for unit, order in (("games", ["l75", "l50", "l25", "l15", "l10", "l5"]),
                    ("pa", ["l300", "l250", "l200", "l60", "l25", "l15"])):
    sizes = [len(apply_window(DF, w, unit)) for w in order]
    for a, b, wa, wb in zip(sizes, sizes[1:], order, order[1:]):
        assert a >= b, (
            f"{wa} ({a} rows) came back smaller than {wb} ({b}) in {unit} — "
            f"the windows are not nested, so a longer window is dropping data "
            f"a shorter one keeps")
print("PASS: long windows are nested and monotonic in both units")

# Exact sizes, so a wrong entry in the n map cannot pass by being merely
# monotonic (l50 typed as 5 would still be nested).
assert len(apply_window(DF, "l50", "games")) == 50 * 4 * 4, "l50 is not 50 games"
assert len(apply_window(DF, "l75", "games")) == 75 * 4 * 4, "l75 is not 75 games"
assert len(apply_window(DF, "l250", "pa")) == 250 * 4, "l250 is not 250 PA"
assert len(apply_window(DF, "l20", "games")) == 20 * 4 * 4, "l20 is not 20 games"
print("PASS: l20 / l50 / l75 / l250 slice exactly what they claim")

# --- 3. ASKING FOR MORE THAN EXISTS RETURNS EVERYTHING ---------------
#
# The unavoidable one. tail() cannot invent PAs a rookie never took, so
# "Last 300 PA" on a 40-game hitter is his whole season under a longer
# label. It must return ALL of it — the failure that would matter is
# returning nothing, which reads as "this hitter has no history".
small = frame(n_games=40)
got = apply_window(small, "l300", "pa")
assert len(got) == len(small), (
    f"a window longer than the data returned {len(got)} of {len(small)} rows; "
    f"it must return everything available, never an empty slice")
print("PASS: a window longer than the season returns the whole season")

# --- 4. THE CONTROL WARNS ABOUT THAT ---------------------------------
#
# "The reader cannot see the denominator unless you put it there" is
# already written into recency_windows for the thin windows. The long
# ones need the mirror image of it, and help text is the only place the
# reader will see it.
assert "lineup_window" in gc_src
help_block = gc_src.split('key="lineup_window"')[1][:900]
assert "help=" in help_block, "the lineup window control lost its help text"
assert "170 PA" in help_block, (
    "the help text no longer says why PA windows matter for power — the "
    "whole reason these were added is that 25 games is under the HR-rate "
    "stabilisation point")
assert "whole season" in help_block, (
    "the help text no longer warns that a window longer than a hitter has "
    "played silently returns less than the label claims")
print("PASS: the lineup control explains what the long windows do and don't give")

# --- 5. LONG AND THIN STAY DISJOINT ----------------------------------
assert not (LONG_WINDOWS & THIN_WINDOWS), (
    "a window is listed as both long and thin — the two sets carry opposite "
    "warnings and a caller reading either would be told the wrong thing")
for w in LONG_WINDOWS:
    assert w in WINDOW_LABELS, f"{w} is long but has no label"
print("PASS: LONG_WINDOWS and THIN_WINDOWS are disjoint and labelled")
