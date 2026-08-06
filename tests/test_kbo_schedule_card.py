"""parse_week reads venue and first pitch off a v3 SCHEDULE card.

WHY THIS EXISTS

Every KBO card rendered `TBD - TBD KST / TBD ET` after the mykbostats
v3 rewrite killed `<div class="venue">`. Probe run 84409273265 fetched
the week of 2026-08-18 from Actions and dumped a real upcoming card, so
this is written against bytes, not against a description of bytes.

Round 1 of that probe fetched the CURRENT week instead and reported
`'pm': 0` and `datetime=: 0`, which read as "the schedule page has no
time or venue at all" and nearly got item V2 closed as impossible. It
was wrong for a reason worth remembering: every game in that window was
already played or heat-canceled, and a finished card shows a score
where an upcoming one shows a clock. **A probe that samples the wrong
rows answers the wrong question.** Round 2 asked for a week two weeks
out and got the opposite answer.

THE TRAP THIS PINS

`ds-game-card__sub is-prose` holds the VENUE on an upcoming card and
the words "Extreme Heat" on a canceled one. Keying on that class would
put a weather note into the stadium field, and `venue_for_game()` would
then hunt for coordinates for a city called Extreme Heat, miss, and
fall back silently. Requiring a clock immediately before the venue is
what separates them.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kbo_precompute as kp  # noqa: E402

failures = []


def check(label, ok):
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def anchor(slug, inner):
    return f'<a id="game-line-x" class="ds-game-card " href="/games/{slug}">{inner}</a>'


# ---- the three real card shapes, copied from run 84409273265 --------
UPCOMING = """
  <div class="ds-game-card__teams">
    <div class="ds-game-team "><span class="ds-game-team__name">
      Kia<span class="ds-game-team__suffix"> Tigers</span></span></div>
    <div class="ds-game-team "><span class="ds-game-team__name">
      Hanwha<span class="ds-game-team__suffix"> Eagles</span></span></div>
  </div>
  <div class="ds-game-card__details">
    <div class="ds-game-card__status">
      <span class="ds-game-card__state is-time ">
        <time data-format="%l:%M%P" data-local="time"
              datetime="2026-08-18T10:00:00Z">
   7:00pm
</time>
      </span>
      <span class="ds-game-card__sub is-prose">Daejeon</span>
    </div>
  </div>
"""

CANCELED = """
  <div class="ds-game-card__teams">
    <div class="ds-game-team is-muted"><span class="ds-game-team__name">
      Hanwha<span class="ds-game-team__suffix"> Eagles</span></span></div>
    <div class="ds-game-team is-muted"><span class="ds-game-team__name">
      Samsung<span class="ds-game-team__suffix"> Lions</span></span></div>
  </div>
  <div class="ds-game-card__details">
    <div class="ds-game-card__status">
      <span class="ds-game-card__state">Canceled</span>
      <span class="ds-game-card__sub is-prose">
              Extreme Heat
            </span>
    </div>
  </div>
"""

FINAL = """
  <div class="ds-game-card__teams">
    <div class="ds-game-team "><span class="ds-game-team__name">
      Hanwha<span class="ds-game-team__suffix"> Eagles</span></span>
      <span class="ds-game-team__score">4</span></div>
    <div class="ds-game-team is-muted"><span class="ds-game-team__name">
      Samsung<span class="ds-game-team__suffix"> Lions</span></span>
      <span class="ds-game-team__score">1</span></div>
  </div>
  <div class="ds-game-card__details">
    <div class="ds-game-card__status">
      <span class="ds-game-card__state ">Final</span>
    </div>
  </div>
"""

# ---- 1. the reader in isolation --------------------------------------
t, v = kp._card_time_venue(UPCOMING)
check("an upcoming card yields a 24h first pitch", t == "19:00")
check("an upcoming card yields the venue", v == "Daejeon")

t, v = kp._card_time_venue(CANCELED)
check("a canceled card yields no time", t is None)
check('"Extreme Heat" is NEVER read as a venue', v is None)

t, v = kp._card_time_venue(FINAL)
check("a final card yields no time", t is None)
check("a final card yields no venue", v is None)

# A score must never be mistaken for a clock. 4 and 1 are adjacent in
# the final card's text and a looser pattern would find "4 1" reachable.
check("no clock is invented from a scoreline",
      kp._card_time_venue(FINAL)[0] is None)


# ---- 2. through parse_week, which is what actually ships -------------
page = (anchor("13832-Kia-vs-Hanwha-20260818", UPCOMING)
        + anchor("13782-Hanwha-vs-Samsung-20260806", CANCELED)
        + anchor("13772-Hanwha-vs-Samsung-20260804", FINAL))
games = {g["game_id"]: g for g in kp.parse_week(page, "2026-08-06", None)}
check("all three cards parse", len(games) == 3)

up = games.get("13832", {})
check("parse_week ships the venue", up.get("stadium") == "Daejeon")
check("parse_week ships KST", up.get("time_kst") == "19:00")
# Korea keeps no DST and the US does, so this must go through a real
# conversion rather than a fixed offset.
check("parse_week ships a real ET conversion",
      up.get("time_et") not in (None, "", "TBD"))

can = games.get("13782", {})
check("a canceled game keeps stadium TBD", can.get("stadium") == "TBD")
check("a canceled game keeps time TBD", can.get("time_kst") == "TBD")

fin = games.get("13772", {})
check("a final keeps stadium TBD", fin.get("stadium") == "TBD")


# ---- 3. the markup key must still win --------------------------------
# If mykbostats ever restores <div class="venue">, the scraped value has
# to beat the text fallback — that is what makes this a fallback and not
# a second source of truth.
WITH_DIV = UPCOMING.replace(
    '<span class="ds-game-card__sub is-prose">Daejeon</span>',
    '<div class="venue">Daejeon Baseball Stadium</div>')
g2 = list(kp.parse_week(anchor("13999-Kia-vs-Hanwha-20260818", WITH_DIV),
                        "2026-08-06", None))
check("a restored venue div beats the text fallback",
      g2 and g2[0]["stadium"] == "Daejeon Baseball Stadium")


# ---- 4. the reader is shared, not copied -----------------------------
# Rule 18 killed four regexes in this file to one redesign. The homepage
# and the schedule page render the same shape, so they read it with the
# same pattern; a second copy is how they drift apart.
_src = open(kp.__file__, encoding="utf-8").read()
check("the card reader reuses the homepage pattern",
      "HOME_TIME_VENUE.search" in _src
      and _src.count("HOME_TIME_VENUE = ") == 1)

print("FAILING:" + (" " + ", ".join(failures) if failures else " none"))
sys.exit(1 if failures else 0)
