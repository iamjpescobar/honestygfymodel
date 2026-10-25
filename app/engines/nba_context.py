"""
NBA game context (10-20) — the two things a player's own history can't
know about TONIGHT, each measured on last season before it moves a
number:

1. THE OPPONENT (defense and pace together). For every team, what
   players have done against it relative to their own projections, by
   stat (optionally by position group), recency-weighted by days
   (half-life OPP_HL) and shrunk toward 1 by K player-games:
       factor = (sum w*actual + K*m) / (sum w*projected + K*m)
   m = the league's average projection for that stat. Walk-forward: a
   game only ever sees games before its date.

2. A TEAMMATE OUT. A rotation player (15+ projected minutes) who misses
   a game leaves his projected production behind; a share ALPHA of it
   goes to the teammates who play, in proportion to their own:
       bump = 1 + ALPHA * sum(w * his mu) / sum(teammates' mu)
   w = 0.5 ** (games he has already missed / OUT_HL): after a few games
   out the teammates' own recent numbers already carry it (half-life 2
   games in the model), so counting it again would double it.

3. THE TEAM'S MINUTES ADD UP (10-22). A team plays 240 minutes; when
   its rotation's projected minutes (every player projected 10+ who
   plays) add to more or less, each one is scaled
       f = (VOL_T / their sum) ^ VOL_BETA
   VOL_T and VOL_BETA fitted on the fit window. A new team with three
   starters who each played 34 for their old teams cannot give all three
   34 again. MEASURED 10-22 on 2025-26: the rotation's projections
   summed to 237 on average, sd 30 — and scaling them beat leaving them
   (deviance, fit and test windows). Ships only when it beats on the
   unseen window (vol_test).

THE FIT: per stat, each piece chosen on the fit window by Poisson
deviance, and switched OFF when it does not beat the plain projection
there. THE TEST: the props test (his own last-10 line at the half point,
vs his own hit rate) on the unseen window, AND paired against the plain
model on the same lines (vs_base) — the context ships only where it
earned it. The model's sizes, test and calibration curves are re-made on
the adjusted numbers, so every page's delivered chance is the new one.

Pure — no streamlit, no requests.
"""
import itertools
from datetime import date

from engines import model_math as mm
from engines import nba_model as nm

OPP_HL = (15, 30, 60, 120)        # days
OPP_K = (15, 40, 100, 300)        # player-games of "average"
OPP_BY_POS = (False, True)
OUT_ALPHA = (0.0, 0.1, 0.2, 0.3, 0.45, 0.6)
OUT_HL = (0.5, 1, 2, 4)           # games already missed
ROT_MIN = 15.0
MAX_MISSED = 25
VOL_T = (210.0, 215.0, 220.0, 225.0, 230.0, 235.0, 240.0)
VOL_BETA = (0.1, 0.2, 0.3, 0.4, 0.5)
VOL_CLIP = (0.8, 1.25)


def _day(s):
    return date.fromisoformat(s).toordinal()


# ----------------------------------------------------------------------
# 1. The opponent
# ----------------------------------------------------------------------
class OppBook:
    """Running opponent sums; cfg {stat: {"hl", "k", "by_pos"} | None}."""

    def __init__(self, cfg, mean_proj):
        self.cfg, self.mean = cfg or {}, mean_proj or {}
        self.acc = {}

    def _key(self, opp, st, grp):
        c = self.cfg.get(st)
        return (str(opp), st, grp if (c and c.get("by_pos")) else "")

    def factor(self, opp, grp, day):
        out = {}
        for st in nm.BASE:
            c = self.cfg.get(st)
            if not c:
                out[st] = 1.0
                continue
            a = self.acc.get(self._key(opp, st, grp))
            A = P = 0.0
            if a:
                w = 0.5 ** ((_day(day) - a[2]) / c["hl"])
                A, P = a[0] * w, a[1] * w
            m = self.mean.get(st) or 1.0
            out[st] = (A + c["k"] * m) / (P + c["k"] * m)
        return out

    def add(self, opp, grp, day, g, mu):
        dn = _day(day)
        for st in nm.BASE:
            c = self.cfg.get(st)
            y = nm.val(g, st)
            if not c or y is None:
                continue
            k = self._key(opp, st, grp)
            a = self.acc.get(k)
            if a:
                w = 0.5 ** ((dn - a[2]) / c["hl"])
                a[0], a[1], a[2] = a[0] * w + y, a[1] * w + mu[st], dn
            else:
                self.acc[k] = [y, mu[st], dn]

    def to_json(self):
        return {"cfg": self.cfg, "mean": self.mean,
                "acc": [[list(k), v] for k, v in self.acc.items()]}

    @classmethod
    def from_json(cls, js):
        b = cls(js.get("cfg"), js.get("mean"))
        b.acc = {tuple(k): v for k, v in js.get("acc") or []}
        return b


def opp_walk(rows, groups, cfg, mean_proj):
    """(factors aligned with rows, the book after the last day). rows are
    (pid, game, projection, ...) in DATE order; a day's games see only
    earlier days."""
    book = OppBook(cfg, mean_proj)
    out = [None] * len(rows)
    i, n = 0, len(rows)
    while i < n:
        day = rows[i][1][0]
        j = i
        while j < n and rows[j][1][0] == day:
            j += 1
        for k in range(i, j):
            pid, g = rows[k][0], rows[k][1]
            out[k] = book.factor(g[2], groups.get(pid, "F"), day)
        for k in range(i, j):
            pid, g, pr = rows[k][0], rows[k][1], rows[k][2]
            book.add(g[2], groups.get(pid, "F"), day, g, pr["mu"])
        i = j
    return out, book


# ----------------------------------------------------------------------
# 2. A teammate out
# ----------------------------------------------------------------------
def schedules(finals):
    """{team_id: [dates]} from finals in either shape (home/away or
    home_id/away_id)."""
    s = {}
    for f in finals or []:
        for k in ("home", "away"):
            t = f.get(k) if f.get(k) is not None else f.get(k + "_id")
            if t is not None:
                s.setdefault(str(t), set()).add(f["date"])
    return {t: sorted(v) for t, v in s.items()}


def absences(players, sched, model):
    """{(team, date): [(games already missed, his minutes, his mu)]} — every
    rotation player's missed team games, with his projection as of his
    last game (no later game is ever seen)."""
    out = {}
    lr = model.get("league") or {}
    for pid, p in (players or {}).items():
        games = sorted(p.get("games") or [], key=lambda g: g[0])
        run = nm.Running(model["hl"], model.get("hl_long"))
        lrg = lr.get(nm.group(p.get("pos"))) or {}
        for i, g in enumerate(games):
            run.add(g)
            if run.n < nm.MIN_PRIOR_GAMES or not nm.val(g, "min"):
                continue
            nxt = games[i + 1] if i + 1 < len(games) else None
            team = str(g[1])
            if nxt and str(nxt[1]) != team:
                continue                      # traded: the gap is not "out"
            pr = run.project(model["k"], lrg, model.get("k_long"), model.get("down_pull") or 0.0)
            if not pr or pr["min"] < ROT_MIN:
                continue
            end = nxt[0] if nxt else "9999"
            missed = [d for d in sched.get(team, []) if g[0] < d < end]
            for m, d in enumerate(missed[:MAX_MISSED]):
                out.setdefault((team, d), []).append((m, pr["min"], pr["mu"]))
    return out


def bump(outs, present_sum, cfg):
    """{stat: multiplier} for the teammates who play; cfg {stat: {"alpha",
    "hl"} | None}."""
    b = {}
    for st in nm.BASE:
        c = (cfg or {}).get(st)
        s_in = present_sum.get(st) or 0.0
        if not c or not c.get("alpha") or not outs or s_in <= 0:
            b[st] = 1.0
            continue
        s_out = sum((0.5 ** (m / c["hl"])) * mu.get(st, 0.0) for m, _mn, mu in outs)
        b[st] = 1.0 + c["alpha"] * s_out / s_in
    return b


def adjust(pr, opp_f, bmp, vf=1.0):
    """A projection with the context applied (combos re-summed)."""
    mu = {st: pr["mu"][st] * (opp_f or {}).get(st, 1.0) * (bmp or {}).get(st, 1.0) * vf
          for st in nm.BASE}
    for c, parts in nm.COMBOS.items():
        mu[c] = sum(mu[x] for x in parts)
    return dict(pr, mu=mu)


def rotation_minutes(players, model):
    """{(team, date): the summed projected minutes of every player who
    played that game and was projected MIN_PROJ_MIN+ (one game on file is
    enough — tonight's pages project anyone with a game). Walk-forward:
    each projection is from the games before."""
    out = {}
    lr = model.get("league") or {}
    for p in (players or {}).values():
        run = nm.Running(model["hl"], model.get("hl_long"))
        lrg = lr.get(nm.group(p.get("pos"))) or {}
        for g in sorted(p.get("games") or [], key=lambda x: x[0]):
            if nm.val(g, "min") and run.n >= 1:
                pr = run.project(model["k"], lrg, model.get("k_long"),
                                 model.get("down_pull") or 0.0)
                if pr and pr["min"] >= nm.MIN_PROJ_MIN:
                    key = (str(g[1]), g[0])
                    out[key] = out.get(key, 0.0) + pr["min"]
            run.add(g)
    return out


def vol_factor(total, cfg):
    """The team-minutes scale for a rotation whose projections add to
    `total`; 1 when the piece is off."""
    if not cfg or not total:
        return 1.0
    f = (cfg["t"] / total) ** cfg["beta"]
    return min(VOL_CLIP[1], max(VOL_CLIP[0], f))


def team_sums(rows):
    """{(team, date): {stat: sum of projections of the players who played}}."""
    s = {}
    for r in rows:
        g, pr = r[1], r[2]
        t = s.setdefault((str(g[1]), g[0]), {st: 0.0 for st in nm.BASE})
        for st in nm.BASE:
            t[st] += pr["mu"][st]
    return s


# ----------------------------------------------------------------------
# Fit and test on last season
# ----------------------------------------------------------------------
def _dev(rows, idx, st, mus):
    tot = n = 0
    for i in idx:
        y = nm.val(rows[i][1], st)
        if y is None:
            continue
        tot += nm.deviance(y, mus[i][st])
        n += 1
    return tot / max(1, n)


def adjusted_rows(rows, groups, sched_outs, ctx, vols=None):
    """rows (pid, game, pr, hist) -> the same rows with the context in pr.
    vols: rotation_minutes(), read when the team-minutes piece is on."""
    F, _book = opp_walk(rows, groups, ctx.get("opp") or {}, ctx.get("mean") or {})
    sums = team_sums(rows)
    out = []
    for k, r in enumerate(rows):
        g = r[1]
        key = (str(g[1]), g[0])
        b = bump(sched_outs.get(key), sums.get(key) or {}, ctx.get("out") or {})
        vf = vol_factor((vols or {}).get(key), ctx.get("vol"))
        out.append((r[0], g, adjust(r[2], F[k], b, vf)) + tuple(r[3:]))
    return out


def fit(prior, model):
    """{"opp", "mean", "out", "sizes", "test", "vs_base", "n_fit"} or None.
    prior = {"players", "finals"} — last season, or last season + this one
    (the nightly passes both, 10-21): the fit window is last season's, the
    TEST window runs from last season's final 45 days through every game
    of this season so far, so the record and the calibration curves grow
    every night."""
    players = prior.get("players") or {}
    if not model or not model.get("hl") or not players:
        return None
    rows = nm.walk(players, model["hl"], model["k"], model.get("league") or {}, "0000", "9999",
                   model.get("hl_long"), model.get("k_long"), model.get("down_pull") or 0.0)
    rows.sort(key=lambda r: r[1][0])
    groups = {pid: nm.group(p.get("pos")) for pid, p in players.items()}
    fw, tw = model["fit_window"], model["test_window"]
    fit_idx = [i for i, r in enumerate(rows) if fw[0] <= r[1][0] < fw[1]]
    test_idx = [i for i, r in enumerate(rows) if r[1][0] >= tw[0]]
    if len(fit_idx) < 500 or len(test_idx) < 500:
        return None
    before = [r for r in rows if r[1][0] < tw[0]]
    mean = {st: sum(r[2]["mu"][st] for r in before) / len(before) for st in nm.BASE}
    base = [r[2]["mu"] for r in rows]

    # 1. the opponent, per stat, OFF unless it beats the plain projection
    best = {st: (None, _dev(rows, fit_idx, st, base)) for st in nm.BASE}
    for hl, k, bp in itertools.product(OPP_HL, OPP_K, OPP_BY_POS):
        c = {"hl": hl, "k": k, "by_pos": bp}
        F, _b = opp_walk(rows, groups, {st: c for st in nm.BASE}, mean)
        mus = [{st: base[i][st] * F[i][st] for st in nm.BASE} for i in range(len(rows))]
        for st in nm.BASE:
            e = _dev(rows, fit_idx, st, mus)
            if e < best[st][1] - 1e-9:
                best[st] = (c, e)
    opp = {st: best[st][0] for st in nm.BASE}
    F, _b = opp_walk(rows, groups, opp, mean)
    mus_opp = [{st: base[i][st] * F[i][st] for st in nm.BASE} for i in range(len(rows))]

    # 2. a teammate out, on top of the opponent
    outs = absences(players, schedules(prior.get("finals")), model)
    sums = team_sums(rows)
    keyed = [(str(r[1][1]), r[1][0]) for r in rows]
    bestb = {st: (None, _dev(rows, fit_idx, st, mus_opp)) for st in nm.BASE}
    for a, hl in itertools.product(OUT_ALPHA[1:], OUT_HL):
        c = {"alpha": a, "hl": hl}
        cfg = {st: c for st in nm.BASE}
        mus = []
        for i in range(len(rows)):
            b = bump(outs.get(keyed[i]), sums.get(keyed[i]) or {}, cfg)
            mus.append({st: mus_opp[i][st] * b[st] for st in nm.BASE})
        for st in nm.BASE:
            e = _dev(rows, fit_idx, st, mus)
            if e < bestb[st][1] - 1e-9:
                bestb[st] = (c, e)
    out_cfg = {st: bestb[st][0] for st in nm.BASE}

    # 3. the team's minutes add up, on top of both
    ctx = {"opp": opp, "mean": mean, "out": out_cfg, "vol": None}
    pre = adjusted_rows(rows, groups, outs, ctx)
    vols = rotation_minutes(players, model)
    keys = [(str(r[1][1]), r[1][0]) for r in rows]

    def vdev(cfg, idx):
        tot = n = 0
        for i in idx:
            f = vol_factor(vols.get(keys[i]), cfg)
            for st in nm.BASE:
                y = nm.val(rows[i][1], st)
                if y is not None:
                    tot += nm.deviance(y, pre[i][2]["mu"][st] * f)
                    n += 1
        return tot / max(1, n)
    bestv = (None, vdev(None, fit_idx))
    for t, be in itertools.product(VOL_T, VOL_BETA):
        c = {"t": t, "beta": be}
        e = vdev(c, fit_idx)
        if e < bestv[1] - 1e-9:
            bestv = (c, e)
    vol_test = None
    if bestv[0]:
        a_, b_ = [], []
        for i in test_idx:
            f = vol_factor(vols.get(keys[i]), bestv[0])
            da = db = 0.0
            for st in nm.BASE:
                y = nm.val(rows[i][1], st)
                if y is not None:
                    da += nm.deviance(y, pre[i][2]["mu"][st] * f)
                    db += nm.deviance(y, pre[i][2]["mu"][st])
            a_.append(da)
            b_.append(db)
        vol_test = mm.paired_verdict(a_, b_)
        if vol_test.get("verdict") == "beats":
            ctx["vol"] = bestv[0]
    adj = adjusted_rows(rows, groups, outs, ctx, vols)
    fit_rows = [adj[i] for i in fit_idx]
    test_rows = [adj[i] for i in test_idx]
    sizes = {st: nm.nb_size(fit_rows, st) for st, _l in nm.STATS}
    test = nm.test(test_rows, sizes)
    ladder = nm.test_ladder(test_rows, sizes)
    vs_base = {}
    for st, _l in nm.STATS:
        new, old = [], []
        for i in test_idx:
            r, a = rows[i], adj[i]
            hv = [nm.val(h, st) for h in r[3] if nm.val(h, "min")]
            hv = [v for v in hv if v is not None]
            y = nm.val(r[1], st)
            if y is None or len(hv) < nm.MIN_PRIOR_GAMES:
                continue
            line = nm.half_line(hv[-10:])
            po = nm.over(r[2]["mu"][st], (model.get("sizes") or {}).get(st), line)
            pn = nm.over(a[2]["mu"][st], sizes.get(st), line)
            if po is None or pn is None:
                continue
            yy = 1 if y > line else 0
            old.append((po - yy) ** 2)
            new.append((pn - yy) ** 2)
        vs_base[st] = mm.paired_verdict(new, old)
    last_prior = max((f["date"] for f in prior.get("finals") or [] if f["date"] <= "2026-06-30"),
                     default="")
    n_this = sum(1 for i in test_idx if rows[i][1][0] > last_prior)
    # 10-25 (Site vs DraftKings, first night graded: the site's over chance
    # ran ~11 points under DraftKings' on 448 of 637 NBA lines and overs
    # hit 58%): does the model under-project THIS season? Mean projected
    # vs actual on unseen player-games, this season vs last season's test
    # window, all and 20+ projected minutes. Diagnostic only.
    bias = {}
    for lab, keep in (("this_season", lambda i: rows[i][1][0] > last_prior),
                      ("last_season", lambda i: rows[i][1][0] <= last_prior)):
        for mlab, mmin in (("all", 0), ("20min", 20)):
            for st, _l in nm.STATS:
                pr_ = ac_ = 0.0
                n_ = 0
                for i in test_idx:
                    if not keep(i):
                        continue
                    mu_ = (adj[i][2].get("mu") or {}).get(st)
                    y = nm.val(rows[i][1], st)
                    if mu_ is None or y is None or (adj[i][2].get("min") or 0) < mmin:
                        continue
                    pr_ += mu_
                    ac_ += y
                    n_ += 1
                if n_:
                    bias.setdefault(lab, {}).setdefault(mlab, {})[st] = {
                        "n": n_, "pred": round(pr_ / n_, 2), "actual": round(ac_ / n_, 2),
                        "ratio": round(ac_ / pr_, 3) if pr_ else None}
    return {"n_this_season": n_this, "bias": bias,
            "opp": opp, "mean": {k: round(v, 4) for k, v in mean.items()}, "out": out_cfg,
            "vol": ctx["vol"], "vol_tried": bestv[0], "vol_test": vol_test,
            "sizes": sizes, "test": test, "ladder": ladder, "vs_base": vs_base,
            "n_fit": len(fit_idx),
            "n_test": len(test_idx), "minutes": nm.minutes_check(test_rows)}


def context_rows(prior, model):
    """Last season's walk-forward rows, date order, with the model's
    context applied (or plain when it has none) — what the simulator's
    links and test read, so they see the numbers the pages print."""
    players = prior.get("players") or {}
    rows = nm.walk(players, model["hl"], model["k"], model.get("league") or {}, "0000", "9999",
                   model.get("hl_long"), model.get("k_long"), model.get("down_pull") or 0.0)
    rows.sort(key=lambda r: r[1][0])
    ctx = model.get("context")
    if not ctx:
        return rows
    groups = {pid: nm.group(p.get("pos")) for pid, p in players.items()}
    outs = absences(players, schedules(prior.get("finals")), model)
    vols = rotation_minutes(players, model) if ctx.get("vol") else None
    return adjusted_rows(rows, groups, outs, ctx, vols)


# ----------------------------------------------------------------------
# Tonight
# ----------------------------------------------------------------------
def book_now(pool, model, ctx):
    """The opponent book after every game in the pool (last season + this
    one) — what tonight's factors read."""
    rows = nm.walk(pool, model["hl"], model["k"], model.get("league") or {}, "0000", "9999",
                   model.get("hl_long"), model.get("k_long"), model.get("down_pull") or 0.0)
    rows.sort(key=lambda r: r[1][0])
    groups = {pid: nm.group(p.get("pos")) for pid, p in (pool or {}).items()}
    _F, book = opp_walk(rows, groups, ctx.get("opp") or {}, ctx.get("mean") or {})
    return book


def outs_now(pool, team_id, out_pids, team_dates, model, today):
    """[(games already missed, his minutes, his mu)] for tonight's Out
    players on this team: 'already missed' = this team's games since his
    last one with them (this season's schedule)."""
    out = []
    for pid in out_pids or []:
        p = (pool or {}).get(pid) or {}
        games = sorted(p.get("games") or [], key=lambda g: g[0])
        if not games:
            continue
        last = games[-1]
        if str(last[1]) != str(team_id):
            continue
        pr = nm.project_now(games, model, p.get("pos"), today=today)
        if not pr or pr["min"] < ROT_MIN:
            continue
        m = sum(1 for d in team_dates or [] if last[0] < d < today)
        if m >= MAX_MISSED:
            continue
        out.append((m, pr["min"], pr["mu"]))
    return out


def apply_tonight(rows, opp_id, opp_abbr, book, outs, out_names, ctx, day):
    """One team's rows for tonight with the context applied in place:
    each row's mu, plus row["ctx"] = {"opp": {stat: f}, "bump": {stat: b}}
    and the reason appended to row["why"]."""
    present = {st: sum(r["mu"][st] for r in rows) for st in nm.BASE}
    b = bump(outs, present, (ctx or {}).get("out") or {})
    tot = sum(r["min"] for r in rows if (r.get("min") or 0) >= nm.MIN_PROJ_MIN)
    vf = vol_factor(tot, (ctx or {}).get("vol"))
    for r in rows:
        f = book.factor(opp_id, nm.group(r.get("pos")), day) if book else \
            {st: 1.0 for st in nm.BASE}
        r["mu"] = {k: round(v, 3) for k, v in adjust({"mu": r["mu"]}, f, b, vf)["mu"].items()}
        r["ctx"] = {"opp": {k: round(v, 3) for k, v in f.items()},
                    "bump": {k: round(v, 3) for k, v in b.items()},
                    "vol": round(vf, 3), "team_min": round(tot)}
        w = why(f, b, opp_abbr, out_names, vf, tot)
        if w:
            r["why"] = (r.get("why") + " · " if r.get("why") else "") + w
    return rows


def why(opp_f, bmp, opp_abbr, out_names, vf=1.0, team_min=None):
    """One plain sentence for a player's row, or ''."""
    bits = []
    if abs(vf - 1) >= 0.02 and team_min:
        bits.append(f"team minutes: his rotation's projections add to {team_min:.0f} min — "
                    f"scaled {100 * (vf - 1):+.0f}% so the team's 240 add up")
    big = {st: f for st, f in (opp_f or {}).items() if abs(f - 1) >= 0.03}
    lab = {"pts": "pts", "reb": "reb", "ast": "ast", "tpm": "3s"}
    if big:
        bits.append(f"vs {opp_abbr}: " + ", ".join(f"{lab[s]} {100 * (f - 1):+.0f}%"
                                                  for s, f in big.items()))
    up = {st: b for st, b in (bmp or {}).items() if b - 1 >= 0.02}
    if up and out_names:
        bits.append(f"with {', '.join(out_names[:2])} out: " + ", ".join(
            f"{lab[s]} {100 * (b - 1):+.0f}%" for s, b in up.items()))
    return " · ".join(bits)
