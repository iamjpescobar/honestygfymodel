"""The pitcher splits table offers real windows, and never a rate
without its denominator.

WHY THIS EXISTS

The Game Card's STATS / STRIKES tables were SEASON ONLY, on a page whose
entire job is tonight's matchup. A starter's season line can be four
months old. Every other window control in the app — the grade window ten
lines above it, the lineup filter, Bullpen Board, Player of the Day —
already offered one; these three rows did not.

Adding it is easy. Adding it honestly is the part with a failure mode.

THE FAILURE MODE

`Last game` is roughly 25 batters faced. A .400 BA against on one night
renders in the same column, the same font and the same colour scale as a
.240 over 700 at-bats, and NOTHING on screen distinguishes them. That is
not a hypothetical about this table: statcast_engine already carries a
long comment about the empty-split case rendering "BA .000, SLG .000,
WHIP 0.00" — a line describing the most dominant pitcher who ever lived —
and its stated reason is that "the table has no sample column to
contradict it."

It has one now, and this file is what keeps it there. The three things
that must not silently regress:

  1. the window options exist and map to real slicer keys;
  2. every rendered column set carries the sample (G) — including
     STRIKES, which had no IP column and so had no denominator at all;
  3. the thin windows are declared next to the slicing code, not
     hardcoded in the view, so the warning list cannot drift away from
     the window list.

Source-asserted rather than rendered, because the view needs streamlit
and a live Statcast pull. Same posture as test_calibration_picks and
test_no_dead_renderers.
"""
import ast
import os
import re
import sys

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "app"))

from engines.recency_windows import (  # noqa: E402
    apply_window, WINDOW_LABELS, THIN_WINDOWS,
)

failures = []


def check(label, ok):
    if ok:
        print(f"PASS: {label}")
    else:
        failures.append(label)


# ----------------------------------------------------------------------
# 1. THE SLICER ACTUALLY SLICES. Twelve games, ten pitches each.
# ----------------------------------------------------------------------
df = pd.DataFrame({
    "game_date": sum([[f"2026-08-{d:02d}"] * 10 for d in range(1, 13)], []),
    "game_pk": sum([[d] * 10 for d in range(1, 13)], []),
    "at_bat_number": list(range(120)),
    "pitch_number": [1] * 120,
})

for window, expected in (("season", 12), ("l10", 10), ("l5", 5),
                         ("l3", 3), ("l1", 1)):
    got = apply_window(df, window, "games")["game_pk"].nunique()
    check(f"{window!r} keeps {expected} game(s)", got == expected)

# An unknown window returns the SEASON, never an empty frame. A typo
# showing more data than asked for is recoverable; one showing none reads
# as "this pitcher has no history", which is a false statement about a
# real player.
check("an unrecognised window falls back to the season, not to empty",
      len(apply_window(df, "l99", "games")) == len(df))

check("l3 and l1 are labelled for any caller that renders them",
      WINDOW_LABELS.get("l3") and WINDOW_LABELS.get("l1"))

# ----------------------------------------------------------------------
# 2. THE VIEW OFFERS THEM, AND THE KEYS ARE REAL.
#
# The options dict is parsed out of the source and every value checked
# against the slicer, so a control offering a window that apply_window
# does not implement — which would silently render season data under a
# "Last 3" label — fails here.
# ----------------------------------------------------------------------
gc = open(os.path.join(ROOT, "app", "views", "GameCard.py"), encoding="utf-8").read()

m = re.search(r"_sw_opts = (\{[^}]*\})", gc, re.S)
check("the splits window control exists", m is not None)
if m:
    opts = ast.literal_eval(m.group(1))
    check("it offers Season, L10, L5, L3 and Last game",
          set(opts.values()) == {"season", "l10", "l5", "l3", "l1"})
    bad = [v for v in opts.values()
           if v != "season" and len(apply_window(df, v, "games")) == len(df)]
    check("every offered window really slices (none is season in disguise)",
          not bad)

    # The window has to reach the fetch. A control wired to nothing looks
    # identical to a working one — it just always shows the season.
    check("the selected window is passed to get_pitcher_advanced_splits",
          re.search(r"get_pitcher_advanced_splits\([^)]*window=_splits_window",
                    gc, re.S) is not None)

# ----------------------------------------------------------------------
# 3. THE DENOMINATOR IS ALWAYS ON SCREEN.
#
# This is the assertion that matters. STRIKES is the one that had no
# sample at all — no IP column, no games — so a Last-game K% rendered
# with nothing beside it.
# ----------------------------------------------------------------------
for name in ("stats_cols", "strikes_cols"):
    mm = re.search(rf"{name} = (\[[^\]]*\])", gc, re.S)
    if not mm:
        failures.append(f"{name} not found")
        continue
    cols = ast.literal_eval(mm.group(1))
    check(f"{name} carries the games count", "G" in cols)
    check(f"{name} puts it before the rates it qualifies",
          cols.index("G") <= 2)

check("STATS still carries IP alongside G",
      "IP" in ast.literal_eval(re.search(r"stats_cols = (\[[^\]]*\])", gc, re.S).group(1)))

# G must not be gradient-coloured. It is a sample size, not a
# performance stat — shading it would say more games is better or worse,
# and neither is a claim this table gets to make.
for fav in re.findall(r"favor_(?:high|low)=(\[[^\]]*\])", gc):
    if "G" in ast.literal_eval(fav):
        failures.append("G appears in a favor_high/favor_low list — a sample "
                        "size must not be colour-ranked as a stat")
        break
else:
    check("G is never colour-ranked as if it were a stat", True)

# ----------------------------------------------------------------------
# 4. THE WARNING LIST LIVES WITH THE WINDOWS.
# ----------------------------------------------------------------------
check("THIN_WINDOWS covers the short windows the control offers",
      {"l1", "l3", "l5"}.issubset(THIN_WINDOWS))
check("the season is never marked thin", "season" not in THIN_WINDOWS)
check("the view imports THIN_WINDOWS rather than hardcoding a list",
      "THIN_WINDOWS" in gc)
check("a thin window warns the reader above the table",
      re.search(r"_splits_window in THIN_WINDOWS", gc) is not None)

# ----------------------------------------------------------------------
# 5. NO ORPHANED FETCH LEFT BEHIND.
#
# splits_vs_r / splits_vs_l were the old season-only fetches and the
# Matchup table was their only consumer. Left in place they would be two
# cached calls whose results nothing reads — rule 20, in the same commit
# that fixed a different instance of it.
# ----------------------------------------------------------------------
tree = ast.parse(gc)
assigned = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name)}
used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
        and isinstance(n.ctx, ast.Load)}
for dead in ("splits_vs_r", "splits_vs_l"):
    check(f"{dead} is not left assigned-and-unread",
          dead not in assigned or dead in used)

if failures:
    print()
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(1)

print("\nA rate is only as good as the sample under it, so the sample is shown.")
