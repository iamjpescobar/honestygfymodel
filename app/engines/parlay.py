"""
Parlay checker (10-18) — is the WHOLE ticket worth its price?

Izzy bets parlays; every board judges singles. A leg that is SKIP on its
own can still belong on a ticket — next to a strong leg, or under a
profit boost — and a leg that looks fine can quietly drag a ticket under.

THE MATH
--------
  chance all hit   = product of each leg's chance (legs in DIFFERENT
                     games are independent).
  payout (decimal) = the book's parlay price if typed, else the product
                     of the legs' prices; a profit boost multiplies the
                     winnings: 1 + (decimal - 1) * (1 + boost).
  EV per $1        = chance * payout - 1.
  each leg         = chance * its decimal price: above 1 it CARRIES the
                     ticket, below 1 it DRAGS it (by that much).

THE GUARD, LEG BY LEG (the same rules every single follows)
-----------------------------------------------------------
  - any leg the book disagrees with by 10+ points (its own call CHECK)
    -> the ticket is CHECK;
  - two legs in the SAME game are linked (a goal and his linemate's
    point happen together; books price that in) and nothing here prices
    the link -> the ticket is at most THIN, and says why;
  - an untested leg -> at most THIN; a leg past its graded range or in a
    thin band -> at most VALUE.
  Ticket tiers by EV per $100: THIN under +10, VALUE +10 to +25, STRONG
  +25 and up — display cuts, like the singles' 2 / 5 points.

Pure — no streamlit, no requests.
"""
import re

from engines import value as vl

THIN_EV, STRONG_EV = 0.10, 0.25
ORDER = {"strong": 0, "value": 1, "thin": 2, "check": 3, "none": 4}
CAP = {"strong": 0, "value": 1, "thin": 2}


def game_id(game):
    """One id for one game however a page labels it ("CAR @ MTL  7:00 PM",
    "MTL vs CAR", "CAR @ MTL"): the two team abbreviations, unordered."""
    toks = [t for t in re.findall(r"\b[A-Z]{2,4}\b", str(game or ""))
            if t not in ("AM", "PM", "ET", "EDT", "EST")]
    return "/".join(sorted(set(toks[:2]))) if toks else None


def leg_key(sport, game, player, what):
    return f"{sport}|{game}|{player}|{what}"


def add_leg(slip, sport, game, player, what, chance, price, support=None, single_tier=None):
    """Put one leg on the slip (a dict kept in session state)."""
    slip[leg_key(sport, game, player, what)] = {
        "sport": sport, "game": game, "player": player, "what": what,
        "chance": chance, "price": int(price), "support": support or {},
        "single_tier": single_tier}
    return slip


def _cap(tier, limit):
    if tier in ("none", "check"):
        return tier
    return tier if CAP[tier] >= CAP[limit] else limit


def judge(legs, parlay_price=None, boost=0.0, staking=None):
    """The ticket's verdict, or None with fewer than two priced legs."""
    legs = [x for x in legs or [] if x.get("chance") is not None
            and vl.decimal_odds(x.get("price")) is not None]
    if len(legs) < 2:
        return None
    joint, dec_legs = 1.0, 1.0
    contrib = []
    for x in legs:
        d = vl.decimal_odds(x["price"])
        joint *= x["chance"]
        dec_legs *= d
        contrib.append(dict(x, ratio=x["chance"] * d))
    book_dec = vl.decimal_odds(parlay_price) if parlay_price not in (None, "") else None
    dec = book_dec or dec_legs
    boost = max(0.0, float(boost or 0.0))
    payout = 1.0 + (dec - 1.0) * (1.0 + boost)
    ev = joint * payout - 1.0
    be = 1.0 / payout

    reasons = []
    tier = "none" if ev <= 0 else ("strong" if ev >= STRONG_EV else
                                    "value" if ev >= THIN_EV else "thin")
    games = [game_id(x.get("game")) for x in legs]
    linked = sorted({g for g in games if g and games.count(g) > 1})
    if tier != "none":
        if any(x.get("single_tier") == "check" for x in legs):
            tier = "check"
            reasons.append("a leg's book price is 10+ points from our chance — find out why first")
        else:
            if linked:
                tier = _cap(tier, "thin")
                reasons.append(f"same-game legs ({', '.join(linked)}) move together and the "
                               f"link is not priced here")
            sup = [x.get("support") or {} for x in legs]
            if any(s.get("untested") for s in sup):
                tier = _cap(tier, "thin")
                reasons.append("a leg is on an untested market or the Live page")
            elif any(not s.get("in_range", True) or (s.get("n") is not None
                                                     and s.get("n", 99) < 30) for s in sup):
                tier = _cap(tier, "value")
                reasons.append("a leg sits past its graded range")
    am = _american(payout)
    stake = None
    if staking and ev > 0 and tier in ("thin", "value", "strong"):
        bankroll, frac, cap = staking
        if bankroll:
            stake = vl.stake(joint, am, bankroll, frac, cap)
    contrib.sort(key=lambda x: -x["ratio"])
    return {"chance": joint, "payout": payout, "american": am, "break_even": be, "ev": ev,
            "tier": tier, "reasons": reasons, "legs": contrib, "linked": linked,
            "used_book_price": bool(book_dec), "stake": stake,
            "drag": [x for x in contrib if x["ratio"] < 1.0]}


def _american(dec):
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100.0 / (dec - 1.0)))
