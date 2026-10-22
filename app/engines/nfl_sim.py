"""
NFL game simulator (10-22) — play a game thousands of times with every
player's line drawn TOGETHER, so a same-game parlay is priced on how its
legs move together.

ONE SIMULATED GAME
------------------
  1. The score: margin and total drawn from the game model (normal, its
     measured SDs) -> each team's points, and two shapes of the game:
       scoring  x = team points / projected - 1
       script   m = (team margin - projected margin) / sd_margin
                    (ahead -> run the clock; behind -> throw)
  2. Every receiver's and back's yards, catches, targets, carries: his
     projection x (1 + E_SCORE x + E_SCRIPT m), each elasticity MEASURED
     per stat on last season; the draw around that has the rest of the
     spread the props boards use (yards normal at the measured cv,
     counts negative binomial), so each line on its own prices like the
     board.
  3. The quarterback's passing line is the SUM of his receivers' lines
     (+ the targets nobody listed): his yards are their yards. MEASURED
     10-22: a QB's yards and a teammate's receiving yards move together
     (residual covariance +0.12) — and that is the arithmetic of the sum,
     not a separate link to invent.
  4. Touchdowns: the team's from its simulated points (Poisson at the
     measured TDs per point); each one passing at the QB's share, and
     handed to a scorer by his touchdown share (receiving or rushing,
     from his targets and carries). Teammates compete for the same
     touchdowns (measured: negative), and a shootout gives everyone more.

WHAT IT CHANGES: the JOINT chance of a same-game parlay — the legs'
delivered chances multiplied, times the simulator's LIFT.

TESTED (rule 1): the parlays people build — QB + his top receiver,
QB + two receivers, a back's rushing yards + his team to win, a
touchdown + the win, two teammates to score, both QBs over, QB + his top
receiver to score — on last season's second half plus this season so
far, priced with the lift vs plain multiplication, against what
happened. A kind that has not beaten that stays at THIN.

numpy, no streamlit, no requests.
"""
import math

import numpy as np

MARKET = {"pass_yds": "Passing yards", "pass_att": "Pass attempts", "pass_cmp": "Completions",
          "pass_td": "Passing TDs", "pass_int": "Interceptions", "rush_yds": "Rushing yards",
          "carries": "Carries", "rec_yds": "Receiving yards", "rec": "Receptions",
          "targets": "Targets", "scrim_yds": "Rush + rec yards", "td": None}
ELASTIC_STATS = ("pass_yds", "rush_yds", "carries", "rec_yds", "rec", "targets")
MIN_MU = {"pass_yds": 100, "rush_yds": 15, "carries": 5, "rec_yds": 15, "rec": 1.5,
          "targets": 2}
DEFAULT_LINKS = {"e": {s: [0.0, 0.0] for s in ELASTIC_STATS}, "tpp": 0.107}
SGP_MAX_LEGS = 8
SGP_SIMS = 200_000
SGP_CHUNK = 50_000
COMBO_SIMS = 20_000
STRONG_MIN_COMBOS = 100
STATS = (("pass_yds", "Passing yards"), ("pass_cmp", "Completions"), ("pass_att", "Pass attempts"),
         ("pass_td", "Passing TDs"), ("pass_int", "Interceptions"), ("rush_yds", "Rushing yards"),
         ("carries", "Carries"), ("rec_yds", "Receiving yards"), ("rec", "Receptions"),
         ("targets", "Targets"), ("scrim_yds", "Rush + rec yards"), ("td", "Touchdowns"))
KIND_LABEL = {"QR": "QB passing yards + his top receiver's yards",
              "QRR": "QB passing yards + two receivers' yards",
              "UW": "a back's rushing yards + his team wins",
              "TW": "a touchdown + his team wins", "TT": "two teammates to score",
              "QQ": "both quarterbacks over", "QT": "QB passing yards + a receiver to score"}


# ----------------------------------------------------------------------
# Rows: every player-game walked forward (the numbers the pages print)
# ----------------------------------------------------------------------
def game_preds(finals):
    """({(date, home_id): pred}, params) — the game model walked forward."""
    from engines import game_model as gm
    from engines import nfl_game_model as ngm
    gfin = gm.clean_finals(ngm.rows(finals))
    par = ngm.fit(gfin)
    if not par:
        return {}, None
    return {(p["date"], str(p["home"])): p for p in ngm._wf(gfin, par["shrink_k"])}, par


def collect(finals, logs, pc, spreads, preds, prior_players=None, prior_w=None, flags=None,
            strength=None):
    """[{"week", "date", "event_id", "home_id", "away_id", "hs", "as",
    "mu_h", "mu_a", "players": [{"pid", "side", "role", "proj", "actual",
    "lines"}]}] — each week priced from earlier weeks only (the prop
    test's walk, nfl_prop_check). Touchdowns are anchored to the market's
    implied points when the game has a recorded line, else to the game
    model's projected points (most 2025 games have no line on file)."""
    import nfl_prop_check as npc
    from engines import nfl_projection as nproj
    from engines import nfl_prop_odds as npo
    weeks = sorted({f["week"] for f in finals if f.get("week")})
    out = []
    for w in weeks[1:]:
        prior_wks = [x for x in weeks if x < w]
        before = [f for f in finals if f.get("week") in prior_wks]
        plogs = npc._slice(logs, prior_wks)
        usage = pc.team_game_usage(plogs)
        league = pc.league_constants(before, usage)
        if not league:
            continue
        league.update(pc.td_opportunity_prior(plogs))
        league.update(pc.qb_rate_priors(plogs))
        teams = pc.attach_ranks(pc.team_research(before, usage))
        players = pc.player_summaries(plogs, usage)
        if prior_players and prior_w:
            players = {pid: pc.merge_prior(p, prior_players.get(pid), prior_w)
                       for pid, p in players.items()}
        for f in [x for x in finals if x.get("week") == w]:
            gp = preds.get((f["date"], str(f.get("home_id"))))
            if not gp or f.get("home_score") is None:
                continue
            a_pts, h_pts, _n = nproj.implied_totals(f.get("odds") or {}, f.get("away_abbr"),
                                                    f.get("home_abbr"))
            if a_pts is None or h_pts is None:
                a_pts, h_pts = gp["mu_a"], gp["mu_h"]
            g = {"away_players": [], "home_players": []}
            for side in ("away", "home"):
                for p in players.values():
                    if p.get("team") != f[side]:
                        continue
                    q = dict(p)
                    q["role"] = pc.role_of(q)
                    if q["role"]:
                        g[f"{side}_players"].append(q)
            nproj.attach_td_shares([g], league)
            rec = {"week": w, "date": f["date"], "event_id": str(f["event_id"]),
                   "home_id": str(f.get("home_id")), "away_id": str(f.get("away_id")),
                   "hs": f["home_score"], "as": f["away_score"], "mu_h": gp["mu_h"],
                   "mu_a": gp["mu_a"], "p_home": gp.get("p_home"), "players": []}
            for side, other in (("away", "home"), ("home", "away")):
                team, opp = teams.get(f[side]), teams.get(f[other])
                implied = a_pts if side == "away" else h_pts
                for p in g[f"{side}_players"]:
                    game = ((logs.get(p["pid"]) or {}).get("games") or {}).get(str(f["event_id"]))
                    if not game:
                        continue                      # did not play: not in the test
                    proj = nproj.project_player(p, team, opp, dict(
                        league, matchup_in_number=flags or {},
                        matchup_strength=dict(strength or {})), implied)
                    lines = {}
                    for stat, _l, _key, _m, roles in npo.STATS:
                        if p["role"] not in roles:
                            continue
                        hist = npc._history(plogs, p["pid"], stat)
                        ln = npc._line_for(hist, stat)
                        if ln is not None and hist:
                            lines[stat] = ln
                    rec["players"].append({
                        "pid": str(p["pid"]), "side": side, "role": p["role"],
                        "proj": {k: v for k, v in proj.items() if isinstance(v, (int, float))},
                        "actual": npc.game_values(game), "lines": lines})
            out.append(rec)
    return out


# ----------------------------------------------------------------------
# The links, measured on last season's first half
# ----------------------------------------------------------------------
def _shape(g, side, sd_margin):
    tp, op = (g["hs"], g["as"]) if side == "home" else (g["as"], g["hs"])
    tm, om = (g["mu_h"], g["mu_a"]) if side == "home" else (g["mu_a"], g["mu_h"])
    return tp / tm - 1.0, ((tp - op) - (tm - om)) / sd_margin


def fit_links(rows, sd_margin, tpp, spreads=None):
    """{"e": {stat: [e_score, e_script]}, "n": {stat: n}, "tpp"}: per
    stat, (actual - projection) on projection x (1, x, m), least squares
    — weighted by volume (a 3-yard projection's ratio is noise)."""
    acc = {s: [] for s in ELASTIC_STATS}
    for g in rows:
        for p in g["players"]:
            x, m = _shape(g, p["side"], sd_margin)
            for s in ELASTIC_STATS:
                mu, y = p["proj"].get(s), p["actual"].get(s)
                if mu is None or y is None or mu < MIN_MU[s]:
                    continue
                acc[s].append((mu, x, m, y))
    e, n = {}, {}
    for s, xs in acc.items():
        n[s] = len(xs)
        if len(xs) < 100:
            e[s] = [0.0, 0.0]
            continue
        A = np.array([(mu, mu * x, mu * m) for mu, x, m, _y in xs])
        y = np.array([yy - mu for mu, _x, _m, yy in xs])
        b = np.linalg.lstsq(A, y, rcond=None)[0]
        e[s] = [round(float(b[1]), 4), round(float(b[2]), 4)]
    return {"e": e, "n": n, "tpp": tpp, "corr": fit_corr(rows, e, sd_margin, spreads)}


CORR_TYPES = ("QR", "RR", "QU", "RU", "UU")


def fit_corr(rows, e, sd_margin, spreads):
    """{"QR": r, ...}: correlations of the standardized residuals (actual
    less the score-shaped projection, over the board's spread) between
    one team's lines in a game — the passer's yards (Q), the top three
    receivers' (R), the top two backs' rushing (U). MEASURED 10-22 on
    2025: QB-receiver +0.29, receiver-receiver +0.01, QB-rush -0.16,
    receiver-rush -0.07, back-back -0.01."""
    sp = spreads or {}
    cv = {s_: (sp.get(MARKET[s_]) or {}).get("cv") for s_ in ("pass_yds", "rec_yds", "rush_yds")}
    if not all(cv.values()):
        return {}

    def z(g, p, s_):
        mu, y = p["proj"].get(s_), p["actual"].get(s_)
        if not mu or y is None or mu < MIN_MU[s_]:
            return None
        x, m = _shape(g, p["side"], sd_margin)
        es, ec = e.get(s_) or [0.0, 0.0]
        return (y - mu * (1 + es * x + ec * m)) / (cv[s_] * mu)
    acc = {k: [] for k in CORR_TYPES}
    for g in rows:
        for side in ("home", "away"):
            P = [p for p in g["players"] if p["side"] == side]
            q = sorted([p for p in P if p["role"] == "QB"],
                       key=lambda p: -(p["proj"].get("pass_att") or 0))[:1]
            r = sorted([p for p in P if p["role"] in ("REC", "RB")],
                       key=lambda p: -(p["proj"].get("rec_yds") or 0))[:3]
            u = sorted([p for p in P if p["role"] == "RB"],
                       key=lambda p: -(p["proj"].get("rush_yds") or 0))[:2]
            zs = ([("Q", p, z(g, p, "pass_yds")) for p in q]
                  + [("R", p, z(g, p, "rec_yds")) for p in r]
                  + [("U", p, z(g, p, "rush_yds")) for p in u])
            zs = [x for x in zs if x[2] is not None]
            for i in range(len(zs)):
                for j in range(i + 1, len(zs)):
                    if zs[i][1] is zs[j][1]:
                        continue
                    k = "".join(sorted(zs[i][0] + zs[j][0], key="QRU".index))
                    acc[k].append((zs[i][2], zs[j][2]))
    out = {}
    for k, xs in acc.items():
        if len(xs) >= 100:
            a = np.array(xs)
            out[k] = round(float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]), 3)
    return out


# ----------------------------------------------------------------------
# One simulated game
# ----------------------------------------------------------------------
def _counts(rng, mean, mu, size, shock_var):
    v_target = mu + (mu * mu / size if size else 0.0)
    extra = v_target - mu - mu * mu * shock_var
    mean = np.clip(mean, 1e-6, None)
    if extra <= 1e-9:
        return rng.poisson(mean)
    r = mu * mu / extra
    return rng.poisson(rng.gamma(r, mean / r))


def simulate(game, players, spreads, links=None, n=10000, seed=7):
    """game: {"mu_home", "mu_away", "sd_margin", "sd_total"};
    players: [{"pid", "side", "role", "proj": {...}}] (the nightly's
    projection keys; "td_exp" for touchdowns).
    -> {"home", "away", "stats": {pid: {stat: int arr}}}"""
    L = dict(DEFAULT_LINKS, **(links or {}))
    E = L.get("e") or {}
    rng = np.random.default_rng(seed)
    mh, ma = float(game["mu_home"]), float(game["mu_away"])
    sdm, sdt = float(game["sd_margin"]), float(game["sd_total"])
    margin = rng.normal(mh - ma, sdm, n)
    total = rng.normal(mh + ma, sdt, n)
    pts = {"home": np.clip((total + margin) / 2.0, 0, None),
           "away": np.clip((total - margin) / 2.0, 0, None)}
    out = {"home": np.rint(pts["home"]).astype(np.int32),
           "away": np.rint(pts["away"]).astype(np.int32), "stats": {}}
    sp = spreads or {}

    def shocks(side, stat):
        mu_t = mh if side == "home" else ma
        x = pts[side] / max(mu_t, 1.0) - 1.0
        mg = ((pts[side] - pts["away" if side == "home" else "home"])
              - ((mh - ma) if side == "home" else (ma - mh))) / sdm
        es, ec = (E.get(stat) or [0.0, 0.0])
        f = es * x + ec * mg
        return np.clip(1.0 + f, 0.05, None), float(np.var(f))

    C = L.get("corr") or {}
    for side in ("home", "away"):
        pl = [p for p in players or [] if p.get("side") == side]
        # the passer: the QB projected to throw the most
        qbs = sorted([p for p in pl if p.get("role") == "QB"],
                     key=lambda p: -((p.get("proj") or {}).get("pass_att") or 0))
        others = [p for p in pl if p.get("role") != "QB"]
        # THE YARDS, TOGETHER: one standard-normal residual per yards line,
        # correlated by type at the MEASURED residual correlations (after
        # the score): passer's yards with each receiver's (Q-R), receivers
        # with each other (R-R), rushing with passing (Q-U) and with
        # receiving (R-U), backs with each other (U-U)
        ylines = []                                    # (pid, stat, type)
        if qbs and (qbs[0].get("proj") or {}).get("pass_yds"):
            ylines.append((qbs[0], "pass_yds", "Q"))
        for p in others:
            pr = p.get("proj") or {}
            if (pr.get("rec_yds") or 0) > 0:
                ylines.append((p, "rec_yds", "R"))
            if (pr.get("rush_yds") or 0) > 0:
                ylines.append((p, "rush_yds", "U"))
        d = len(ylines)
        Z = np.zeros((n, 0))
        if d:
            M = np.eye(d)
            for a in range(d):
                for b in range(a + 1, d):
                    if ylines[a][0] is ylines[b][0]:
                        continue                       # one player's two lines
                    key = "".join(sorted(ylines[a][2] + ylines[b][2], key="QRU".index))
                    M[a, b] = M[b, a] = float(C.get(key) or 0.0)
            for shrink in (1.0, 0.8, 0.6, 0.4, 0.0):
                try:
                    Lc = np.linalg.cholesky(np.eye(d) + shrink * (M - np.eye(d)))
                    break
                except np.linalg.LinAlgError:
                    continue
            Z = rng.standard_normal((n, d)) @ Lc.T
        zmap = {(id(pp), st_): Z[:, k] for k, (pp, st_, _t) in enumerate(ylines)}
        for p in others + qbs:
            pr, st = p.get("proj") or {}, {}
            for s_ in ("pass_yds", "rush_yds", "rec_yds"):
                mu = pr.get(s_)
                if not mu or mu <= 0 or (s_ == "pass_yds" and p.get("role") != "QB"):
                    continue
                f, v = shocks(side, s_)
                cv = (sp.get(MARKET[s_]) or {}).get("cv") or 0.8
                sd = math.sqrt(max((cv * mu) ** 2 - mu * mu * v, (0.15 * mu) ** 2))
                z = zmap.get((id(p), s_))
                if z is None:
                    z = rng.standard_normal(n)
                # floored at 0 like the board's distribution (its normal
                # puts every negative yard on 0)
                st[s_] = np.clip(np.rint(mu * f + sd * z), 0, None).astype(np.int32)
            for s_ in ("carries", "rec", "targets", "pass_cmp", "pass_att", "pass_int"):
                mu = pr.get(s_)
                if not mu or mu <= 0 or (s_.startswith("pass") and p.get("role") != "QB"):
                    continue
                ek = "targets" if s_ in ("pass_att", "pass_cmp") else (
                    "rec" if s_ == "rec" else ("carries" if s_ == "carries" else None))
                f, v = shocks(side, ek) if ek else (np.ones(n), 0.0)
                st[s_] = _counts(rng, mu * f, mu, (sp.get(MARKET[s_]) or {}).get("size"), v)
            out["stats"][str(p["pid"])] = st
        # TOUCHDOWNS: the team's from its points, each to a scorer
        tpp = L.get("tpp") or 0.107
        T = rng.poisson(np.clip(pts[side] * tpp, 1e-9, None))
        mu_team_td = (mh if side == "home" else ma) * tpp
        q_pass = 0.0
        if qbs and (qbs[0].get("proj") or {}).get("pass_td"):
            q_pass = min(0.9, qbs[0]["proj"]["pass_td"] / max(mu_team_td, 1e-6))
        k = len(others)
        w_rec = np.zeros(k + 1)
        w_rush = np.zeros(k + 1)
        for i, p in enumerate(others):
            pr = p.get("proj") or {}
            lam = pr.get("td_exp") or 0.0
            tg, ca = pr.get("targets") or 0.0, pr.get("carries") or 0.0
            share = tg / (tg + ca) if (tg + ca) > 0 else (1.0 if p.get("role") == "REC" else 0.0)
            w_rec[i], w_rush[i] = lam * share, lam * (1 - share)
        w_rec[k] = max(0.0, q_pass * mu_team_td - w_rec[:k].sum())
        w_rush[k] = max(0.0, (1 - q_pass) * mu_team_td - w_rush[:k].sum())
        n_pass = rng.binomial(T, q_pass)
        n_rush = T - n_pass
        td = np.zeros((n, k + 1), dtype=np.int32)
        for cnt, w in ((n_pass, w_rec), (n_rush, w_rush)):
            if w.sum() > 0:
                td += _multi(rng, cnt, w / w.sum())
        for i, p in enumerate(others):
            st = out["stats"][str(p["pid"])]
            st["td"] = td[:, i]
            st["scrim_yds"] = st.get("rush_yds", 0) + st.get("rec_yds", 0)
        if qbs:
            out["stats"][str(qbs[0]["pid"])]["pass_td"] = n_pass
    for pid, st in out["stats"].items():
        out["stats"][pid] = {k: np.asarray(v, dtype=np.int16) if np.ndim(v) else
                             np.full(n, int(v), dtype=np.int16) for k, v in st.items()}
    return out


def _multi(rng, counts, p):
    """Row-wise multinomial: counts (n,) draws over probabilities p (k,),
    vectorised one draw-slot at a time (a team scores a handful)."""
    n, k = len(counts), len(p)
    out = np.zeros((n, k), dtype=np.int32)
    cum = np.cumsum(p)
    cum[-1] = 1.0
    for j in range(int(counts.max()) if n else 0):
        on = counts > j
        col = np.searchsorted(cum, rng.random(int(on.sum())), side="right")
        np.add.at(out, (np.nonzero(on)[0], np.minimum(col, k - 1)), 1)
    return out


# ----------------------------------------------------------------------
# Legs and the joint chance
# ----------------------------------------------------------------------
def leg_hits(sim, leg):
    if leg.get("pid") == "_game":
        h, a = sim["home"], sim["away"]
        st = leg["stat"]
        if st == "home_win":
            return h > a
        if st == "away_win":
            return a > h
        v = (h + a) if st == "total" else ((h - a) if st == "home_margin" else (a - h))
    else:
        v = sim["stats"][str(leg["pid"])].get(leg["stat"])
        if v is None:
            return np.zeros(len(sim["home"]), dtype=bool)
    hit = v > leg["line"]
    return hit if leg.get("side", "Over") == "Over" else ~hit


def joint(sim, legs):
    hits = [leg_hits(sim, lg) for lg in legs]
    each = [float(h.mean()) for h in hits]
    allp = float(np.logical_and.reduce(hits).mean()) if hits else None
    prod = float(np.prod(each)) if each else None
    return {"each": each, "all": allp, "product": prod,
            "lift": (allp / prod) if prod else None}


def joint_precise(game, players, spreads, links, legs, n=SGP_SIMS, chunk=SGP_CHUNK, seed=7):
    """joint() at n games in chunks, the leg players' TEAMS simulated whole
    (a QB's line is his receivers', touchdowns are shared)."""
    need = {str(lg["pid"]) for lg in legs if lg.get("pid") != "_game"}
    sides = {p["side"] for p in players or [] if str(p["pid"]) in need}
    pl = [p for p in players or [] if p["side"] in sides]
    each_hits = [0] * len(legs)
    all_hits = done = k = 0
    while done < n:
        m = min(chunk, n - done)
        sim = simulate(game, pl, spreads, links, n=m, seed=seed + 1000 * k)
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


def combo_kind(legs, info):
    """The graded kind of a parlay, or None. info: {pid: (side, role)}."""
    if any(lg.get("side", "Over") != "Over" for lg in legs):
        return None
    ts = []
    for lg in legs:
        if lg.get("pid") == "_game":
            if lg["stat"] not in ("home_win", "away_win"):
                return None
            ts.append(("W", lg["stat"].split("_")[0]))
            continue
        side, role = (info or {}).get(str(lg["pid"]), (None, None))
        st = lg.get("stat")
        if st == "pass_yds" and role == "QB":
            ts.append(("Q", side))
        elif st == "rec_yds":
            ts.append(("R", side))
        elif st == "rush_yds" and role == "RB":
            ts.append(("U", side))
        elif st == "td" and lg.get("line") == 0.5:
            ts.append(("T", side))
        else:
            return None
    kind = "".join(sorted((t for t, _s in ts), key=lambda x: "QRUTW".index(x)))
    sides = {s for _t, s in ts}
    if kind == "QQ":
        return kind if len(sides) == 2 else None
    if kind in KIND_LABEL and len(sides) == 1:
        return kind
    return None


def sgp_support(combos, legs, info):
    kind = combo_kind(legs, info)
    g = (combos or {}).get(kind) if kind else None
    if not g or (g.get("verdict") or {}).get("verdict") != "beats":
        return {"measured": False, "in_range": False, "n": 0, "untested": True, "kind": kind,
                "why": "untested" if not g else "not_beaten"}
    return {"measured": True, "in_range": g["n"] >= STRONG_MIN_COMBOS, "n": g["n"],
            "untested": False, "kind": kind, "why": None}


def sgp_guard(sup, tier):
    from engines import nhl_sim as _h
    return _h.sgp_guard(sup, tier)


# ----------------------------------------------------------------------
# The test
# ----------------------------------------------------------------------
def _combos(g):
    """(kind, legs, hit) for the parlays people build from one game."""
    P = g["players"]
    hw = g["hs"] > g["as"]
    out = []

    def best(side, role, key, n=1, need=None):
        xs = [p for p in P if p["side"] == side and (role is None or p["role"] in role)
              and (need is None or need in p["lines"] or need == "td")
              and (p["proj"].get(key) or 0) > 0]
        return sorted(xs, key=lambda p: -(p["proj"].get(key) or 0))[:n]

    def ov(p, st):
        y = p["actual"].get(st)
        if st == "td":
            return (y or 0) > 0
        return y is not None and y > p["lines"][st]

    def leg(p, st):
        return {"pid": p["pid"], "stat": st, "line": 0.5 if st == "td" else p["lines"][st],
                "side": "Over"}
    for side in ("home", "away"):
        win_hit = hw if side == "home" else not hw
        W = {"pid": "_game", "stat": f"{side}_win", "line": 0.5, "side": "Over"}
        qb = best(side, ("QB",), "pass_yds", 1, "pass_yds")
        rc = best(side, ("REC", "RB"), "rec_yds", 2, "rec_yds")
        rb = best(side, ("RB",), "rush_yds", 1, "rush_yds")
        td = best(side, ("REC", "RB"), "td_exp", 2, "td")
        if qb and rc:
            out.append(("QR", [leg(qb[0], "pass_yds"), leg(rc[0], "rec_yds")],
                        ov(qb[0], "pass_yds") and ov(rc[0], "rec_yds")))
        if qb and len(rc) == 2:
            out.append(("QRR", [leg(qb[0], "pass_yds")] + [leg(x, "rec_yds") for x in rc],
                        ov(qb[0], "pass_yds") and all(ov(x, "rec_yds") for x in rc)))
        if rb:
            out.append(("UW", [leg(rb[0], "rush_yds"), W], ov(rb[0], "rush_yds") and win_hit))
        if td:
            out.append(("TW", [leg(td[0], "td"), W], ov(td[0], "td") and win_hit))
        if len(td) == 2:
            out.append(("TT", [leg(x, "td") for x in td], all(ov(x, "td") for x in td)))
        if qb and td:
            out.append(("QT", [leg(qb[0], "pass_yds"), leg(td[0], "td")],
                        ov(qb[0], "pass_yds") and ov(td[0], "td")))
    qh, qa = best("home", ("QB",), "pass_yds", 1, "pass_yds"), best("away", ("QB",), "pass_yds",
                                                                     1, "pass_yds")
    if qh and qa:
        out.append(("QQ", [leg(qh[0], "pass_yds"), leg(qa[0], "pass_yds")],
                    ov(qh[0], "pass_yds") and ov(qa[0], "pass_yds")))
    return out


def _marginal(leg, players, spreads, cal, g):
    """A leg's chance as the pages deliver it: the board's distribution
    at the line, through the prop test's curve for that stat; the win
    from the game model."""
    from engines import model_math as mm
    from engines import nfl_prop_odds as npo
    from engines import top_plays_board as tpb
    if leg["pid"] == "_game":
        p = g.get("p_home")
        if p is None:
            return None
        return p if leg["stat"] == "home_win" else 1 - p
    pr = next((p["proj"] for p in players if p["pid"] == leg["pid"]), {})
    key = "td_exp" if leg["stat"] == "td" else leg["stat"]
    pm = npo.stat_pmf(MARKET[leg["stat"]], pr.get(key), spreads)
    if not pm:
        return None
    raw = mm.over_prob_pmf(pm, leg["line"])
    bins = (cal or {}).get(f"@{leg['stat']}")
    c = tpb.calibrate(raw, bins) if bins else None
    return c if c is not None else raw


def test_combos(rows, spreads, links, sds, cal, n=COMBO_SIMS, seed=23):
    """Per kind: {n, sim_brier, independent_brier, verdict, avg_lift,
    predicted_ind, predicted_sim, actual}."""
    from engines import model_math as mm
    acc = {}
    for k_, g in enumerate(rows):
        combos = _combos(g)
        if not combos:
            continue
        players = [{"pid": p["pid"], "side": p["side"], "role": p["role"], "proj": p["proj"]}
                   for p in g["players"]]
        sim = simulate({"mu_home": g["mu_h"], "mu_away": g["mu_a"], "sd_margin": sds[0],
                        "sd_total": sds[1]}, players, spreads, links, n=n, seed=seed + k_)
        for kind, legs, hit in combos:
            j = joint(sim, legs)
            marg = [_marginal(lg, g["players"], spreads, cal, g) for lg in legs]
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


def _phome(margin, sd):
    return 0.5 * (1 + math.erf(margin / (sd * math.sqrt(2))))


def build(prior, finals, logs, pc, league, prior_players=None, prior_w=None, quarters=None):
    """{"links", "combos", "sds", "n_games", "this_season_games", "cut"}:
    links fitted on last season's first half of weeks, the parlay test on
    its second half plus this season (prior = {"finals", "logs"} for
    2025, finals / logs this season's, pc = nfl_precompute). quarters:
    data/nfl/prior_quarters.json's games -> "quarters": the 1st-quarter /
    1st-half model fitted on the same first half of weeks, tested on the
    second (engines/nfl_quarters.build)."""
    spreads = (league or {}).get("prop_spreads") or {}
    flags, strength = league.get("matchup_in_number"), league.get("matchup_strength")
    pf = list((prior or {}).get("finals") or [])
    preds_p, par = game_preds(pf) if pf else ({}, None)
    if not par:
        return None
    cur = [f for f in finals or [] if f.get("home_score") is not None]
    preds_all, _par2 = game_preds(pf + cur)
    old = collect(pf, prior.get("logs") or {}, pc, spreads, preds_p, None, None, flags,
                  strength)
    new = collect(cur, logs or {}, pc, spreads, preds_all, prior_players, prior_w, flags,
                  strength) if cur else []
    wks = sorted({g["week"] for g in old})
    if not wks:
        return None
    cut = wks[len(wks) // 2]
    for g in old + new:
        g["p_home"] = _phome(g["mu_h"] - g["mu_a"], par["sd_margin"])
    links = fit_links([g for g in old if g["week"] < cut], par["sd_margin"],
                      league.get("td_per_point") or DEFAULT_LINKS["tpp"], spreads)
    test = [g for g in old if g["week"] >= cut] + new
    cal = {f"@{k}": v["calibration"] for k, v in (league.get("prop_validation") or {}).items()
           if isinstance(v, dict) and v.get("calibration")}
    combos = test_combos(test, spreads, links, (par["sd_margin"], par["sd_total"]), cal)
    qblk = None
    if quarters:
        from engines import nfl_quarters as nq
        qblk = nq.build(old, quarters, cut)
    return {"links": links, "combos": combos, "sds": [par["sd_margin"], par["sd_total"]],
            "n_games": len(test), "this_season_games": len(new), "cut_week": cut,
            "quarters": qblk}
