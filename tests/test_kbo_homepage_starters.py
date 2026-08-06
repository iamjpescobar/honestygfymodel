"""KBO probables come off the mykbostats HOMEPAGE, not the game page.

WHY THIS TEST EXISTS

kbo_precompute reported `0 had at least one probable posted` on every
run for weeks, including one at 16:49 KST — an hour forty before first
pitch, when starters are long since announced. Nothing raised, because
parse_starters() searched for <div class="away-starter"> and a regex
that matches nothing returns an empty dict silently. KBO pitcher
matchups ran blind the whole time. No number was fabricated (probable
stayed None and was never guessed) but the boards had less behind them
than they looked.

Four probe runs from Actions established why: mykbostats shipped
"v3 Build 886 (2026-08-04)", an Elixir/Phoenix rewrite. On an upcoming
game page the words probable / starter / pitcher / 선발 / 예고 all count
ZERO, there is no JSON blob, /games/{slug}.json returns HTML and
/games/{slug}/probables 404s. The homepage carries them instead.

So this pins the replacement against the REAL captured text, and pins
the two rules that keep a silent-empty from happening again: ids are
never aligned on a guess, and a game with no line is omitted rather
than recorded as blank.

The fixture strips to exactly the text the live homepage rendered on
2026-08-05. The parser strips tags before matching, so testing against
that text tests precisely what the parser consumes — the surrounding
class names are deliberately NOT part of the contract, because they
have already changed once and will change again.

Plain script, like everything in tests/ — exits non-zero on failure.
No network.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kbo_precompute as kp  # noqa: E402

# The module source, read once. Several checks below assert on it
# directly: this file's whole history is regexes that matched nothing
# and returned an empty dict without raising, so "the code still says
# what we think it says" is itself part of the contract.
_src = (ROOT / "kbo_precompute.py").read_text(encoding="utf-8")

failures = []


def check(label, ok):
    if not ok:
        failures.append(label)


def card(slug, body):
    return f'<a class="ds-game-card" href="/games/{slug}"><div>{body}</div></a>'


# The five 2026-08-05 cards as the homepage actually rendered them,
# including the heat warning on the 35 degree game at Jamsil.
HOME = (
    card("13777-Hanwha-vs-Samsung-20260805",
         "Hanwha Eagles Samsung Lions 31&deg; 6:30pm Daegu "
         "<span>Starters: Park Jun-yeong vs. Chris Paddack</span>")
    + card("13778-KT-vs-Kia-20260805",
           "KT Wiz Kia Tigers 32&deg; 6:30pm Gwangju "
           "<span>Starters: Allen vs. Oller</span>")
    + card("13779-LG-vs-SSG-20260805",
           "LG Twins SSG Landers 33&deg; 6:30pm Incheon-Munhak "
           "<span>Starters: Im Chan-kyu vs. Hatch</span>")
    + card("13780-NC-vs-Doosan-20260805",
           "NC Dinos Doosan Bears 35&deg; 6:30pm Seoul-Jamsil "
           "Chance of Heat Cancellation "
           "<span>Starters: Thompson vs. Choi Min-seok</span>")
    + card("13781-Kiwoom-vs-Lotte-20260805",
           "Kiwoom Heroes Lotte Giants 30&deg; 6:30pm Busan-Sajik "
           "<span>Starters: An Woo-jin vs. Park Se-woong</span>")
    + '<a href="/stats/compare?pids=15400%2C15284%2C15357%2C15404%2C15448'
      '%2C15496%2C15581%2C15745%2C15735%2C15784">Compare starting pitchers</a>'
)

got = kp.parse_homepage_starters(HOME)

check("all five games parsed", len(got) == 5)
check("keyed by numeric game id", "13777" in got and "13781" in got)

g = got.get("13777", {})
check("away starter name", g.get("away_starter") == "Park Jun-yeong")
check("home starter name", g.get("home_starter") == "Chris Paddack")

# A single-word romanised surname, which the old two-anchor structure
# handled differently from a full name. Both shapes ship on one slate.
check("single-name starters", got.get("13778", {}).get("away_starter") == "Allen"
      and got.get("13778", {}).get("home_starter") == "Oller")

# The heat warning sits between the venue and the Starters line. A
# greedy or line-anchored match would swallow it into the away name.
check("heat warning does not leak into the name",
      got.get("13780", {}).get("away_starter") == "Thompson")
check("hyphenated home name survives",
      got.get("13780", {}).get("home_starter") == "Choi Min-seok")

# Ids: two per game, in slate order, off the compare link.
check("first game gets the first pid pair",
      got.get("13777", {}).get("away_starter_id") == "15400"
      and got.get("13777", {}).get("home_starter_id") == "15284")
check("last game gets the last pid pair",
      got.get("13781", {}).get("away_starter_id") == "15735"
      and got.get("13781", {}).get("home_starter_id") == "15784")

# ---- the two rules that prevent a silent wrong answer ---------------

# A mismatched pid count must drop ids ENTIRELY rather than align them.
# An id on the wrong pitcher is worse than no id: every downstream
# lookup would confidently describe a different player.
short = HOME.replace(
    "pids=15400%2C15284%2C15357%2C15404%2C15448%2C15496%2C15581%2C15745"
    "%2C15735%2C15784", "pids=15400%2C15284")
bad = kp.parse_homepage_starters(short)
check("mismatched pid count leaves every id unset",
      all(v.get("away_starter_id") is None and v.get("home_starter_id") is None
          for v in bad.values()))
check("names still parse when ids are dropped", len(bad) == 5)

# A canceled or not-yet-announced game carries no Starters line. It must
# be OMITTED, so the caller can tell "nothing announced" from
# "announced as nothing" — measured live at 06:36 KST on a heat-canceled
# slate, where every card lacked the line.
none_yet = card("13900-Kia-vs-LG-20260810",
                "Kia Tigers LG Twins Canceled Extreme Heat")
check("a card with no Starters line is omitted",
      kp.parse_homepage_starters(none_yet) == {})
check("an empty page yields an empty dict",
      kp.parse_homepage_starters("") == {})

# The key set every consumer reads. KBO.py, run_total, kbo_k_projection
# and matchup_grades_intl all index these, so a rename here breaks four
# boards at once.
# Superset, not equality: entries now also carry hp_time / hp_venue,
# which the caller consumes and does not ship. Every starter key every
# consumer reads must still be present.
check("full starter key set present", set(kp._STARTER_KEYS) <= set(g))
check("only the starter keys reach the slate row",
      '{k: (s or {}).get(k) for k in _STARTER_KEYS}' in _src)
check("the two readers are separate functions",
      "def parse_homepage_schedule(" in _src)
check("_no_starters matches that key set",
      set(kp._no_starters()) == set(kp._STARTER_KEYS)
      and all(v is None for v in kp._no_starters().values()))

# The dead game-page parser must not come back: it matched nothing for
# weeks without raising, and re-adding it would reinstate exactly that.
check("no live away-starter div regex remains",
      'class="{cls}"' not in _src)
check("the caller fetches the homepage once, not per game",
      "fetch_homepage_starters()" in _src
      and "fetch_starters_for_game(" not in _src)


# ---- 6. time and venue, read SEPARATELY from the starters ------------
# parse_week() reads both off the schedule page keyed on
# <div class="venue"> and a datetime= attribute. The v3 rewrite killed
# those too, so every KBO card rendered "TBD - TBD KST / TBD ET" — the
# third and fourth regex in that file to die to one redesign.
#
# They are a separate reader because membership of the starters map
# means "this game has announced starters", and test_kbo_heat_risk
# depends on that. Measured live at 13:13 KST: every card had a time and
# a venue and NOT ONE had a starter, which is exactly the game a bettor
# most needs to see.
NO_SP = card("13792-Kiwoom-vs-Lotte-20260806",
             "Kiwoom Heroes Lotte Giants 30&deg; 6:30pm Busan-Sajik")
only = kp.parse_homepage_schedule(NO_SP).get("13792", {})
check("a starterless card still yields venue", only.get("venue") == "Busan-Sajik")
check("a starterless card still yields time", only.get("time") == "6:30pm")
check("a starterless card stays OUT of the starters map",
      kp.parse_homepage_starters(NO_SP) == {})

# The heat warning sits between venue and starters; a greedy match would
# ship a city called "Seoul-Jamsil Chance of Heat Cancellation".
check("heat warning does not leak into the venue",
      kp.parse_homepage_schedule(HOME).get("13780", {}).get("venue")
      == "Seoul-Jamsil")

# 12-hour to 24-hour, including noon and midnight — the two every naive
# converter gets wrong.
check("evening start converts", kp._kst_24h("6:30pm") == "18:30")
check("noon converts", kp._kst_24h("12:00pm") == "12:00")
check("midnight converts", kp._kst_24h("12:30am") == "00:30")
check("junk yields None rather than an invented time",
      kp._kst_24h("later") is None and kp._kst_24h("") is None)

# KST->ET goes through real timezones. Korea has no DST and the US does,
# so the gap is 13 hours for part of the year and 14 for the rest —
# subtracting a constant would be wrong for half the season.
check("summer KST->ET uses the 13-hour gap",
      kp._kbo_et("2026-08-06", "18:30") == "5:30 AM")
check("winter KST->ET uses the 14-hour gap",
      kp._kbo_et("2026-01-15", "18:30") == "4:30 AM")
check("an unparseable date stays TBD",
      kp._kbo_et("not-a-date", "18:30") == "TBD")

# A scraped value must still WIN — this is a fallback, not a takeover.
# If parse_week ever starts working again, this quietly stops firing.
check("the repair only fires on TBD",
      'str(g.get("stadium") or "").upper() == "TBD"' in _src
      and 'str(g.get("time_kst") or "").upper() == "TBD"' in _src)

if failures:
    print("FAIL:", "; ".join(failures))
    sys.exit(1)
print("PASS: homepage supplies starters, venue and start time; guess-free")
