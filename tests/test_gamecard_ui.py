"""Row labels survive rendering, and every window control offers L25.

WHY THIS EXISTS

Three separate defects, all invisible to the existing suite because
they live in view code that no test imports.

  1. THE MISSING NAMES. The bullpen "vs this arsenal" table rendered
     nine anonymous stat rows: batter names gone. Cause was exact and
     documented in the codebase's own docstring —
     `render_html_table` requires the row label to be a real COLUMN,
     because `_base_styler` calls `.hide(axis="index")` before
     rendering. The view called `.set_index("Player")`, so the names
     were dropped on the way in. `HR_Edge_Board` did the same with
     `set_index("#")` and lost its rank column.

     This is a whole CLASS of bug, not one instance, so the test scans
     every view rather than pinning the two we happened to find.

  2. THE UNLABELLED SWITCH HITTER. A switch hitter renders two or three
     rows — one per platoon side, plus a combined one when no probable
     is posted. The combined row was labelled with a bare "S" while its
     siblings were "S (L)" and "S (R)", so the reader saw the same
     player at the same batting order with different numbers and no way
     to tell which was which. It is now "S (both)", which is what it
     actually is: every PA from both sides. Labelling it "S (L)" would
     have been worse than the bare S — a confident wrong answer.

  3. L25 MISSING FROM ONE PICKER. `apply_window` has always mapped l25,
     and every other window control in the app offered it. The Game
     Card's lineup Window was the only one that didn't.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS = os.path.join(ROOT, "app", "views")

failures = []


def check(label, ok):
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def view_src(name):
    return open(os.path.join(VIEWS, name), encoding="utf-8").read()


# ---- 1. no view hands a set_index frame to the HTML renderer --------
# The PROPERTY, not the spelling (rule 11): any set_index() in a view is
# suspect, because _base_styler hides the index for every table that
# goes through style_stat_table/render_html_table.
offenders = []
for fn in sorted(os.listdir(VIEWS)):
    if not fn.endswith(".py"):
        continue
    src = view_src(fn)
    for m in re.finditer(r"\.set_index\(", src):
        line = src[:m.start()].count("\n") + 1
        offenders.append(f"{fn}:{line}")
check(f"no view calls .set_index() before styling (found: {offenders or 'none'})",
      not offenders)

# And the renderer's contract is still the one we're relying on — if
# someone stops hiding the index, this test should stop mattering and
# we want to notice.
ts = open(os.path.join(ROOT, "app", "styles", "table_style.py"),
          encoding="utf-8").read()
check("_base_styler still hides the index (the reason for the rule above)",
      'hide(axis="index")' in ts)


# ---- 2. switch-hitter rows all say which side they are --------------
gc = view_src("GameCard.py")
check("the combined switch row is labelled, not bare",
      '"S (both)"' in gc)
# The dangerous near-miss: labelling the combined row with a side.
check("the combined row is NOT labelled with a platoon side",
      not re.search(r'else\s+f?[\'"]S \(\{_own\}\)', gc))
check("tonight's side still renders as S->side when a probable is posted",
      "S\\u2192{_tonight}" in gc or "S\u2192{_tonight}" in gc)
# _bats_column must colour a label naming a side, and leave "both" alone.
sys.path.insert(0, os.path.join(ROOT, "app"))
import pandas as pd  # noqa: E402
from styles.table_style import _bats_column  # noqa: E402
styles = _bats_column(pd.Series(["S (L)", "S (R)", "S (both)", "R", "L"]))
check("split rows get a platoon colour", styles[0] and styles[1])
check("the combined row stays neutral, not miscoloured as a side",
      styles[2] == "")
check("plain L/R still colour", styles[3] and styles[4])


# ---- 3. every window control offers L25 -----------------------------
from engines.recency_windows import apply_window  # noqa: E402
check("the engine supports l25 (it always did)",
      apply_window.__doc__ and "l25" in apply_window.__doc__)

WINDOW_VIEWS = {
    "GameCard.py": ("Last 25 Games", "L25"),
    "Bullpen_Board.py": ("L25",),
    "Player_Of_The_Day.py": ("L25",),
    "WNBA.py": ("L25",),
}
for fn, needles in WINDOW_VIEWS.items():
    src = view_src(fn)
    for n in needles:
        check(f"{fn} offers {n}", n in src)


# ---- 4. the game picker is a carousel, not a pager ------------------
check("no page state left in the game picker",
      "gc_page" not in gc and "PAGE_SIZE" not in gc)
check("the carousel renderer exists and is called",
      gc.count("_render_game_carousel") >= 2)
check("the strip is scoped to its own container key, not a global rule",
      "st-key-gc_gamestrip" in gc)
check("selection state and callback are unchanged",
      "gc_selected_game_idx" in gc and "on_click=_pick_game" in gc)
# The clamp that stopped an IndexError when the slate shrinks must
# survive the rewrite — it was a real crash, not a nicety.
check("the shrinking-slate clamp survived the rewrite",
      'min(\n        st.session_state["gc_selected_game_idx"], len(games) - 1)' in gc)


# ---- 5. weak spots render in ONE language ---------------------------
check("weak spots go through a single renderer",
      "_render_weak_spots" in gc)
# THE INVARIANT CHANGED, DELIBERATELY, AND THIS IS WHY.
#
# It used to be "every group uses the same row unit" (>= 5 _ws_group
# calls), which was right when the panel was a bar stack: one shape,
# repeated, no hand-rolled variants.
#
# Three groups are now SPATIAL because their data is. A pitch type
# carries two numbers (usage and damage) and a bar draws one, so usage
# was demoted to a subtitle where it stopped being comparable.
# Up/middle/down is a strike zone that was drawn sideways. Times through
# the order is a three-point trend drawn as three unconnected bars.
#
# The rule the old check was really protecting — DON'T HAND-ROLL A NEW
# VISUAL LANGUAGE INLINE IN THE VIEW — still holds, and is what these
# assert: the spatial panels come from one engine module, and whatever
# stays a bar still goes through the one bar renderer.
check("the spatial panels come from weakspot_view, not inline SVG",
      "from engines.weakspot_view import" in gc)
check("the view hand-rolls no SVG of its own",
      "<svg" not in gc)
check("remaining bar groups still use the one row unit",
      gc.count("_ws_group(") >= 2)
check("the legend is drawn, not just described",
      "below its sample floor" in gc and "_WS_FLOOR" in gc)
# A missing value must still occupy space — a vanishing row is how
# "not measured" gets misread as "fine". Exercise the real function
# rather than grepping for a phrase: extract _ws_bar and run it with a
# stub palette, so this tests behaviour and survives any rewording.
_fn = re.search(r"^def _ws_bar\(.*?(?=^def _ws_group)", gc, re.S | re.M)
check("_ws_bar is extractable", bool(_fn))
if _fn:
    _ns = {"COLOR": {k: "#111111" for k in ("error", "warn", "stat_high", "text")},
           "XSLG_HOT": 0.550, "XSLG_COLD": 0.380,
           "_WS_FLOOR": 0.250, "_WS_CEIL": 0.800}
    exec(_fn.group(0), _ns)
    _bar = _ns["_ws_bar"]
    _none = _bar(None, "12 bbe")
    check("an unmeasured value still renders a sized track",
          "height:14px" in _none)
    check("an unmeasured value renders NO filled portion",
          "width:" not in _none)
    check("an unmeasured value says so with an em dash",
          "\u2014" in _none)
    # Length must encode the number, so two different values cannot
    # render the same bar — that is the whole point of moving off a
    # colour-only heatmap.
    _w = lambda v: re.search(r"width:([\d.]+)%", _bar(v, "")).group(1)
    check("a worse xSLG draws a longer bar", float(_w(0.700)) > float(_w(0.400)))
    check("the scale is clamped, not overflowing",
          float(_w(0.950)) <= 100.0 and float(_w(0.100)) >= 0.0)


# ---- 6. the chip must not discard the label it was given -------------
# The label fix above was correct and STILL showed a bare "S" on screen,
# because bats_chip() rendered `str(v)[:1]`. Two layers, and fixing one
# without the other changes nothing a reader can see — rule 20: follow
# the signal to the pixel.
from styles.table_style import bats_chip  # noqa: E402
_chip = bats_chip()
_strip = lambda h: re.sub(r"<[^>]+>", "", h)  # noqa: E731
for _lbl in ("S (both)", "S (L)", "S (R)"):
    check(f"the chip keeps {_lbl!r} intact", _strip(_chip(_lbl)) == _lbl)
check("a plain L still renders as L", _strip(_chip("L")) == "L")
check("the chip does not shout the label", _strip(_chip("S (both)")) != "S (BOTH)")
check("a missing hand renders an em dash", _strip(_chip(None)) == "\u2014")
# Colour still keys off the leading letter, so a qualified switch label
# is coloured as a switch hitter rather than falling through uncoloured.
check("a qualified switch label is still coloured",
      "background:" in _chip("S (L)"))
check("the chip cannot wrap inside a narrow column",
      "white-space:nowrap" in _chip("S (both)"))

print("FAILING:" + (" " + ", ".join(failures) if failures else " none"))
sys.exit(1 if failures else 0)
