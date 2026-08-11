"""The live-hits conditional frequency is real, and refuses to be fake.

WHY THIS EXISTS

This is the first number on the site a person reads and acts on WITHIN
SECONDS, mid-game, with money already in play. Every other board is
published before first pitch and graded after. That changes what a
mistake costs: a wrong pregame number is a bad pick, a wrong live number
is a bad pick made under time pressure by someone who trusted it.

So the properties below are not stylistic. Each one is a way this could
produce a plausible number that is wrong.

THE BIG ONE — SURVIVORSHIP BIAS

A game where the batter was pinch-hit for after two at-bats with one hit
FINISHED with one hit. It belongs in the denominator as a loss, and the
engine gets that right by doing nothing special.

The danger is a future reader deciding those games look truncated and
adding a minimum-PA filter to "clean" them. Measured at a 12% removal
rate: keeping them gives 42.3%, dropping them gives 48.8%. **Six and a
half points of pure optimism, biased in the exact direction that costs
the bettor money**, and completely invisible on screen.

That is what the first block below pins, and it is the assertion to
re-read before touching `_game_states`.
"""
import os
import sys
import types

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

# statcast_engine carries @st.cache_data; live_hits imports its hit set.
_st = types.ModuleType("streamlit")


def _memo(*a, **k):
    def deco(fn):
        return fn
    return a[0] if (a and callable(a[0]) and not k) else deco


_st.cache_data = _st.cache_resource = _memo
_st.session_state = {}
_st.secrets = {}
for _n in ("markdown", "caption", "stop", "write", "info", "warning", "error"):
    setattr(_st, _n, lambda *a, **k: None)
sys.modules.setdefault("streamlit", _st)

from engines.live_hits import (  # noqa: E402
    conditional_rate, removal_rate, state_grid, interval,
    MIN_SHOW, MIN_TRUST, _game_states,
)

failures = []


def check(label, ok):
    if ok:
        print(f"PASS: {label}")
    else:
        failures.append(label)


def frame(games):
    """games = [[event, event, ...], ...] -> a Statcast-shaped frame."""
    rows, abn = [], 1
    for pk, evs in enumerate(games, start=1):
        for e in evs:
            rows.append({"game_pk": pk, "at_bat_number": abn, "events": e})
            abn += 1
    return pd.DataFrame(rows)


H, O = "single", "field_out"

# ----------------------------------------------------------------------
# 1. PINCH-HIT GAMES STAY IN THE DENOMINATOR.
#
# Ten games, all reaching 1-for-2. Four end there (removed). Six carry on
# and reach a second hit. The honest answer is 6/10 = 60%. Dropping the
# four short games gives 6/6 = 100%.
# ----------------------------------------------------------------------
games = [[H, O] for _ in range(4)]                    # removed at 2 PAs
games += [[H, O, H, O] for _ in range(6)]             # played on, got there
r = conditional_rate(frame(games), hits_so_far=1, pa_so_far=2, line=2)
check(f"a game that ended early counts as a LOSS, not an exclusion "
      f"(got {r['hit']}/{r['n']})",
      (r["hit"], r["n"]) == (6, 10))

# And the engine must not be silently filtering anywhere else either.
check("_game_states keeps short games",
      len(_game_states(frame([[H], [H, O, H, O]]))) == 2)

# ----------------------------------------------------------------------
# 2. THE STATE IS EXACT, not "at least".
#
# A game where he was 2-for-2 is NOT evidence about a 1-for-2 state. It
# is a different situation with a different remaining distribution, and
# pooling them would quietly inflate the answer.
# ----------------------------------------------------------------------
mixed = ([[H, O, O, O] for _ in range(5)]     # 1-for-2, finished 1
         + [[H, H, O, O] for _ in range(5)])  # 2-for-2 — different state
r = conditional_rate(frame(mixed), 1, 2, 2)
check(f"a 2-for-2 game is not counted as a 1-for-2 game (n={r['n']})",
      r["n"] == 5)

# ----------------------------------------------------------------------
# 3. `line` IS THE FINAL TOTAL, not the remainder.
#
# "1-for-2, I want 2+" is line=2 and is already half done. Reading it as
# "2 MORE hits" would understate every answer on the board.
# ----------------------------------------------------------------------
one_more = [[H, O, H, O]] * 10          # finishes with 2
r = conditional_rate(frame(one_more), 1, 2, 2)
check("line counts hits ALREADY IN, not hits still needed", r["hit"] == 10)

# ----------------------------------------------------------------------
# 4. ALREADY THERE IS NOT A PROBABILITY QUESTION.
# ----------------------------------------------------------------------
r = conditional_rate(frame([[H, H, O, O]] * 3), 2, 2, 2)
check("a line already cleared returns already=True, not a sampled rate",
      r["already"] and r["rate"] == 1.0)

# ----------------------------------------------------------------------
# 5. THE FLOORS. A percentage off eleven games is noise wearing a
#    percent sign, and this one gets acted on in seconds.
# ----------------------------------------------------------------------
thin = conditional_rate(frame([[H, O, H, O]] * (MIN_SHOW - 1)), 1, 2, 2)
check(f"under {MIN_SHOW} games there is NO percentage", thin["rate"] is None)
check("but the count is still returned — '6 of 11' is useful",
      thin["n"] == MIN_SHOW - 1 and thin["hit"] == MIN_SHOW - 1)

mid = conditional_rate(frame([[H, O, H, O]] * MIN_SHOW), 1, 2, 2)
check(f"at {MIN_SHOW} a rate appears", mid["rate"] is not None)
check(f"but is untrusted until {MIN_TRUST}", not mid["trusted"])

big = conditional_rate(frame([[H, O, H, O]] * MIN_TRUST), 1, 2, 2)
check(f"at {MIN_TRUST} it is trusted", big["trusted"])

# ----------------------------------------------------------------------
# 6. THE INTERVAL CANNOT EXCEED CERTAINTY.
#
# Wilson, not the normal approximation — which at 3-of-4 produces a band
# running past 100%. An interval that claims more than certainty is worse
# than no interval, because it looks like arithmetic.
# ----------------------------------------------------------------------
for hit, n in ((3, 4), (0, 5), (5, 5), (1, 1), (19, 34)):
    lo, hi = interval(hit, n)
    if not (0.0 <= lo <= hi <= 1.0):
        failures.append(f"interval({hit},{n}) = ({lo},{hi}) escaped [0,1]")
        break
else:
    check("the 95% band never leaves [0,1], even at n=1", True)
check("no sample yields no band", interval(0, 0) == (None, None))

# ----------------------------------------------------------------------
# 7. REMOVAL IS REPORTED SEPARATELY, never folded into the rate.
#
# The base rate answers "what happens in games like this". A live bettor
# often knows something it does not — that he is due up twice more. This
# is the number that lets them adjust.
# ----------------------------------------------------------------------
rm, n = removal_rate(frame([[H, O]] * 4 + [[H, O, H, O]] * 6), 2)
check(f"removal rate is its own number ({rm}/{n})", (rm, n) == (4, 10))

# ----------------------------------------------------------------------
# 8. NOTHING CRASHES A LIVE PAGE.
# ----------------------------------------------------------------------
for bad in (None, pd.DataFrame(), pd.DataFrame({"nope": [1]})):
    r = conditional_rate(bad, 1, 2, 2)
    if r["rate"] is not None or r["n"] != 0:
        failures.append("malformed input produced a number")
        break
else:
    check("missing or malformed data yields no number, not an exception", True)

check("an impossible state (3 hits in 2 PAs) yields nothing",
      conditional_rate(frame([[H, H]] * 30), 3, 2, 4)["n"] == 0)

# ----------------------------------------------------------------------
# 9. NO SECOND DEFINITION OF "HIT".
#
# Two definitions of what counts as a hit is how a board ends up
# disagreeing with the box score in front of the reader.
# ----------------------------------------------------------------------
src = open(os.path.join(os.path.dirname(__file__), "..", "app", "engines",
                        "live_hits.py"), encoding="utf-8").read()
check("the hit set is imported from statcast_engine, not redefined",
      "from engines.statcast_engine import _HIT_EVENTS" in src)
check("no local hit-event literal shadows it",
      '"single", "double", "triple"' not in src)

# The window rule from the module docstring, asserted so it cannot drift:
# recent-form conditioning would cut ~60 games to ~15.
check("no recent-form window is applied to the frequency",
      "apply_window" not in src and "recency_windows" not in src)

# ----------------------------------------------------------------------
# 10. THE GRID COVERS THE STATES A LIVE BETTOR IS ACTUALLY IN.
# ----------------------------------------------------------------------
grid = state_grid(frame([[H, O, H, O]] * 30), line=2)
check("the grid holds both the hitless and the one-hit states",
      (0, 2) in grid and (1, 2) in grid)
check("the grid never holds an impossible state",
      all(h <= pa for (h, pa) in grid))

if failures:
    print()
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(1)

print("\nA game that ended early is a result, not a defect.")
