"""
The game models' picks: which bets have value at the POSTED price, a
pre-game record of every one of them, and the grade once the game is
final. This record is the only honest answer to "should I stake these".

WHAT GETS LOGGED
----------------
For every game with a projection and a posted price, each market side
whose expected value is positive at that price (engines/value):

    moneyline   home / away        price: the posted moneyline
    total       over / under       price: the posted over/under price
    spread      home / away (NFL)  price: the posted spread price

A side whose price was NOT posted is not logged — a record that assumed
-110 would report a profit the bettor never saw. Logged only BEFORE the
game starts, and FIRST WRITER WINS per (game, market): a later run that
sees a moved line cannot rewrite the pick, the same rule hr_edge follows
about confirmed lineups. A pick made after first pitch is not a pick.

GRADING
-------
Win, loss or push from the final score; units at the logged price (one
unit staked per pick). ROI is units / picks. No closing-line value: the
feeds here do not carry a closing price for every market, and a CLV
figure computed on some games and not others would be a right number
under a wrong label (rule 9).

Files: data/model_picks/{mlb,nhl,nfl}.json — one per sport so the two
workflows that write them (slate-picks for MLB, the nightly for NHL and
NFL) never commit the same file.

Pure — no streamlit, no requests. The grader script fetches finals and
calls grade_pick.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from engines import value as vl

ROOT = Path(__file__).resolve().parents[2]
PICKS_DIR = ROOT / "data" / "model_picks"
SPORTS = ("mlb", "nhl", "nfl")
EDGE_BUCKETS = ((0.0, 0.02, "0-2 pts"), (0.02, 0.05, "2-5 pts"), (0.05, 1.0, "5+ pts"))


# Which bets are really ONE bet. A moneyline and a spread on the same
# team win and lose together far more often than not, so a card that
# stakes both has staked the same opinion twice. Per game, at most one
# bet per GROUP is logged or staked — the one with the higher EV.
GROUP = {"moneyline": "side", "spread": "side", "total": "total"}


def candidate_bets(proj, odds):
    """Every side the model prices, with the posted price when there is
    one. [{"market","side","line","p","p_model","p_market","price"}].

    `p` is the FINAL probability (engines/market_blend): the market's
    no-vig chance moved toward the model by the model's fitted weight.
    It is None when no market line exists to anchor to — the model alone
    is shown (p_model) but no edge is claimed from it."""
    if not proj:
        return []
    o = odds or {}
    out = []

    def add(market, side, line, p_model, p_mkt, p_final, price):
        out.append({"market": market, "side": side, "line": line, "p": p_final,
                    "p_model": p_model, "p_market": p_mkt, "price": price})

    def inv(x):
        return None if x is None else 1 - x

    ph = proj.get("p_home")
    if ph is not None:
        pm, pf = proj.get("p_home_mkt"), proj.get("p_home_final")
        add("moneyline", "home", None, ph, pm, pf, o.get("home_ml"))
        add("moneyline", "away", None, 1 - ph, inv(pm), inv(pf), o.get("away_ml"))
    po = proj.get("p_over")
    if po is not None and proj.get("market_total") is not None:
        line = proj["market_total"]
        pm, pf = proj.get("p_over_mkt"), proj.get("p_over_final")
        add("total", "over", line, po, pm, pf, o.get("over_price"))
        add("total", "under", line, 1 - po, inv(pm), inv(pf), o.get("under_price"))
    pc = proj.get("p_home_cover")
    if pc is not None and proj.get("market_spread_home") is not None:
        s = proj["market_spread_home"]
        pm, pf = proj.get("p_cover_mkt"), proj.get("p_cover_final")
        add("spread", "home", s, pc, pm, pf, o.get("home_spread_price"))
        add("spread", "away", -s, 1 - pc, inv(pm), inv(pf), o.get("away_spread_price"))
    return out


def value_bets(proj, odds, one_per_group=True):
    """Candidate bets with a posted price and positive EV at it, priced
    on the FINAL probability. With one_per_group, a game yields at most
    one side bet (moneyline OR spread) and one total — the higher-EV one."""
    out = []
    for b in candidate_bets(proj, odds):
        if b["price"] is None or b["p"] is None:
            continue
        a = vl.assess(b["p"], b["price"])
        if a and a["value"]:
            out.append(dict(b, edge=round(a["edge"], 4), ev_per_100=a["ev_per_100"]))
    if one_per_group:
        best = {}
        for b in out:
            g = GROUP.get(b["market"], b["market"])
            if g not in best or b["ev_per_100"] > best[g]["ev_per_100"]:
                best[g] = b
        out = [b for b in out if best.get(GROUP.get(b["market"], b["market"])) is b]
    return out


# ----------------------------------------------------------------------
# The record
# ----------------------------------------------------------------------
def _path(sport, root=None):
    return Path(root or PICKS_DIR) / f"{sport}.json"


def load(sport, root=None):
    p = _path(sport, root)
    if not p.exists():
        return {"picks": []}
    try:
        return json.loads(p.read_text()) or {"picks": []}
    except Exception:
        return {"picks": []}


def save(sport, record, root=None):
    p = _path(sport, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, indent=1, sort_keys=True))


def log_picks(sport, games, now=None, root=None):
    """Append this run's value picks. games: [{"id","date","start",
    "home","away","proj","odds"}] with start an aware ISO timestamp.
    Returns the number of NEW picks written."""
    now = now or datetime.now(timezone.utc)
    rec = load(sport, root)
    # First writer wins per (game, GROUP): a moneyline logged this
    # afternoon blocks a spread on the same game tonight — they are one
    # opinion, and the record must not count it twice.
    have = {(p["game_id"], GROUP.get(p["market"], p["market"])) for p in rec["picks"]}
    new = 0
    for g in games:
        try:
            start = datetime.fromisoformat(str(g["start"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if start.tzinfo is None or start <= now:
            continue                    # not a pick once it has started
        for b in value_bets(g.get("proj"), g.get("odds")):
            key = (str(g["id"]), GROUP.get(b["market"], b["market"]))
            if key in have:
                continue                # first writer wins
            have.add(key)
            rec["picks"].append({
                "game_id": str(g["id"]), "date": g["date"], "start": g["start"],
                "home": g["home"], "away": g["away"], "market": b["market"],
                "side": b["side"], "line": b["line"], "price": b["price"],
                "p": round(b["p"], 4), "edge": b["edge"], "ev_per_100": b["ev_per_100"],
                "p_model": None if b.get("p_model") is None else round(b["p_model"], 4),
                "p_market": None if b.get("p_market") is None else round(b["p_market"], 4),
                "formula": "market-anchored",
                "logged_at": now.isoformat(timespec="seconds"), "result": None,
            })
            new += 1
    if new:
        save(sport, rec, root)
    return new


def grade_pick(pick, home_score, away_score):
    """(result, units): result is "win" / "loss" / "push"."""
    hs, as_ = home_score, away_score
    m, side, line = pick["market"], pick["side"], pick.get("line")
    if m == "moneyline":
        if hs == as_:
            won = None
        else:
            won = (hs > as_) if side == "home" else (as_ > hs)
    elif m == "total":
        tot = hs + as_
        won = None if tot == line else ((tot > line) if side == "over" else (tot < line))
    elif m == "spread":
        margin = (hs - as_) if side == "home" else (as_ - hs)
        won = None if margin + line == 0 else (margin + line > 0)
    else:
        return None, None
    res = "push" if won is None else ("win" if won else "loss")
    return res, round(vl.profit_units(won, pick["price"]), 4)


def summary(picks):
    """Record, units and ROI over graded picks, overall and by edge."""
    graded = [p for p in picks if p.get("result") in ("win", "loss", "push")]

    def agg(rows):
        w = sum(1 for r in rows if r["result"] == "win")
        lo = sum(1 for r in rows if r["result"] == "loss")
        pu = sum(1 for r in rows if r["result"] == "push")
        units = round(sum(r.get("units") or 0 for r in rows), 2)
        n = len(rows)
        return {"n": n, "w": w, "l": lo, "p": pu, "units": units,
                "roi": round(100.0 * units / n, 1) if n else None,
                "win_pct": round(100.0 * w / (w + lo), 1) if (w + lo) else None}
    out = {"all": agg(graded), "pending": sum(1 for p in picks if not p.get("result")),
           "by_edge": [], "by_market": {}}
    for lo, hi, label in EDGE_BUCKETS:
        rows = [r for r in graded if lo <= (r.get("edge") or 0) < hi]
        out["by_edge"].append(dict(agg(rows), bucket=label))
    for m in ("moneyline", "total", "spread"):
        rows = [r for r in graded if r["market"] == m]
        if rows:
            out["by_market"][m] = agg(rows)
    # The formula changed on 10-04 (engines/market_blend). Picks logged
    # before it were priced on the model alone and are kept — the record
    # is the record — but reported apart, so the new formula is judged
    # on its own picks and not on the ones it was built to stop.
    out["by_formula"] = {}
    for f in ("market-anchored", "model-only"):
        rows = [r for r in graded if formula_of(r) == f]
        if rows:
            out["by_formula"][f] = agg(rows)
    return out


def formula_of(pick):
    return pick.get("formula") or "model-only"
