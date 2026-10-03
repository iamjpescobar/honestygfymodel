"""
NHL game model + skater props.

GAME MODEL
----------
engines/game_model on GOALS, keyed by ESPN team id: offense x opponent
defense / league x home multiplier, Poisson-or-NB goals (dispersion
measured; hockey usually comes back near Poisson and the fit says so),
regulation ties resolved at the MEASURED rate the home side wins OT/SO.

In October there is not enough of this season to fit on, so parameters
are fitted on LAST season (data/nhl/prior_season.json) and each team
starts from its last-season rating regressed by a measured carryover;
this season's games take over through the fitted shrinkage. The page
says which season the fit and the test came from.

SHOTS MODEL
-----------
The same pairing on SHOTS ON GOAL (who generates and who allows volume),
fitted on squared error rather than win probability — volume is the
output, not a winner. It sets tonight's shot environment for each team.

SKATER PROPS
------------
Per skater, three rates per game — shots, goals, assists — each shrunk
toward his position group (F or D) by a gamma-Poisson prior FITTED over
every skater. Tonight's matchup scales them by the ratio of his team's
expected shots (or goals) tonight to its neutral rate:

    exp SOG   = his SOG rate   x team exp shots tonight / team shots rate
    exp G, A  = his G, A rates x team exp goals tonight / team goals rate

SOG is negative binomial with a MEASURED size; goals, assists and points
are Poisson (points = goals + assists, treated as independent). Each
market is scored walk-forward against the skater's OWN hit rate, exactly
like MLB; a market that does not beat it is starred.

NOT IN THE NUMBER, stated on the page: tonight's line deployment and
power-play unit, injuries announced after the nightly, the goalie.

Pure — no streamlit, no requests.
"""
from collections import defaultdict

from engines import game_model as gm
from engines import model_math as mm

MARKETS = (
    ("sog2", "SOG O1.5", "sog", 2),
    ("sog3", "SOG O2.5", "sog", 3),
    ("sog4", "SOG O3.5", "sog", 4),
    ("pt1", "Pts O0.5", "pts", 1),
    ("g1", "Goal O0.5", "g", 1),
    ("a1", "Ast O0.5", "a", 1),
)
# Not a model parameter: how much of the end of a season the props
# report covers. Printed beside the result.
VALIDATION_DAYS = 60


def group(pos):
    return "D" if str(pos or "").upper().startswith("D") else "F"


def goal_rows(finals):
    return [{"date": f["date"], "home": f["home"], "away": f["away"],
             "hs": f["hs"], "as": f["as"], "extra": f.get("extra")} for f in finals]


def shot_rows(finals):
    return [{"date": f["date"], "home": f["home"], "away": f["away"],
             "hs": f["home_sog"], "as": f["away_sog"]}
            for f in finals if f.get("home_sog") is not None and f.get("away_sog") is not None]


# ----------------------------------------------------------------------
# Skater rates
# ----------------------------------------------------------------------
def _sums(games):
    """(gp, sog, sog_gp, g, a) — sog_gp counts only games where shots were
    recorded, so a missing box line never reads as a 0-shot game."""
    gp = sog = sog_gp = g = a = 0
    for row in games:
        _d, _opp, s, gg, aa, _toi = row
        gp += 1
        if s is not None:
            sog += s
            sog_gp += 1
        g += gg or 0
        a += aa or 0
    return gp, sog, sog_gp, g, a


def fit_priors(pool):
    """{group: {"sog": [mean, s], "g": [...], "a": [...]}} plus the SOG
    negative-binomial size, all fitted over the pool."""
    by = defaultdict(lambda: {"sog": [], "g": [], "a": []})
    for p in pool.values():
        gp, sog, sog_gp, g, a = _sums(p["games"])
        if not gp:
            continue
        grp = group(p.get("pos"))
        if sog_gp:
            by[grp]["sog"].append((sog, sog_gp))
        by[grp]["g"].append((g, gp))
        by[grp]["a"].append((a, gp))
    pri = {}
    for grp, d in by.items():
        pri[grp] = {}
        for stat, obs in d.items():
            mu, s = mm.fit_gamma_prior(obs)
            if mu is None:
                return None
            pri[grp][stat] = [round(mu, 5), round(s, 3)]
    pairs = []
    for p in pool.values():
        r = rates(p, pri)
        if not r:
            continue
        for _d, _o, s, *_ in p["games"]:
            if s is not None:
                pairs.append((r["sog"], s))
    pri["sog_dispersion"] = mm.nb_dispersion(pairs)
    return pri


def rates(player, priors, before=None):
    """{"sog","g","a","gp"} per game, shrunk; games on/after `before`
    excluded (walk-forward)."""
    grp = (priors or {}).get(group(player.get("pos")))
    if not grp:
        return None
    games = [x for x in player["games"] if before is None or x[0] < before]
    gp, sog, sog_gp, g, a = _sums(games)
    out = {"gp": gp}
    for stat, cnt, n in (("sog", sog, sog_gp), ("g", g, gp), ("a", a, gp)):
        mu, s = grp[stat]
        out[stat] = (cnt + mu * s) / (n + s)
    return out


def probs(r, shot_ratio=1.0, goal_ratio=1.0, sog_disp=None):
    """{market: p} for one skater tonight."""
    if not r:
        return None
    sog_mu = r["sog"] * (shot_ratio or 1.0)
    g_mu, a_mu = r["g"] * (goal_ratio or 1.0), r["a"] * (goal_ratio or 1.0)
    pm = {"sog": mm.nb_pmf(sog_mu, sog_disp, 20), "g": mm.poisson_pmf(g_mu, 10),
          "a": mm.poisson_pmf(a_mu, 10), "pts": mm.poisson_pmf(g_mu + a_mu, 10)}
    out = {k: round(mm.prob_at_least(pm[stat], n), 4) for k, _l, stat, n in MARKETS}
    out["_exp_sog"] = round(sog_mu, 2)
    out["_exp_pts"] = round(g_mu + a_mu, 2)
    return out


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------
def _env_by_opp(wf):
    """{(date, opp_team): (team expectation, team neutral rate)} from a
    walk-forward — keyed by OPPONENT because a skater's game line records
    who he played, not (reliably) whom he played for that night."""
    out = {}
    for p in wf:
        out[(p["date"], p["away"])] = (p["mu_h"], p["off_h"])
        out[(p["date"], p["home"])] = (p["mu_a"], p["off_a"])
    return out


def validate_props(skaters, goal_finals, shot_finals, days=VALIDATION_DAYS,
                   goal_k=None, shot_k=None):
    """Walk-forward over the last `days` of a season's skater lines."""
    all_dates = sorted({x[0] for p in skaters.values() for x in p["games"]})
    if len(all_dates) < days + 30:
        return {"note": "season too short to validate"}
    cut = all_dates[-days]
    priors = fit_priors(skaters)
    if not priors:
        return {"note": "prior fit failed"}
    g_env = _env_by_opp(gm.walk_forward(gm.clean_finals(goal_finals), goal_k or 30.0))
    s_env = _env_by_opp(gm.walk_forward(gm.clean_finals(shot_finals), shot_k or 30.0,
                                        score_only=True)) if shot_finals else {}
    preds = {k: [] for k, *_ in MARKETS}
    base = {k: [] for k, *_ in MARKETS}
    for p in skaters.values():
        games = sorted(p["games"], key=lambda x: x[0])
        for i, (d, opp, s, g, a, _toi) in enumerate(games):
            if d < cut or i == 0:
                continue
            r = rates(p, priors, before=d)
            ge, se = g_env.get((d, opp)), s_env.get((d, opp))
            gr = ge[0] / ge[1] if ge and ge[1] else 1.0
            sr = se[0] / se[1] if se and se[1] else 1.0
            pr = probs(r, sr, gr, priors.get("sog_dispersion"))
            actual = {"sog": s, "g": g or 0, "a": a or 0, "pts": (g or 0) + (a or 0)}
            prior_games = games[:i]
            for k, _l, stat, n in MARKETS:
                if actual[stat] is None:
                    continue
                y = 1 if actual[stat] >= n else 0
                hist = [{"sog": x[2], "g": x[3] or 0, "a": x[4] or 0,
                         "pts": (x[3] or 0) + (x[4] or 0)}[stat] for x in prior_games]
                hist = [h for h in hist if h is not None]
                if not hist:
                    continue
                preds[k].append((pr[k], y))
                base[k].append((sum(1 for h in hist if h >= n) / len(hist), y))
    out = {"from": cut, "to": all_dates[-1], "days": days}
    for k, *_ in MARKETS:
        m, b = mm.score_predictions(preds[k]), mm.score_predictions(base[k])
        out[k] = {"verdict": mm.paired_verdict([(p_ - y) ** 2 for p_, y in preds[k]],
                                               [(q - y) ** 2 for q, y in base[k]]),
                  "n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
                  "beats_baseline": bool(m["brier"] is not None and b["brier"] is not None
                                         and m["brier"] < b["brier"]),
                  "calibration": mm.calibration_bins(preds[k])}
    return out


# ----------------------------------------------------------------------
# Build — called by nhl_precompute with everything it already holds
# ----------------------------------------------------------------------
def pool_skaters(prior_skaters, current_skaters, current_id_of):
    """Prior-season lines + this season's, per ESPN athlete id.

    current_skaters is nhl_precompute's live dict ({pid: {"games":
    {eid: line}}}); current_id_of maps a team display name to its id so
    the opponent on this season's lines is keyed like last season's.
    """
    pool = {}
    for pid, p in (prior_skaters or {}).items():
        pool[pid] = {"name": p.get("name"), "pos": p.get("pos"), "team": p.get("team"),
                     "games": [tuple(x) for x in p.get("games") or []]}
    for pid, rec in (current_skaters or {}).items():
        dst = pool.setdefault(str(pid), {"name": rec.get("name"), "pos": rec.get("pos"),
                                         "team": None, "games": []})
        dst["name"] = rec.get("name") or dst["name"]
        dst["pos"] = rec.get("pos") or dst["pos"]
        for line in (rec.get("games") or {}).values():
            dst["games"].append((line.get("date"), current_id_of.get(line.get("opp")),
                                 line.get("sog"), line.get("g"), line.get("a"), line.get("toi")))
    return pool


def build(current_finals, prior, current_skaters=None, current_id_of=None, slate=None,
          regular_ids=None):
    """Fit everything, attach projections to `slate` in place, return the
    model block for games.json."""
    prior = prior or {}
    pf = prior.get("finals") or []
    goal = gm.build(goal_rows(current_finals), goal_rows(pf) if pf else None)
    if goal is None:
        return None
    shots = gm.fit_volume(shot_rows(current_finals), shot_rows(pf) if pf else None)

    pool = pool_skaters(prior.get("skaters"), current_skaters, current_id_of or {})
    priors = fit_priors(pool) if pool else None
    # The props test runs on the season the parameters can be judged on:
    # last season, end to end (the current one is days old).
    pval = validate_props(
        {k: v for k, v in ((prior.get("skaters") or {}).items())},
        goal_rows(pf), shot_rows(pf),
        goal_k=goal["params"]["shrink_k"],
        shot_k=(shots or {}).get("params", {}).get("shrink_k")) if pf else {"note": "no prior season file"}

    for g in slate or []:
        hid, aid = g.get("home_id"), g.get("away_id")
        o = g.get("odds") or {}
        proj = gm.project(goal, hid, aid, market={"home_ml": o.get("home_ml"),
                                                  "away_ml": o.get("away_ml"),
                                                  "total": o.get("total")})
        if proj:
            g["model"] = proj
        if not priors or not proj:
            continue
        s_h = s_a = None
        if shots:
            s_rates = {t: (r["off"], r["def"]) for t, r in shots["rates"].items()}
            s_h, s_a = gm.expected_scores(hid, aid, s_rates, shots["league"])
        g_rates = goal["rates"]
        for side, tid, mu_g, mu_s in (("home", hid, proj["home_score"], s_h),
                                      ("away", aid, proj["away_score"], s_a)):
            gr = mu_g / g_rates[tid]["off"] if tid in g_rates and g_rates[tid]["off"] else 1.0
            sr = (mu_s / shots["rates"][tid]["off"]
                  if shots and mu_s and tid in shots["rates"] and shots["rates"][tid]["off"] else 1.0)
            rows = []
            for sk in g.get(f"{side}_skaters") or []:
                p = pool.get(str(sk.get("pid")))
                if not p or str(sk.get("pos") or "").upper() == "G":
                    continue
                r = rates(p, priors)
                pr = probs(r, sr, gr, priors.get("sog_dispersion"))
                if not pr:
                    continue
                rows.append({"pid": sk.get("pid"), "name": sk.get("name") or p.get("name"),
                             "pos": sk.get("pos") or p.get("pos"), "gp": r["gp"],
                             "toi": sk.get("toi"), "exp_sog": pr["_exp_sog"],
                             "exp_pts": pr["_exp_pts"],
                             "probs": {k: pr[k] for k, *_ in MARKETS}})
            g[f"{side}_props"] = rows
            g[f"{side}_env"] = {"goal_ratio": round(gr, 3), "shot_ratio": round(sr, 3)}

    return {
        "params": goal["params"], "league": goal["league"], "validation": goal["validation"],
        "shots": {"params": (shots or {}).get("params"),
                  "league": (shots or {}).get("league")},
        "skater_priors": priors,
        "props_validation": pval,
        "prior_season": prior.get("season"),
        "current_finals": len(current_finals),
    }
