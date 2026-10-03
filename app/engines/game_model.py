"""
The game model — projected score, win probability, fair line — for any
sport whose score is a count (MLB runs, NHL goals).

WHAT IT IS
----------
Each side's expected score is its offense against the opponent's
defense, relative to the league, with home field applied:

    mu_home = off_home * def_away / league * home_mult
    mu_away = off_away * def_home / league * away_mult

That pairing is the same one engines/run_total has used for KBO and NPB
since July; this module adds the two things run_total refused to do
without evidence — a win probability and a fair line — now that a
season of real finals exists to measure them against.

Win probability comes from the two score distributions (model_math):
P(home ahead) plus the level-after-regulation mass resolved at the
MEASURED rate the home side wins those games.

EVERY NUMBER IS MEASURED OR FITTED (rule 1)
-------------------------------------------
    league rate            mean score per team-game, from finals
    home_mult / away_mult  home and road scoring vs league, from finals
    tie_home_win           home win rate in extra-inning / OT games
    shrink_k               how many games of league-average evidence a
                           team's own rate is pulled toward — FITTED by
                           minimising walk-forward log loss
    carryover              (optional) how much of LAST season a team
                           keeps — FITTED the same way, on the prior
                           season's own walk-forward
    dispersion             negative-binomial size, method of moments on
                           the walk-forward residuals

WALK-FORWARD, NOT IN-SAMPLE
---------------------------
Every validation number this module reports was produced by predicting
each game using only games played on EARLIER dates. A model scored on
the games it was fitted to always looks good; that number would be on
the page and it would be a lie. The fitted parameters themselves are
chosen on the same walk-forward, which is honest about the parameter
being learnt from the season but means the reported figures are
slightly optimistic by two degrees of freedom — stated on the page.

Pure — no streamlit, no requests. The nightly imports it to fit; the
pages import it to project from the fitted file.
"""
from collections import defaultdict
from math import exp, log

from engines import model_math as mm


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# ----------------------------------------------------------------------
# Measurement
# ----------------------------------------------------------------------
def clean_finals(finals):
    """Keep only rows with both teams and both scores, sorted by date.

    Each row: {"date": "YYYY-MM-DD", "home": key, "away": key,
               "hs": int, "as": int, "extra": bool|None}
    Keys are whatever stable team identifier the sport uses (MLB team
    id, ESPN team id) — never a display name, because names change
    between seasons (Utah, the Athletics) and the carryover would miss.
    """
    out = []
    for f in finals or []:
        hs, as_ = _num(f.get("hs")), _num(f.get("as"))
        if not f.get("home") or not f.get("away") or hs is None or as_ is None:
            continue
        if not f.get("date"):
            continue
        # Every other key is CARRIED THROUGH (starter ids, game_pk). The
        # first version rebuilt the row from five fields, which silently
        # dropped home_sp/away_sp — the starter layer then saw no starter
        # on any game and "with starters" scored identical to team-only
        # to four decimals. Asserted in tests/test_game_model.py.
        row = dict(f)
        row.update({"date": str(f["date"])[:10], "home": str(f["home"]),
                    "away": str(f["away"]), "hs": int(hs), "as": int(as_),
                    "extra": f.get("extra")})
        out.append(row)
    out.sort(key=lambda r: r["date"])
    return out


def league_constants(finals):
    """Exact arithmetic over a set of finals."""
    if not finals:
        return None
    n = len(finals)
    h = sum(f["hs"] for f in finals) / n
    a = sum(f["as"] for f in finals) / n
    lg = (h + a) / 2.0
    extras = [f for f in finals if f.get("extra") is True]
    ex_home = sum(1 for f in extras if f["hs"] > f["as"])
    return {
        "games": n,
        "league_rate": round(lg, 4),
        "home_mult": round(h / lg, 4) if lg else None,
        "away_mult": round(a / lg, 4) if lg else None,
        "home_win_rate": round(sum(1 for f in finals if f["hs"] > f["as"]) / n, 4),
        "extra_games": len(extras),
        # None, not 0.5, when there is nothing to measure — the caller
        # decides what an unmeasured tie-break means and the page says so.
        "tie_home_win": round(ex_home / len(extras), 4) if extras else None,
        "avg_total": round(h + a, 3),
    }


def team_totals(finals):
    """{team: {"gf", "ga", "gp"}} over a set of finals."""
    t = defaultdict(lambda: {"gf": 0, "ga": 0, "gp": 0})
    for f in finals:
        for side, opp in (("home", "away"), ("away", "home")):
            k = f[side]
            t[k]["gf"] += f["hs"] if side == "home" else f["as"]
            t[k]["ga"] += f["as"] if side == "home" else f["hs"]
            t[k]["gp"] += 1
    return dict(t)


def prior_targets(prior_totals, prior_league, league_rate, carryover):
    """{team: (off_target, def_target)} — last season, regressed.

    target = league + carryover * (last season's rate - last league),
    expressed against THIS season's league rate so a scoring-environment
    change between seasons does not leak in as team strength.
    """
    out = {}
    if not prior_totals or not prior_league or carryover is None:
        return out
    for team, t in prior_totals.items():
        if not t.get("gp"):
            continue
        off = t["gf"] / t["gp"] / prior_league
        dfn = t["ga"] / t["gp"] / prior_league
        out[team] = (league_rate * (1 + carryover * (off - 1)),
                     league_rate * (1 + carryover * (dfn - 1)))
    return out


def team_rates(totals, league_rate, k, targets=None):
    """{team: (off_rate, def_rate)} after shrinkage toward each team's
    target (last season regressed, or the league when there is none)."""
    out = {}
    targets = targets or {}
    teams = set(totals) | set(targets)
    for team in teams:
        t = totals.get(team) or {"gf": 0, "ga": 0, "gp": 0}
        to, td = targets.get(team, (league_rate, league_rate))
        out[team] = (mm.shrunk_rate(t["gf"], t["gp"], to, k),
                     mm.shrunk_rate(t["ga"], t["gp"], td, k))
    return out


def expected_scores(home, away, rates, consts, s_home=None, s_away=None):
    """(mu_home, mu_away) or (None, None) if either team is unknown.

    s_home / s_away: optional (share, rate) for the side's starting
    pitcher (or goalie) — the share of the game he is expected to cover
    and his own allowed rate on the per-game scale. His share of the
    team's defensive rate is REPLACED by his own; the rest stays the
    team's. Both numbers come from his real game logs (see
    mlb_model_precompute.starter_layer); None leaves the team rate alone.
    """
    lg = consts.get("league_rate")
    if not lg or home not in rates or away not in rates:
        return None, None
    oh, dh = rates[home]
    oa, da = rates[away]
    if s_home:
        sh, rh = s_home
        dh = (1.0 - sh) * dh + sh * rh
    if s_away:
        sa, ra = s_away
        da = (1.0 - sa) * da + sa * ra
    mu_h = oh * da / lg * (consts.get("home_mult") or 1.0)
    mu_a = oa * dh / lg * (consts.get("away_mult") or 1.0)
    return mu_h, mu_a


# ----------------------------------------------------------------------
# Walk-forward
# ----------------------------------------------------------------------
def walk_forward(finals, k, dispersion=None, prior_totals=None,
                 prior_league=None, carryover=None, tie_home_win=None,
                 starter_fn=None, score_only=False):
    """Predict every game from strictly earlier dates.

    Returns [{"date","home","away","mu_h","mu_a","p_home","y","total"}].
    League constants are re-measured from the games before each date as
    well — the home multiplier on April 2 cannot know the season's final
    home edge.

    starter_fn(final, side, league_rate) -> (share, rate) | None, called
    with the final itself so it can read who started and look up his
    record from BEFORE that date. It must never see the game's own line.

    score_only: expected scores without a win probability — for volume
    models (NHL shots) where "who out-shoots whom" is not the question
    and a 30-a-side expectation would overrun the score pmf anyway.
    """
    out = []
    by_date = defaultdict(list)
    for f in finals:
        by_date[f["date"]].append(f)
    seen = []
    totals = defaultdict(lambda: {"gf": 0, "ga": 0, "gp": 0})
    for d in sorted(by_date):
        if seen:
            consts = league_constants(seen)
            lg = consts["league_rate"]
            targets = prior_targets(prior_totals, prior_league, lg, carryover)
            rates = team_rates(dict(totals), lg, k, targets)
            thw = tie_home_win if tie_home_win is not None else (
                consts.get("tie_home_win") if consts.get("tie_home_win") is not None else 0.5)
            for f in by_date[d]:
                s_h = starter_fn(f, "home", lg) if starter_fn else None
                s_a = starter_fn(f, "away", lg) if starter_fn else None
                mu_h, mu_a = expected_scores(f["home"], f["away"], rates, consts,
                                             s_home=s_h, s_away=s_a)
                if mu_h is None:
                    continue
                p = None if score_only else mm.win_prob(mu_h, mu_a, dispersion, thw)
                if p is None and not score_only:
                    continue
                out.append({"date": d, "home": f["home"], "away": f["away"],
                            "mu_h": mu_h, "mu_a": mu_a, "p_home": p,
                            "off_h": rates[f["home"]][0], "off_a": rates[f["away"]][0],
                            "y": 1 if f["hs"] > f["as"] else 0, "extra": f.get("extra"),
                            "total": f["hs"] + f["as"], "hs": f["hs"], "as": f["as"],
                            "base_home": consts["home_win_rate"],
                            "base_total": consts["avg_total"]})
        for f in by_date[d]:
            seen.append(f)
            for side, gf, ga in (("home", f["hs"], f["as"]), ("away", f["as"], f["hs"])):
                totals[f[side]]["gf"] += gf
                totals[f[side]]["ga"] += ga
                totals[f[side]]["gp"] += 1
    return out


def _wf_logloss(finals, k, dispersion, **kw):
    preds = walk_forward(finals, k, dispersion, **kw)
    if not preds:
        return float("inf")
    return sum(mm.log_loss(p["p_home"], p["y"]) for p in preds) / len(preds)


def fit(finals, prior_totals=None, prior_league=None, fit_carryover=False,
        carryover=None):
    """Fit shrink_k (and carryover, if asked) by walk-forward log loss,
    then measure dispersion on the residuals. Returns the fitted dict.

    Two passes: k is fitted under Poisson, dispersion measured from
    those predictions, then k refitted under the measured dispersion.
    The second pass rarely moves k much, but it means the k on the page
    is the one that is optimal for the distribution actually used.
    """
    finals = clean_finals(finals)
    if len(finals) < 20:
        return None
    kw = {"prior_totals": prior_totals, "prior_league": prior_league}

    def fit_k(disp, carry):
        f = lambda lk: -_wf_logloss(finals, exp(lk), disp, carryover=carry, **kw)
        return exp(mm.golden_max(f, log(0.5), log(400.0), iters=40))

    carry = carryover if carryover is not None else (0.0 if prior_totals else None)
    k = fit_k(None, carry)
    if fit_carryover and prior_totals:
        f = lambda c: -_wf_logloss(finals, k, None, carryover=c, **kw)
        carry = mm.golden_max(f, 0.0, 1.0, iters=30)
        k = fit_k(None, carry)
    preds = walk_forward(finals, k, None, carryover=carry, **kw)
    pairs = [(p["mu_h"], p["hs"]) for p in preds] + [(p["mu_a"], p["as"]) for p in preds]
    disp = mm.nb_dispersion(pairs)
    if disp is not None:
        k = fit_k(disp, carry)
    return {"shrink_k": round(k, 3), "dispersion": round(disp, 3) if disp else None,
            "carryover": round(carry, 3) if carry is not None else None}


def validate(finals, params, prior_totals=None, prior_league=None,
             starter_fn=None):
    """Walk-forward report: the model against the two baselines a reader
    would otherwise use — a coin flip, and "the home team wins at the
    league's measured home rate" — plus totals against the league average
    total, and the calibration curve."""
    finals = clean_finals(finals)
    preds = walk_forward(finals, params["shrink_k"], params.get("dispersion"),
                         prior_totals=prior_totals, prior_league=prior_league,
                         carryover=params.get("carryover"), starter_fn=starter_fn)
    if not preds:
        return {"n": 0}
    model = mm.score_predictions([(p["p_home"], p["y"]) for p in preds])
    coin = mm.score_predictions([(0.5, p["y"]) for p in preds])
    home = mm.score_predictions([(p["base_home"], p["y"]) for p in preds])
    n = len(preds)
    mae_model = sum(abs(p["mu_h"] + p["mu_a"] - p["total"]) for p in preds) / n
    mae_base = sum(abs(p["base_total"] - p["total"]) for p in preds) / n
    picks_right = sum(1 for p in preds if (p["p_home"] >= 0.5) == (p["y"] == 1))
    # Paired against the STRONGER of the two win baselines per game (the
    # measured home rate) and the league-average total: what the trust
    # badges read.
    ml_v = mm.paired_verdict([mm.log_loss(p["p_home"], p["y"]) for p in preds],
                             [mm.log_loss(p["base_home"], p["y"]) for p in preds])
    tot_v = mm.paired_verdict([abs(p["mu_h"] + p["mu_a"] - p["total"]) for p in preds],
                              [abs(p["base_total"] - p["total"]) for p in preds])
    return {
        "ml_verdict": ml_v, "total_verdict": tot_v,
        "n": n,
        "from": preds[0]["date"], "to": preds[-1]["date"],
        "model": model, "coin_flip": coin, "home_rate": home,
        "beats_coin": model["log_loss"] < coin["log_loss"],
        "beats_home_rate": model["log_loss"] < home["log_loss"],
        "favourite_won_pct": round(100.0 * picks_right / n, 1),
        "total_mae_model": round(mae_model, 3),
        "total_mae_league_avg": round(mae_base, 3),
        "total_beats_league_avg": mae_model < mae_base,
        "calibration": mm.calibration_bins([(p["p_home"], p["y"]) for p in preds]),
    }


def build(finals, prior_finals=None, fit_carryover=True):
    """Everything the nightly writes for one sport: fitted params,
    league constants, current team rates, validation. None if there is
    not enough to fit."""
    finals = clean_finals(finals)
    prior_totals = prior_league = None
    carry_fit = None
    if prior_finals:
        pf = clean_finals(prior_finals)
        prior_totals = team_totals(pf)
        pc = league_constants(pf)
        prior_league = pc["league_rate"] if pc else None
    # Too few games this season to fit on (opening week): fit on the
    # prior season's own walk-forward instead, then carry the fitted
    # parameters forward. The page states which season the fit is from.
    fit_on, fit_season = finals, "current"
    if len(finals) < 150 and prior_finals:
        fit_on, fit_season = clean_finals(prior_finals), "prior"
    params = fit(fit_on) if fit_season == "prior" else fit(
        finals, prior_totals, prior_league, fit_carryover=fit_carryover and bool(prior_totals))
    if params is None:
        return None
    if fit_season == "prior" and prior_totals:
        # The carryover cannot be fitted on the season that IS the prior
        # (it would need the season before it). Measured instead as the
        # share of a team's first-half rate that survives into its second
        # half within the prior season — the same question, asked inside
        # one year. Documented on the page as the weaker of the two.
        carry_fit = _split_half_carryover(fit_on)
        params["carryover"] = carry_fit
    params["fit_on"] = fit_season
    # League constants come from the SAME season the fit came from. With
    # a few dozen games this season, home advantage and the league
    # scoring rate measured on them are noise (a 25-game home edge can be
    # anything), and they multiply every projection on the slate.
    if fit_season == "prior":
        consts = league_constants(clean_finals(prior_finals))
        consts["from"] = "prior"
    else:
        consts = league_constants(finals)
        consts["from"] = "current"
    lg = consts["league_rate"]
    targets = prior_targets(prior_totals, prior_league, lg, params.get("carryover"))
    rates = team_rates(team_totals(finals), lg, params["shrink_k"], targets)
    # Validation is always reported on the season the parameters were
    # fitted on — the only one with enough games to say anything — and
    # labelled with its date range.
    report = validate(fit_on, params) if fit_season == "prior" else validate(
        finals, params, prior_totals, prior_league)
    return {
        "params": params,
        "league": consts,
        "rates": {t: {"off": round(o, 4), "def": round(d, 4),
                      "gp": (team_totals(finals).get(t) or {}).get("gp", 0)}
                  for t, (o, d) in rates.items()},
        "validation": report,
    }


def _split_half_carryover(finals):
    """Regression slope of second-half team scoring rate on first-half,
    pooled over offense and defense, in league-relative units. A measured
    stand-in for year-to-year carryover when only one season exists."""
    finals = clean_finals(finals)
    if len(finals) < 40:
        return None
    mid = len(finals) // 2
    a, b = team_totals(finals[:mid]), team_totals(finals[mid:])
    la = league_constants(finals[:mid])["league_rate"]
    lb = league_constants(finals[mid:])["league_rate"]
    xs, ys = [], []
    for t in set(a) & set(b):
        if not a[t]["gp"] or not b[t]["gp"]:
            continue
        for key in ("gf", "ga"):
            xs.append(a[t][key] / a[t]["gp"] / la - 1)
            ys.append(b[t][key] / b[t]["gp"] / lb - 1)
    if len(xs) < 4:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return round(max(0.0, min(1.0, slope)), 3)


# ----------------------------------------------------------------------
# Projection — what a page calls
# ----------------------------------------------------------------------
def project(model, home, away, market=None, s_home=None, s_away=None):
    """The card for one game, from a built model dict.

    market: optional {"home_ml","away_ml","total"} from a book feed.
    s_home / s_away: optional (share, rate) starter layer, see
    expected_scores.
    Returns None when either team is unknown to the model — never a
    league-average stand-in, which would print a confident 50/50 for a
    team the model has simply never seen.
    """
    if not model:
        return None
    rates = {t: (r["off"], r["def"]) for t, r in (model.get("rates") or {}).items()}
    consts = model.get("league") or {}
    params = model.get("params") or {}
    mu_h, mu_a = expected_scores(str(home), str(away), rates, consts,
                                 s_home=s_home, s_away=s_away)
    if mu_h is None:
        return None
    disp = params.get("dispersion")
    thw = consts.get("tie_home_win")
    thw_measured = thw is not None
    p = mm.win_prob(mu_h, mu_a, disp, thw if thw_measured else 0.5)
    if p is None:
        return None
    out = {
        "home_score": round(mu_h, 2), "away_score": round(mu_a, 2),
        "total": round(mu_h + mu_a, 2),
        "p_home": round(p, 4), "p_away": round(1 - p, 4),
        "fair_home": mm.fair_american(p), "fair_away": mm.fair_american(1 - p),
        "tie_rule_measured": thw_measured,
    }
    market = market or {}
    mh, ma = mm.no_vig_pair(market.get("home_ml"), market.get("away_ml"))
    if mh is not None:
        out["market_home"] = round(mh, 4)
        out["market_away"] = round(ma, 4)
        out["edge_home"] = round(p - mh, 4)
    line = _num(market.get("total"))
    if line is not None:
        po = mm.total_over_prob(mu_h, mu_a, line, disp)
        if po is not None:
            out["market_total"] = line
            out["p_over"] = round(po, 4)
            out["fair_over"] = mm.fair_american(po)
            out["fair_under"] = mm.fair_american(1 - po)
    return out


def fit_volume(finals, prior_finals=None):
    """shrink_k for a VOLUME model (shots) by walk-forward squared error
    on each side's count — the right objective when the expectation, not
    a winner, is the output. Returns a build()-shaped dict (params,
    league, rates) or None."""
    finals = clean_finals(finals)
    fit_on = finals if len(finals) >= 150 or not prior_finals else clean_finals(prior_finals)
    if len(fit_on) < 20:
        return None

    def neg_mse(lk):
        preds = walk_forward(fit_on, exp(lk), score_only=True)
        if not preds:
            return float("-inf")
        return -sum((p["mu_h"] - p["hs"]) ** 2 + (p["mu_a"] - p["as"]) ** 2
                    for p in preds) / len(preds)

    k = exp(mm.golden_max(neg_mse, log(0.5), log(400.0), iters=40))
    base = finals if finals else fit_on
    consts = league_constants(base)
    prior_totals = prior_league = None
    carry = None
    if prior_finals:
        pf = clean_finals(prior_finals)
        prior_totals, prior_league = team_totals(pf), league_constants(pf)["league_rate"]
        carry = _split_half_carryover(pf)
    targets = prior_targets(prior_totals, prior_league, consts["league_rate"], carry)
    rates = team_rates(team_totals(finals), consts["league_rate"], k, targets)
    return {"params": {"shrink_k": round(k, 3), "carryover": carry,
                       "fit_on": "current" if fit_on is finals else "prior"},
            "league": consts,
            "rates": {t: {"off": round(o, 4), "def": round(d, 4)} for t, (o, d) in rates.items()}}
