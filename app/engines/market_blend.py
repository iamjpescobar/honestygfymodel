"""
The formula every bet on the site is priced with: START FROM THE MARKET,
move toward the model only as far as the model has EARNED.

WHY (10-04)
-----------
Until this file, every "edge" on the site was the model's probability
minus the book's break-even, as if the model were the truth and the book
the guess. The models know team scoring rates and (MLB) the starter; the
market also knows quarterbacks, goalies, injuries, rest, weather and
everything bettors have learned. On the first weekend that formula
flagged 44 NFL bets out of 16 games with "edges" up to 22 points — on a
model whose totals TIED the league average (MAE 10.96 vs 10.97). A model
that barely beats a coin flip cannot out-vote a market that beats it by
more.

THE FORMULA
-----------
For each market (moneyline, total, spread), in log-odds:

    logit(p_final) = w * logit(p_model) + (1 - w) * logit(p_market)

p_market is the posted price with the bookmaker's margin removed
(model_math.no_vig_pair). w is the MODEL'S WEIGHT, FITTED by maximum
likelihood on past games where both the model's walk-forward
prediction (made with only earlier games) and the market's recorded
line exist. w = 0 means "the market already knows everything the model
does"; w = 1 means "ignore the market".

Every edge, value tier, stake and logged pick is computed from p_final.

THE MODEL HAS TO EARN ITS WEIGHT
--------------------------------
w is scored CROSS-FITTED: fit on the first half of the history, score
the second half, and vice versa, so the reported number is on games the
weight never saw. That cross-fitted log loss is compared, game by game,
against the market alone (model_math.paired_verdict, the same test as
every trust badge):

    beats  -> w is used                      badge: BEATS MARKET
    thin   -> better on average but inside the noise: NOT proof, so
              w = 0 until it is              badge: NOT PROVEN YET
    fails  -> w = 0: the market price IS the probability, and the only
              value left is a better price at YOUR book than the
              posted one (line shopping)     badge: MARKET WINS
    none   -> no history yet: same as fails, and the page says to run
              the Market history workflow    badge: UNTESTED

Nothing here is chosen by eye: w is fitted, the verdict is the site's
significance convention (printed), and the no-vig conversion is exact.

WHEN A TOTAL OR SPREAD HAS NO PRICES
------------------------------------
A total line is set where the market thinks over and under are even, so
with no over/under prices the market's over chance at its own line is
read as 50% — that is what the line means, not an assumption about the
juice. Rows record whether real prices were used (`priced`), and the
nightly prints the share.

Pure — no streamlit, no requests.
"""
from math import exp, log

from engines import model_math as mm

MARKETS = ("moneyline", "total", "spread")
_EPS = 1e-6


def logit(p):
    p = min(max(float(p), _EPS), 1.0 - _EPS)
    return log(p / (1.0 - p))


def expit(x):
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


def blend(p_model, p_market, w):
    """p_final. No market -> None (nothing to anchor to, so no edge is
    claimed). No fitted weight -> the market itself."""
    if p_market is None:
        return None
    if p_model is None or not w:
        return float(p_market)
    return expit(w * logit(p_model) + (1.0 - w) * logit(p_market))


# ----------------------------------------------------------------------
# Reading the market off a posted line
# ----------------------------------------------------------------------
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def home_spread(odds, home_abbr="", away_abbr=""):
    """The posted spread as the HOME side's number, or None when the line
    contradicts itself.

    ESPN states `spread` relative to the home team. That convention could
    silently invert every cover probability, so it is CHECKED twice, as
    nfl_projection.implied_totals checks it: `details` names the
    favourite by abbreviation, and the moneyline says who is favoured.
    Either disagreeing with the sign -> None, never a backwards line.
    """
    o = odds or {}
    s = _num(o.get("spread"))
    if s is None:
        return None
    if s == 0:
        return 0.0
    home_fav_by_sign = s < 0
    details = str(o.get("details") or "").upper()
    fav = details.split()[0] if details else ""
    if fav and home_abbr and away_abbr and fav in (home_abbr.upper(), away_abbr.upper()):
        if (fav == home_abbr.upper()) != home_fav_by_sign:
            return None
    hm, am = _num(o.get("home_ml")), _num(o.get("away_ml"))
    if hm is not None and am is not None and hm != am:
        # the lower American price is the favourite (-150 < +130)
        if (hm < am) != home_fav_by_sign:
            return None
    return s


def market_probs(odds, home_abbr="", away_abbr=""):
    """What the posted line says, margin removed.

    {"moneyline": p_home | None,
     "total":  {"line", "p_over", "priced"} | None,
     "spread": {"line" (home), "p_cover" (home), "priced"} | None}
    """
    o = odds or {}
    out = {"moneyline": None, "total": None, "spread": None}
    ph, _pa = mm.no_vig_pair(o.get("home_ml"), o.get("away_ml"))
    out["moneyline"] = ph
    line = _num(o.get("total"))
    if line is not None:
        po, _pu = mm.no_vig_pair(o.get("over_price"), o.get("under_price"))
        out["total"] = {"line": line, "p_over": po if po is not None else 0.5,
                        "priced": po is not None}
    s = home_spread(o, home_abbr, away_abbr)
    if s is not None:
        pc, _pac = mm.no_vig_pair(o.get("home_spread_price"), o.get("away_spread_price"))
        out["spread"] = {"line": s, "p_cover": pc if pc is not None else 0.5,
                         "priced": pc is not None}
    return out


# ----------------------------------------------------------------------
# Fitting the weight
# ----------------------------------------------------------------------
def _mean_ll(rows, w):
    return sum(mm.log_loss(blend(pm, pk, w), y) for _d, pm, pk, y in rows) / len(rows)


def fit_weight(rows):
    """Maximum-likelihood w in [0, 1] for [(date, p_model, p_market, y)]."""
    if not rows:
        return None
    w = mm.golden_max(lambda x: -_mean_ll(rows, x), 0.0, 1.0, iters=50)
    # golden-section never lands exactly on an endpoint; a weight within
    # a thousandth of one IS that endpoint for any number printed.
    if w < 1e-3:
        w = 0.0
    elif w > 1 - 1e-3:
        w = 1.0
    return w


def fit(rows):
    """Fit and test one market's weight. rows: [(date, p_model, p_market, y)].

    Returns {"w", "w_used", "n", "from", "to", "market_log_loss",
    "model_log_loss", "blend_log_loss_cv", "verdict"} or {"n": 0}.
    """
    rows = sorted((r for r in rows or []
                   if r[1] is not None and r[2] is not None and r[3] in (0, 1)),
                  key=lambda r: r[0])
    n = len(rows)
    if n < 4:
        return {"n": n, "w": None, "w_used": 0.0, "verdict": {"n": n, "verdict": None}}
    half = n // 2
    a, b = rows[:half], rows[half:]
    wa, wb = fit_weight(a), fit_weight(b)
    # each half scored with the weight fitted on the OTHER half
    cv = ([mm.log_loss(blend(pm, pk, wb), y) for _d, pm, pk, y in a]
          + [mm.log_loss(blend(pm, pk, wa), y) for _d, pm, pk, y in b])
    mkt = [mm.log_loss(pk, y) for _d, _pm, pk, y in rows]
    mdl = [mm.log_loss(pm, y) for _d, pm, _pk, y in rows]
    verdict = mm.paired_verdict(cv, mkt)
    w = fit_weight(rows)
    # The model gets its say ONLY when it beat the market by more than
    # noise on games the weight never saw. "Better on average, inside
    # the noise" is not proof — on 128 simulated games where the market
    # knew every team's true strength, a noisy model still came out
    # "thin" with w = 0.31, and staking that would be staking noise.
    used = w if verdict.get("verdict") == "beats" else 0.0
    return {
        "n": n, "from": rows[0][0], "to": rows[-1][0],
        "w": round(w, 4), "w_used": round(used, 4),
        "w_halves": [round(wa, 4), round(wb, 4)],
        "market_log_loss": round(sum(mkt) / n, 5),
        "model_log_loss": round(sum(mdl) / n, 5),
        "blend_log_loss_cv": round(sum(cv) / n, 5),
        "verdict": verdict,
    }


def weight(blend_block, market):
    """The weight a page applies for one market (0 when untested)."""
    m = (blend_block or {}).get(market) or {}
    return m.get("w_used") or 0.0


def verdict(blend_block, market):
    m = (blend_block or {}).get(market) or {}
    return ((m.get("verdict") or {}).get("verdict")) if m.get("n") else None


# ----------------------------------------------------------------------
# History rows: the model's walk-forward predictions joined to lines
# ----------------------------------------------------------------------
def line_key(date, home, away):
    return f"{str(date)[:10]}|{home}|{away}"


def load_lines(stem, root=None):
    """{line_key: {...}} from data/market_lines/<stem>.json (written only
    by market_history.py), or {} when it has not been run yet."""
    import json
    from pathlib import Path
    base = Path(root) if root else Path(__file__).resolve().parents[2] / "data" / "market_lines"
    p = base / f"{stem}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()).get("lines") or {}
    except Exception:
        return {}


def build_rows(preds, lines, p_over_fn=None, p_cover_fn=None, key_fn=None):
    """{market: [(date, p_model, p_market, y)]} plus a coverage report.

    preds: walk-forward predictions ({"date","home","away","p_home","y",
    "hs","as", ...}); lines: {line_key: {"odds", "home_abbr",
    "away_abbr"}}; p_over_fn(pred, line) / p_cover_fn(pred, home_spread)
    give the MODEL's chance at the market's line; key_fn(pred) -> the
    line_key (defaults to the pred's own date/home/away).
    """
    key_fn = key_fn or (lambda p: line_key(p["date"], p["home"], p["away"]))
    out = {m: [] for m in MARKETS}
    cov = {"preds": len(preds or []), "with_line": 0, "total_priced": 0, "spread_priced": 0,
           "spread_contradicts": 0}
    for p in preds or []:
        ln = (lines or {}).get(key_fn(p))
        if not ln:
            continue
        cov["with_line"] += 1
        mk = market_probs(ln.get("odds"), ln.get("home_abbr") or "", ln.get("away_abbr") or "")
        if mk["moneyline"] is not None and p.get("p_home") is not None:
            out["moneyline"].append((p["date"], p["p_home"], mk["moneyline"], p["y"]))
        t = mk["total"]
        if t and p_over_fn:
            tot = p["hs"] + p["as"]
            if tot != t["line"]:
                pm = p_over_fn(p, t["line"])
                if pm is not None:
                    out["total"].append((p["date"], pm, t["p_over"], 1 if tot > t["line"] else 0))
                    cov["total_priced"] += 1 if t["priced"] else 0
        s = mk["spread"]
        if (ln.get("odds") or {}).get("spread") is not None and s is None:
            cov["spread_contradicts"] += 1
        if s and p_cover_fn:
            m = (p["hs"] - p["as"]) + s["line"]
            if m != 0:
                pm = p_cover_fn(p, s["line"])
                if pm is not None:
                    out["spread"].append((p["date"], pm, s["p_cover"], 1 if m > 0 else 0))
                    cov["spread_priced"] += 1 if s["priced"] else 0
    return out, cov


def fit_all(preds, lines, p_over_fn=None, p_cover_fn=None, key_fn=None, markets=MARKETS):
    """The block a model file carries: {market: fit(...)} + coverage."""
    rows, cov = build_rows(preds, lines, p_over_fn, p_cover_fn, key_fn)
    out = {m: fit(rows[m]) for m in markets}
    out["coverage"] = cov
    return out


def describe(block, market):
    """One line for a [verify] log or a caption."""
    m = (block or {}).get(market) or {}
    if not m.get("n"):
        return f"{market}: no market history yet"
    v = (m.get("verdict") or {})
    return (f"{market}: n={m['n']} market LL {m['market_log_loss']} vs blend (cross-fitted) "
            f"{m['blend_log_loss_cv']} vs model alone {m['model_log_loss']} -> "
            f"{v.get('verdict')} (z {v.get('z')}); model weight {m['w']} "
            f"(halves {m.get('w_halves')}), used {m['w_used']}")


# ----------------------------------------------------------------------
# Applying it to one projection
# ----------------------------------------------------------------------
def apply(proj, block, odds, home_abbr="", away_abbr="", p_cover_fn=None):
    """Adds the market and final probabilities to a projection, in place.

    proj must carry p_home (and p_over at market_total when a total is
    posted). p_cover_fn(home_spread) -> the model's home cover chance, for
    sports that price a spread here. Writes:

        p_home_mkt / p_home_final      moneyline
        p_over_mkt / p_over_final      total (at market_total)
        p_cover_mkt / p_cover_final    spread (at market_spread_home)
        model_weight                   {market: w used}
        blend_state                    "fitted" | "untested"
    """
    if not proj:
        return proj
    mk = market_probs(odds, home_abbr, away_abbr)
    state = "fitted" if any(((block or {}).get(m) or {}).get("n") for m in MARKETS) else "untested"
    proj["blend_state"] = state
    proj["model_weight"] = {m: weight(block, m) for m in MARKETS}
    if mk["moneyline"] is not None and proj.get("p_home") is not None:
        proj["p_home_mkt"] = round(mk["moneyline"], 4)
        proj["p_home_final"] = round(blend(proj["p_home"], mk["moneyline"],
                                           weight(block, "moneyline")), 4)
    t = mk["total"]
    if t and proj.get("p_over") is not None and proj.get("market_total") == t["line"]:
        proj["p_over_mkt"] = round(t["p_over"], 4)
        proj["p_over_final"] = round(blend(proj["p_over"], t["p_over"], weight(block, "total")), 4)
        proj["total_priced"] = t["priced"]
    s = mk["spread"]
    if s and p_cover_fn is not None:
        pc = p_cover_fn(s["line"])
        if pc is not None:
            proj["market_spread_home"] = s["line"]
            proj["p_home_cover"] = round(pc, 4)
            proj["fair_cover_home"] = mm.fair_american(pc)
            proj["fair_cover_away"] = mm.fair_american(1 - pc)
            proj["p_cover_mkt"] = round(s["p_cover"], 4)
            proj["p_cover_final"] = round(blend(pc, s["p_cover"], weight(block, "spread")), 4)
            proj["spread_priced"] = s["priced"]
    return proj
