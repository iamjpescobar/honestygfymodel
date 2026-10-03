"""
NFL game model — the site's OWN projected score, win probability, fair
spread and fair total, set beside the market's.

WHY IT EXISTS BESIDE nfl_projection
-----------------------------------
nfl_projection anchors touchdowns to the MARKET's implied points: exact
arithmetic on the posted line, and the right anchor for a player prop.
But a board anchored to the line can never disagree with it. This module
is the independent opinion: what the teams' own scoring says, so the
page can show where the model and the market part ways.

THE MODEL
---------
Points per side from engines/game_model's pairing (offense x opponent
defense / league x home multiplier, on ESPN team ids). Football scores
are not a count you can sum like runs — they come in 3s and 7s — so the
MARGIN and the TOTAL are each treated as normal around the projection,
with their spreads MEASURED as the walk-forward residual SDs:

    P(home wins)        = Phi(margin / sd_margin)
    P(home covers s)    = Phi((margin + s) / sd_margin)   s = home spread
    P(over line)        = 1 - Phi((line - total) / sd_total)

That normality is the one assumption, named on the page, and the
calibration curve under it is the check.

FITTED, NOT CHOSEN (rule 1)
---------------------------
shrink_k by walk-forward log loss; with four weeks of 2026 that is not
enough games, so it is fitted on the 2025 season (data/nfl/prior_season.json,
fetched by nfl_precompute the first night it is missing), each team
starts from its 2025 rating regressed by the measured split-half
carryover, and 2026's games move it. Home edge measured; SDs measured.

Pure — no streamlit, no requests.
"""
from math import exp, log

from engines import game_model as gm
from engines import model_math as mm


def rows(finals):
    """nfl_precompute finals -> game_model rows (ties dropped: an NFL tie
    is too rare to model and is neither a home win nor a loss)."""
    out = []
    for f in finals or []:
        if not f.get("home_id") or not f.get("away_id"):
            continue
        hs, as_ = f.get("home_score"), f.get("away_score")
        if hs is None or as_ is None or hs == as_:
            continue
        out.append({"date": f["date"], "home": str(f["home_id"]), "away": str(f["away_id"]),
                    "hs": int(hs), "as": int(as_)})
    return out


def _wf(finals, k, carry=None, prior_totals=None, prior_league=None):
    return gm.walk_forward(finals, k, score_only=True, carryover=carry,
                           prior_totals=prior_totals, prior_league=prior_league)


def _sds(preds):
    """(sd_margin, sd_total) — residual SDs of the walk-forward."""
    n = len(preds)
    if n < 10:
        return None, None
    rm = [(p["mu_h"] - p["mu_a"]) - (p["hs"] - p["as"]) for p in preds]
    rt = [(p["mu_h"] + p["mu_a"]) - (p["hs"] + p["as"]) for p in preds]
    return ((sum(x * x for x in rm) / n) ** 0.5, (sum(x * x for x in rt) / n) ** 0.5)


def _logloss(preds, sd):
    if not preds or not sd:
        return float("inf")
    return sum(mm.log_loss(mm.normal_cdf(p["mu_h"] - p["mu_a"], 0, sd), p["y"])
               for p in preds) / len(preds)


def fit(finals, prior_totals=None, prior_league=None, carry=None):
    """{"shrink_k","sd_margin","sd_total"} fitted on `finals`."""
    finals = gm.clean_finals(finals)
    if len(finals) < 40:
        return None

    def obj(lk):
        pr = _wf(finals, exp(lk), carry, prior_totals, prior_league)
        sd, _ = _sds(pr)
        return -_logloss(pr, sd)

    k = exp(mm.golden_max(obj, log(0.5), log(60.0), iters=40))
    sd_m, sd_t = _sds(_wf(finals, k, carry, prior_totals, prior_league))
    return {"shrink_k": round(k, 3), "sd_margin": round(sd_m, 3), "sd_total": round(sd_t, 3)}


def validate(finals, params, prior_totals=None, prior_league=None):
    finals = gm.clean_finals(finals)
    preds = _wf(finals, params["shrink_k"], params.get("carryover"), prior_totals, prior_league)
    if not preds:
        return {"n": 0}
    sd = params["sd_margin"]
    pp = [(mm.normal_cdf(p["mu_h"] - p["mu_a"], 0, sd), p["y"]) for p in preds]
    model = mm.score_predictions(pp)
    coin = mm.score_predictions([(0.5, y) for _p, y in pp])
    home = mm.score_predictions([(p["base_home"], p["y"]) for p in preds])
    n = len(preds)
    mae_m = sum(abs((p["mu_h"] - p["mu_a"]) - (p["hs"] - p["as"])) for p in preds) / n
    # Margin baseline: the league's home-points edge measured on games
    # BEFORE each date — what a reader would guess knowing nothing but
    # "home teams win by about this much".
    edge_before, cum, cnt, by_date = {}, 0.0, 0, {}
    for f in finals:
        by_date.setdefault(f["date"], []).append(f["hs"] - f["as"])
    for d in sorted(by_date):
        edge_before[d] = cum / cnt if cnt else 0.0
        cum += sum(by_date[d])
        cnt += len(by_date[d])
    mae_mb = sum(abs(edge_before[p["date"]] - (p["hs"] - p["as"])) for p in preds) / n
    mae_t = sum(abs(p["mu_h"] + p["mu_a"] - p["total"]) for p in preds) / n
    mae_tb = sum(abs(p["base_total"] - p["total"]) for p in preds) / n
    right = sum(1 for (p_, y) in pp if (p_ >= 0.5) == (y == 1))
    return {
        "n": n, "from": preds[0]["date"], "to": preds[-1]["date"],
        "model": model, "coin_flip": coin, "home_rate": home,
        "beats_coin": model["log_loss"] < coin["log_loss"],
        "beats_home_rate": model["log_loss"] < home["log_loss"],
        "favourite_won_pct": round(100.0 * right / n, 1),
        "margin_mae_model": round(mae_m, 2), "margin_mae_home_edge": round(mae_mb, 2),
        "margin_beats_home_edge": mae_m < mae_mb,
        "total_mae_model": round(mae_t, 2), "total_mae_league_avg": round(mae_tb, 2),
        "total_beats_league_avg": mae_t < mae_tb,
        "calibration": mm.calibration_bins(pp),
    }


def build(current_finals, prior_finals=None):
    cur = gm.clean_finals(rows(current_finals))
    prior = gm.clean_finals(rows(prior_finals)) if prior_finals else []
    prior_totals = prior_league = None
    if prior:
        prior_totals = gm.team_totals(prior)
        prior_league = gm.league_constants(prior)["league_rate"]
    if len(cur) >= 150 or not prior:
        fit_on, season = cur, "current"
        carry = gm._split_half_carryover(prior) if prior else None
        params = fit(cur, prior_totals, prior_league, carry)
        report_args = (cur, prior_totals, prior_league)
    else:
        fit_on, season = prior, "prior"
        carry = gm._split_half_carryover(prior)
        params = fit(prior)
        report_args = (prior, None, None)
    if params is None:
        return None
    params["carryover"] = carry
    params["fit_on"] = season
    consts = gm.league_constants(fit_on)
    consts["from"] = season
    lg = consts["league_rate"]
    targets = gm.prior_targets(prior_totals, prior_league, lg, carry)
    rates = gm.team_rates(gm.team_totals(cur), lg, params["shrink_k"], targets)
    report = validate(*report_args[:1], params, *report_args[1:])
    return {
        "params": params, "league": consts,
        "rates": {t: {"off": round(o, 3), "def": round(d, 3),
                      "gp": (gm.team_totals(cur).get(t) or {}).get("gp", 0)}
                  for t, (o, d) in rates.items()},
        "validation": report,
        "current_finals": len(cur), "prior_finals": len(prior),
    }


def project(model, home_id, away_id, odds=None, home_abbr="", away_abbr=""):
    """Card dict for one game, or None if a team is unknown."""
    if not model:
        return None
    rates = {t: (r["off"], r["def"]) for t, r in (model.get("rates") or {}).items()}
    mu_h, mu_a = gm.expected_scores(str(home_id), str(away_id), rates, model["league"])
    if mu_h is None:
        return None
    p = model["params"]
    sd_m, sd_t = p["sd_margin"], p["sd_total"]
    margin = mu_h - mu_a
    ph = mm.normal_cdf(margin, 0, sd_m)
    out = {"home_score": round(mu_h, 1), "away_score": round(mu_a, 1),
           "total": round(mu_h + mu_a, 1), "margin": round(margin, 1),
           "fair_spread_home": round(-margin, 1),
           "p_home": round(ph, 4), "p_away": round(1 - ph, 4),
           "fair_home": mm.fair_american(ph), "fair_away": mm.fair_american(1 - ph)}
    o = odds or {}
    # The posted spread is only read through the same favourite check
    # nfl_projection applies — a backwards sign would invert the cover
    # probability and look like a confident edge.
    from engines.nfl_projection import implied_totals
    a_imp, h_imp, why = implied_totals(o, away_abbr, home_abbr)
    if o.get("spread") is not None and h_imp is not None and not why:
        s = float(o["spread"])
        pc = mm.normal_cdf(margin + s, 0, sd_m)
        out.update({"market_spread_home": s, "p_home_cover": round(pc, 4),
                    "fair_cover_home": mm.fair_american(pc),
                    "fair_cover_away": mm.fair_american(1 - pc),
                    "market_home_pts": h_imp, "market_away_pts": a_imp})
    elif why:
        out["market_note"] = why
    if o.get("total") is not None:
        po = 1 - mm.normal_cdf(float(o["total"]), mu_h + mu_a, sd_t)
        out.update({"market_total": float(o["total"]), "p_over": round(po, 4),
                    "fair_over": mm.fair_american(po), "fair_under": mm.fair_american(1 - po)})
    mh, ma = mm.no_vig_pair(o.get("home_ml"), o.get("away_ml"))
    if mh is not None:
        out.update({"market_home": round(mh, 4), "market_away": round(ma, 4),
                    "edge_home": round(ph - mh, 4)})
    return out
