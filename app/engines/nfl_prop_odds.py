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


# ----------------------------------------------------------------------
# The board's stats and their distributions (moved here from model_view
# on 10-06 so the nightly can test what the page prices)
# ----------------------------------------------------------------------
# stat -> (label, projection key, how its spread is measured, roles)
STATS = (
    ("pass_yds", "Passing yards", "pass_yds", "Passing yards", ("QB",)),
    ("pass_cmp", "Completions", "pass_cmp", "Completions", ("QB",)),
    ("pass_att", "Pass attempts", "pass_att", "Pass attempts", ("QB",)),
    ("pass_td", "Passing TDs", "pass_td", "Passing TDs", ("QB",)),
    ("pass_int", "Interceptions", "pass_int", "Interceptions", ("QB",)),
    ("rush_yds", "Rushing yards", "rush_yds", "Rushing yards", ("RB", "QB")),
    ("carries", "Carries", "carries", "Carries", ("RB",)),
    ("rec_yds", "Receiving yards", "rec_yds", "Receiving yards", ("REC", "RB")),
    ("rec", "Receptions", "rec", "Receptions", ("REC", "RB")),
    ("targets", "Targets", "targets", "Targets", ("REC", "RB")),
    ("scrim_yds", "Rush + rec yards", "scrim_yds", "Rush + rec yards", ("RB", "REC")),
    ("td", "Touchdowns (rush + rec)", "td_exp", None, ("RB", "REC")),
)


def stat_pmf(stat_market, mean, spreads):
    """A projection as a distribution, with the game-to-game scatter
    MEASURED per market (engines/nfl_prop_odds): counts negative
    binomial, yards normal at a measured cv, discretised to whole yards
    (a yard line of 64.5 is then P(65 or more), the same number p_over
    gives). Touchdowns: the anytime Poisson. None if unmeasured."""
    if mean is None or mean <= 0:
        return None
    if stat_market is None:                      # touchdowns
        return mm.poisson_pmf(mean, 8)
    sp = (spreads or {}).get(stat_market)
    if not sp:
        return None
    if sp["kind"] == "count":
        return mm.nb_pmf(mean, sp.get("size"), max(40, int(mean * 4)))
    sd = (sp.get("cv") or 0) * mean
    if sd <= 0:
        # An unmeasured (or zero) scatter is not a certainty — no
        # distribution, so no chance, rather than a crash or a 100%.
        return None
    hi = int(mean + 5 * sd) + 2
    out = []
    for k in range(0, hi + 1):
        lo_c = mm.normal_cdf(k - 0.5, mean, sd) if k > 0 else 0.0
        out.append(mm.normal_cdf(k + 0.5, mean, sd) - lo_c)
    tail = 1.0 - sum(out)
    out[-1] += max(0.0, tail)
    return out
