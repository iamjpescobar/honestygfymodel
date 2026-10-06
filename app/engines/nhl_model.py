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

ICE TIME (10-06)
---------------
A skater's rate is per GAME, but a game is minutes. When his recent ice
time differs from what his rate was built on, the rate is scaled by

    (his last W games' TOI / his TOI over the games the rate uses) ^ alpha

alpha and W are FITTED per family (shots; goals/assists/points) on the
window just before the props test, then the family is TESTED on the
props window against the same model without it. A family whose pooled
verdict is not "beats" gets alpha 0 — the factor is shown on the page
as context and kept out of the number (rule 12). fit_toi.

DEFENSE VS POSITION (10-06)
---------------------------
What each team allows to centres, wingers and defencemen (shots, points,
goals, assists), this season and last, blended at a fitted weight and
ranked — engines/defense_matchup. validate_dvp tests whether the
POSITION split moves the chance once the team's total shots and goals
allowed are already in it (the shots/goals model above). Unless it beats
on games it had not seen, it is context on the page, not the number.

NOT IN THE NUMBER, stated on the page: tonight's line deployment and
power-play unit, injuries announced after the nightly, the goalie.

Pure — no streamlit, no requests.
"""
from collections import defaultdict

from engines import defense_matchup as dm
from engines import game_model as gm
from engines import model_math as mm

MARKETS = (
    ("sog2", "SOG O1.5", "sog", 2),
    ("sog3", "SOG O2.5", "sog", 3),
    ("sog4", "SOG O3.5", "sog", 4),
    ("sog5", "SOG O4.5", "sog", 5),
    ("pt1", "Pts O0.5", "pts", 1),
    ("pt2", "Pts O1.5", "pts", 2),
    ("g1", "Goal O0.5", "g", 1),
    ("a1", "Ast O0.5", "a", 1),
)
# Stat groups on the page: (stat, label, lines shown); any other line is
# priced by the any-line checker off the same distribution.
STATS = (
    ("sog", "Shots on goal", (1.5, 2.5, 3.5, 4.5)),
    ("pts", "Points", (0.5, 1.5)),
    ("g", "Goals", (0.5,)),
    ("a", "Assists", (0.5,)),
)
# Goalie saves: (key, label, stat, at_least). Tested at TEAM level on the
# prior season (validate_saves) — the goalie's own save rate is the only
# thing the team test does not exercise, and the page says so.
SAVE_MARKETS = (
    ("sv23", "Saves O22.5", "sv", 23),
    ("sv25", "Saves O24.5", "sv", 25),
    ("sv27", "Saves O26.5", "sv", 27),
    ("sv29", "Saves O28.5", "sv", 29),
)
SAVE_STATS = (("sv", "Saves", (22.5, 24.5, 26.5, 28.5)),)
# Not a model parameter: how much of the end of a season the props
# report covers. Printed beside the result.
VALIDATION_DAYS = 60
# Ice-time windows SEARCHED by fit_toi (the fit picks one; these are the
# candidates, not a choice). Stat families the factor is fitted per.
TOI_WINDOWS = (5, 10, 20)
TOI_FAMILIES = {"sog": ("sog",), "pts": ("g", "a", "pts")}
# Defense-vs-position groups and the stats tabulated for them.
DVP_GROUPS = ("C", "W", "D")
DVP_STATS = ("sog", "pts", "g", "a")
DVP_GROUP_LABELS = {"C": "centres", "W": "wingers", "D": "defencemen", "ALL": "skaters"}
DVP_STAT_LABELS = {"sog": "shots on goal", "pts": "points", "g": "goals", "a": "assists"}


def group(pos):
    return "D" if str(pos or "").upper().startswith("D") else "F"


def dvp_group(pos):
    """C / W / D — the defense-vs-position split (finer than group())."""
    p = str(pos or "").upper()
    if p.startswith("D"):
        return "D"
    return "C" if p.startswith("C") else "W"


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


def probs(r, shot_ratio=1.0, goal_ratio=1.0, sog_disp=None, toi_sog=1.0, toi_pts=1.0):
    """{market: p} for one skater tonight. toi_sog / toi_pts are the
    fitted ice-time scales (1.0 when the factor did not earn its way in)."""
    if not r:
        return None
    sog_mu = r["sog"] * (shot_ratio or 1.0) * (toi_sog or 1.0)
    gs = (goal_ratio or 1.0) * (toi_pts or 1.0)
    g_mu, a_mu = r["g"] * gs, r["a"] * gs
    pm = {"sog": mm.nb_pmf(sog_mu, sog_disp, 20), "g": mm.poisson_pmf(g_mu, 10),
          "a": mm.poisson_pmf(a_mu, 10), "pts": mm.poisson_pmf(g_mu + a_mu, 10)}
    out = {k: round(mm.prob_at_least(pm[stat], n), 4) for k, _l, stat, n in MARKETS}
    out["_exp_sog"] = round(sog_mu, 2)
    out["_exp_pts"] = round(g_mu + a_mu, 2)
    out["_mu"] = {"sog": round(sog_mu, 4), "g": round(g_mu, 4), "a": round(a_mu, 4)}
    return out


def skater_pmfs(mu, sog_disp=None):
    """{stat: pmf} for a skater's stored tonight-means — what the page's
    prop board and any-line checker price from. Same distributions as
    probs(): shots negative binomial at the measured size, goals and
    assists Poisson, points their (independent) sum."""
    if not mu:
        return {}
    g, a = mu.get("g") or 0.0, mu.get("a") or 0.0
    return {"sog": mm.nb_pmf(mu.get("sog") or 0.0, sog_disp, 20),
            "pts": mm.poisson_pmf(g + a, 10), "g": mm.poisson_pmf(g, 10),
            "a": mm.poisson_pmf(a, 10)}


# ----------------------------------------------------------------------
# Goalie saves
# ----------------------------------------------------------------------
def saves_pmf(mu_shots, shot_disp, sv_pct, max_saves=80):
    """P(saves = k): shots against negative binomial around the shots
    model's expectation for the OPPONENT (size measured on its residuals),
    each shot saved with his shrunk save rate (binomial thinning)."""
    if not mu_shots or sv_pct is None:
        return None
    shots = mm.nb_pmf(mu_shots, shot_disp, max_saves)
    tot = sum(shots)
    shots = [x / tot for x in shots] if tot else shots      # mass past the cap folded back
    out = [0.0] * (max_saves + 1)
    for n, ps in enumerate(shots):
        if ps < 1e-12:
            continue
        # binomial(n, sv) pmf by recurrence
        q = 1.0 - sv_pct
        b = q ** n
        for k in range(n + 1):
            out[k] += ps * b
            if k < n:
                b = b * (n - k) / (k + 1) * (sv_pct / q if q > 0 else 0.0)
    return out


def fit_save_prior(goalies):
    """(mean, strength in shots) — beta-binomial over every goalie's
    season saves / shots against, FITTED."""
    obs = [(int(g.get("sv") or 0), int(g.get("sa") or 0)) for g in (goalies or {}).values()
           if g.get("sa")]
    return mm.fit_beta_prior(obs)


def goalie_sv(prior_g, cur_g, prior_mean, strength):
    """His save rate: last season's and this season's saves and shots,
    pulled toward the league by the fitted strength."""
    sv = int((prior_g or {}).get("sv") or 0) + int((cur_g or {}).get("sv") or 0)
    sa = int((prior_g or {}).get("sa") or 0) + int((cur_g or {}).get("sa") or 0)
    if prior_mean is None or strength is None:
        return None
    return (sv + prior_mean * strength) / (sa + strength), sa


def shot_dispersion(shot_finals, k):
    """NB size of team shots on the shots model's walk-forward residuals."""
    preds = gm.walk_forward(gm.clean_finals(shot_finals), k, score_only=True)
    pairs = [(p["mu_h"], p["hs"]) for p in preds] + [(p["mu_a"], p["as"]) for p in preds]
    return mm.nb_dispersion(pairs) if pairs else None


def validate_saves(prior_finals, shot_k, days=VALIDATION_DAYS):
    """Walk-forward, TEAM level, over the last `days` of last season:
    saves = opponent shots on goal - opponent goals; the model is the
    shots model's expectation for the opponent with the team's save rate
    to date (shrunk to the league by a beta prior fitted on teams),
    against the baseline of the team's own earlier frequency at the line.
    Tests the machinery a goalie line uses — except his personal rate."""
    rows = [f for f in prior_finals or [] if f.get("home_sog") is not None
            and f.get("away_sog") is not None]
    if len(rows) < 200:
        return {"note": "not enough finals with shots"}
    shots = shot_rows(rows)
    disp = shot_dispersion(shots, shot_k)
    preds = gm.walk_forward(gm.clean_finals(shots), shot_k, score_only=True)
    by_game = {(p["date"], p["home"], p["away"]): p for p in preds}
    dates = sorted({f["date"] for f in rows})
    cut = dates[-days] if len(dates) > days else dates[0]
    team = {}
    team_obs = {}
    for f in sorted(rows, key=lambda r: r["date"]):
        for side, opp_sog, opp_g in (("home", f["away_sog"], f["as"]), ("away", f["home_sog"], f["hs"])):
            t = f[side]
            team_obs.setdefault(t, []).append((f["date"], opp_sog - opp_g, opp_sog))
    mean, strength = mm.fit_beta_prior([(sum(x[1] for x in v), sum(x[2] for x in v))
                                        for v in team_obs.values()])
    preds_out = {k: [] for k, *_ in SAVE_MARKETS}
    base = {k: [] for k, *_ in SAVE_MARKETS}
    for f in rows:
        if f["date"] < cut:
            continue
        p = by_game.get((f["date"], f["home"], f["away"]))
        if not p:
            continue
        for side, mu_opp, opp_sog, opp_g in (("home", p["mu_a"], f["away_sog"], f["as"]),
                                             ("away", p["mu_h"], f["home_sog"], f["hs"])):
            before = [x for x in team_obs[f[side]] if x[0] < f["date"]]
            if not before:
                continue
            sv = (sum(x[1] for x in before) + mean * strength) / (sum(x[2] for x in before) + strength)
            pmf = saves_pmf(mu_opp, disp, sv)
            actual = opp_sog - opp_g
            for k, _l, _s, n in SAVE_MARKETS:
                y = 1 if actual >= n else 0
                preds_out[k].append((mm.prob_at_least(pmf, n), y))
                base[k].append((sum(1 for x in before if x[1] >= n) / len(before), y))
    out = {"from": cut, "to": dates[-1], "days": days, "shot_dispersion": disp,
           "level": "team"}
    for k, *_ in SAVE_MARKETS:
        m, b = mm.score_predictions(preds_out[k]), mm.score_predictions(base[k])
        out[k] = {"verdict": mm.paired_verdict([(p_ - y) ** 2 for p_, y in preds_out[k]],
                                               [(q - y) ** 2 for q, y in base[k]]),
                  "n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
                  "beats_baseline": bool(m["brier"] is not None and b["brier"] is not None
                                         and m["brier"] < b["brier"]),
                  "calibration": mm.calibration_bins(preds_out[k])}
    return out


# ----------------------------------------------------------------------
# Ice time (10-06)
# ----------------------------------------------------------------------
def toi_ratio(games_before, window):
    """(recent TOI, baseline TOI, ratio) from game tuples in date order —
    baseline over every game the rate is built on, recent over the last
    `window`. None when either is unmeasured (rule 6: a missing TOI is
    not a 0-minute game)."""
    prev = [x[5] for x in games_before if x[5]]
    if not prev:
        return None
    base = sum(prev) / len(prev)
    rec = prev[-window:]
    recent = sum(rec) / len(rec)
    if base <= 0:
        return None
    return recent, base, recent / base


def toi_scales(games_before, toi):
    """{"sog": scale, "pts": scale, "recent", "base", "window"} for the
    adopted ice-time fit (alpha 0 -> 1.0)."""
    out = {"sog": 1.0, "pts": 1.0}
    if not toi:
        return out
    for fam in TOI_FAMILIES:
        f = toi.get(fam) or {}
        if not f.get("window"):
            continue
        tr = toi_ratio(games_before, f["window"])
        if tr:
            out[fam] = tr[2] ** f["alpha"]
    w = max([(toi.get(f) or {}).get("window") or 0 for f in TOI_FAMILIES] or [0]) or TOI_WINDOWS[1]
    tr = toi_ratio(games_before, w)
    if tr:
        out.update({"recent": round(tr[0], 1), "base": round(tr[1], 1), "window": w})
    return out


def _wf_rows(skaters, goal_finals, shot_finals, lo, hi, goal_k, shot_k, priors):
    """Every skater-game in [lo, hi) as (rate, shot_ratio, goal_ratio,
    {window: ice ratio}, actual) — the inputs both the ice-time fit and
    its test reuse, so the expensive part runs once per window."""
    g_env = _env_by_opp(gm.walk_forward(gm.clean_finals(goal_finals), goal_k or 30.0))
    s_env = _env_by_opp(gm.walk_forward(gm.clean_finals(shot_finals), shot_k or 30.0,
                                        score_only=True)) if shot_finals else {}
    rows = []
    for p in skaters.values():
        games = sorted(p["games"], key=lambda x: x[0])
        for i, (d, opp, s, g, a, _toi) in enumerate(games):
            if d < lo or d >= hi or i == 0:
                continue
            r = rates(p, priors, before=d)
            if not r:
                continue
            ge, se = g_env.get((d, opp)), s_env.get((d, opp))
            gr = ge[0] / ge[1] if ge and ge[1] else 1.0
            sr = se[0] / se[1] if se and se[1] else 1.0
            ratios = {}
            for w in TOI_WINDOWS:
                tr = toi_ratio(games[:i], w)
                ratios[w] = tr[2] if tr else 1.0
            rows.append((r, sr, gr, ratios,
                         {"sog": s, "g": g or 0, "a": a or 0, "pts": (g or 0) + (a or 0)},
                         (d, opp, dvp_group(p.get("pos")))))
    return rows


def _family_losses(rows, fam, window, alpha, disp):
    """[(p, y)] over the family's markets at one (window, alpha)."""
    stats = TOI_FAMILIES[fam]
    out = []
    for r, sr, gr, ratios, actual, _key in rows:
        sc = ratios.get(window, 1.0) ** alpha if window else 1.0
        pr = probs(r, sr, gr, disp, toi_sog=sc if fam == "sog" else 1.0,
                   toi_pts=sc if fam == "pts" else 1.0)
        for k, _l, stat, n in MARKETS:
            if stat not in stats or actual[stat] is None:
                continue
            out.append((pr[k], 1 if actual[stat] >= n else 0))
    return out


def fit_toi(skaters, goal_finals, shot_finals, days=VALIDATION_DAYS, goal_k=None, shot_k=None):
    """Fit (window, alpha) per family on the `days` before the props
    window, test on the props window against alpha 0. Returns
    {fam: {"window", "alpha", "fitted_alpha", "train_n", "verdict", ...}};
    alpha is the fitted one only when the test verdict is "beats"."""
    all_dates = sorted({x[0] for p in skaters.values() for x in p["games"]})
    if len(all_dates) < 2 * days + 30:
        return {"note": "season too short to fit ice time"}
    cut = all_dates[-days]
    lo = all_dates[-2 * days]
    priors = fit_priors(skaters)
    if not priors:
        return {"note": "prior fit failed"}
    disp = priors.get("sog_dispersion")
    train = _wf_rows(skaters, goal_finals, shot_finals, lo, cut, goal_k, shot_k, priors)
    test = _wf_rows(skaters, goal_finals, shot_finals, cut, "9999", goal_k, shot_k, priors)
    out = {"train": [lo, cut], "test": [cut, all_dates[-1]]}
    for fam in TOI_FAMILIES:
        best = None
        for w in TOI_WINDOWS:
            def ll(alpha, w=w):
                pts = _family_losses(train, fam, w, alpha, disp)
                return -sum(mm.log_loss(p, y) for p, y in pts) / max(len(pts), 1)
            a = mm.golden_max(ll, 0.0, 2.0, iters=24)
            v = ll(a)
            if best is None or v > best[2]:
                best = (w, a, v)
        w, a, _v = best
        with_ = _family_losses(test, fam, w, a, disp)
        without = _family_losses(test, fam, w, 0.0, disp)
        verdict = mm.paired_verdict([mm.log_loss(p, y) for p, y in with_],
                                    [mm.log_loss(p, y) for p, y in without])
        sb, sw = mm.score_predictions(without), mm.score_predictions(with_)
        adopted = verdict.get("verdict") == "beats"
        out[fam] = {"window": w, "fitted_alpha": round(a, 3),
                    "alpha": round(a, 3) if adopted else 0.0,
                    "adopted": adopted, "verdict": verdict,
                    "n": sw["n"], "brier_with": sw["brier"], "brier_without": sb["brier"],
                    "log_loss_with": sw["log_loss"], "log_loss_without": sb["log_loss"]}
    return out


# ----------------------------------------------------------------------
# Defense vs position (10-06)
# ----------------------------------------------------------------------
def dvp_lines(skaters, season, id_of=None, regular_ids=None):
    """engines/defense_matchup rows from skater game lines.

    skaters: last season's {pid: {"pos", "games": [(date, opp_id, sog, g,
    a, toi)]}} (season="prior"), or this season's live dict {pid: {"pos",
    "games": {eid: {date, opp, sog, g, a}}}} (season="cur"; opp is a
    display name mapped through id_of). The game key is the date: a team
    plays once a day."""
    out = []
    for p in (skaters or {}).values():
        grp = dvp_group(p.get("pos"))
        if str(p.get("pos") or "").upper() == "G":
            continue
        games = p.get("games") or []
        if isinstance(games, dict):
            items = [(eid, ln) for eid, ln in games.items()
                     if regular_ids is None or str(eid) in regular_ids]
            rows = [(ln.get("date"), (id_of or {}).get(ln.get("opp")), ln.get("sog"),
                     ln.get("g"), ln.get("a")) for _eid, ln in items]
        else:
            rows = [(x[0], x[1], x[2], x[3], x[4]) for x in games]
        for d, opp, s, g, a in rows:
            if not d or opp in (None, ""):
                continue
            stats = {"sog": s, "g": g, "a": a,
                     "pts": (g or 0) + (a or 0) if (g is not None or a is not None) else None}
            out.append({"season": season, "defense": str(opp), "game": d,
                        "group": grp, "stats": stats})
    return out


def validate_dvp(skaters, goal_finals, shot_finals, days=VALIDATION_DAYS,
                 goal_k=None, shot_k=None):
    """Does the POSITION split move the chance once the team's total
    shots/goals allowed are in? Walk-forward on last season's props
    window: the model as-is vs the model x the defense's shrunk SHARE of
    what it allows going to his position group (beta prior fitted over
    defenses, recomputed from games before each date). Pooled per family."""
    all_dates = sorted({x[0] for p in skaters.values() for x in p["games"]})
    if len(all_dates) < days + 30:
        return {"note": "season too short to validate"}
    cut = all_dates[-days]
    priors = fit_priors(skaters)
    if not priors:
        return {"note": "prior fit failed"}
    disp = priors.get("sog_dispersion")
    per_game = {}
    for p in skaters.values():
        grp = dvp_group(p.get("pos"))
        for d, opp, s, g, a, _t in p["games"]:
            if opp is None:
                continue
            c = per_game.setdefault((d, opp), {}).setdefault(grp, {"sog": 0.0, "pts": 0.0})
            c["sog"] += s or 0
            c["pts"] += (g or 0) + (a or 0)
    dates = sorted({k[0] for k in per_game})
    # Cumulative shares by date, built incrementally (one pass).
    cum = {}
    fac_by_date = {}
    ordered = sorted(per_game.items(), key=lambda kv: kv[0][0])
    j = 0
    for d in dates:
        if d >= cut:
            fac = {}
            for st in ("sog", "pts"):
                for grp in DVP_GROUPS:
                    obs = [(int(round(v[grp][st][0])), int(round(v[grp][st][1])))
                           for v in cum.values() if v.get(grp) and v[grp][st][1]]
                    mean, strength = mm.fit_beta_prior(obs)
                    if not mean:
                        continue
                    for t, v in cum.items():
                        x, n = (v.get(grp) or {}).get(st, (0, 0))
                        fac[(t, grp, st)] = ((x + mean * strength) / (n + strength)) / mean
            fac_by_date[d] = fac
        while j < len(ordered) and ordered[j][0][0] == d:
            (_dd, opp), byg = ordered[j]
            tot = {st: sum(v[st] for v in byg.values()) for st in ("sog", "pts")}
            for grp, v in byg.items():
                slot = cum.setdefault(opp, {}).setdefault(
                    grp, {"sog": [0.0, 0.0], "pts": [0.0, 0.0]})
                for st in ("sog", "pts"):
                    slot[st][0] += v[st]
                    slot[st][1] += tot[st]
            j += 1
    rows = _wf_rows(skaters, goal_finals, shot_finals, cut, "9999", goal_k, shot_k, priors)
    out = {"from": cut, "to": all_dates[-1], "level": "position share of team allowed"}
    for fam, st in (("sog", "sog"), ("pts", "pts")):
        base, alt = [], []
        for r, sr, gr, _rat, actual, (d, opp, grp) in rows:
            f = fac_by_date.get(d, {}).get((opp, grp, st), 1.0)
            b = probs(r, sr, gr, disp)
            x = probs(r, sr * (f if fam == "sog" else 1.0), gr * (f if fam == "pts" else 1.0), disp)
            for k, _l, stat, n in MARKETS:
                if stat not in TOI_FAMILIES[fam] or actual[stat] is None:
                    continue
                y = 1 if actual[stat] >= n else 0
                base.append((b[k], y))
                alt.append((x[k], y))
        verdict = mm.paired_verdict([mm.log_loss(p, y) for p, y in alt],
                                    [mm.log_loss(p, y) for p, y in base])
        out[fam] = {"verdict": verdict, "n": len(base),
                    "brier_with": mm.score_predictions(alt)["brier"],
                    "brier_without": mm.score_predictions(base)["brier"],
                    "in_number": verdict.get("verdict") == "beats"}
    return out


def why_line(name, pos, r, env, toi, opp_abbr, dvp_card_sog, exp_sog, exp_pts):
    """The skater's numbers restated as one sentence, in the order the
    model used them. Ice time and the position split are each marked as
    IN the number or CONTEXT, from their own tests."""
    bits = []
    if r:
        bits.append(f"{r['sog']:.2f} shots and {r['g'] + r['a']:.2f} points a game over "
                    f"{r['gp']} games (this season + last, pulled toward the "
                    f"{'defence' if group(pos) == 'D' else 'forward'} average)")
    if toi and toi.get("recent") is not None:
        sc = toi.get("sog") or 1.0
        state = (f"→ shots x{sc:.2f}" if abs(sc - 1.0) > 1e-9
                 else "→ context only (did not beat the model untested)")
        bits.append(f"ice time {toi['recent']:.1f} min over his last {toi['window']} vs "
                    f"{toi['base']:.1f} on his rate {state}")
    if env:
        bits.append(f"{opp_abbr} matchup sets tonight's shot volume x{env.get('shot_ratio', 1):.2f}"
                    f" and scoring x{env.get('goal_ratio', 1):.2f}")
    if dvp_card_sog and dvp_card_sog.get("rank"):
        bits.append(f"{opp_abbr} allows the {dm.rank_text(dvp_card_sog)} shots to "
                    f"{DVP_GROUP_LABELS[dvp_card_sog['group']]} "
                    f"({dvp_card_sog['per_game']:.1f} a game vs {dvp_card_sog['league']:.1f})")
    bits.append(f"→ {exp_sog:.2f} expected shots, {exp_pts:.2f} expected points")
    return " · ".join(bits)


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
                   goal_k=None, shot_k=None, toi=None):
    """Walk-forward over the last `days` of a season's skater lines —
    with the ADOPTED ice-time factor (`toi`, from fit_toi), so the
    verdicts and calibration test the model the page uses."""
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
            sc = toi_scales(games[:i], toi)
            pr = probs(r, sr, gr, priors.get("sog_dispersion"),
                       toi_sog=sc["sog"], toi_pts=sc["pts"])
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
def pool_skaters(prior_skaters, current_skaters, current_id_of, regular_ids=None):
    """Prior-season lines + this season's, per ESPN athlete id, in date
    order.

    current_skaters is nhl_precompute's live dict ({pid: {"games":
    {eid: line}}}); current_id_of maps a team display name to its id so
    the opponent on this season's lines is keyed like last season's.
    regular_ids: when given, only those events count. The live dict ALSO
    holds the exhibition games parsed as a parser check — preseason
    lineups and minutes — and until 10-06 they leaked into every rate.
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
        for eid, line in (rec.get("games") or {}).items():
            if regular_ids is not None and str(eid) not in regular_ids:
                continue
            dst["games"].append((line.get("date"), current_id_of.get(line.get("opp")),
                                 line.get("sog"), line.get("g"), line.get("a"), line.get("toi")))
    for p in pool.values():
        p["games"].sort(key=lambda x: x[0] or "")
    return pool


def current_lines(finals):
    """{line_key: {...}} from this season's finals rows that carry the
    line recorded for them (nhl_precompute: scoreboard, else pickcenter)."""
    from engines import market_blend as mb
    out = {}
    for f in finals or []:
        if f.get("odds") and f.get("home") and f.get("away") and f.get("date"):
            out[mb.line_key(f["date"], str(f["home"]), str(f["away"]))] = {
                "odds": f["odds"], "home_abbr": f.get("home_abbr") or "",
                "away_abbr": f.get("away_abbr") or ""}
    return out


def fit_blend(goal, current_finals, prior_finals, lines):
    """The model's weight against the market, from last season's own
    walk-forward and this season's carried-over one, joined to recorded
    lines (market_lines/nhl_2025-26.json + this season's finals)."""
    from engines import market_blend as mb
    p = goal["params"]
    disp = p.get("dispersion")
    preds = []
    pf = gm.clean_finals(goal_rows(prior_finals or []))
    if pf:
        preds += gm.walk_forward(pf, p["shrink_k"], disp)
    cur = gm.clean_finals(goal_rows(current_finals or []))
    if cur:
        pt = gm.team_totals(pf) if pf else None
        pl = gm.league_constants(pf)["league_rate"] if pf else None
        preds += gm.walk_forward(cur, p["shrink_k"], disp, prior_totals=pt,
                                 prior_league=pl, carryover=p.get("carryover"))
    p_over, p_cover = gm.blend_fns(disp)
    return mb.fit_all(preds, lines, p_over, p_cover)


def build(current_finals, prior, current_skaters=None, current_id_of=None, slate=None,
          regular_ids=None, prior_lines=None):
    """Fit everything, attach projections to `slate` in place, return the
    model block for games.json."""
    prior = prior or {}
    pf = prior.get("finals") or []
    goal = gm.build(goal_rows(current_finals), goal_rows(pf) if pf else None)
    if goal is None:
        return None
    shots = gm.fit_volume(shot_rows(current_finals), shot_rows(pf) if pf else None)

    rids = {str(x) for x in regular_ids} if regular_ids is not None else None
    pool = pool_skaters(prior.get("skaters"), current_skaters, current_id_of or {}, rids)
    priors = fit_priors(pool) if pool else None
    _gk = goal["params"]["shrink_k"]
    _sk = (shots or {}).get("params", {}).get("shrink_k")
    _psk = {k: v for k, v in ((prior.get("skaters") or {}).items())}
    # ICE TIME: fitted on the window before the props test, tested on it;
    # only an adopted family moves the number. Own try — costs the factor,
    # never the model.
    try:
        toi = fit_toi(_psk, goal_rows(pf), shot_rows(pf), goal_k=_gk, shot_k=_sk) if pf else {
            "note": "no prior season file"}
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NHL ice-time fit failed: {type(exc).__name__}: {exc}")
        toi = {"note": f"fit failed: {type(exc).__name__}"}
    # The props test runs on the season the parameters can be judged on:
    # last season, end to end (the current one is days old).
    pval = validate_props(_psk, goal_rows(pf), shot_rows(pf), goal_k=_gk, shot_k=_sk,
                          toi=toi) if pf else {"note": "no prior season file"}
    # DEFENSE VS POSITION: the table (this season + last) and its test.
    try:
        dvp = dm.build_table(
            dvp_lines(prior.get("skaters"), dm.PRIOR)
            + dvp_lines(current_skaters, dm.CUR, current_id_of or {}, rids),
            DVP_STATS, DVP_GROUPS)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NHL defense-vs-position table failed: {type(exc).__name__}: {exc}")
        dvp = None
    try:
        dvp_val = validate_dvp(_psk, goal_rows(pf), shot_rows(pf), goal_k=_gk,
                               shot_k=_sk) if pf else {"note": "no prior season file"}
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NHL defense-vs-position test failed: {type(exc).__name__}: {exc}")
        dvp_val = {"note": f"test failed: {type(exc).__name__}"}

    if prior_lines is None:
        from engines import market_blend as mb
        prior_lines = mb.load_lines("nhl_2025-26")
    lines = dict(prior_lines or {})
    lines.update(current_lines(current_finals))
    try:
        goal["blend"] = fit_blend(goal, current_finals, pf, lines)
    except Exception as exc:  # noqa: BLE001 — costs the blend, never the model
        print(f"::warning::NHL market blend failed: {type(exc).__name__}: {exc}")
        goal["blend"] = {}

    save_prior = fit_save_prior(prior.get("goalies")) if prior.get("goalies") else (None, None)
    shot_k = (shots or {}).get("params", {}).get("shrink_k")
    shot_disp = shot_dispersion(shot_rows(pf) if pf else shot_rows(current_finals),
                                shot_k) if shots and shot_k else None
    try:
        sval = validate_saves(pf, shot_k) if pf and shot_k else {"note": "no prior season file"}
    except Exception as exc:  # noqa: BLE001 — costs the saves test, never the model
        print(f"::warning::NHL saves validation failed: {type(exc).__name__}: {exc}")
        sval = {"note": f"validation failed: {type(exc).__name__}"}

    for g in slate or []:
        hid, aid = g.get("home_id"), g.get("away_id")
        o = g.get("odds") or {}
        proj = gm.project(goal, hid, aid, market=o,
                          home_abbr=g.get("home_abbr") or "", away_abbr=g.get("away_abbr") or "")
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
                sc = toi_scales(p["games"], toi)
                pr = probs(r, sr, gr, priors.get("sog_dispersion"),
                           toi_sog=sc["sog"], toi_pts=sc["pts"])
                if not pr:
                    continue
                pos = sk.get("pos") or p.get("pos")
                opp_id = aid if side == "home" else hid
                opp_abbr = g.get("away_abbr" if side == "home" else "home_abbr") or ""
                grp = dvp_group(pos)
                cards = {st: dm.card(dvp, opp_id, grp, st) for st in DVP_STATS} if dvp else {}
                env = {"goal_ratio": round(gr, 3), "shot_ratio": round(sr, 3)}
                rows.append({"pid": sk.get("pid"), "name": sk.get("name") or p.get("name"),
                             "pos": pos, "gp": r["gp"],
                             "toi": sk.get("toi"), "exp_sog": pr["_exp_sog"],
                             "exp_pts": pr["_exp_pts"], "mu": pr["_mu"],
                             "rate": {"sog": round(r["sog"], 3), "g": round(r["g"], 3),
                                      "a": round(r["a"], 3)},
                             "ice": {k: (round(v, 3) if isinstance(v, float) else v)
                                     for k, v in sc.items()},
                             "dvp": {st: c for st, c in cards.items() if c},
                             "why": why_line(sk.get("name") or p.get("name"), pos, r, env, sc,
                                             opp_abbr, cards.get("sog"),
                                             pr["_exp_sog"], pr["_exp_pts"]),
                             "probs": {k: pr[k] for k, *_ in MARKETS}})
            g[f"{side}_props"] = rows
            g[f"{side}_env"] = {"goal_ratio": round(gr, 3), "shot_ratio": round(sr, 3)}
            # GOALIES of this side face the OTHER side's shots.
            mu_against = s_a if side == "home" else s_h
            if mu_against and save_prior[0] is not None:
                grows = []
                for gk in (g.get(f"{side}_goalies") or [])[:2]:
                    gid = str(gk.get("pid"))
                    res = goalie_sv((prior.get("goalies") or {}).get(gid), gk,
                                    save_prior[0], save_prior[1])
                    if not res:
                        continue
                    sv, sa_seen = res
                    grows.append({"pid": gid, "name": gk.get("name"),
                                  "starts": gk.get("starts"), "crease": gk.get("crease_share"),
                                  "shots_seen": sa_seen, "sv_pct": round(sv, 4),
                                  "exp_sa": round(mu_against, 2),
                                  "exp_saves": round(mu_against * sv, 2)})
                g[f"{side}_goalie_props"] = grows

    return {
        "blend": goal["blend"],
        "params": goal["params"], "league": goal["league"], "validation": goal["validation"],
        "shots": {"params": (shots or {}).get("params"),
                  "league": (shots or {}).get("league"), "dispersion": shot_disp},
        "save_prior": {"mean": save_prior[0], "strength_shots": save_prior[1]},
        "saves_validation": sval,
        "skater_priors": priors,
        "props_validation": pval,
        "toi": toi,
        "dvp": dvp,
        "dvp_validation": dvp_val,
        "prior_season": prior.get("season"),
        "current_finals": len(current_finals),
    }
