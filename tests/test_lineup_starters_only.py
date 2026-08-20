"""Nine slots, nine names — a substitute is not a starter.

THE BUG THIS PINS

MLB encodes the batting slot in the hundreds and the order WITHIN that
slot in the tens and units. The starter batting fourth is "400". The man
who pinch-hits for him is "401". The next replacement is "402".

get_confirmed_lineup skipped a player only when battingOrder was falsy,
and "401" is not falsy. So every substitute came back as a starter.

WHY IT HID FOR SO LONG. On a CONFIRMED lineup this is invisible: MLB
posts the card before first pitch, no substitutions have happened, and
every value really is x00. It only surfaced through the PROJECTED
fallback, which calls the same function on a game that has ALREADY BEEN
PLAYED. Cincinnati on 2026-08-20 came back with eleven starters for nine
slots — Suarez and Hayes both showing Ord 4, Toglia and Friedl both
showing Ord 6.

WHY IT MATTERS MORE THAN A COSMETIC DUPLICATE. The extra name is a bat
who specifically did NOT start, presented as one who did, on the card a
reader uses to decide who is playing. And a visibly impossible lineup —
two men batting fourth — undermines every correct number beside it.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "app" / "engines" / "roster.py").read_text(encoding="utf-8")
failures = []

# --- 1. THE FILTER EXISTS AND IS THE RIGHT ONE -----------------------
#
# Pinned as "a modulo-100 test guards the batting order", not as an
# exact line, so the check survives reformatting but not deletion.
_fn = src[src.index("def get_confirmed_lineup"):]
_fn = _fn[:_fn.index("\n@st.cache_data")]
if "battingOrder" not in _fn:
    failures.append("get_confirmed_lineup no longer reads battingOrder")
if not re.search(r"int\(\s*batting_order\s*\)\s*%\s*100", _fn):
    failures.append(
        "get_confirmed_lineup does not test batting_order % 100. Without it "
        "every substitute ('401', '402') is returned as a starter, and the "
        "projected lineup shows two men batting fourth.")
else:
    print("PASS: the batting order is filtered to multiples of 100")

# --- 2. A NON-NUMERIC VALUE DROPS THE ROW, IT DOES NOT RAISE ---------
#
# MLB has typed this as a string throughout. A page that is otherwise
# fine should not 500 because one field arrived unexpected.
if not re.search(r"except\s*\(\s*TypeError\s*,\s*ValueError\s*\)", _fn):
    failures.append(
        "the batting-order conversion is unguarded — a non-numeric value "
        "would raise on a card that is otherwise fine")
else:
    print("PASS: a non-numeric batting order drops the row rather than raising")

# --- 3. THE RULE ITSELF, EXECUTED ------------------------------------
#
# The regex above proves the guard is written. This proves it is
# correct, by running the same arithmetic over the real encoding.
STARTERS = ["100", "200", "300", "400", "500", "600", "700", "800", "900"]
SUBS = ["101", "401", "402", "703", "901"]
kept = [b for b in STARTERS + SUBS if int(b) % 100 == 0]
if kept != STARTERS:
    failures.append(f"the modulo rule keeps {kept}, expected the nine starters")
elif len(kept) != 9:
    failures.append(f"a starting lineup is nine slots, this rule keeps {len(kept)}")
else:
    print("PASS: nine starters kept, every substitute dropped")

# --- 4. ONE NAME PER SLOT --------------------------------------------
#
# The symptom a reader actually sees. Two bats sharing an Ord is the
# thing that must never render again.
_slots = [int(b) // 100 for b in kept]
if len(set(_slots)) != len(_slots):
    failures.append("two starters share a batting slot — the original bug")
else:
    print("PASS: no two starters share a batting slot")

# --- 5. THE POOL TOGGLE CANNOT CONTRADICT THE FLOOR ------------------
#
# Separate bug, same screenshot. The returning-bat floor announced
# "held back from the table: Will Banfield" and Full roster mode then
# added Banfield to the table, three lines below. Both true, the pair
# nonsense.
#
# The floor decides who is worth ASSERTING into a projected nine, so it
# has to be conditional on which pool is being built — which means the
# mode must be resolved BEFORE the floor runs, not after.
gc = (ROOT / "app" / "views" / "GameCard.py").read_text(encoding="utf-8")
_i_mode = gc.find("_full_roster = ")
_i_floor = gc.find("_RET_MIN_PA_PER_GAME):")
if _i_mode < 0:
    failures.append("GameCard no longer resolves a pool mode")
elif _i_floor < 0:
    failures.append("the returning-bat floor is gone from GameCard")
elif _i_mode > _i_floor:
    failures.append(
        "the pool mode is resolved AFTER the returning-bat floor, so the "
        "floor cannot know which pool it is gating — the exact ordering "
        "that printed 'held back' above a table containing that player")
elif "if _held and not _full_roster" not in gc:
    failures.append(
        "the held-back caption is not gated on the pool mode, so it will "
        "name bats that Full roster mode goes on to show")
else:
    print("PASS: the floor and its caption are gated on the pool mode")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1)
print("\nTwo men batting fourth is not a rounding error.")
