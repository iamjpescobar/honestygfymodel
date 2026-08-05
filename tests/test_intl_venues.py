"""Roof status for KBO/NPB, and the distinction that makes it safe.

WHY IT MATTERS. Both leagues report a postponement only after it is
announced, which is routinely after a bet is placed. Voids followed. A
forecast needs a weather provider the site doesn't have; a roof needs
nothing, and half the NPB slate plays under one.

THE FAILURE THIS GUARDS. "We don't know this venue" and "this venue is
open air" must never collapse into each other. Defaulting an unknown
stadium to open air invents a rain risk that may not exist; defaulting
it to domed hides one that does. Either way the badge asserts something
nobody measured, on a screen someone is betting off. Unknown returns
None and the views render nothing at all.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines.intl_venues import (  # noqa: E402
    roof, rainout_possible, roof_note, NPB_VENUES, KBO_VENUE_PATTERNS)

failures = []

# --- the certain answers ---------------------------------------------
for venue in ("Tokyo Dome", "Vantelin Dome", "Kyocera Dome Osaka",
              "PayPay Dome", "Belluna Dome"):
    if rainout_possible("npb", venue) is not False:
        failures.append(f"{venue} is a fixed roof and must be un-rainable")
if not failures:
    print(f"PASS: {sum(1 for v in NPB_VENUES.values() if v == 'dome')} NPB "
          f"domes report rain-out impossible")

if rainout_possible("kbo", "Gocheok Sky Dome") is not False:
    failures.append("Gocheok is KBO's only dome and must be un-rainable")
else:
    print("PASS: Gocheok Sky Dome reports rain-out impossible")

# --- open air is a real answer too ------------------------------------
for venue in ("Koshien Stadium", "Jingu Stadium", "Yokohama Stadium"):
    if rainout_possible("npb", venue) is not True:
        failures.append(f"{venue} is open air and must be rainable")
if rainout_possible("kbo", "Jamsil Baseball Stadium") is not True:
    failures.append("Jamsil is open air and must be rainable")
else:
    print("PASS: open-air parks report rain-out possible")

# --- THE ONE THAT MATTERS: unknown is not open ------------------------
# A neutral site, a newly opened park, a club that moved buildings, a
# venue string the scrape mangled. All of these are "we don't know".
for league, venue in (("npb", "Some New Park"), ("kbo", "Unknown Field"),
                      ("npb", ""), ("kbo", None), ("mlb", "Fenway Park")):
    if rainout_possible(league, venue) is not None:
        failures.append(
            f"{league}/{venue!r} resolved to a definite answer — an unknown "
            f"venue must be None, never assumed open or domed, because the "
            f"badge is something people bet off")
    if roof_note(league, venue) != "":
        failures.append(f"{league}/{venue!r} produced a UI note for a venue "
                        f"nothing is known about")
if not failures:
    print("PASS: unknown venues return None and render nothing")

# --- retractable is labelled separately -------------------------------
# Escon's roof closing is a decision someone makes, not a property of
# the building. It shouldn't silently merge into "dome".
if roof("npb", "Escon Field") != "retractable":
    failures.append("Escon Field is retractable, not a fixed dome")
elif "roof" not in roof_note("npb", "Escon Field").lower():
    failures.append("the Escon note doesn't say the roof is the reason")
else:
    print("PASS: retractable roofs are labelled distinctly from fixed domes")

# Belluna is roofed with open sides — the note must not claim a sealed
# building even though it counts as un-rainable.
_bn = roof_note("npb", "Belluna Dome")
if "open sides" not in _bn:
    failures.append("the Belluna note doesn't mention its open sides, so it "
                    "overstates what the building actually is")
else:
    print("PASS: Belluna is un-rainable but described accurately")

# --- the tables must match what the scrapers actually emit ------------
# roof() keys on the venue STRING. If npb_precompute renames a stadium
# in its STADIUMS map and this table isn't updated, every game there
# silently degrades to None — no badge, no error, nobody notices.
npb_src = (ROOT / "npb_precompute.py").read_text()
emitted = set(re.findall(r':\s*"([A-Za-z][^"]*(?:Stadium|Dome|Park|Field)[^"]*)"',
                         npb_src))
missing = sorted(e for e in emitted if e not in NPB_VENUES)
if missing:
    failures.append("npb_precompute emits venue names this table has never "
                    "heard of, so they render no badge at all: "
                    + ", ".join(missing))
else:
    print(f"PASS: all {len(emitted)} venue names npb_precompute emits are "
          f"classified")

# --- the views must actually use it -----------------------------------
for view in ("KBO", "NPB"):
    src = (ROOT / "app" / "views" / f"{view}.py").read_text()
    if "intl_venues" not in src:
        failures.append(f"{view} no longer reads roof status — the void "
                        f"warning is gone from the page")
else:
    print("PASS: both international views render the roof badge")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nA domed game cannot be rained out. Everything else, we say we "
      "don't know.")
