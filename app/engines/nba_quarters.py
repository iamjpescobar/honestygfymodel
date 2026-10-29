"""
NBA first-quarter player points (10-21) — "Brunson 1Q over 7.5".

THE NUMBER: his projected game points x his first-quarter SHARE (a
straight line on his projected minutes — a starter plays most of the
first quarter, a bench man little of it), blended W with his own average
over his last N_HIST first quarters:
    mu_q1 = (1 - W) x mu_pts x (C0 + C1 x minutes / 36) + W x his own
C0 / C1 / W / N_HIST fitted on the fit window by Poisson deviance; the
spread a negative binomial sized there (method of moments). MEASURED
(10-21): the share alone did NOT beat his own hit rate on unseen games
(z 0.33); with 40% of his own last 20 first quarters it does (z 2.47) —
a first quarter is its own habit (scripted openings, who gets the first
touches).

THE TEST (the props test's shape): the unseen window — last season's
final 45 days plus this season so far — each player at HIS line (his
last-10 first quarters, set at the half point) against his own last-20
hit rate over it; calibration bins -> the delivered chance and the
guard's support on every page.

The first-quarter points are play-by-play (engines/nba_pbp "qpts"): a
player who played in a game whose play-by-play we have, and is not in
it, scored 0 in the first quarter. A game with no play-by-play is
missing, never zero.

Pure — no streamlit, no requests.
"""
import itertools

from engines import model_math as mm
from engines import nba_model as nm

STAT = "q1pts"
LABEL = "1st-quarter points"
C0 = (0.14, 0.18, 0.22, 0.26)
C1 = (0.0, 0.05, 0.10)
W = (0.0, 0.2, 0.4, 0.6)
N_HIST = (10, 20)


def q1_map(pbp_games):
    """({(pid, date): q1 points}, {(team, date)} with play-by-play)."""
    qm, cov = {}, set()
    for g in pbp_games or []:
        d = g.get("date")
        if not d or not g.get("lines"):
            continue
        for t in (g.get("home"), g.get("away")):
            cov.add((str(t), d))
        for pid, q in (g.get("qpts") or {}).items():
            qm[(str(pid), d)] = q[0]
    return qm, cov


def q1_of(pid, game, qm, cov):
    """His first-quarter points in this game tuple, or None (no play-by-play)."""
    if (str(game[1]), game[0]) not in cov or not nm.val(game, "min"):
        return None
    return qm.get((str(pid), game[0]), 0)


def share(minutes, prm):
    return max(0.02, prm["c0"] + prm["c1"] * (minutes or 0) / 36.0)


def mu(pr, prm, hist=None):
    """pr: a projection {"min", "mu"}; hist: his first quarters, oldest first."""
    base = pr["mu"]["pts"] * share(pr["min"], prm)
    h = [v for v in (hist or []) if v is not None][-prm.get("n_hist", 20):]
    if not h or not prm.get("w"):
        return base
    return (1 - prm["w"]) * base + prm["w"] * sum(h) / len(h)


def _rows(rows, qm, cov):
    out = []
    for pid, g, pr, hist in rows:
        y = q1_of(pid, g, qm, cov)
        if y is None:
            continue
        hv = [q1_of(pid, h, qm, cov) for h in hist]
        hv = [v for v in hv if v is not None]
        out.append((pid, g, pr, y, hv))
    return out


def fit(rows, pbp_games, fit_window, test_window):
    """{"params": {"c0", "c1"}, "size", "test": {n, model_brier,
    baseline_brier, verdict, calibration}} or None."""
    qm, cov = q1_map(pbp_games)
    R = _rows(rows, qm, cov)
    fw, tw = fit_window, test_window
    F = [r for r in R if fw[0] <= r[1][0] < fw[1] and len(r[4]) >= nm.MIN_PRIOR_GAMES]
    T = [r for r in R if r[1][0] >= tw[0]]
    if len(F) < 500 or len(T) < 500:
        return None
    best = None
    for c0, c1, w, nh in itertools.product(C0, C1, W, N_HIST):
        if not w and nh != N_HIST[0]:
            continue
        prm = {"c0": c0, "c1": c1, "w": w, "n_hist": nh}
        e = sum(nm.deviance(r[3], mu(r[2], prm, r[4])) for r in F) / len(F)
        if best is None or e < best[0]:
            best = (e, prm)
    prm = best[1]
    num = den = 0.0
    for r in F:
        m = mu(r[2], prm, r[4])
        num += m * m
        den += (r[3] - m) ** 2 - m
    size = round(num / den, 3) if den > 0 else None
    preds, base = [], []
    for _pid, _g, pr, y, hv in T:
        if len(hv) < nm.MIN_PRIOR_GAMES:
            continue
        line = nm.half_line(hv[-10:])
        p = nm.over(mu(pr, prm, hv), size, line)
        if p is None:
            continue
        last = hv[-20:]
        preds.append((p, 1 if y > line else 0))
        base.append((sum(1 for v in last if v > line) / len(last), 1 if y > line else 0))
    m, b = mm.score_predictions(preds), mm.score_predictions(base)
    return {"params": prm, "size": size, "fit_dev": round(best[0], 4),
            "test": {"n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
                     "verdict": mm.paired_verdict([(q - y) ** 2 for q, y in preds],
                                                  [(q - y) ** 2 for q, y in base]),
                     "calibration": mm.calibration_bins(preds)}}


# ----------------------------------------------------------------------
# The Live page, tested (10-21; every stat 10-29): at the end of the 1st,
# 2nd and 3rd quarter of every test-window game with play-by-play, what
# would the Live page have said a player's chance was of going over HIS
# line (his last-10 average at the half point) — and what happened? Paired
# against a naive live read: his own average before the game, cut to the
# time left, plus what he has (Poisson). Points from "qpts"; rebounds,
# assists and threes from "qstats" — only in games whose play-by-play
# counts matched the box score for every player ("qstats_ok"); the combos
# from their parts when every part is there.
# ----------------------------------------------------------------------
CHECKPOINTS = ((1, 0.75), (2, 0.5), (3, 0.25))
LIVE_STATS = ("pts", "reb", "ast", "tpm", "pra", "pr", "pa", "ra")


def _quarters(g, pid, stat):
    """[q1, q2, q3, q4] for one player's stat in one parsed game, or None
    when the play-by-play can't vouch for it."""
    if stat == "pts":
        return (g.get("qpts") or {}).get(pid, [0, 0, 0, 0]) if g.get("lines") else None
    if stat in nm.COMBOS:
        parts = [_quarters(g, pid, s_) for s_ in nm.COMBOS[stat]]
        if any(x is None for x in parts):
            return None
        return [sum(x[k] for x in parts) for k in range(4)]
    if stat not in (g.get("qstats_ok") or []):
        return None
    return (((g.get("qstats") or {}).get(pid) or {}).get(stat) or [0, 0, 0, 0, 0])[:4]


def live_check(rows, pbp_games, sizes, test_lo):
    """{stat: {n, model_brier, naive_brier, verdict, calibration,
    by_checkpoint}} for every stat with 500+ quarter-end calls, or None."""
    from engines import live_props as lp
    byg = {}
    for g in pbp_games or []:
        for t in (g.get("home"), g.get("away")):
            byg[(str(t), g.get("date"))] = g
    acc = {st: ([], [], {}) for st in LIVE_STATS}
    for pid, g, pr, hist in rows:
        if g[0] < test_lo:
            continue
        pg = byg.get((str(g[1]), g[0]))
        if not pg:
            continue
        for st in LIVE_STATS:
            q = _quarters(pg, str(pid), st)
            y = nm.val(g, st)
            if q is None or y is None:
                continue
            hv = [nm.val(h, st) for h in hist if nm.val(h, "min")]
            hv = [v for v in hv if v is not None]
            if len(hv) < nm.MIN_PRIOR_GAMES:
                continue
            line = nm.half_line(hv[-10:])
            avg = sum(hv) / len(hv)
            mu_ = pr.get("mu") or {}
            mu_st = mu_.get(st)
            if mu_st is None and st in nm.COMBOS:
                parts = [mu_.get(s_) for s_ in nm.COMBOS[st]]
                mu_st = None if None in parts else sum(parts)
            if mu_st is None:
                continue
            model, naive, by = acc[st]
            for k, f in CHECKPOINTS:
                have = sum(q[:k])
                ch, nd = lp.nba_chance(mu_st, (sizes or {}).get(st), line, have, f)
                if ch is None or nd <= 0:
                    continue                   # already over: nothing left to price
                nv_ = lp.over_chance(mm.poisson_pmf(avg * f, max(30, int(avg * f * 4) + 15)), nd)
                hit = 1 if y > line else 0
                model.append((ch, hit))
                naive.append((nv_, hit))
                by.setdefault(k, []).append((ch, hit))
    out = {}
    for st, (model, naive, by) in acc.items():
        if len(model) < 500:
            continue
        a, b = mm.score_predictions(model), mm.score_predictions(naive)
        out[st] = {"n": a["n"], "model_brier": a["brier"], "naive_brier": b["brier"],
                   "verdict": mm.paired_verdict([(p - y) ** 2 for p, y in model],
                                                [(p - y) ** 2 for p, y in naive]),
                   "calibration": mm.calibration_bins(model),
                   "by_checkpoint": {f"after Q{k}": mm.score_predictions(v)
                                     for k, v in sorted(by.items())}}
    return out or None
