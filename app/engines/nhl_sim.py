"""
NHL game simulator (10-22) — play tonight's game thousands of times with
every skater's shots, goals and assists drawn TOGETHER, so a same-game
parlay is priced on how its legs actually move together.

ONE SIMULATED GAME
------------------
  1. The shot environment: each team's shots against the shots model's
     expectation, Z_home / Z_away — lognormal, mean 1, the variance and
     the home/away correlation MEASURED on last season's team shots
     (one team's extra shots come out of the other's possession).
  2. Each skater's shots on goal: his projection x Z, negative binomial
     with the rest of his spread, so on his own he still prices like the
     props board (the same size the board uses).
  3. His goals: each of his simulated shots goes in at his own goals per
     shot (from his projection), scaled so a team's goals rise Z ^ E_GOALS
     with its shots (the elasticity MEASURED — more shots, but not
     one-for-one more goals). A scorer needs a shot, and two linemates on
     a night the team piles up shots score together more often. Goals no
     listed skater is projected for go to "someone else"; the team's
     total averages the game model's. A regulation tie goes to overtime:
     the home side wins it at the game model's measured rate; the winner
     gets the extra goal.
  4. (First try, 10-22, measured and dropped: a fixed team total shared
     out among the shooters — it made two teammates' goals pull APART,
     lift 0.96, where real ones go together; it failed its test.)
  5. Assists: each goal has 0 / 1 / 2 assists at the MEASURED shares,
     from teammates other than the scorer, weighted by their assist rates.
  6. Goalie saves = the opponent's shots - its regulation goals.

WHAT IT CHANGES: the JOINT chance of a same-game parlay — the legs'
delivered chances multiplied, times the simulator's LIFT (P(all) / the
product of P(each), both from the simulator).

TESTED (rule 1): the parlays people build — two / three linemates with a
point, two teammates over their shots lines, two teammates to score, a
scorer + his team to win, a point + the win, one point-getter from each
side, four point legs — on last season's final 60 days plus this season
so far, priced with the lift vs plain multiplication, against what
happened (paired, squared error). A kind that has not beaten that stays
at THIN on the page.

numpy, no streamlit, no requests.
"""
import numpy as np

DEFAULT_LINKS = {"shot_var": 0.014, "shot_rho": -0.13, "e_goals": 0.37,
                 "assists": [0.064, 0.184, 0.752], "tie_home_win": 0.55}
SGP_MAX_LEGS = 8
SGP_SIMS = 200_000
SGP_CHUNK = 50_000
COMBO_SIMS = 20_000
STRONG_MIN_COMBOS = 100
TEST_DAYS = 60
STATS = (("sog", "Shots on goal"), ("g", "Goals"), ("a", "Assists"), ("pts", "Points"))
LEG_TYPE = {"pts": "P", "sog": "S", "g": "G"}
KIND_LABEL = {"PP": "2 teammates with a point", "PPP": "3 teammates with a point",
              "SS": "2 teammates over their shots lines", "GG": "2 teammates to score",
              "GW": "a goal + his team wins", "PW": "a point + his team wins",
              "PPopp": "a point-getter from each side", "PPPP": "4 point legs (2 a side)"}


# ----------------------------------------------------------------------
# The links, measured on last season
# ----------------------------------------------------------------------
def fit_links(finals, goal_preds, shot_preds, skaters, tie_home_win=None):
    """{"shot_var", "shot_rho", "e_goals", "assists": [p0, p1, p2],
    "tie_home_win", "n"} from last season: finals with team shots,
    walk-forward goal and shot predictions keyed (date, home), skater
    lines [date, opp, sog, g, a, toi]."""
    G = {(p["date"], str(p["home"])): p for p in goal_preds or []}
    Sh = {(p["date"], str(p["home"])): p for p in shot_preds or []}
    xs, ys, hr, ar, pois = [], [], [], [], []
    for f in finals or []:
        k = (f["date"], str(f["home"]))
        if k not in G or k not in Sh or f.get("home_sog") is None or f.get("away_sog") is None:
            continue
        g, s = G[k], Sh[k]
        for gg, mg, ss, ms in ((f["hs"], g["mu_h"], f["home_sog"], s["mu_h"]),
                               (f["as"], g["mu_a"], f["away_sog"], s["mu_a"])):
            if mg and ms:
                xs.append(ss / ms - 1.0)
                ys.append(gg / mg - 1.0)
                pois.append(1.0 / ms)
        if s["mu_h"] and s["mu_a"]:
            hr.append(f["home_sog"] / s["mu_h"] - 1.0)
            ar.append(f["away_sog"] / s["mu_a"] - 1.0)
    if len(xs) < 200:
        return dict(DEFAULT_LINKS, n=len(xs), note="too few games: default links")
    xs, ys = np.array(xs), np.array(ys)
    # Var(S/mu) = Var(Z) + 1/mu (Poisson): the environment's own variance
    shot_var = max(0.0, float(xs.var() - np.mean(pois)))
    rho = float(np.corrcoef(hr, ar)[0, 1]) if len(hr) > 50 else 0.0
    e_goals = float((xs * ys).sum() / (xs * xs).sum())
    # assists per goal: team-games from the skater lines (team = the other
    # side of the final he played on that date)
    team_of = {}
    for f in finals or []:
        team_of[(f["date"], str(f["home"]))] = str(f["away"])
        team_of[(f["date"], str(f["away"]))] = str(f["home"])
    acc = {}
    for p in (skaters or {}).values():
        for d, opp, _s, g, a, *_r in p.get("games") or []:
            t = team_of.get((d, str(opp)))
            if t is None:
                continue
            x = acc.setdefault((d, t), [0, 0])
            x[0] += g or 0
            x[1] += a or 0
    Gs = np.array([v[0] for v in acc.values()], dtype=float)
    As = np.array([v[1] for v in acc.values()], dtype=float)
    assists = DEFAULT_LINKS["assists"]
    if Gs.sum() > 500:
        m = As.sum() / Gs.sum()
        v = float(((As - m * Gs) ** 2).sum() / Gs.sum())      # Var(A | G) = G x v
        p2 = (v + m * m - m) / 2.0
        p1 = m - 2 * p2
        p0 = 1 - p1 - p2
        if min(p0, p1, p2) >= 0:
            assists = [float(round(p0, 4)), float(round(p1, 4)), float(round(p2, 4))]
    return {"shot_var": round(shot_var, 5), "shot_rho": round(rho, 3),
            "e_goals": round(e_goals, 3), "assists": assists,
            "tie_home_win": tie_home_win if tie_home_win is not None
            else DEFAULT_LINKS["tie_home_win"], "n": len(xs)}


# ----------------------------------------------------------------------
# One simulated game
# ----------------------------------------------------------------------
def _nb(rng, mean, extra_var):
    """Counts with mean `mean` and variance mean + extra_var (gamma-Poisson)."""
    mean = np.clip(mean, 1e-9, None)
    if extra_var <= 1e-12:
        return rng.poisson(mean)
    # gamma with shape r: variance mean^2 / r of the rate
    r = np.clip(mean * mean / extra_var, 1e-6, None)
    return rng.poisson(rng.gamma(r, mean / r))


def _draw(rng, W):
    """One weighted column per row of W (T x k)."""
    tot = W.sum(axis=1)
    tot = np.where(tot > 0, tot, 1.0)
    cum = np.cumsum(W, axis=1) / tot[:, None]
    u = rng.random(W.shape[0])[:, None]
    return np.minimum((u > cum).sum(axis=1), W.shape[1] - 1)


def simulate(game, skaters, links=None, sog_size=None, n=10000, seed=7):
    """game: {"mu_home", "mu_away" (goals), "shots_home", "shots_away"}.
    skaters: [{"pid", "side", "mu": {"sog", "g", "a"}}].
    -> {"home", "away" (final goals, OT goal included), "ot": bool arr,
        "home_reg", "away_reg", "shots": {side: arr},
        "stats": {pid: {"sog", "g", "a", "pts": int16 arr}}}"""
    L = dict(DEFAULT_LINKS, **(links or {}))
    rng = np.random.default_rng(seed)
    sv = max(L["shot_var"], 0.0)
    s2 = np.log1p(sv)
    rho = float(np.clip(L.get("shot_rho") or 0.0, -0.9, 0.9))
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + np.sqrt(1 - rho * rho) * rng.standard_normal(n)
    Z = {"home": np.exp(np.sqrt(s2) * z1 - s2 / 2), "away": np.exp(np.sqrt(s2) * z2 - s2 / 2)}
    out = {"stats": {}, "shots": {}}
    goals = {}
    by_side = {s: [p for p in skaters or [] if p.get("side") == s] for s in ("home", "away")}
    for side in ("home", "away"):
        mu_g = float(game[f"mu_{side}"])
        mu_s = float(game.get(f"shots_{side}") or 0.0)
        z = Z[side]
        pl = by_side[side]
        k = len(pl)
        sog = np.zeros((n, k), dtype=np.int32)
        for i, p in enumerate(pl):
            m = float((p.get("mu") or {}).get("sog") or 0.0)
            if m <= 0:
                continue
            v_target = m + (m * m / sog_size if sog_size else 0.0)
            extra = max(0.0, v_target - m - m * m * sv)
            sog[:, i] = _nb(rng, m * z, extra)
        listed_s = sum(float((p.get("mu") or {}).get("sog") or 0.0) for p in pl)
        other_s = rng.poisson(np.clip(max(0.0, mu_s - listed_s) * z, 0, None)) if mu_s else 0
        out["shots"][side] = sog.sum(axis=1) + other_s
        # his goals from HIS shots: each converts at his own goals-per-shot,
        # scaled so the team's goals rise Z ^ E_GOALS with its shots (the
        # measured elasticity), not one-for-one
        sh = np.array([((p.get("mu") or {}).get("g") or 0.0) / max(
            (p.get("mu") or {}).get("sog") or 0.0, 1e-6) for p in pl])
        listed_g = sum(float((p.get("mu") or {}).get("g") or 0.0) for p in pl)
        # the team's goals average the GAME MODEL's: when the listed skaters'
        # own projections add to more (18 dressed, rates per game played),
        # every one is scaled down to fit
        fit_g = min(1.0, mu_g / listed_g) if listed_g > 0 else 1.0
        conv = np.clip(sh[None, :] * fit_g * (z ** (L["e_goals"] - 1.0))[:, None], 0.0, 0.95)
        g_cnt = rng.binomial(sog, conv) if k else np.zeros((n, 0), dtype=np.int64)
        other_g = rng.poisson(np.clip(max(0.0, mu_g - listed_g) * z ** L["e_goals"], 0, None))
        G = g_cnt.sum(axis=1) + other_g
        goals[side] = G
        # assists: 0 / 1 / 2 per goal, from teammates other than the scorer,
        # weighted by their assist rates ("someone else" for the unlisted)
        a_cnt = np.zeros((n, k), dtype=np.int64)
        cols = np.concatenate([g_cnt, other_g[:, None]], axis=1) if k else other_g[:, None]
        rows_i, cols_i = np.nonzero(cols)
        if len(rows_i):
            reps = cols[rows_i, cols_i]
            gs = np.repeat(rows_i, reps)           # one entry per goal: its sim
            gc = np.repeat(cols_i, reps)           # ... and its scorer's column (k = other)
            T = len(gs)
            amu = np.array([float((p.get("mu") or {}).get("a") or 0.0) for p in pl])
            pa = L["assists"]
            m_ast = pa[1] + 2 * pa[2]
            base = np.concatenate([amu, [max(0.0, m_ast * mu_g - amu.sum())]])
            u = rng.random(T)
            n_ast = (u > pa[0]).astype(int) + (u > pa[0] + pa[1]).astype(int)
            W = np.repeat(base[None, :], T, axis=0)
            W[np.arange(T), gc] = np.where(gc < k, 0.0, W[np.arange(T), gc])
            a1 = _draw(rng, W)
            W2 = W.copy()
            W2[np.arange(T), a1] = np.where(a1 < k, 0.0, W2[np.arange(T), a1])
            a2 = _draw(rng, W2)
            for col, on in ((a1, n_ast >= 1), (a2, n_ast >= 2)):
                hit = on & (col < k)
                np.add.at(a_cnt, (gs[hit], col[hit]), 1)
        for i, p in enumerate(pl):
            out["stats"][str(p["pid"])] = {
                "sog": sog[:, i].astype(np.int16), "g": g_cnt[:, i].astype(np.int16),
                "a": a_cnt[:, i].astype(np.int16),
                "pts": (g_cnt[:, i] + a_cnt[:, i]).astype(np.int16)}
    h, a = goals["home"], goals["away"]
    tie = h == a
    home_ot = rng.random(n) < L["tie_home_win"]
    out["home_reg"], out["away_reg"] = h, a
    out["home"] = h + (tie & home_ot)
    out["away"] = a + (tie & ~home_ot)
    out["ot"] = tie
    # saves: the opponent's shots minus its regulation goals
    out["saves"] = {"home": np.clip(out["shots"]["away"] - a, 0, None),
                    "away": np.clip(out["shots"]["home"] - h, 0, None)}
    return out


# ----------------------------------------------------------------------
# Legs and the joint chance
# ----------------------------------------------------------------------
def leg_hits(sim, leg):
    """Boolean array. leg: {"pid", "stat", "line", "side"}; pid "_game"
    with stat "home_win" / "away_win" / "total" / "home_margin" (the puck
    line, home side) / "away_margin"; pid "_goalie_home" / "_goalie_away"
    with stat "sv"."""
    pid = leg.get("pid")
    if pid == "_game":
        h, a = sim["home"], sim["away"]
        st = leg["stat"]
        if st == "home_win":
            return h > a
        if st == "away_win":
            return a > h
        v = (h + a) if st == "total" else ((h - a) if st == "home_margin" else (a - h))
    elif str(pid).startswith("_goalie_"):
        v = sim["saves"][str(pid).split("_")[-1]]
    else:
        v = sim["stats"][str(pid)][leg["stat"]]
    hit = v > leg["line"]
    return hit if leg.get("side", "Over") == "Over" else ~hit


def joint(sim, legs):
    hits = [leg_hits(sim, lg) for lg in legs]
    each = [float(h.mean()) for h in hits]
    allp = float(np.logical_and.reduce(hits).mean()) if hits else None
    prod = float(np.prod(each)) if each else None
    return {"each": each, "all": allp, "product": prod,
            "lift": (allp / prod) if prod else None}


def joint_precise(game, skaters, links, sog_size, legs, n=SGP_SIMS, chunk=SGP_CHUNK, seed=7):
    """joint() at n games in chunks; the leg players' TEAMS are simulated
    whole (who scores is a competition among teammates). lift_se: Monte
    Carlo standard error of the lift."""
    need = {str(lg["pid"]) for lg in legs if not str(lg.get("pid")).startswith("_")}
    sides = {p["side"] for p in skaters or [] if str(p["pid"]) in need}
    pl = [p for p in skaters or [] if p["side"] in sides]
    each_hits = [0] * len(legs)
    all_hits = done = k = 0
    while done < n:
        m = min(chunk, n - done)
        sim = simulate(game, pl, links, sog_size, n=m, seed=seed + 1000 * k)
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


def combo_kind(legs, side_of=None):
    """The test group a parlay belongs to, e.g. "PP" (two point overs),
    "GW" (a goal + his team wins), "PPopp" (a point from each side);
    None when it is not a kind that was graded. side_of: {pid: side}."""
    if any(lg.get("side", "Over") != "Over" for lg in legs):
        return None
    types = []
    for lg in legs:
        if lg.get("pid") == "_game":
            if lg["stat"] not in ("home_win", "away_win"):
                return None
            types.append("W")
            continue
        t = LEG_TYPE.get(lg.get("stat"))
        if t is None or (t in "PG" and lg.get("line") != 0.5):
            return None
        types.append(t)
    kind = "".join(sorted(types, key=lambda x: "GPSW".index(x)))
    sides = {(side_of or {}).get(str(lg["pid"])) for lg in legs if lg.get("pid") != "_game"}
    if kind == "PP" and len(sides - {None}) == 2:
        kind = "PPopp"
    if kind in ("GW", "PW"):
        # the win must be HIS team's
        pl = next(lg for lg in legs if lg.get("pid") != "_game")
        w = next(lg for lg in legs if lg.get("pid") == "_game")
        if (side_of or {}).get(str(pl["pid"])) != w["stat"].split("_")[0]:
            return None
    return kind if kind in KIND_LABEL else None


def sgp_support(combos, legs, side_of=None):
    """The guard for a same-game parlay priced here: its kind BEAT plain
    multiplication on graded games with 100+ of them -> STRONG allowed; a
    beaten kind with fewer -> VALUE at most; anything else -> THIN."""
    kind = combo_kind(legs, side_of)
    g = (combos or {}).get(kind) if kind else None
    if not g or (g.get("verdict") or {}).get("verdict") != "beats":
        return {"measured": False, "in_range": False, "n": 0, "untested": True, "kind": kind,
                "why": "untested" if not g else "not_beaten"}
    return {"measured": True, "in_range": g["n"] >= STRONG_MIN_COMBOS, "n": g["n"],
            "untested": False, "kind": kind, "why": None}


SGP_GUARD = {
    "not_beaten": ("Capped at THIN: on graded games, parlays like this one priced with the "
                   "simulator did not beat simply multiplying the legs."),
    "untested": ("Capped at THIN: no parlay of this kind has been graded, so the link between "
                 "its legs is the model's assumption."),
    "small": "Capped at VALUE: too few parlays like this were graded for STRONG.",
}


def sgp_guard(sup, tier):
    why = (sup or {}).get("why")
    if tier == "thin" and why in ("not_beaten", "untested"):
        return SGP_GUARD[why]
    if tier == "value" and not (sup or {}).get("in_range"):
        return SGP_GUARD["small"]
    return None


# ----------------------------------------------------------------------
# The test on last season (+ this one)
# ----------------------------------------------------------------------
def test_rows(skaters, finals, priors, goal_preds, shot_preds, toi, lo):
    """{(date, home): {"home", "away", "mu_h", "mu_a", "s_h", "s_a",
    "p_home", "players": [(pid, side, mu, sog_line, actual)]}} for every
    game from `lo`: each skater's projection from his games before it
    (engines/nhl_model rates x the walk-forward environment x his fitted
    ice-time scale) — the numbers the pages print."""
    from engines import nhl_model as hm
    from engines import nba_model as _nb_
    G = {(p["date"], str(p["home"])): p for p in goal_preds or []}
    Sh = {(p["date"], str(p["home"])): p for p in shot_preds or []}
    side_of, out = {}, {}
    for f in finals or []:
        k = (f["date"], str(f["home"]))
        if f["date"] < lo or k not in G:
            continue
        g, s = G[k], Sh.get(k)
        out[k] = {"home": str(f["home"]), "away": str(f["away"]), "hs": f["hs"], "as": f["as"],
                  "mu_h": g["mu_h"], "mu_a": g["mu_a"], "p_home": g.get("p_home"),
                  "off_h": g.get("off_h"), "off_a": g.get("off_a"),
                  "s_h": s["mu_h"] if s else None, "s_a": s["mu_a"] if s else None,
                  "soff_h": s.get("off_h") if s else None, "soff_a": s.get("off_a") if s else None,
                  "players": []}
        side_of[(f["date"], str(f["away"]))] = (k, "home")   # his opp is away -> he is home
        side_of[(f["date"], str(f["home"]))] = (k, "away")
    for pid, p in (skaters or {}).items():
        games = sorted(p.get("games") or [], key=lambda x: x[0])
        for i, (d, opp, s, g, a, _toi) in enumerate(games):
            if d < lo or i < 5:
                continue
            hit = side_of.get((d, str(opp)))
            if not hit:
                continue
            k, side = hit
            gm_ = out[k]
            r = hm.rates(p, priors, before=d)
            if not r:
                continue
            mu_t, off = (gm_["mu_h"], gm_["off_h"]) if side == "home" else (gm_["mu_a"],
                                                                           gm_["off_a"])
            ms, soff = (gm_["s_h"], gm_["soff_h"]) if side == "home" else (gm_["s_a"],
                                                                           gm_["soff_a"])
            gr = mu_t / off if off else 1.0
            sr = ms / soff if (ms and soff) else 1.0
            sc = hm.toi_scales(games[:i], toi, p.get("pp"))
            mu = {"sog": r["sog"] * sr * sc["sog"], "g": r["g"] * gr * sc["pts"],
                  "a": r["a"] * gr * sc["pts"]}
            hv = [x[2] for x in games[:i] if x[2] is not None][-10:]
            line = _nb_.half_line(hv) if hv else None
            gm_["players"].append((str(pid), side, mu, line,
                                   {"sog": s, "g": g or 0, "a": a or 0,
                                    "pts": (g or 0) + (a or 0)}))
    return out


def _combos(gm_):
    """The parlays people build from one game: (kind, legs, hit)."""
    P = gm_["players"]
    hw = gm_["hs"] > gm_["as"]
    out = []

    def top(side, key, n):
        return sorted([x for x in P if x[1] == side], key=key)[:n]
    for side in ("home", "away"):
        win_hit = hw if side == "home" else not hw
        wleg = {"pid": "_game", "stat": f"{side}_win", "line": 0.5, "side": "Over"}
        bp = top(side, lambda x: -(x[2]["g"] + x[2]["a"]), 3)
        bg = top(side, lambda x: -x[2]["g"], 2)
        bs = [x for x in top(side, lambda x: -x[2]["sog"], 2) if x[3] is not None
              and x[4]["sog"] is not None]

        def pl(x, st, line):
            return {"pid": x[0], "stat": st, "line": line, "side": "Over"}
        if len(bp) >= 2:
            out.append(("PP", [pl(bp[0], "pts", .5), pl(bp[1], "pts", .5)],
                        bp[0][4]["pts"] > 0 and bp[1][4]["pts"] > 0))
        if len(bp) >= 3:
            out.append(("PPP", [pl(x, "pts", .5) for x in bp],
                        all(x[4]["pts"] > 0 for x in bp)))
        if len(bg) >= 2:
            out.append(("GG", [pl(bg[0], "g", .5), pl(bg[1], "g", .5)],
                        bg[0][4]["g"] > 0 and bg[1][4]["g"] > 0))
        if len(bs) == 2:
            out.append(("SS", [pl(x, "sog", x[3]) for x in bs],
                        all(x[4]["sog"] > x[3] for x in bs)))
        if bg:
            out.append(("GW", [pl(bg[0], "g", .5), wleg], bg[0][4]["g"] > 0 and win_hit))
        if bp:
            out.append(("PW", [pl(bp[0], "pts", .5), wleg], bp[0][4]["pts"] > 0 and win_hit))
    H = top("home", lambda x: -(x[2]["g"] + x[2]["a"]), 2)
    A = top("away", lambda x: -(x[2]["g"] + x[2]["a"]), 2)
    if H and A:
        out.append(("PPopp", [{"pid": H[0][0], "stat": "pts", "line": .5, "side": "Over"},
                              {"pid": A[0][0], "stat": "pts", "line": .5, "side": "Over"}],
                    H[0][4]["pts"] > 0 and A[0][4]["pts"] > 0))
    if len(H) == 2 and len(A) == 2:
        out.append(("PPPP", [{"pid": x[0], "stat": "pts", "line": .5, "side": "Over"}
                             for x in H + A], all(x[4]["pts"] > 0 for x in H + A)))
    return out


def _marginal(leg, mu, sog_size, cal, gm_):
    """A leg's chance as the pages deliver it: the props model's pmf
    through the props test's curve for that market; the win from the game
    model."""
    from engines import model_math as mm
    from engines import nhl_model as hm
    from engines import top_plays_board as tpb
    if leg["pid"] == "_game":
        p = gm_["p_home"]
        if p is None:
            return None
        return p if leg["stat"] == "home_win" else 1 - p
    pm = hm.skater_pmfs(mu, sog_size)[leg["stat"]]
    raw = mm.prob_at_least(pm, int(np.floor(leg["line"])) + 1)
    # the tested line's curve, else the nearest tested line of the stat
    # (model_view.curve_for's rule — model_view itself imports streamlit)
    cands = [(k, nn - 0.5) for k, _l, s_, nn in hm.MARKETS
             if s_ == leg["stat"] and (cal or {}).get(k)]
    bins = (cal[min(cands, key=lambda x: abs(x[1] - leg["line"]))[0]] if cands else None)
    c = tpb.calibrate(raw, bins) if bins else None
    return c if c is not None else raw


def test_combos(rows, links, sog_size, cal, n=COMBO_SIMS, seed=23):
    """Per kind: {n, sim_brier, independent_brier, verdict, avg_lift,
    predicted_ind, predicted_sim, actual}."""
    from engines import model_math as mm
    acc = {}
    for k_, (key, gm_) in enumerate(sorted(rows.items())):
        if len([x for x in gm_["players"] if x[1] == "home"]) < 3 or \
                len([x for x in gm_["players"] if x[1] == "away"]) < 3:
            continue
        combos = _combos(gm_)
        if not combos:
            continue
        sk = [{"pid": x[0], "side": x[1], "mu": x[2]} for x in gm_["players"]]
        mus = {x[0]: x[2] for x in gm_["players"]}
        sim = simulate({"mu_home": gm_["mu_h"], "mu_away": gm_["mu_a"],
                        "shots_home": gm_["s_h"], "shots_away": gm_["s_a"]},
                       sk, links, sog_size, n=n, seed=seed + k_)
        for kind, legs, hit in combos:
            j = joint(sim, legs)
            marg = [_marginal(lg, mus.get(lg["pid"]), sog_size, cal, gm_) for lg in legs]
            if None in marg or not j["lift"]:
                continue
            ind = float(np.prod(marg))
            sp = min(1.0, ind * j["lift"])
            acc.setdefault(kind, []).append((j["lift"], ind, sp, 1 if hit else 0))
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


def build(prior, model_block, pool, cur_rows=None, days=TEST_DAYS):
    """{"links", "combos", "test_from", "n_games", "this_season_games"} —
    links on last season; the combos test on last season's final `days`
    days plus every game of this season so far. prior: data/nhl/
    prior_season.json; model_block: nhl_model.build()'s; pool: the
    skater pool (last season + this one, nhl_model.pool_skaters);
    cur_rows: this season's finals in the goal_rows shape (+ home_sog)."""
    from engines import game_model as gm
    from engines import nhl_model as hm
    pf = list(prior.get("finals") or [])
    if not pf or not model_block:
        return None
    gk = model_block["params"]["shrink_k"]
    disp = model_block["params"].get("dispersion")
    sk = ((model_block.get("shots") or {}).get("params") or {}).get("shrink_k") or 30.0
    sog_size = (model_block.get("skater_priors") or {}).get("sog_dispersion")
    # last season's walk-forward (the links are fitted on its first part)
    gprior = gm.walk_forward(gm.clean_finals(hm.goal_rows(pf)), gk, disp)
    sprior = gm.walk_forward(gm.clean_finals(hm.shot_rows(pf)), sk, score_only=True)
    dates = sorted({f["date"] for f in pf})
    lo = dates[-days] if len(dates) > days else dates[0]
    links = fit_links([f for f in pf if f["date"] < lo], gprior, sprior,
                      {k: dict(v, games=[x for x in v.get("games") or [] if x[0] < lo])
                       for k, v in (prior.get("skaters") or {}).items()},
                      (model_block.get("league") or {}).get("tie_home_win"))
    # this season: walked forward from last season's ratings (as the page's model is)
    cur = [r for r in (cur_rows or []) if r.get("hs") is not None]
    gcur = scur = []
    if cur:
        pt = gm.team_totals(gm.clean_finals(hm.goal_rows(pf)))
        pl = gm.league_constants(gm.clean_finals(hm.goal_rows(pf)))["league_rate"]
        gcur = gm.walk_forward(gm.clean_finals(hm.goal_rows(cur)), gk, disp, prior_totals=pt,
                               prior_league=pl,
                               carryover=model_block["params"].get("carryover"))
        cs = [r for r in cur if r.get("home_sog") is not None]
        if cs:
            scur = gm.walk_forward(gm.clean_finals(hm.shot_rows(cs)), sk, score_only=True)
    priors = model_block.get("skater_priors")
    rows = test_rows(pool, pf + cur, priors, gprior + gcur, sprior + scur,
                     model_block.get("toi"), lo)
    cal = {k: (v or {}).get("calibration") for k, v in
           (model_block.get("props_validation") or {}).items() if isinstance(v, dict)}
    combos = test_combos(rows, links, sog_size, cal)
    last_prior = dates[-1]
    return {"links": links, "combos": combos, "test_from": lo, "n_games": len(rows),
            "this_season_games": sum(1 for k in rows if k[0] > last_prior),
            "sog_size": sog_size}
