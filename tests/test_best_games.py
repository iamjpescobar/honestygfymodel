"""The best-games ranking (item C) sorts as decided, and Home leads with it.

WHY THIS EXISTS

The hero card is the first thing on the landing page of a betting site,
which makes two properties non-negotiable and both of them are easy to
break silently.

  1. IT MUST BE FORWARD-LOOKING. The design rule: past results must never
     sit where they could read as a suggestion for today's slate. A
     ranked list at the top of the page is the strongest suggestion the
     site makes, so it has to be about games not yet played.

  2. IT MUST NOT INVENT AN ORDER. A slate with no starters posted has
     nothing to rank on. Sorting it anyway produces alphabetical order
     wearing the costume of a ranking, and a reader has no way to tell
     the difference from what is on screen.

THE RANKING, AS DECIDED: biggest modeled edge, then highest projected run
total, then biggest weather/park swing. Closest matchup rejected.

This runs headlessly — engines/best_games.py imports no streamlit, makes
no network calls and reads no files, which is exactly why the ranking
lives there and not inside the view.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from engines.best_games import (  # noqa: E402
    rank_games, why_first, park_swing, has_any_signal, edge_reasons,
)


def g(name, **kw):
    row = {"away": name, "home": "H " + name}
    row.update(kw)
    return row


# EVERY FIXTURE BELOW NAMES ITS EXPECTED WINNER SO THAT THE WINNER SORTS
# ALPHABETICALLY LAST ("z-..."), AND THE LOSER FIRST ("a-...").
#
# This is not decoration. rank_games' final tiebreak is the team names,
# there so the card does not reshuffle between refreshes when two games
# tie on all three tiers. That tiebreak will happily produce the RIGHT
# answer for the WRONG reason: if a tier stops discriminating, the sort
# falls through to alphabetical, and a fixture whose expected winner
# happens to sort first still passes.
#
# It was caught by re-introducing the exact bug this file exists to
# prevent — making a missing edge sort as zero — and watching every
# assertion stay green. Three of the six ranking cases were being
# rescued that way. Naming the winner last inverts it: a broken tier now
# falls through to alphabetical and puts the LOSER first, which fails.
#
# If you add a case, name it the same way, then break the tier on purpose
# and check the case actually goes red. A ranking test that cannot fail
# is worse than no ranking test.


# ----------------------------------------------------------------------
# TIER 1 — modeled edge is the primary sort, and it beats everything.
# ----------------------------------------------------------------------
rows = [
    g("a-small-edge", edge_net=1, proj_total=12.0, park_factor=110, park_verified=True),
    g("z-big-edge", edge_net=4),
]
assert rank_games(rows)[0]["away"] == "z-big-edge", (
    "edge is tier 1: a 4-signal edge must outrank a 1-signal edge even when "
    "the weaker game wins on every other tier")
print("PASS: biggest modeled edge ranks first")

# ----------------------------------------------------------------------
# TIER 2 — projected run total breaks an edge tie, and nothing else does.
#
# MLB carries no proj_total today (run_total needs team RS/RA per game and
# nothing on disk has them for MLB). The tier is wired and tested anyway so
# it lights up the day the field appears, rather than being discovered
# broken then.
# ----------------------------------------------------------------------
rows = [
    g("a-low-total", edge_net=2, proj_total=7.5, park_factor=115, park_verified=True),
    g("z-high-total", edge_net=2, proj_total=11.0),
]
assert rank_games(rows)[0]["away"] == "z-high-total", (
    "tier 2: on equal edge, the higher projected total wins — and a bigger "
    "park swing must not override it, because the tiers are strict")
print("PASS: projected run total breaks an edge tie, ahead of park swing")

# ----------------------------------------------------------------------
# TIER 3 — weather/park swing breaks a tie on the first two.
# ----------------------------------------------------------------------
rows = [
    g("a-neutral", edge_net=2, weather_temp=72, park_factor=100, park_verified=True),
    g("z-wrigley-wind", edge_net=2, weather_temp=72, park_factor=100,
      park_verified=True, wind_adj=5.5, wind_note="14 mph blowing out (+5.5)"),
]
assert rank_games(rows)[0]["away"] == "z-wrigley-wind", (
    "tier 3: equal edge and equal (absent) total — the bigger environmental "
    "swing wins")
print("PASS: weather/park swing breaks a tie on the first two tiers")

# ----------------------------------------------------------------------
# CLOSEST MATCHUP WAS REJECTED. An even game is the one the model has
# least to say about, and it must not be promoted for being close.
# ----------------------------------------------------------------------
rows = [g("a-even", edge_net=0), g("z-lopsided", edge_net=3)]
assert rank_games(rows)[0]["away"] == "z-lopsided", (
    "closest-matchup was considered and rejected: a coin flip is the ABSENCE "
    "of a modeled opinion, not a reason to lead with a game")
print("PASS: an even matchup is not promoted")

# ----------------------------------------------------------------------
# MISSING IS NOT ZERO — the property this whole ranking rests on.
#
# A game with no posted starters has no edge. That must sort below a game
# measured AT zero, and must not be silently treated as either the best or
# the worst thing on the slate.
# ----------------------------------------------------------------------
rows = [g("a-unmeasured"), g("z-measured-zero", edge_net=0)]
assert rank_games(rows)[0]["away"] == "z-measured-zero", (
    "an unmeasured edge must sort below a measured zero — 'we looked and "
    "found nothing' is a different claim from 'we could not look'")
print("PASS: unmeasured sorts below measured zero")

# And per-tier, not per-game: a game missing ONLY the total still competes
# normally on edge.
rows = [
    g("z-no-total-big-edge", edge_net=4),
    g("a-has-total-small-edge", edge_net=1, proj_total=11.0),
]
assert rank_games(rows)[0]["away"] == "z-no-total-big-edge", (
    "a missing tier must not demote a game on the tiers it DOES have")
print("PASS: a missing tier doesn't cost a game the tiers it has")

# ----------------------------------------------------------------------
# park_swing: None means unmeasured, and 0.0 is a real measurement.
# ----------------------------------------------------------------------
assert park_swing(g("nothing"))[0] is None, (
    "no verified park, no wind, no temp — that is unmeasured, not neutral")
_score, _reasons = park_swing(g("a-neutral", weather_temp=72, park_factor=100,
                                park_verified=True))
assert _score == 0.0, "a neutral park on a mild night is a measured zero"
assert _reasons == [], "a measured zero has nothing to say about itself"
print("PASS: park swing tells unmeasured apart from neutral")

# An UNVERIFIED park factor is never read. park_factors ships verified=False
# for the Athletics (no re-verified number) and the Rays (a rolling figure
# spanning three different buildings); reading it here would reintroduce
# the exact bug that flag exists to prevent.
assert park_swing(g("rays", park_factor=97, park_verified=False))[0] is None, (
    "an unverified park factor must not contribute to the swing — the flag "
    "exists because the number looks perfectly fine")
print("PASS: an unverified park factor is not read")

# ----------------------------------------------------------------------
# has_any_signal — the guard that stops an unrankable slate rendering as
# a ranking.
# ----------------------------------------------------------------------
assert not has_any_signal([g("a"), g("b"), g("c")]), (
    "a slate with no edge, no total and no environment on any game has "
    "nothing to rank; the card must say so rather than sort alphabetically")
assert has_any_signal([g("a"), g("b", edge_net=1)])
assert has_any_signal([g("a", weather_temp=95)]), (
    "environment alone is a real signal — a 95-degree night is measured")
print("PASS: an unrankable slate is detectable before it is ranked")

# ----------------------------------------------------------------------
# why_first reports the tier the SORT actually used, not a nicer one.
# ----------------------------------------------------------------------
why = why_first(g("x", edge_net=3, edge_lean="Team A", edge_grade="B",
                  weather_temp=95))
assert "modeled edge" in why and "Team A" in why, why
why = why_first(g("x", weather_temp=95, wind_adj=5.0,
                  wind_note="14 mph blowing out (+5.0)"))
assert why is not None and "swing" in why, why
assert why_first(g("x")) is None, (
    "a game with nothing measured must produce no reason at all rather than "
    "a sentence that sounds like one")
print("PASS: the stated reason is the tier the sort used")

# Malformed rows must not take the landing page down.
assert rank_games([{}, None, g("ok", edge_net=1)])[0]["away"] == "ok"
assert rank_games(None) == []
print("PASS: a malformed slate row costs a card, not the page")

# ----------------------------------------------------------------------
# THE TIER-3 LABEL NAMES ONLY WHAT WAS MEASURED.
#
# This said "Biggest weather and park swing" unconditionally. Measured on
# the real 2026-08-10 slate: ten games, NOT ONE with a temperature or a
# wind, because MLB does not post either until close to first pitch and
# the 1 PM build ran six hours early. The swing came from the park factor
# alone, and the sentence claimed weather that had never been read.
#
# A wrong number is catchable. A right number under a wrong label is not
# — nothing on screen tells the reader which signals went into it.
# ----------------------------------------------------------------------
_park_only = g("a-park", park_factor=108, park_verified=True, venue="Fenway Park")
_why = why_first(_park_only)
assert "park" in _why and "weather" not in _why, (
    f"tier 3 measured the park and nothing else; the label must not say "
    f"weather. Got: {_why!r}")

_with_wind = g("a-wind", park_factor=108, park_verified=True, venue="Fenway Park",
               wind_adj=5.0, wind_note="14 mph blowing out (+5.0)")
assert "weather and park" in why_first(_with_wind), why_first(_with_wind)

_wind_only = g("a-w", park_verified=False, wind_adj=5.0,
               wind_note="14 mph blowing out (+5.0)")
_why = why_first(_wind_only)
assert "weather" in _why and "park" not in _why, (
    f"an unverified park contributes nothing, so the label must not claim "
    f"it. Got: {_why!r}")
print("PASS: the tier-3 label names only the signals it measured")

# park_swing's PUBLIC shape is unchanged — it still returns (score,
# reasons). The third value lives on _swing, so every existing caller and
# the four assertions above keep working.
assert len(park_swing(_park_only)) == 2
print("PASS: park_swing's public 2-tuple is unchanged")

# ----------------------------------------------------------------------
# edge_reasons — the signals were published and read by NOTHING.
#
# calibration_picks writes the real comparisons behind each grade
# ("WHIP: edge Boston Red Sox (1.28 vs 1.55)"). The card showed the
# letter and the lean — the conclusion — while the reasoning sat unread
# in the file. Rule 20, on the one page whose whole claim is "here is
# where the model has an opinion".
# ----------------------------------------------------------------------
assert edge_reasons({"edge_signals": ["a", "b", "c", "d"]}) == ["a", "b", "c"], \
    "capped at three: the hero card is a summary, not the Game Card"
assert edge_reasons({}) == []
assert edge_reasons({"edge_signals": "not a list"}) == [], \
    "a malformed field costs the reasons, not the page"
print("PASS: the edge signals reach the card instead of dying in the file")

# ----------------------------------------------------------------------
# HOME WIRING — the hero is FIRST, and it is the forward-looking one.
#
# Parsed rather than grepped: the ORDER of the calls inside render() is
# the property that matters, and a substring search cannot see order.
# Rule 11 — assert the property, not the spelling.
# ----------------------------------------------------------------------
home = os.path.join(os.path.dirname(__file__), "..", "app", "views", "Home.py")
tree = ast.parse(open(home, encoding="utf-8").read())
render = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "render")

calls = []
for node in ast.walk(render):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id.startswith("_render"):
            calls.append((node.lineno, node.func.id))
calls.sort()
order = [name for _ln, name in calls]

assert order and order[0] == "_render_best_games", (
    f"the hero card must be the first thing render() draws; order was {order}")
assert "_render_last_night" in order, "Home still reports last night somewhere"
assert order.index("_render_best_games") < order.index("_render_last_night"), (
    "DESIGN RULE: past results must never sit where they could read as a "
    "suggestion for today. The forward-looking card leads; last night's "
    "graded outcome stays below it.")
assert order.index("_render_today") < order.index("_render_last_night"), (
    "rule 10: above the 'Today' tag everything is about today")
print("PASS: Home leads with the forward-looking card, last night stays below")

# RULE 5 — Home makes zero network calls. The hero card is the first thing
# on the page and the most tempting place to break it, since the slate it
# needs is genuinely a live API call for MLB. It reads CI's file instead.
src = open(home, encoding="utf-8").read()
for banned in ("requests.", "urlopen", "httpx", "get_todays_games_with_weather"):
    assert banned not in src, (
        f"Home must make no network calls (rule 5) — found {banned!r}. The "
        f"MLB slate is written to disk by calibration_picks.py in CI "
        f"precisely so this page never has to fetch it.")
print("PASS: Home still makes no network calls")
