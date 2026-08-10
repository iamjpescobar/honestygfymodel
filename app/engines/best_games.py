"""
Rank tonight's MLB slate so the home page can lead with the games worth
opening — item C, the best-games hero card.

WHAT THIS IS
------------
A pure ranking over a slate ALREADY BUILT AND SCORED by CI. It fetches
nothing, imports no streamlit, reads no files, and computes no baseball.
Every number it sorts on was produced by an engine that already exists
and is already on a board:

    modeled edge      engines/matchup_grades.grade_matchup()  -> ml.score
    projected total   engines/run_total.project_total()
    weather/park      engines/park_factors + engines/wind_engine
                      + MLB's posted game-time temperature

calibration_picks.py calls those in CI and writes the results into
data/mlb/games.json. This file only decides the ORDER. That split is the
whole point: Home makes zero network calls (rule 5), so anything the
hero card needs must already be on disk, and the ranking has to be
runnable headlessly or it cannot be tested.

THE RANKING, AS DECIDED
-----------------------
Three tiers, in strict priority order:

    1. biggest modeled edge
    2. highest projected run total
    3. biggest weather/park swing

Closest matchup was considered and REJECTED. A game between two evenly
matched teams is interesting to watch and is precisely the game this
site has least to say about — the whole argument for the card is "here
is where the model has an opinion", and a coin flip is the absence of
one.

Tier 1 is the primary sort and the other two are tiebreaks, not a
blended score. A weighted composite would need weights, weights would be
invented, and an invented weight dressed as a ranking is the confident
wrong answer this codebase exists to avoid. Strict tiers mean the card
can always say WHY a game is first, in one clause, truthfully.

MISSING IS NOT ZERO
-------------------
A game with no posted starters has no modeled edge. That is not an edge
of zero — it is no measurement, and it must not outrank a game measured
at zero, nor be silently treated as the worst game on the slate.
Anything unmeasured on a tier sorts BELOW everything measured on that
tier and keeps its place on the tiers it does have. Same rule the WNBA
prop tables use for a missing stat, for the same reason.

TIER 2 IS ALLOWED TO BE ABSENT
------------------------------
MLB has no projected run total yet. engines/run_total was built for KBO
and NPB and needs each team's runs scored and runs allowed per game;
nothing on disk carries those for MLB. Until a source does, `proj_total`
is simply absent from every game, tier 2 never fires, and ranking falls
through to tier 3 — which is correct behaviour, not a degraded mode.
The tier is wired and tested so it lights up the day the field appears,
the same way announced_starters() is left in place for WNBA.

DO NOT substitute the over/under lean for it. The O/U checklist counts
signals toward Over; it is not a number of runs, and ranking "highest
projected total" by it would be a different quantity wearing the label
of the decided one.
"""

# ----------------------------------------------------------------------
# WEATHER/PARK SWING — calibration constants, not measurements.
#
# Tier 3 asks one question: how far from neutral is the environment this
# game is played in. Three real signals answer it, and they arrive in
# three different units, so combining them REQUIRES weights. These are
# the weights. They are judgements about how much each signal moves a
# game, and nothing recomputes them.
#
# Argue with them here, in this one file, and never by special-casing a
# game at a call site — that is how an app ends up with five definitions
# of "hitter's park". Same rule as styles/stat_scales.py.
#
# The unit is deliberately arbitrary: swing is an ORDERING quantity used
# to break a tie, never displayed as a number. The card names the signals
# that fired ("Wrigley, 14 mph blowing out") because those are real; the
# score behind them is not a measurement and is not shown.
# ----------------------------------------------------------------------

# Park factor arrives as an index where 100 is neutral, so its deviation
# is already in natural units. Weight 1.0 makes it the reference all the
# others are stated against: a 105 park contributes 5.
PARK_WEIGHT = 1.0

# wind_engine caps its adjustment at ±6.0 (WIND_CAP) for a 15 mph wind
# straight out to centre. Weighted so a full-cap wind counts about the
# same as a 6-point park factor — one of the strongest parks in the
# league. That is the intended reading: on the right day, wind is a park
# factor.
WIND_WEIGHT = 1.0

# Temperature, per degree outside a neutral band. matchup_grades already
# fires an O/U signal at >=80F and <=65F, so the band is those same two
# thresholds rather than a second opinion about where warm starts —
# rule 21 in its quiet form: one definition, used by both.
TEMP_NEUTRAL_LO = 65.0
TEMP_NEUTRAL_HI = 80.0
# 15 degrees past the band is worth about 3 park points. Deliberately
# the smallest of the three: temperature is real but slow, and it is
# already partly baked into the park factor of a park that is usually
# hot.
TEMP_WEIGHT = 0.2

# A park factor is only used when park_factors marked it verified. The
# Athletics have no re-verified number and the Rays' rolling figure spans
# three different buildings; both ship verified=False precisely so
# downstream code skips them. Reading the number anyway here would
# reintroduce the bug that flag exists to prevent.


def _num(v):
    """float(v) or None — and None for NaN, which is not a measurement."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def park_swing(game):
    """(score, reasons) — how far from neutral this game's environment is.

    score is None when NOTHING could be measured: no verified park, no
    resolvable wind, no posted temperature. None means unmeasured and
    sorts below a real zero (a neutral park on a still 72-degree night IS
    a measurement, and a true zero).

    reasons is a list of short human clauses for the ones that fired, in
    the order they were measured. The card shows these; it never shows
    the score.
    """
    return _swing(game)[:2]


def _swing(game):
    """(score, reasons, measured_signals) — park_swing plus WHICH of the
    three signals actually contributed.

    The third value exists because a swing built from the park factor
    alone was being described to the reader as a "weather and park"
    swing. Measured on the 2026-08-10 slate: ten games, not one with a
    temperature or a wind, because MLB does not post either until close
    to first pitch and the 1 PM build ran six hours early. The number was
    real; the label on it was not.

    calibration_picks now fills the gap from the National Weather Service
    the way GameCard always has, so weather should normally be present —
    but "should normally be" is exactly the assumption that produced the
    wrong label in the first place. why_first() reads this and names only
    what it measured.
    """
    total = 0.0
    reasons = []
    measured = []

    pf = _num(game.get("park_factor"))
    if pf is not None and game.get("park_verified"):
        measured.append("park")
        dev = pf - 100.0
        total += abs(dev) * PARK_WEIGHT
        if abs(dev) >= 2:
            reasons.append(
                f"{game.get('venue') or 'park'} plays "
                f"{'up' if dev > 0 else 'down'} ({pf:g})")

    wind = _num(game.get("wind_adj"))
    if wind is not None:
        measured.append("wind")
        total += abs(wind) * WIND_WEIGHT
        note = game.get("wind_note")
        if note and abs(wind) >= 0.5:
            reasons.append(str(note))

    temp = _num(game.get("weather_temp"))
    if temp is not None:
        measured.append("temp")
        if temp > TEMP_NEUTRAL_HI:
            out = temp - TEMP_NEUTRAL_HI
        elif temp < TEMP_NEUTRAL_LO:
            out = TEMP_NEUTRAL_LO - temp
        else:
            out = 0.0
        total += out * TEMP_WEIGHT
        if out >= 5:
            reasons.append(f"{temp:g}\u00b0F")

    if not measured:
        return None, [], []
    return round(total, 2), reasons, measured


def _sort_key(game):
    """Strict tiers, with unmeasured sorting last WITHIN each tier.

    Each tier contributes a PAIR: (0 if measured else 1, -value). Python
    compares the pair left to right, so an unmeasured tier loses to every
    measured one before its value is ever looked at — and because the
    flag is per tier, a game missing a projected total still competes
    normally on edge and on swing.
    """
    edge = _num(game.get("edge_net"))
    total = _num(game.get("proj_total"))
    swing, _reasons = park_swing(game)

    return (
        (1, 0.0) if edge is None else (0, -edge),
        (1, 0.0) if total is None else (0, -total),
        (1, 0.0) if swing is None else (0, -swing),
        # Final tiebreak so the order is STABLE across runs rather than
        # dependent on however the slate happened to be written. Two
        # games identical on all three tiers is common early in the day,
        # before starters are posted, and a card that reshuffles on
        # every refresh looks broken.
        str(game.get("away") or ""), str(game.get("home") or ""),
    )


def why_first(game):
    """One clause saying why this game leads, or None.

    Reads the tiers in the same order they are sorted in and reports the
    FIRST one that is actually measured — so the sentence on the card is
    the reason the sort used, never a nicer-sounding one further down.
    """
    edge = _num(game.get("edge_net"))
    if edge is not None and edge > 0:
        lean = game.get("edge_lean")
        grade = game.get("edge_grade")
        bits = f"{int(edge)} signal{'s' if edge != 1 else ''}"
        if lean:
            bits += f" toward {lean}"
        if grade:
            bits += f", grade {grade}"
        return f"Biggest modeled edge on the slate \u2014 {bits}"

    total = _num(game.get("proj_total"))
    if total is not None:
        return f"Highest projected run total on the slate \u2014 {total:g} runs"

    swing, reasons, measured = _swing(game)
    if swing is not None and reasons:
        # NAME ONLY WHAT WAS MEASURED. This said "weather and park swing"
        # unconditionally, including on a slate where no game had a
        # temperature or a wind and the number came from the park factor
        # alone. Saying "weather" about a reading that never looked at
        # any is the plainest kind of wrong label, and it is the one a
        # reader has no way to catch.
        parts = [p for p in ("weather", "park") if
                 (p == "park" and "park" in measured) or
                 (p == "weather" and ("wind" in measured or "temp" in measured))]
        # "weather and park", matching the decided ranking's own wording
        # rather than inventing a second phrasing for the same tier.
        what = " and ".join(parts) if parts else "environment"
        return f"Biggest {what} swing \u2014 " + ", ".join(reasons)

    return None


def edge_reasons(game, limit=3):
    """The actual signals behind this game's edge grade.

    calibration_picks publishes `edge_signals` — the real comparisons
    grade_matchup made, like "WHIP: edge Boston Red Sox (1.28 vs 1.55)" —
    and for a while NOTHING read them. The card showed the grade and the
    lean, which is the conclusion, while the file held the reasoning and
    nobody saw it. Rule 20: a computed field nobody renders is not a
    feature, and on a page whose whole claim is "here is where the model
    has an opinion", the reasons ARE the product.

    Capped because the card is a summary, not the Game Card.
    """
    sigs = game.get("edge_signals")
    if not isinstance(sigs, list):
        return []
    return [str(s) for s in sigs if s][:limit]


def rank_games(games, limit=3):
    """The slate, best first, capped at `limit`.

    Never raises on a malformed row: a game missing every field ranks
    last rather than taking the page down. A hero card is the first thing
    on the landing page, and a landing page that 500s because one slate
    row lost a key is a worse outcome than a card that is one game short.
    """
    rows = [g for g in (games or []) if isinstance(g, dict)]
    rows.sort(key=_sort_key)
    return rows[:limit] if limit else rows


def has_any_signal(games):
    """True when at least one game carries a measurement worth ranking on.

    A slate that is on disk but entirely unscored — every game missing
    edge, total and environment, which is exactly what an early-morning
    build looks like before starters are posted — must render as "not
    built yet" and not as a ranked list of three arbitrary games. The
    order would be alphabetical and would LOOK like a recommendation.
    """
    for g in (games or []):
        if not isinstance(g, dict):
            continue
        if _num(g.get("edge_net")) is not None:
            return True
        if _num(g.get("proj_total")) is not None:
            return True
        if park_swing(g)[0] is not None:
            return True
    return False
