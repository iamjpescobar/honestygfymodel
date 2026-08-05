"""Every HR metric that gets computed must reach a screen.

WHY THIS EXISTS

The pitcher-allowed metrics were computed by _compute_batted_ball_metrics
and aliased under "Allowed" names, and for a stretch nothing rendered
them. A comment in statcast_engine saying so outlived the fix by long
enough to send someone hunting for work that had already been done —
so the codebase was wrong in both directions at once: metrics with no
screen, then a note claiming metrics had no screen when they did.

A number that is measured every night and shown nowhere is pure cost:
it burns nightly minutes, rides in the archive, and pays nothing back.
This test is cheap insurance that the pipeline and the pages stay
connected, in both directions:

  * every metric key the engine emits has somewhere it can be seen
  * every column the views ask for is a key the engine actually emits
    (a typo'd profile.get() returns None forever and renders as N/A,
    which looks exactly like missing data rather than like a bug)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "app" / "engines" / "statcast_engine.py").read_text()
VIEWS = {p.name: p.read_text() for p in (ROOT / "app" / "views").glob("*.py")}
ENGINES = {p.name: p.read_text() for p in (ROOT / "app" / "engines").glob("*.py")}
ALL_UI = "\n".join(list(VIEWS.values()) + list(ENGINES.values()))

failures = []

# The metric keys the batted-ball layer promises. Read off the `empty`
# dict, which is the function's own declaration of its shape — not a
# list maintained here, which would drift the moment someone adds a
# metric and forgets this file.
m = re.search(r"empty = \{(.*?)\n    \}", ENGINE, re.S)
assert m, "the `empty` metrics dict moved — this test can't find the contract"
keys = set(re.findall(r'"([^"]+)":', m.group(1)))
keys = {k for k in keys if not k.startswith("_")}

# Bookkeeping, not display: counts and flags nothing renders directly.
NOT_DISPLAYED = {"BBE", "PA", "AB", "FB_count"}

unrendered = []
for k in sorted(keys - NOT_DISPLAYED):
    if f'"{k}"' not in ALL_UI:
        unrendered.append(k)
if unrendered:
    failures.append(
        "computed nightly and shown on no screen: " + ", ".join(unrendered)
        + " — either render it or stop computing it")
else:
    print(f"PASS: all {len(keys - NOT_DISPLAYED)} displayable metrics reach a screen")

# --- the new HR columns, specifically ---------------------------------
# These are the ones just added, and the ones most likely to be dropped
# by a future refactor of the tables they live in.
for col, where in (("FB95 %", "GameCard.py"),
                   ("ClearsAnywhere %", "GameCard.py"),
                   ("HRThreat", "GameCard.py"),
                   ("FB95 % Allowed", "GameCard.py"),
                   ("ClearsAnywhere % Allowed", "GameCard.py")):
    if f'"{col}"' not in VIEWS.get(where, ""):
        failures.append(f"{col} is no longer read by {where}")
if not failures:
    print("PASS: the new hitter and pitcher-allowed columns are on the Game Card")

board = VIEWS.get("HR_Edge_Board.py", "")
for key in ("hr_threat", "clears_anywhere"):
    if key not in board:
        failures.append(f"HR Edge Board no longer shows {key}")
if "hr_threat" in board and "clears_anywhere" in board:
    print("PASS: HR Edge Board shows the threat composite and no-doubt rate")

# rank_batters must actually attach them, or the board reads None forever.
top = ENGINES.get("top_plays.py", "")
for key in ("hr_threat", "clears_anywhere_pct", "fb95_pct"):
    if key not in top:
        failures.append(f"rank_batters no longer attaches {key}; the board "
                        f"would render N/A with nothing to explain it")
else:
    print("PASS: rank_batters attaches the slate-wide HR metrics")

# --- reverse direction: views must not ask for keys that don't exist --
# profile.get("Typo %") returns None forever and renders as N/A, which
# is indistinguishable from a hitter with no measured contact.
asked = set()
for name, src in VIEWS.items():
    asked |= set(re.findall(r'profile\.get\("([^"]+)"\)', src))
    asked |= set(re.findall(r'pitcher_data\.get\("([^"]+)"\)', src))

ALIASED = set(re.findall(r'\("([^"]+)", "([^"]+)"\)', ENGINE))
known = set(keys)
for src, dst in ALIASED:
    if src in known:
        known.add(dst)
# Names the engine adds outside the `empty` contract.
known |= {k for k in re.findall(r'metrics\["([^"]+)"\]', ENGINE)}
known |= {k for k in re.findall(r'out\["([^"]+)"\] = ', ENGINE)}

phantom = sorted(a for a in asked
                 if a not in known and f'"{a}"' not in ENGINE)
if phantom:
    failures.append("views read metric keys the engine never emits — these "
                    "render as N/A forever: " + ", ".join(phantom))
else:
    print(f"PASS: all {len(asked)} metric keys the views request are real")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nNothing is measured for a screen that doesn't show it.")
