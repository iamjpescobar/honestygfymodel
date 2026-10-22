"""
Bet Finder (10-09) — type your book's prices, get BET or SKIP.

WHY
---
Every board on the site colours a cell by how LIKELY it is, and a likely
outcome at a short price is a bad bet. Izzy, reading the boards: "I
don't know how to tell a good or bad bet in none of the models." The
rule is one line —

    a bet is good when the book PAYS MORE than the price the chance is
    worth (its break-even is below our chance)

— but applying it meant reading two columns per row by eye, one row at
a time, on five pages. This module does that sum for a whole list at
once, for every sport, with the same numbers the boards print:

    chance   the DELIVERED chance (model_view.delivered_over): the
             model's number mapped through what calls like it hit on
             games it had not seen. The same chance the price checkers
             and Top Plays use, so the Finder never disagrees with a
             board.
    call     BET when the edge is positive on the printed 0.1-point grid,
             tiered THIN / VALUE / STRONG exactly as model_view.edge_tier
             tiers it; SKIP otherwise.
    stake    value.assess at the reader's bankroll settings.

Nothing new is estimated here. Pure apart from importing model_view for
delivered_over / edge_tier (the page's own definitions).
"""
from engines import model_math as mm
from engines import value as vl

CALL_ORDER = {"strong": 0, "value": 1, "thin": 2, "check": 3, "none": 4}
TIER_LABEL = {"strong": "STRONG", "value": "VALUE", "thin": "THIN", "check": "CHECK",
              "none": "SKIP"}


def valid_price(x):
    """An American price a book can post, as int, or None."""
    try:
        v = int(round(float(x)))
    except (TypeError, ValueError):
        return None
    return v if (v <= -100 or v >= 100) else None


def break_even(price):
    """The hit rate a price needs, 0-1, or None."""
    d = vl.decimal_odds(price)
    return None if d is None else 1.0 / d


def chance_at(row, stat, line, side, markets, calibration):
    """(chance, raw, basis) for one player row at stat / line / side —
    the delivered chance, as every board prices it. None when the row has
    no distribution for that stat."""
    from engines import model_view as mv
    pmf = (row.get("_pmfs") or {}).get(stat)
    raw_over = mm.over_prob_pmf(pmf, line) if pmf else None
    if raw_over is None:
        return None, None, None
    over, basis = mv.delivered_over(raw_over, stat, line, markets, calibration)
    if side == "Under":
        return 1 - over, 1 - raw_over, basis
    return over, raw_over, basis


def support_at(row, stat, line, markets, calibration):
    """How well-measured this call is (model_view.support_for) — what the
    guard reads to decide whether the chance may carry STRONG."""
    from engines import model_view as mv
    if row.get("_untested"):
        # a row the model was never tested on (an NBA newcomer projected
        # from preseason): THIN at most, whatever the curve says
        return {"measured": False, "in_range": False, "n": 0, "untested": True}
    pmf = (row.get("_pmfs") or {}).get(stat)
    raw_over = mm.over_prob_pmf(pmf, line) if pmf else None
    return mv.support_for(raw_over, stat, line, markets, calibration)


MARKET_SUPPORT = {"measured": True, "in_range": True, "n": 10 ** 6, "untested": False}


def judge(chance, price, staking=None, other=None, support=None):
    """{"call", "tier", "edge", "break_even", "ev_per_100", "stake", "book",
    "guard"} for one price, or None when the price is not a real one.

    THE GUARD (model_view.guarded_tier, 10-11): a 10+ point gap to the
    book's own chance is CHECK, not a bet; an untested chance is at most
    THIN; a chance past the graded range is at most VALUE. `other` is the
    other side's price (de-vigs the book's chance); `support` how well the
    chance is measured (support_at; MARKET_SUPPORT for game lines, which
    are anchored to the market already)."""
    from engines import model_view as mv
    px = valid_price(price)
    if chance is None or px is None:
        return None
    bankroll, frac, cap = staking or (None, 0.25, 0.02)
    a = vl.assess(chance, px, bankroll or None, frac, cap)
    if not a:
        return None
    tier, guard = mv.guarded_tier(a, px, valid_price(other), support)
    book, _devig = mv.market_chance(px, valid_price(other))
    bet = tier in ("strong", "value", "thin")
    return {"call": "BET" if bet else ("CHECK" if tier == "check" else "SKIP"), "tier": tier,
            "edge": a["edge"], "break_even": a["break_even"],
            "ev_per_100": a["ev_per_100"], "book": book, "guard": guard,
            "stake": a.get("stake") if bet else 0.0}


def price_list(rows, stat, line, side, markets, calibration):
    """Every player who has this stat, with his chance and the price it is
    worth — the list the reader types his book's prices next to, most
    likely first."""
    out = []
    for r in rows or []:
        ch, raw, basis = chance_at(r, stat, line, side, markets, calibration)
        if ch is None or not 0 < ch < 1:
            continue
        out.append({"name": r.get("_name"), "chance": ch, "raw": raw, "basis": basis,
                    "worth": mm.fair_american(ch), "why": r.get("_why"),
                    "support": support_at(r, stat, line, markets, calibration)})
    out.sort(key=lambda x: -x["chance"])
    return out


def results(items, prices, staking=None, others=None):
    """items: price_list rows; prices: {name: price}; others: {name: the
    other side's price}. Judged rows for every name with a real price,
    BETs first (strongest edge first), then CHECK, then SKIP."""
    out = []
    for it in items or []:
        j = judge(it["chance"], prices.get(it["name"]), staking, (others or {}).get(it["name"]),
                  it.get("support"))
        if j:
            out.append(dict(it, price=valid_price(prices.get(it["name"])), **j))
    out.sort(key=lambda x: (CALL_ORDER[x["tier"]], -x["edge"]))
    return out


def game_line_items(proj, odds, away, home):
    """The game's own bets (moneyline, total, spread) at the posted lines,
    priced on the FINAL chance (the market moved toward the model only as
    far as the model has beaten it — engines/market_blend). A side with no
    market to anchor to is left out rather than priced on the model alone
    (rule 11)."""
    from engines import model_picks as mpk
    out = []
    for b in mpk.candidate_bets(proj, odds):
        if b.get("p") is None:
            continue
        if b["market"] == "moneyline":
            label = f"{home if b['side'] == 'home' else away} moneyline"
        elif b["market"] == "total":
            label = f"{'Over' if b['side'] == 'over' else 'Under'} {b['line']:g} total"
        else:
            label = f"{home if b['side'] == 'home' else away} {b['line']:+g}"
        out.append({"name": label, "chance": b["p"], "raw": b.get("p_model"),
                    "basis": "final", "worth": mm.fair_american(b["p"]),
                    "posted": b.get("price"), "market": b["market"]})
    return out


def card_key(sport, game, name, stat_label, line, side):
    return f"{sport}|{game}|{name}|{stat_label}|{line:g}|{side}"


def card_rows(card):
    """Tonight's card (session dict key -> judged row), BETs only,
    strongest first."""
    rows = [v for v in (card or {}).values() if v.get("call") == "BET"]
    return sorted(rows, key=lambda x: (CALL_ORDER[x["tier"]], -x["edge"]))
