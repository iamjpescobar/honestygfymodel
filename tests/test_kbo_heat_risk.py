"""
The KBO heat-cancellation warning must survive a redesign, and must not
invent calm weather.

WHY THIS EXISTS

parse_starters() died silently in the mykbostats Aug 2026 rewrite and
nobody noticed for weeks, because nothing ever ran it against a page.
This pins the conditions reader against the real card text so the same
thing cannot happen twice.

Plain script, not pytest. Exits non-zero on failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kbo_precompute as K

failures = []

# Real shape, captured from the homepage: an at-risk card, a clear card
# carrying the entity form of the degree sign, and a card with neither.
HTML = (
    '<a href="/games/13777-Hanwha-vs-Samsung-20260806">'
    'Hanwha Eagles Samsung Lions 31° 6:30pm Daegu '
    'Chance of Heat Cancellation</a>'
    '<a href="/games/13778-Lotte-vs-KT-20260806">'
    'Lotte Giants KT Wiz 27&deg; 6:30pm Suwon '
    'Starters: Park Jun-yeong vs. Chris Paddack</a>'
    '<a href="/games/13779-SSG-vs-NC-20260806">'
    'SSG Landers NC Dinos 6:30pm Changwon</a>'
)

cond = K.parse_homepage_conditions(HTML)

if cond.get("13777", {}).get("heat_risk") is not True:
    failures.append("an at-risk game was not flagged")
else:
    print("PASS: Chance of Heat Cancellation is read as a risk")

if cond.get("13777", {}).get("temp_c") != 31:
    failures.append("temperature not read from the literal degree sign")
elif cond.get("13778", {}).get("temp_c") != 27:
    failures.append("temperature not read from the &deg; entity form")
else:
    print("PASS: temperature reads in both degree forms")

if cond.get("13778", {}).get("heat_risk") is not False:
    failures.append("a clear game was flagged at risk")
else:
    print("PASS: a clear game is False, not missing")

# A card with no temperature and no warning is OMITTED, so a caller can
# tell "nothing published" from "published as fine". Same contract the
# starters parser keeps.
if "13779" in cond:
    failures.append("a card with neither reading was recorded anyway")
else:
    print("PASS: a card with nothing to say is omitted, not guessed")

# The two readers must stay independent: a heat warning routinely lands
# on a game whose pitchers are not announced, which is the game a bettor
# most needs warned about.
st = K.parse_homepage_starters(HTML)
if "13777" in st:
    failures.append("heat-only game leaked into the starters map")
elif st.get("13778", {}).get("home_starter") != "Chris Paddack":
    failures.append("starters parsing broke")
else:
    print("PASS: starters and conditions stay independent")

# Negative control: if the risk pattern matched anything, the suite
# would pass while telling every bettor every game is at risk.
if K.parse_homepage_conditions(
        '<a href="/games/1-A-vs-B-20260806">A B 24° 6:30pm</a>'
).get("1", {}).get("heat_risk") is not False:
    failures.append("risk pattern fires on a card that does not mention heat")
else:
    print("PASS: negative control - no warning means no risk")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nAll KBO heat-risk checks passed.")
