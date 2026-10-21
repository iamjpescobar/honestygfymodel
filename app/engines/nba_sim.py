"""
NBA game simulator (10-20) — play a game out thousands of times, every
player's line TOGETHER, so a same-game parlay is priced on how its legs
move together instead of as if they were strangers.

ONE SIMULATED GAME
------------------
  1. The score: margin and total drawn from the game model (normal, its
     measured SDs, engines/nfl_game_model) -> each team's points.
  2. The game's shape, from that score:
       team scoring vs its projection  x = team_pts / projected - 1
       pace (both teams)               p = total / projected total - 1
       blowout                         |margin| bucket
  3. Each player:
       minutes  = projected x the MEASURED minutes share for his role
                  (starter: 28+ projected minutes; bench) in that
                  blowout bucket — stars sit in a 25-point game;
       mean     = projection x minutes share x (1 + e_stat * shape),
                  points riding team scoring, rebounds / assists / 3s
                  riding pace, each elasticity e MEASURED;
       the draw = negative binomial around that mean, its size set so
                  his OWN spread is exactly the model's (the game shocks
                  above already carry part of it) — every leg on its own
                  still prices like the Props board.
  Combos are the sums of his own simulated stats.

WHAT IT CHANGES: the JOINT chance. A parlay's legs are priced as the
model's delivered chances multiplied, times the simulator's LIFT —
P(all, simulated) / product of P(each, simulated) — so the calibration of
each leg is kept and only the link between them comes from the sim.

EVERY LINK IS MEASURED, AND THE SIMULATOR IS TESTED (rule 1)
------------------------------------------------------------
fit_links: elasticities and minutes shares from last season's games the
model had not seen (walk-forward rows joined to final scores), on the
fit window. test: the last 45 days — for teammate pairs and same-game
opponent pairs, "both over their lines" priced with the lift vs plain
multiplication, against what happened (paired, squared error). Until it
BEATS, same-game legs stay capped at THIN on the parlay slip.

numpy, no streamlit, no requests.
"""
import numpy as np

from engines import nba_model as nm

BLOWOUT = (10.0, 20.0)            # |margin| bucket edges: close / comfortable / blowout
STARTER_MIN = 28.0
ELASTIC = {"pts": "team", "reb": "pace", "ast": "pace", "tpm": "pace"}
DEFAULT_LINKS = {"e": {"pts": 1.0, "reb": 0.5, "ast": 0.5, "tpm": 0.5},
                 "min_share": {"starter": [1.0, 0.97, 0.85], "bench": [1.0, 1.0, 1.1]}}


def bucket(margin_abs):
    return 0 if margin_abs < BLOWOUT[0] else (1 if margin_abs < BLOWOUT[1] else 2)


# ----------------------------------------------------------------------
# Measuring the links on last season
# ----------------------------------------------------------------------
def game_outcomes(finals):
    """{(date, team_id): (team_pts, opp_pts)} from prior finals."""
    out = {}
    for f in finals or []:
        if f.get("hs") is None or f.get("as") is None:
            continue
        out[(f["date"], str(f["home"]))] = (float(f["hs"]), float(f["as"]))
        out[(f["date"], str(f["away"]))] = (float(f["as"]), float(f["hs"]))
    return out


def game_preds(preds):
    """{(date, team_id): (team_proj, opp_proj)} from game-model walk-forward."""
    out = {}
    for p in preds or []:
        out[(p["date"], str(p["home"]))] = (p["mu_h"], p["mu_a"])
        out[(p["date"], str(p["away"]))] = (p["mu_a"], p["mu_h"])
    return out


def fit_links(rows, outcomes, gpreds):
    """Elasticities and minutes shares from walk rows (nba_model.walk)."""
    acc = {s: [0.0, 0.0] for s in ELASTIC}
    mins = {"starter": [[], [], []], "bench": [[], [], []]}
    for _pid, g, pr, _h in rows:
        key = (g[0], str(g[1]))
        if key not in outcomes or key not in gpreds:
            continue
        tp, op = outcomes[key]
        tproj, oproj = gpreds[key]
        if not tproj or not oproj:
            continue
        shape = {"team": tp / tproj - 1.0, "pace": (tp + op) / (tproj + oproj) - 1.0}
        m_act = nm.val(g, "min")
        role = "starter" if pr["min"] >= STARTER_MIN else "bench"
        if m_act and pr["min"]:
            mins[role][bucket(abs(tp - op))].append(m_act / pr["min"])
            share = m_act / pr["min"]
        else:
            continue
        for st, kind in ELASTIC.items():
            y = nm.val(g, st)
            mu = pr["mu"][st] * share
            if y is None or mu <= 0.5:
                continue
            x = shape[kind]
            acc[st][0] += x * (y / mu - 1.0)
            acc[st][1] += x * x
    e = {st: (round(a / b, 3) if b > 0 else DEFAULT_LINKS["e"][st]) for st, (a, b) in acc.items()}
    share = {role: [round(float(np.mean(v)), 3) if len(v) >= 30 else
                    DEFAULT_LINKS["min_share"][role][i] for i, v in enumerate(bs)]
             for role, bs in mins.items()}
    n = {role: [len(v) for v in bs] for role, bs in mins.items()}
    return {"e": e, "min_share": share, "n": n}


# ----------------------------------------------------------------------
# Simulating one game
# ----------------------------------------------------------------------
def simulate(mu_home, mu_away, sd_margin, sd_total, players, sizes, links=None, n=10000,
             seed=7):
    """players: [{"pid", "side": "home"|"away", "min", "mu": {stat: mean}}].
    -> {"home": arr, "away": arr, "stats": {pid: {stat: int arr}}}"""
    links = links or DEFAULT_LINKS
    rng = np.random.default_rng(seed)
    margin = rng.normal(mu_home - mu_away, sd_margin, n)
    total = rng.normal(mu_home + mu_away, sd_total, n)
    home = (total + margin) / 2.0
    away = (total - margin) / 2.0
    b = np.where(np.abs(margin) < BLOWOUT[0], 0, np.where(np.abs(margin) < BLOWOUT[1], 1, 2))
    pace = total / (mu_home + mu_away) - 1.0
    out = {"home": home, "away": away, "stats": {}}
    for p in players or []:
        side = p.get("side")
        team = (home / mu_home - 1.0) if side == "home" else (away / mu_away - 1.0)
        role = "starter" if (p.get("min") or 0) >= STARTER_MIN else "bench"
        share = np.asarray(links["min_share"][role], dtype=float)[b]
        # only the SHAPE across game scripts: the projection already is his
        # average over them, so the share averages to 1 over these games
        # (otherwise a bench bias in last season's minutes moves his mean
        # and the sim stops pricing each leg like the props model)
        share = share / share.mean()
        st_out = {}
        for st in nm.BASE:
            mu = (p.get("mu") or {}).get(st) or 0.0
            if mu <= 0:
                st_out[st] = np.zeros(n, dtype=int)
                continue
            shock = team if ELASTIC[st] == "team" else pace
            mean = np.clip(mu * share * (1.0 + links["e"].get(st, 0.0) * shock), 1e-6, None)
            # the model's own spread for him: Var = mu + mu^2 / r; the game
            # shocks already give Var(mean) of it, the draw supplies the rest
            r = (sizes or {}).get(st)
            v_target = mu + (mu * mu / r if r else 0.0)
            v_rest = v_target - float(np.var(mean)) - mu
            if v_rest <= 1e-9:
                st_out[st] = rng.poisson(mean)
            else:
                r2 = mu * mu / v_rest
                st_out[st] = rng.poisson(rng.gamma(r2, mean / r2))
        for c, parts in nm.COMBOS.items():
            st_out[c] = sum(st_out[x] for x in parts)
        # int16: a 10,000-game slate of 26 players x 8 stats is 4 MB, not
        # 17 MB — the page caches several games on a 512 MB server
        out["stats"][str(p["pid"])] = {k: np.asarray(v, dtype=np.int16) for k, v in st_out.items()}
    return out


SGP_MAX_LEGS = 8          # 500,000 games keep an 8-leg link to +/- 0.02 (measured 10-20)
STRONG_MIN_COMBOS = 100   # graded parlays of this kind before one may read STRONG


def sgp_support(test, legs=2, combos=None):
    """How a same-game parlay priced with the simulator is guarded. The
    parlay's group (combo_kind: legs x all-points / mixed) is looked up in
    the combos test on last season:
      group BEAT plain multiplication, every leg an over, 100+ graded
        -> measured and IN range: STRONG allowed (it is the kind graded);
      group beat but the parlay has an under, or the group is small
        -> measured, out of range: at most VALUE;
      group not beaten, or never graded (5+ legs)  -> untested: THIN.
    Without a combos test (an older nightly): the pairs test alone, as
    before — beats -> VALUE at most for 2 legs, 3+ legs THIN."""
    t = test or {}
    n_legs = legs if isinstance(legs, int) else len(legs)
    if combos and not isinstance(legs, int):
        kind = combo_kind(legs)
        if any(lg.get("side", "Over") != "Over" for lg in legs):
            kind = f"{n_legs}|{'pts' if all(lg.get('stat') == 'pts' for lg in legs) else 'mixed'}"
        g = combos.get(kind)
        if not g or (g.get("verdict") or {}).get("verdict") != "beats":
            return {"measured": False, "in_range": False, "n": 0, "untested": True,
                    "kind": kind, "why": "untested" if not g else "not_beaten"}
        overs = all(lg.get("side", "Over") == "Over" for lg in legs)
        return {"measured": True, "in_range": overs and g["n"] >= STRONG_MIN_COMBOS,
                "n": g["n"], "untested": False, "kind": kind,
                "why": None if overs else "unders"}
    if n_legs > 2:
        return {"measured": False, "in_range": False, "n": 0, "untested": True, "legs": n_legs,
                "why": "untested"}
    if ((t.get("verdict") or {}).get("verdict")) == "beats":
        return {"measured": True, "in_range": False, "n": t.get("n") or 0, "untested": False,
                "why": "pairs_only"}
    return {"measured": False, "in_range": False, "n": 0, "untested": True, "why": "not_beaten"}


SGP_GUARD = {
    "not_beaten": ("Capped at THIN: on last season's games, parlays like this one priced with "
                   "the simulator did not beat simply multiplying the legs."),
    "untested": ("Capped at THIN: no parlay of this size has been graded on last season's "
                 "games, so the link between its legs is the model's assumption."),
    "unders": ("Capped at VALUE: parlays like this were graded with every leg an over; an "
               "under in it is outside what was tested."),
    "pairs_only": ("Capped at VALUE: the simulator passed its test on two-player points pairs; "
                   "STRONG on a same-game parlay would need that kind of parlay graded."),
    "small": ("Capped at VALUE: too few parlays like this were graded for STRONG."),
}


def sgp_guard(sup, tier):
    """The page's sentence for a capped SGP call, or None."""
    why = (sup or {}).get("why")
    if tier == "thin" and why in ("not_beaten", "untested"):
        return SGP_GUARD[why]
    if tier == "value":
        return SGP_GUARD.get(why) or (SGP_GUARD["small"] if not (sup or {}).get("in_range")
                                      else None)
    return None


def leg_hits(sim, leg):
    """Boolean array: the leg {"pid","stat","line","side"} hit in each sim."""
    if leg.get("pid") == "_game":
        h, a = sim["home"], sim["away"]
        if leg["stat"] == "total":
            v = h + a
        elif leg["stat"] == "home_margin":
            v = h - a
        else:
            v = a - h
        hit = v > leg["line"]
    else:
        v = sim["stats"][str(leg["pid"])][leg["stat"]]
        hit = v > leg["line"]
    return hit if leg.get("side", "Over") == "Over" else ~hit


def joint(sim, legs):
    """{"each": [P], "all": P, "product": prod, "lift": all / product}."""
    hits = [leg_hits(sim, lg) for lg in legs]
    each = [float(h.mean()) for h in hits]
    allp = float(np.logical_and.reduce(hits).mean()) if hits else None
    prod = float(np.prod(each)) if each else None
    lift = (allp / prod) if prod else None
    return {"each": each, "all": allp, "product": prod, "lift": lift}


SGP_SIMS = 500_000       # the parlay's legs: 10k left a 4-leg lift +/- 2.2% (run to run),
SGP_CHUNK = 100_000      # as big as the lift itself; 500k is +/- 0.4%, in 100k chunks


def joint_precise(mu_home, mu_away, sd_margin, sd_total, players, sizes, links, legs,
                  n=SGP_SIMS, chunk=SGP_CHUNK, seed=7):
    """joint() for a parlay, at n games, simulating ONLY the leg players
    (each player's draw needs only the shared score and his own numbers),
    in chunks so memory stays flat. Adds lift_se: the Monte Carlo
    standard error of the lift (from the all-hit count)."""
    need = {str(lg["pid"]) for lg in legs if lg.get("pid") != "_game"}
    pl = [p for p in players or [] if str(p["pid"]) in need]
    each_hits = [0] * len(legs)
    all_hits = done = k = 0
    while done < n:
        m = min(chunk, n - done)
        sim = simulate(mu_home, mu_away, sd_margin, sd_total, pl, sizes, links, n=m,
                       seed=seed + 1000 * k)
        hs = [leg_hits(sim, lg) for lg in legs]
        for i, h in enumerate(hs):
            each_hits[i] += int(h.sum())
        all_hits += int(np.logical_and.reduce(hs).sum()) if hs else 0
        done += m
        k += 1
    each = [h / n for h in each_hits]
    allp = all_hits / n if legs else None
    prod = float(np.prod(each)) if each else None
    lift = (allp / prod) if (prod and allp) else None
    se = (float(np.sqrt(allp * (1 - allp) / n)) / prod) if lift else None
    return {"each": each, "all": allp, "product": prod, "lift": lift, "lift_se": se, "n": n}


# ----------------------------------------------------------------------
# The test on last season
# ----------------------------------------------------------------------
def test(rows, outcomes, gpreds, sds, sizes, links, n=4000, seed=11, bins=None):
    """Pairs in the same game — teammates' points, and one player from
    each side — "both over their lines": the simulator's lift on the
    model's own chances vs plain multiplication, against what happened."""
    from engines import model_math as mm
    from engines import top_plays_board as tpb

    def delivered(p):
        # each leg as the pages price it (the points curve), so the test
        # isolates the one thing the simulator adds: the link
        c = tpb.calibrate(p, bins) if (bins and p is not None) else None
        return c if c is not None else p
    by_game = {}
    for pid, g, pr, hist in rows:
        hv = [nm.val(h, "pts") for h in hist if nm.val(h, "min")]
        hv = [v for v in hv if v is not None]
        if len(hv) < nm.MIN_PRIOR_GAMES or nm.val(g, "pts") is None:
            continue
        by_game.setdefault((g[0], tuple(sorted((str(g[1]), str(g[2]))))), []).append(
            (str(pid), str(g[1]), pr, nm.half_line(hv[-10:]), nm.val(g, "pts")))
    sim_p, ind_p = [], []
    teammates, opponents = [], []
    k = 0
    for (d, teams), plist in sorted(by_game.items()):
        home_t = next((t for t in teams if (d, t) in gpreds), None)
        if home_t is None or len(plist) < 4:
            continue
        tproj, oproj = gpreds[(d, home_t)]
        players = [{"pid": p, "side": "home" if t == home_t else "away", "min": pr["min"],
                    "mu": pr["mu"]} for p, t, pr, _l, _y in plist]
        sim = simulate(tproj, oproj, sds[0], sds[1], players, sizes, links, n=n, seed=seed + k)
        k += 1
        top = sorted(plist, key=lambda x: -x[2]["mu"]["pts"])
        home_top = [x for x in top if x[1] == home_t][:2]
        away_top = [x for x in top if x[1] != home_t][:2]
        pairs = []
        if len(home_top) == 2:
            pairs.append(("team", home_top))
        if len(away_top) == 2:
            pairs.append(("team", away_top))
        if home_top and away_top:
            pairs.append(("opp", [home_top[0], away_top[0]]))
        for kind, pr2 in pairs:
            legs = [{"pid": x[0], "stat": "pts", "line": x[3], "side": "Over"} for x in pr2]
            j = joint(sim, legs)
            marg = [delivered(nm.over(x[2]["mu"]["pts"], sizes.get("pts"), x[3])) for x in pr2]
            if None in marg or j["lift"] is None:
                continue
            y = 1 if all(x[4] > x[3] for x in pr2) else 0
            ind = marg[0] * marg[1]
            sp = min(1.0, ind * j["lift"])
            sim_p.append((sp, y))
            ind_p.append((ind, y))
            (teammates if kind == "team" else opponents).append((j["lift"], ind, sp, y))
    m, b = mm.score_predictions(sim_p), mm.score_predictions(ind_p)

    def summ(xs):
        if not xs:
            return {"n": 0}
        return {"n": len(xs), "avg_lift": round(sum(x[0] for x in xs) / len(xs), 3),
                "predicted_ind": round(sum(x[1] for x in xs) / len(xs), 4),
                "predicted_sim": round(sum(x[2] for x in xs) / len(xs), 4),
                "actual": round(sum(x[3] for x in xs) / len(xs), 4)}
    return {"n": m["n"], "sim_brier": m["brier"], "independent_brier": b["brier"],
            "verdict": mm.paired_verdict([(q - y) ** 2 for q, y in sim_p],
                                         [(q - y) ** 2 for q, y in ind_p]),
            "teammates": summ(teammates), "opponents": summ(opponents)}


COMBO_SIMS = 20_000       # per test game: a 4-leg joint near 5% keeps its noise near 3%


def combo_kind(legs):
    """The test group a parlay belongs to: "<legs>|pts" when every leg is
    a points over, else "<legs>|mixed" (rebounds / assists / 3s, or any
    under — unders were never graded, see sgp_support)."""
    pts = all(lg.get("stat") == "pts" and lg.get("side", "Over") == "Over" for lg in legs)
    return f"{len(legs)}|{'pts' if pts else 'mixed'}"


def _combos(top, tm, opp):
    """The parlays a bettor actually builds, from one game's players:
    (kind, [(player, stat), ...]). top: {team: [players by projected
    points]}; reb / ast leaders found per team."""
    out = []

    def lead(team, stat, skip):
        c = [x for x in sorted(top[team], key=lambda x: -x[2]["mu"][stat]) if x[0] not in skip]
        return c[0] if c else None
    for t, o in ((tm, opp), (opp, tm)):
        T = top[t]
        if len(T) >= 2:
            out.append(("2|pts", [(T[0], "pts"), (T[1], "pts")]))
        if len(T) >= 3:
            out.append(("3|pts", [(T[0], "pts"), (T[1], "pts"), (T[2], "pts")]))
        if T:
            rb = lead(t, "reb", {T[0][0]})
            asst = lead(t, "ast", {T[0][0]} | ({rb[0]} if rb else set()))
            if rb:
                out.append(("2|mixed", [(T[0], "pts"), (rb, "reb")]))
            if rb and asst:
                out.append(("3|mixed", [(T[0], "pts"), (rb, "reb"), (asst, "ast")]))
    A, B = top[tm], top[opp]
    if A and B:
        out.append(("2|pts", [(A[0], "pts"), (B[0], "pts")]))
    if len(A) >= 2 and len(B) >= 2:
        out.append(("4|pts", [(A[0], "pts"), (A[1], "pts"), (B[0], "pts"), (B[1], "pts")]))
        ra, rb_ = lead(tm, "reb", {A[0][0]}), lead(opp, "reb", {B[0][0]})
        if ra and rb_:
            out.append(("4|mixed", [(A[0], "pts"), (ra, "reb"), (B[0], "pts"), (rb_, "reb")]))
    return out


def test_combos(rows, outcomes, gpreds, sds, sizes, links, bins_by_stat, n=COMBO_SIMS, seed=23):
    """The simulator on the same-game parlays people build — 2, 3 and 4
    legs, all-points and mixed stats, every leg an over at the player's
    own last-10 line — priced as the delivered chances multiplied, and
    times the simulator's lift, against what happened. Per group:
    {n, sim_brier, independent_brier, verdict, avg_lift, predicted_ind,
    predicted_sim, actual}."""
    from engines import model_math as mm
    from engines import top_plays_board as tpb

    def delivered(p, st):
        b = (bins_by_stat or {}).get(st)
        c = tpb.calibrate(p, b) if (b and p is not None) else None
        return c if c is not None else p
    by_game = {}
    for pid, g, pr, hist in rows:
        lines = {}
        for st in ("pts", "reb", "ast"):
            hv = [nm.val(h, st) for h in hist if nm.val(h, "min")]
            hv = [v for v in hv if v is not None]
            if len(hv) < nm.MIN_PRIOR_GAMES or nm.val(g, st) is None:
                break
            lines[st] = (nm.half_line(hv[-10:]), nm.val(g, st))
        else:
            by_game.setdefault((g[0], tuple(sorted((str(g[1]), str(g[2]))))), []).append(
                (str(pid), str(g[1]), pr, lines))
    acc = {}
    k = 0
    for (d, teams), plist in sorted(by_game.items()):
        tm = next((t for t in teams if (d, t) in gpreds), None)
        if tm is None:
            continue
        opp = next((t for t in teams if t != tm), None)
        top = {t: sorted([x for x in plist if x[1] == t], key=lambda x: -x[2]["mu"]["pts"])[:6]
               for t in (tm, opp)}
        combos = _combos(top, tm, opp)
        if not combos:
            continue
        tproj, oproj = gpreds[(d, tm)]
        need = {x[0][0]: x[0] for _k, legs in combos for x in legs}
        players = [{"pid": p, "side": "home" if x[1] == tm else "away", "min": x[2]["min"],
                    "mu": x[2]["mu"]} for p, x in need.items()]
        sim = simulate(tproj, oproj, sds[0], sds[1], players, sizes, links, n=n, seed=seed + k)
        k += 1
        for kind, legs in combos:
            L = [{"pid": x[0], "stat": st, "line": x[3][st][0], "side": "Over"} for x, st in legs]
            j = joint(sim, L)
            marg = [delivered(nm.over(x[2]["mu"][st], sizes.get(st), x[3][st][0]), st)
                    for x, st in legs]
            if None in marg or j["lift"] is None:
                continue
            y = 1 if all(x[3][st][1] > x[3][st][0] for x, st in legs) else 0
            ind = 1.0
            for q in marg:
                ind *= q
            sp = min(1.0, ind * j["lift"])
            acc.setdefault(kind, []).append((j["lift"], ind, sp, y))
    out = {}
    for kind, xs in sorted(acc.items()):
        m = mm.score_predictions([(x[2], x[3]) for x in xs])
        b = mm.score_predictions([(x[1], x[3]) for x in xs])
        out[kind] = {"n": len(xs), "sim_brier": m["brier"], "independent_brier": b["brier"],
                     "verdict": mm.paired_verdict([(x[2] - x[3]) ** 2 for x in xs],
                                                  [(x[1] - x[3]) ** 2 for x in xs]),
                     "avg_lift": round(sum(x[0] for x in xs) / len(xs), 3),
                     "predicted_ind": round(sum(x[1] for x in xs) / len(xs), 4),
                     "predicted_sim": round(sum(x[2] for x in xs) / len(xs), 4),
                     "actual": round(sum(x[3] for x in xs) / len(xs), 4)}
    return out


def season_finals(cur_finals):
    """This season's finals (the nightly's home_id / home_score shape) in
    last season's shape (home / hs) — so one list feeds every test."""
    return [{"date": f["date"], "home": str(f.get("home_id")), "away": str(f.get("away_id")),
             "hs": f.get("home_score"), "as": f.get("away_score")}
            for f in cur_finals or [] if f.get("home_score") is not None]


def build(prior, model, pool=None, cur_finals=None):
    """{"links", "test", "combos", "sds"} — links fitted on last season;
    the tests on last season's unseen 45 days PLUS every game of this
    season so far (pool = last season + this one per player, cur_finals
    this season's) — so the graded record grows every night and a group
    of parlays can earn its way out of THIN."""
    from engines import nfl_game_model as ngm
    from engines import game_model as gm
    finals = list(prior.get("finals") or []) + season_finals(cur_finals)
    data = {"players": pool or prior.get("players") or {}, "finals": finals}
    players = data["players"]
    rows_f = [{"date": f["date"], "home_id": f["home"], "away_id": f["away"],
               "home_score": f.get("hs"), "away_score": f.get("as")}
              for f in finals]
    gfin = gm.clean_finals(ngm.rows(rows_f))
    gpar = ngm.fit(gfin)
    if not gpar or not model or not model.get("hl"):
        return None
    preds = ngm._wf(gfin, gpar["shrink_k"])
    outcomes, gp = game_outcomes(finals), game_preds(preds)
    lr = model.get("league") or nm.league_rates(players, before=model["test_window"][0])
    # the rows the pages' numbers come from: with the opponent and
    # teammates-out context when the model carries it (engines/nba_context)
    from engines import nba_context as nc
    every = nc.context_rows(data, dict(model, league=lr))
    fw, tw = model["fit_window"], model["test_window"]
    fit_rows = [r for r in every if fw[0] <= r[1][0] < fw[1]]
    test_rows = [r for r in every if r[1][0] >= tw[0]]
    links = fit_links(fit_rows, outcomes, gp)
    sds = (gpar["sd_margin"], gpar["sd_total"])
    bins = {st: ((model.get("test") or {}).get(st) or {}).get("calibration")
            for st in ("pts", "reb", "ast")}
    this = sum(1 for r in test_rows if r[1][0] > (max(f["date"] for f in prior.get("finals")
                                                         or [{"date": ""}])))
    return {"links": links, "sds": list(sds), "test_rows": len(test_rows),
            "this_season_rows": this,
            "test": test(test_rows, outcomes, gp, sds, model.get("sizes") or {}, links,
                         bins=bins["pts"]),
            "combos": test_combos(test_rows, outcomes, gp, sds, model.get("sizes") or {}, links,
                                  bins)}
