"""
NFL prop over/under chances — turning a projection into a probability.

nfl_projection gives a MEAN ("62.4 rushing yards"). A bet needs the
chance of clearing a line, and that needs to know how widely a player's
games scatter around his mean. That scatter is MEASURED here, per
market, from every player's real game lines this season:

  - COUNT markets (carries, receptions, targets, pass attempts): negative
    binomial, size measured by method of moments on (player mean, game)
    pairs — model_math.nb_dispersion. A huge size means Poisson.
  - YARD markets (rushing, receiving, passing, rush+rec): normal around
    the projection with SD = cv x projection, cv the pooled game-to-game
    coefficient of variation measured across players. Yards scale with
    volume, so a constant cv (not a constant SD) is what the data shape
    suggests; it is the one assumption, named on the page.

Anytime TD already has its own probability (nfl_projection).

What it does NOT know: the measured scatter is around each player's own
SEASON mean (in-sample), so it slightly understates the real miss of a
forward projection. These chances are not yet graded against outcomes;
the page says so.

Pure — no streamlit.
"""
from engines import model_math as mm

# market -> (box category, stat, kind)
MARKET_STAT = {
    "Rushing yards": ("rushing", "yds", "yards"),
    "Carries": ("rushing", "att", "count"),
    "Receiving yards": ("receiving", "yds", "yards"),
    "Receptions": ("receiving", "rec", "count"),
    "Targets": ("receiving", "tgt", "count"),
    "Passing yards": ("passing", "yds", "yards"),
    "Pass attempts": ("passing", "att", "count"),
    "Rush + rec yards": (None, "scrim", "yards"),
    "Completions": ("passing", "cmp", "count"),
    "Passing TDs": ("passing", "td", "count"),
    "Interceptions": ("passing", "int", "count"),
}
# Games a player needs in a market to contribute a scatter measurement:
# a variance needs two observations. Not a tuning knob.
_MIN_GAMES = 2


def _value(game, cat, stat):
    if cat is None:                       # rush + rec yards
        r = (game.get("rushing") or {}).get("yds")
        c = (game.get("receiving") or {}).get("yds")
        if r is None and c is None:
            return None
        return (r or 0) + (c or 0)
    return (game.get(cat) or {}).get(stat)


def measure_spreads(logs):
    """{market: {"kind","cv"|"size","players","games"}} from nfl_precompute
    logs ({pid: {"games": {eid: {"rushing": {...}, ...}}}})."""
    out = {}
    for market, (cat, stat, kind) in MARKET_STAT.items():
        pairs, players = [], 0
        for rec in (logs or {}).values():
            xs = [_value(g, cat, stat) for g in (rec.get("games") or {}).values()]
            xs = [x for x in xs if x is not None]
            if len(xs) < _MIN_GAMES:
                continue
            m = sum(xs) / len(xs)
            if m <= 0:
                continue
            players += 1
            pairs.extend((m, x) for x in xs)
        if not pairs:
            continue
        if kind == "count":
            size = mm.nb_dispersion(pairs)
            out[market] = {"kind": "count", "size": round(size, 3) if size else None,
                           "players": players, "games": len(pairs)}
        else:
            ss = sum(((x - m) / m) ** 2 for m, x in pairs)
            cv = (ss / len(pairs)) ** 0.5
            out[market] = {"kind": "yards", "cv": round(cv, 4),
                           "players": players, "games": len(pairs)}
    return out


def p_over(market, projection, line, spreads):
    """P(stat > line) for a projected mean, or None if unmeasured."""
    sp = (spreads or {}).get(market)
    if sp is None or projection is None or line is None or projection <= 0:
        return None
    if sp["kind"] == "count":
        pmf = mm.nb_pmf(projection, sp.get("size"), max_k=max(60, int(projection * 4)))
        # The smallest count that clears the line: over 4.5 needs 5,
        # over 5 needs 6 (5 exactly is a push, handled below).
        over = mm.prob_at_least(pmf, int(line) + 1)
        if float(line).is_integer():
            push = pmf[int(line)] if int(line) < len(pmf) else 0.0
            under = 1.0 - over - push
            return over / (over + under) if (over + under) > 0 else None
        return over
    sd = sp["cv"] * projection
    return 1.0 - mm.normal_cdf(line, projection, sd)
