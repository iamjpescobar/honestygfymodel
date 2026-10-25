"""
NBA first basket (10-21) — who scores the game's first FIELD GOAL (the
usual market; books settle "first basket" on a field goal), and which
team does.

THE NUMBER, one game
--------------------
  starters  his team's starters from its last game who are available
            tonight, filled to five by projected minutes (last season:
            the scorer was one of a team's projected five RHO of the time
            — the rest is "someone else" and stays priced as such)
  the tip   each team's jumper = the starter who has jumped for it most;
            his tip record shrunk K_TIP jumps toward 50%:
              r = (wins + K/2) / (jumps + K)
            P(home wins tip) = r_h(1-r_a) / (r_h(1-r_a) + r_a(1-r_h))
  the team  P(team scores first) = tip x C + (1 - tip) x (1 - C)
            C = how often the tip winner scored first (fitted; ~63%)
  a player  P(team) x RHO x his share among his team's five:
              share ∝ (projected points) ^ G, blended LAMBDA with his own
              first-basket record as a starter (shrunk to his usage share)
Everything (K_TIP, C, RHO, G, LAMBDA, K_HIST) FITTED on the fit window,
walk-forward (a game sees only earlier games), by log loss; TESTED on the
unseen window against the naive price (each of the ten projected
starters equally likely), paired per game. Calibration bins per player
call -> the delivered chance and the guard's support on the page.

THE CONFIRMED FIVE (10-25): every first field goal last season (1,235 of
1,235) came from one of the ten starters. fit() also prices the unseen
games on their REAL fives (rho_confirmed, measured on the fit side) and
pairs that against the projected five: 2.27 vs 2.35 log loss per game,
z ~17 on the 593-game test, on its own calibration curve. reprice() is
what the page runs when ESPN posts a lineup or the user sets one.

Pure — no streamlit, no requests.
"""
import itertools
import math

from engines import model_math as mm

K_TIP = (2, 5, 15, 40)
G_POW = (0.5, 1.0, 1.5, 2.0, 2.5)
LAMBDA = (0.0, 0.25, 0.5, 0.75, 1.0)
K_HIST = (5, 20, 60)
EDGES = (0, .02, .04, .06, .08, .10, .13, .16, .20, .25, .30, .40, .50, 1.0001)


class Book:
    """Walk-forward records: jumps, tip wins, who jumps for each team,
    each team's last starters, first baskets and starts per player."""

    def __init__(self):
        self.tip = {}           # pid -> [wins, jumps]
        self.jumper = {}        # team -> {pid: jumps}
        self.last_start = {}    # team -> [pids]
        self.fb = {}            # pid -> first field goals as a starter
        self.starts = {}        # pid -> starts
        self.tip_first = [0, 0]  # [tip winner scored first, games]
        self.recent = {}        # team -> its last RECENT starting fives
        self.last_date = {}     # team -> date of its last game

    def add(self, g):
        st = g.get("starters") or {}
        side = {}
        tip = g.get("tip") or {}
        for t, ps in st.items():
            self.last_start[t] = list(ps)
            self.recent[t] = (self.recent.get(t, []) + [list(ps)])[-RECENT:]
            self.last_date[t] = g.get("date")
            for p in ps:
                self.starts[p] = self.starts.get(p, 0) + 1
                if p in (tip.get("jumpers") or []):
                    side[p] = t
        if len(side) == 2 and tip.get("team"):
            for p, t in side.items():
                r = self.tip.setdefault(p, [0, 0])
                r[0] += 1 if t == tip["team"] else 0
                r[1] += 1
                self.jumper.setdefault(t, {})[p] = self.jumper.get(t, {}).get(p, 0) + 1
        fb = g.get("first_fg") or {}
        if fb.get("pid"):
            self.fb[fb["pid"]] = self.fb.get(fb["pid"], 0) + 1
            if tip.get("team"):
                self.tip_first[0] += 1 if tip["team"] == fb.get("team") else 0
                self.tip_first[1] += 1

    def to_json(self):
        return {k: getattr(self, k) for k in ("tip", "jumper", "last_start", "fb", "starts",
                                              "tip_first", "recent", "last_date")}

    @classmethod
    def from_json(cls, js):
        b = cls()
        for k, v in (js or {}).items():
            setattr(b, k, v)
        return b


RECENT = 5               # starting fives remembered per team
SEASON_GAP = 60          # days: a team's last game before this is last season


def starters(book, team, available, proj_min, day=None):
    """The probable five among the available players: who started most of
    the team's last RECENT games (ties and fill by projected minutes).
    Across the offseason (no game in SEASON_GAP days) the five is the top
    five by projected minutes — last April's lineups were rest games and
    trades. Measured choice (10-21): last game only picked rest-game
    lineups (an April OKC five without its two stars)."""
    from datetime import date as _d
    last = book.last_date.get(team)
    gap = (day and last and (_d.fromisoformat(day) - _d.fromisoformat(last)).days > SEASON_GAP)
    count = {}
    if not gap:
        for five in book.recent.get(team, []):
            for p in five:
                count[p] = count.get(p, 0) + 1
    order = sorted(available, key=lambda x: (-count.get(x, 0), -proj_min.get(x, 0)))
    return order[:5]


def jumper(book, team, five, proj_reb=None):
    js = book.jumper.get(team, {})
    on = [p for p in five if js.get(p)]
    if on:
        return max(on, key=lambda p: js[p])
    known = [p for p in five if (book.tip.get(p) or [0, 0])[1]]
    if known:
        return max(known, key=lambda p: book.tip[p][1])
    return max(five, key=lambda p: (proj_reb or {}).get(p, 0)) if five else None


def tip_rate(book, pid, k):
    w, n = book.tip.get(pid) or (0, 0)
    return (w + k / 2.0) / (n + k)


def p_home_tip(book, jh, ja, k):
    rh, ra = tip_rate(book, jh, k), tip_rate(book, ja, k)
    a, b = rh * (1 - ra), ra * (1 - rh)
    return a / (a + b) if a + b > 0 else 0.5


def shares(book, five, proj_pts, g_pow, lam, k_hist):
    """{pid: share of his team's first baskets among its five}."""
    w = {p: max(proj_pts.get(p, 0.0), 0.1) ** g_pow for p in five}
    tot = sum(w.values()) or 1.0
    use = {p: w[p] / tot for p in five}
    if not lam:
        return use
    fbs = {p: book.fb.get(p, 0) for p in five}
    starts = {p: book.starts.get(p, 0) for p in five}
    # his first-basket rate per start, shrunk toward what his usage says
    rate = {p: (fbs[p] + k_hist * use[p] * 0.5) / (starts[p] + k_hist) for p in five}
    rt = sum(rate.values()) or 1.0
    hist = {p: rate[p] / rt for p in five}
    return {p: (1 - lam) * use[p] + lam * hist[p] for p in five}


def price_game(book, home, away, avail, proj_min, proj_pts, proj_reb, prm, day=None,
               five=None, sure=None):
    """{"tip": P(home wins tip), "team": {home: P, away: P}, "jumpers":
    {team: pid}, "players": {pid: (team, P first FG)}, "five": {team: [...]}}.
    `five` = {team: [5 pids]} CONFIRMED starters (10-25): priced with
    prm["rho_confirmed"] instead of rho — last season every first field
    goal was scored by one of the ten starters. `sure` = the teams whose
    given five is confirmed (default: every team given one)."""
    given = five or {}
    sure = set(t for t in given if len(given[t] or ()) >= 5) if sure is None else set(sure)
    five = {t: (list(given[t])[:5] if len(given.get(t) or ()) >= 5 else
                starters(book, t, avail.get(t, set()), proj_min, day)) for t in (home, away)}
    jh = jumper(book, home, five[home], proj_reb)
    ja = jumper(book, away, five[away], proj_reb)
    tip = p_home_tip(book, jh, ja, prm["k_tip"]) if jh and ja else 0.5
    c = prm["c"]
    ph = tip * c + (1 - tip) * (1 - c)
    team = {home: ph, away: 1 - ph}
    players = {}
    for t in (home, away):
        rho = prm.get("rho_confirmed", 0.99) if t in sure else prm["rho"]
        sh = shares(book, five[t], proj_pts, prm["g"], prm["lam"], prm["k_hist"])
        for p, s in sh.items():
            players[p] = (t, team[t] * rho * s)
    return {"tip": tip, "team": team, "jumpers": {home: jh, away: ja}, "players": players,
            "five": five}


# ----------------------------------------------------------------------
# Fit and test on last season
# ----------------------------------------------------------------------
def _game_inputs(rows_by_game, g):
    avail, pmin, ppts, preb = {}, {}, {}, {}
    for t in (g["home"], g["away"]):
        rs = rows_by_game.get((g["date"], t)) or []
        avail[t] = {p for p, _pr in rs}
        for p, pr in rs:
            pmin[p], ppts[p], preb[p] = pr["min"], pr["mu"]["pts"], pr["mu"]["reb"]
    return avail, pmin, ppts, preb


def _walk(games, rows_by_game, prm, lo, hi, confirmed=False):
    """[(priced game, actual first-FG pid, actual team, tip winner)] for
    games in [lo, hi), each priced before it is added to the book.
    confirmed=True prices each game on its REAL starting fives (what the
    page does once lineups are out) — the five is known before the tip,
    nothing after it is used."""
    book = Book()
    out = []
    for g in games:
        if lo <= g["date"] < hi and g.get("first_fg"):
            avail, pmin, ppts, preb = _game_inputs(rows_by_game, g)
            if all(len(avail.get(t, ())) >= 5 for t in (g["home"], g["away"])):
                five = None
                if confirmed:
                    five = {t: list((g.get("starters") or {}).get(t) or [])
                            for t in (g["home"], g["away"])}
                    if not all(len(v) >= 5 for v in five.values()):
                        book.add(g)
                        continue
                pg = price_game(book, g["home"], g["away"], avail, pmin, ppts, preb, prm,
                                g["date"], five=five)
                pg["key"] = (g["date"], g["home"])
                out.append((pg, g["first_fg"]["pid"], g["first_fg"]["team"],
                            (g.get("tip") or {}).get("team"), g["home"]))
        book.add(g)
    return out


def _loss(priced):
    """Mean log loss of the outcome (the scorer if priced, else 'someone
    else' at the leftover) per game."""
    tot = 0.0
    for pg, pid, _t, _tip, _h in priced:
        p = pg["players"].get(pid, (None, None))[1]
        if p is None:
            p = max(1e-6, 1 - sum(v for _t2, v in pg["players"].values()))
        tot += -math.log(max(p, 1e-6))
    return tot / max(1, len(priced))


def fit(games, rows_by_game, fit_window, test_window):
    games = sorted(games, key=lambda g: g["date"])
    fw, tw = fit_window, test_window
    base = {"k_tip": 15, "c": 0.5, "rho": 0.85, "g": 1.0, "lam": 0.0, "k_hist": 20}
    # C and RHO measured on everything before the test window
    pre = _walk(games, rows_by_game, base, "0000", tw[0])
    both = [(pg, t, tip) for pg, _p, t, tip, _h in pre if tip]
    c = sum(1 for _pg, t, tip in both if t == tip) / max(1, len(both))
    rho = sum(1 for pg, pid, *_r in pre if pid in pg["players"]) / max(1, len(pre))
    # 10-25: how often the first field goal came from one of the REAL ten
    # starters (fit side only), shrunk one game toward "not"
    fit_g = [g for g in games if g["date"] < tw[0] and g.get("first_fg")
             and len(g.get("starters") or {}) == 2]
    rho_c = (sum(1 for g in fit_g if any(g["first_fg"]["pid"] in v
                                         for v in g["starters"].values())) / (len(fit_g) + 1.0)
             if fit_g else 0.95)
    base["rho_confirmed"] = round(rho_c, 4)
    best = None
    for k, gp, lam, kh in itertools.product(K_TIP, G_POW, LAMBDA, K_HIST):
        if not lam and kh != K_HIST[0]:
            continue
        prm = dict(base, k_tip=k, c=c, rho=rho, g=gp, lam=lam, k_hist=kh)
        e = _loss(_walk(games, rows_by_game, prm, fw[0], fw[1]))
        if best is None or e < best[0]:
            best = (e, prm)
    prm = best[1]
    test = _walk(games, rows_by_game, prm, tw[0], "9999")
    naive = dict(prm, g=0.0, lam=0.0, c=0.5, k_tip=1e9)   # every projected starter equal
    test_naive = _walk(games, rows_by_game, naive, tw[0], "9999")

    def per_game(priced):
        out = []
        for pg, pid, *_r in priced:
            p = pg["players"].get(pid, (None, None))[1]
            if p is None:
                p = max(1e-6, 1 - sum(v for _t2, v in pg["players"].values()))
            out.append(-math.log(max(p, 1e-6)))
        return out
    lm, ln = per_game(test), per_game(test_naive)
    calls = [(v, 1 if p == pid else 0) for pg, pid, *_r in test for p, (_t, v) in
             pg["players"].items()]
    team_calls = [(pg["team"][h], 1 if t == h else 0) for pg, _p, t, _tip, h in test]
    tips = [(pg["tip"], 1 if tip == h else 0) for pg, _p, _t, tip, h in test if tip]
    # 10-25: the same unseen games priced on their CONFIRMED fives, paired
    # with the projected-five price of the same game
    conf = _walk(games, rows_by_game, prm, tw[0], "9999", confirmed=True)
    lc = per_game(conf)
    proj_loss = {pg["key"]: v for (pg, *_r), v in zip(test, lm)}
    pairs = [(v, proj_loss[pg["key"]]) for (pg, *_r), v in zip(conf, lc)
             if pg["key"] in proj_loss]
    conf_calls = [(v, 1 if p == pid else 0) for pg, pid, *_r in conf
                  for p, (_t, v) in pg["players"].items()]
    return {"params": prm, "n_test": len(test), "fit_loss": round(best[0], 4),
            "test_loss": round(sum(lm) / max(1, len(lm)), 4),
            "naive_loss": round(sum(ln) / max(1, len(ln)), 4),
            "verdict": mm.paired_verdict(lm, ln),
            "calibration": mm.calibration_bins(calls, EDGES),
            "team": {"brier": mm.score_predictions(team_calls)["brier"],
                     "coin": mm.score_predictions([(0.5, y) for _p, y in team_calls])["brier"],
                     "verdict": mm.paired_verdict([(p - y) ** 2 for p, y in team_calls],
                                                  [(0.5 - y) ** 2 for _p, y in team_calls])},
            "tip": {"brier": mm.score_predictions(tips)["brier"],
                    "verdict": mm.paired_verdict([(p - y) ** 2 for p, y in tips],
                                                 [(0.5 - y) ** 2 for _p, y in tips])},
            "confirmed": {"n": len(conf), "loss": round(sum(lc) / max(1, len(lc)), 4),
                          "rho": prm["rho_confirmed"],
                          "verdict": mm.paired_verdict([a for a, _b in pairs],
                                                       [b for _a, b in pairs]),
                          "calibration": mm.calibration_bins(conf_calls, EDGES)},
            "scorer_in_five": round(sum(1 for pg, pid, *_r in test if pid in pg["players"])
                                    / max(1, len(test)), 3)}


# ----------------------------------------------------------------------
# The page's re-price (10-25): the nightly ships each game's whole pool of
# available players with what pricing needs; the page re-prices on the
# five the user (or ESPN) confirms. Same functions as the test.
# ----------------------------------------------------------------------
def pool_row(book, pid, team, name, pmin, pts, reb):
    return {"pid": pid, "team": team, "name": name, "min": round(pmin or 0, 1),
            "pts": round(pts or 0, 2), "reb": round(reb or 0, 2),
            "fb": book.fb.get(pid, 0), "starts": book.starts.get(pid, 0),
            "tip": list(book.tip.get(pid) or [0, 0]),
            "jumps": (book.jumper.get(team) or {}).get(pid, 0)}


def reprice(game, prm, fives=None, sure=None):
    """One game's first-basket prices from its shipped pool. `game` =
    {"home", "away", "pool": [pool_row], "five": {team: projected five}};
    `fives` = {team: [5 pids]} to use instead (only pids in the pool);
    `sure` = teams whose five is CONFIRMED. Returns the payload shape:
    {"tip_home", "team", "jumpers", "players", "other", "five", "sure"}."""
    home, away = str(game["home"]), str(game["away"])
    pool = {str(r["pid"]): r for r in game.get("pool") or []}
    b = Book()
    for p, r in pool.items():
        b.tip[p] = list(r.get("tip") or [0, 0])
        b.fb[p] = r.get("fb", 0)
        b.starts[p] = r.get("starts", 0)
        if r.get("jumps"):
            b.jumper.setdefault(str(r["team"]), {})[p] = r["jumps"]
    use, mine = {}, set()
    for t in (home, away):
        f = [str(p) for p in ((fives or {}).get(t) or []) if str(p) in pool]
        if len(f) >= 5:
            use[t] = f[:5]
            mine.add(t)
        else:
            use[t] = [str(p) for p in (game.get("five") or {}).get(t) or []]
    sure = {t for t in (sure or ()) if t in mine}      # only a five that was really used
    avail = {t: {p for p, r in pool.items() if str(r["team"]) == t} for t in (home, away)}
    g_ = {p: r.get("min", 0) for p, r in pool.items()}
    pts = {p: r.get("pts", 0) for p, r in pool.items()}
    reb = {p: r.get("reb", 0) for p, r in pool.items()}
    pg = price_game(b, home, away, avail, g_, pts, reb, prm, five=use, sure=sure)
    jump = {}
    for t, p in pg["jumpers"].items():
        w, n = b.tip.get(p) or [0, 0]
        jump[t] = {"pid": p, "name": (pool.get(p) or {}).get("name"), "wins": w, "jumps": n}
    return {"tip_home": pg["tip"], "team": pg["team"], "jumpers": jump,
            "players": sorted([{"pid": p, "name": (pool.get(p) or {}).get("name") or p,
                                "team": t, "p": v, "starts": b.starts.get(p, 0),
                                "fb": b.fb.get(p, 0)} for p, (t, v) in pg["players"].items()],
                              key=lambda x: -x["p"]),
            "other": max(0.0, 1 - sum(v for _t, v in pg["players"].values())),
            "five": pg["five"], "sure": sorted(sure)}


def pregame_starters(summary):
    """{team id: [5 pids]} from an ESPN summary when it marks exactly five
    starters for a team (box score or rosters block) — the lineup is out.
    {} when it does not (most of the day before tip)."""
    out = {}
    blocks = (((summary or {}).get("boxscore") or {}).get("players") or [])
    for b in blocks:
        t = str(((b.get("team") or {}).get("id")) or "")
        ids = []
        for grp in b.get("statistics") or []:
            for ent in grp.get("athletes") or []:
                a = (ent.get("athlete") or {}).get("id")
                if ent.get("starter") and a and str(a) not in ids:
                    ids.append(str(a))
        if t and len(ids) == 5:
            out[t] = ids
    for r in (summary or {}).get("rosters") or []:
        t = str(((r.get("team") or {}).get("id")) or "")
        ids = [str((e.get("athlete") or {}).get("id")) for e in r.get("roster") or []
               if e.get("starter") and (e.get("athlete") or {}).get("id")]
        if t and t not in out and len(ids) == 5:
            out[t] = ids
    return out


def book_from(games):
    b = Book()
    for g in sorted(games or [], key=lambda g: g["date"]):
        b.add(g)
    return b
