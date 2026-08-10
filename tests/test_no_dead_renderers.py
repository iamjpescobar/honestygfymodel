"""Every renderer a view defines must actually be invoked by that view.

WHY THIS EXISTS

Rule 20 says a computed field nobody renders is not a feature. This repo
has now been bitten by that idea in three different disguises, each one a
layer further from the data than the last:

  1. COMPUTED, NEVER RENDERED. The international weather pipeline was
     complete and correct for days while every board showed nothing, and
     the Open-Meteo licence credit printed for data that never appeared.

  2. WRITTEN, NEVER CALLED. parse_homepage_schedule() was correct and
     tested and had no production caller, while main() unpacked two
     values from a one-value function and KBO died on every run with 66
     tests green. That produced rule 22 and tests/test_return_arity.py.

  3. RENDERED, NEVER INVOKED — this file. app/views/KBO.py defined
     _render_batting_leaders() in full: it loaded batters.json, formatted
     AVG/HR/RBI/SB/OBP/SLG and drew a card. Nothing called it. Meanwhile
     kbo_precompute fetched, sorted and wrote batters.json on every
     single run, printing "wrote N batters to batters.json" into the
     Actions log to prove it. The pipeline published KBO batting leaders
     every night, for months, to nobody. The KBO board also carried a
     "What launches first" card promising Team Profiles while the data
     behind them sat unrendered on disk.

None of the three is caught by anything else in the suite, because a
function that is never called is syntactically perfect. Nothing fails.
Nothing logs. The page simply lacks a section, and a missing section
looks exactly like a section that was never built — which is why this
one survived so long.

WHAT THIS CHECKS

For every file in app/views/, every module-level function whose name
starts with _render must appear as a call — `name(` — somewhere else in
that same file.

WHY THAT RULE AND NOT A GENERAL ONE

A general "unused function" check over the whole repo is noise: engines
export helpers for other modules, tests import things by name, and
callers reach across files constantly. A VIEW is different. A view is a
script that runs top to bottom to draw one page; a renderer defined there
and called nowhere in it cannot be drawing anything, and cannot be for
another module either, because nothing imports a view. That makes the
check exact rather than heuristic — see rule 11: assert the property, not
the spelling.

Deliberately narrow: _render_* only. Loaders, formatters and helpers are
legitimately shared or conditionally used. A renderer is not.

No imports of streamlit, no network, no data files — this parses source
with ast and runs anywhere, which is the point of catching it in CI
rather than by opening the page.
"""
import ast
import os
import re
import sys

VIEWS = "app/views"

# Views that intentionally define no renderers at all are fine; this
# only ever complains about one that defines a renderer and drops it.
PREFIX = "_render"

failures = []
checked = 0
renderers = 0

for fn in sorted(os.listdir(VIEWS)):
    if not fn.endswith(".py") or fn == "__init__.py":
        continue
    path = os.path.join(VIEWS, fn)
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    checked += 1

    defs = [n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith(PREFIX)]

    for node in defs:
        renderers += 1
        name = node.name
        # Count calls by NAME rather than by scanning for the identifier,
        # so the def line itself and any mention in a comment or docstring
        # don't count as a call. A renderer passed to st.fragment() is
        # invoked too — st.fragment(f)() and the decorator form both show
        # up as the bare name, so accept a reference that is an argument
        # to fragment as well as a direct call.
        called = False
        for other in ast.walk(tree):
            if isinstance(other, ast.Call):
                f = other.func
                if isinstance(f, ast.Name) and f.id == name:
                    called = True
                    break
                # st.fragment(...)(_render_slate) and
                # st.fragment(_render_slate) — the renderer arrives as an
                # argument, and the wrapper is what gets called.
                for arg in list(other.args) + [kw.value for kw in other.keywords]:
                    if isinstance(arg, ast.Name) and arg.id == name:
                        called = True
                        break
                if called:
                    break
        if not called:
            failures.append(
                f"{path}:{node.lineno}  {name}() is defined and never invoked — "
                f"whatever it draws does not appear on the page")

if failures:
    for f in failures:
        print("FAIL:", f)
    raise SystemExit(1)

print(f"PASS: {renderers} renderers across {checked} views, every one invoked")

# THE EXACT REGRESSION, pinned by name.
#
# The general check above is the real guard; this is the one instance that
# actually shipped, so it cannot come back quietly if someone narrows the
# scan later. KBO publishes both leaderboards and must draw both.
kbo = open(os.path.join(VIEWS, "KBO.py"), encoding="utf-8").read()
for who in ("_render_pitching_leaders", "_render_batting_leaders"):
    # Calls only: subtract the single `def` occurrence.
    calls = len(re.findall(r"(?<!def )\b" + who + r"\(", kbo))
    assert calls >= 1, (
        f"KBO.py defines {who}() but never calls it. kbo_precompute writes "
        f"both leaderboards on every run; a board that draws one of them is "
        f"publishing the other into silence.")
print("PASS: KBO draws both the pitching and the batting leaderboard")
