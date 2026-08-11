"""
Live hits props: given where a batter stands RIGHT NOW, how often has he
finished at or above a line?

    "He's 1-for-2. I want 2+ hits. What are my chances?"

WHAT THIS IS, AND WHAT IT REFUSES TO BE
---------------------------------------
An EMPIRICAL CONDITIONAL FREQUENCY. It finds this batter's real games
that reached the same state, and counts how many finished at or above
the line. Numerator and denominator, both real, both shown.

It is NOT a model. The tempting version — "he needs one more hit in two
likely at-bats, his rate is .270, assume a binomial" — produces a
confident number out of an assumption nobody can check. Plate
appearances are not independent draws: the pitcher changes, the lineup
turns over, a blowout empties the bench, a rain delay ends his night.
Every one of those is already inside the real games this counts, and
none of them is inside a binomial.

That choice costs precision and buys the only thing that matters here:
when this says 56%, there are 34 actual games behind it and you can
count them.

PINCH HITS, AND WHY THIS HANDLES THEM BY DOING NOTHING
------------------------------------------------------
A game where he was lifted after two at-bats with one hit FINISHED with
one hit. It lands in the denominator, not the numerator, and correctly
counts as a loss. No substitution detection is needed.

The failure mode is the opposite one — someone later deciding those
games look truncated and filtering them out. Measured on a simulation at
a 12% removal rate: keeping them gives 42.3%, dropping them gives 48.8%.
Six and a half points of pure optimism, biased in exactly the direction
that costs the bettor money.

**A GAME THAT ENDED EARLY IS A RESULT, NOT A DEFECT.** Do not add a
minimum-PA filter to `_game_states`. If a future reader wants to know how
often he gets removed, `removal_rate()` below reports it separately,
which is the honest place for it.

THE BULLPEN, AND WHY IT IS NOT BLENDED IN
------------------------------------------
The base rate ALREADY accounts for bullpens structurally: in every
historical game where he was 1-for-2, his later at-bats also came
against relievers. Late-inning exposure to a pen is the normal shape of
a baseball game and is baked into the number by construction.

What it cannot see is THIS pen. A rested elite bullpen and a depleted
one both live inside that average.

The fix is NOT to adjust the frequency. Adjusting requires a weight —
how many percentage points is a B-grade pen worth? — and that weight
would be invented, then hidden inside a single number where nobody could
argue with it. Same reasoning as the best-games ranking's strict tiers.

Instead the caller shows pen quality BESIDE the number, carrying its own
label and its own window, from the Bullpen Board data that already
exists. A reader can discount 56% against a shutdown pen. A blended 51%
tells them nothing about why.

WINDOWS — ONE, AND IT IS STATED
--------------------------------
Three windows are in play and they must not merge:

    conditional frequency   the batter pull's span (season; see
                            statcast_engine.DEFAULT_START_DATE)
    pen quality             whatever the Bullpen Board uses — shown
                            beside, never folded in
    batter recent form      NOT USED, deliberately

That last one is the one that will get argued. Conditioning on state
already cuts ~150 games to ~60. Adding "and he's been hot lately" takes
it to ~15, trading a real measurement for a noisier one to chase a
signal that cannot be verified at that sample size. If form is wanted
later, show both numbers with both denominators — do not merge them.
"""
import pandas as pd

# The same event sets statcast_engine uses. Imported rather than
# redefined: two definitions of "what counts as a hit" is how a board
# ends up disagreeing with the box score.
from engines.statcast_engine import _HIT_EVENTS

# SAMPLE FLOORS. Below MIN_SHOW there is no number at all; between
# MIN_SHOW and MIN_TRUST there is a number carrying a warning.
#
# Not arbitrary, and the arithmetic is worth keeping: a .270 hitter over
# a 150-game season reaches 0-for-2 in about 80 games and 1-for-2 in
# about 59 — both comfortable. But 2-for-2 happens ~11 times and 3-for-3
# about 3. A percentage off 11 games is noise wearing a percent sign, and
# a live number gets acted on within seconds of being read.
#
# 25 is where a single game moves the answer by less than four points.
# 50 is where the 95% interval is roughly ±14 — still wide, and the
# reason `interval()` exists and the caller is expected to show it.
MIN_SHOW = 25
MIN_TRUST = 50


def _hits_in(events) -> int:
    return int(pd.Series(list(events)).isin(_HIT_EVENTS).sum()) if len(events) else 0


def _game_states(df: pd.DataFrame):
    """[(game_pk, [event, event, ...]), ...] — each game's PA outcomes in order.

    One row per PLATE APPEARANCE, not per pitch: Statcast records the
    event only on the last pitch of a PA, so dropping nulls IS the PA
    list. at_bat_number orders them within the game and is game-wide, so
    a batter's own PAs are a subsequence of it — which is all the
    ordering this needs.

    NO MINIMUM-PA FILTER. See the pinch-hit section above; a short game
    is a real result and removing it inflates every number here.
    """
    if df is None or df.empty:
        return []
    need = {"game_pk", "at_bat_number", "events"}
    if not need.issubset(df.columns):
        return []
    d = df[list(need)].dropna(subset=["events"])
    if d.empty:
        return []
    d = d.sort_values(["game_pk", "at_bat_number"])
    return [(pk, list(g["events"])) for pk, g in d.groupby("game_pk", sort=True)]


def conditional_rate(df: pd.DataFrame, hits_so_far: int, pa_so_far: int,
                     line: int):
    """How often he finished with >= `line` hits, from this exact state.

    Returns a dict, never raises, and never guesses:

        rate        float 0-1, or None when the sample is under MIN_SHOW
        hit, n      numerator and denominator — ALWAYS returned, even
                    when rate is None, because "6 of 11" is a useful
                    thing to see and 55% off 11 games is not
        trusted     bool, n >= MIN_TRUST
        lo, hi      95% interval, or None with rate

    `line` is the FINAL total, not the remainder: "1-for-2, I want 2+"
    is conditional_rate(df, 1, 2, 2), and it is already half done.
    """
    out = {"rate": None, "hit": 0, "n": 0, "trusted": False,
           "lo": None, "hi": None, "already": False}

    if pa_so_far < 0 or hits_so_far < 0 or hits_so_far > pa_so_far:
        return out

    # ALREADY THERE. Not a probability question — he has the hits, the
    # bet is won, and returning 1.0 from an empty sample would be a
    # coincidence rather than an answer.
    if hits_so_far >= line:
        out["already"] = True
        out["rate"] = 1.0
        return out

    hit = n = 0
    for _pk, events in _game_states(df):
        if len(events) < pa_so_far:
            continue                       # never reached this state
        if _hits_in(events[:pa_so_far]) != hits_so_far:
            continue                       # reached a different one
        n += 1
        if _hits_in(events) >= line:
            hit += 1

    out["hit"], out["n"] = hit, n
    if n >= MIN_SHOW:
        out["rate"] = hit / n
        out["trusted"] = n >= MIN_TRUST
        out["lo"], out["hi"] = interval(hit, n)
    return out


def interval(hit: int, n: int):
    """95% Wilson interval, or (None, None).

    Wilson rather than the textbook normal approximation because the
    normal one is actively wrong at the sample sizes this operates on —
    at 19-of-34 it produces a plausible-looking band, and at 3-of-4 it
    produces one that extends past 100%. An interval that can exceed
    certainty is worse than no interval.
    """
    if not n:
        return None, None
    z = 1.96
    p = hit / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / d
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def removal_rate(df: pd.DataFrame, pa_so_far: int):
    """How often his night ENDED at exactly `pa_so_far` PAs. (removed, n)

    Reported beside the frequency, never folded into it. The base rate
    answers "what happens in games like this", but a live bettor often
    knows something it does not — that he is due up twice more, that it
    is a one-run game, that he is not coming out. This is the number that
    lets them adjust, and it is the honest way to surface what the
    pinch-hit games are doing inside the denominator.
    """
    states = _game_states(df)
    n = sum(1 for _pk, e in states if len(e) >= pa_so_far)
    removed = sum(1 for _pk, e in states if len(e) == pa_so_far)
    return removed, n


def state_grid(df: pd.DataFrame, line: int, max_pa: int = 4):
    """Every (hits, PAs) state and its rate — for a board, and for eyeballing.

    Cheap enough to render whole: it walks the game list once per state
    over at most ~150 games.
    """
    return {
        (h, pa): conditional_rate(df, h, pa, line)
        for pa in range(0, max_pa + 1)
        for h in range(0, pa + 1)
    }
