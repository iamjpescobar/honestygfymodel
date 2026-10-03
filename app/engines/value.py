"""
Is this bet worth it at THIS price, and how much of a bankroll should it
get? One answer for every model on the site.

THE ARITHMETIC (exact, no parameters)
-------------------------------------
    decimal odds   d = 1 + 100/|a| (favourite)  or  1 + a/100 (underdog)
    EV per $1      = p * (d - 1) - (1 - p)
    break-even p   = 1 / d
    edge           = p - break-even     (probability points over the price)

A bet is "value" only when EV > 0 AT THE PRICE YOU ARE OFFERED — the
model saying 55% is worthless information at -150 (break-even 60%).

STAKE: FRACTIONAL KELLY, CAPPED
-------------------------------
Full Kelly, f* = (p*(d-1) - (1-p)) / (d-1), maximises long-run growth
IF p is exactly right. It never is: every probability on this site comes
from a model whose walk-forward edge over a coin flip is a few hundredths
of log loss. Over-betting a noisy edge is the classic way a real edge
still loses the bankroll, so the page uses a FRACTION of Kelly and a hard
per-bet cap, both set by the reader (bankroll, fraction, cap) and shown.
These two are risk preferences, not model parameters — rule 1 is about
numbers that claim to describe the world; these describe the bettor.
The defaults (quarter Kelly, 2% cap) are the conservative end of common
practice and are stated wherever a stake is printed.
"""


def decimal_odds(american):
    try:
        a = float(american)
    except (TypeError, ValueError):
        return None
    if -100 < a < 100:
        return None
    return 1.0 + (100.0 / -a if a < 0 else a / 100.0)


def break_even(american):
    d = decimal_odds(american)
    return None if d is None else 1.0 / d


def ev_per_dollar(p, american):
    d = decimal_odds(american)
    if d is None or p is None:
        return None
    return p * (d - 1.0) - (1.0 - p)


def kelly_fraction(p, american):
    """Full-Kelly fraction of bankroll (0 when there is no edge)."""
    d = decimal_odds(american)
    if d is None or p is None:
        return None
    b = d - 1.0
    f = (p * b - (1.0 - p)) / b
    return max(0.0, f)


def stake(p, american, bankroll, fraction=0.25, cap=0.02):
    """Dollars to stake: fraction x Kelly, never above cap x bankroll."""
    f = kelly_fraction(p, american)
    if f is None or not bankroll or bankroll <= 0:
        return None
    return round(min(f * fraction, cap) * bankroll, 2)


def assess(p, american, bankroll=None, fraction=0.25, cap=0.02):
    """Everything a card prints about one side of one bet, or None."""
    d = decimal_odds(american)
    if d is None or p is None:
        return None
    ev = ev_per_dollar(p, american)
    be = 1.0 / d
    out = {
        "p": p, "price": int(float(american)), "break_even": be,
        "edge": p - be, "ev_per_100": round(100.0 * ev, 2), "value": ev > 0,
    }
    if bankroll:
        out["stake"] = stake(p, american, bankroll, fraction, cap) if ev > 0 else 0.0
    return out


def profit_units(won, american):
    """Units won (1 unit staked) for a graded bet; push = 0."""
    if won is None:
        return 0.0
    d = decimal_odds(american)
    if d is None:
        return None
    return (d - 1.0) if won else -1.0
