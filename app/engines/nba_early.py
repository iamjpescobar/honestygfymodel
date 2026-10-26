"""
NBA first three minutes (10-25) — does a starter SCORE in the game's first
3:00 (period 1, 9:00 or more left)? Izzy bets it. Two targets:
  "pts"  any point (a free throw counts)
  "fg"   a made field goal
Data: engines/nba_pbp.parse "early" {pid: [points, made FGs]} — last
season's 1,235 games (the prior play-by-play, re-run 10-25) plus this
season's from the nightly.

MEASURED 10-25 before building (last season, walk-forward, test from
2026-01-20, 5,920 starter-games): a starter scored in the first 3 minutes
46.6% of the time. The model below beat the league's starter rate (Brier
0.2419 vs 0.2487, z 7.7) AND each player's own shrunk record (0.2435,
z 2.7), calibrated from 30% to 65%. His team's and the opponent's early
pace added nothing (fitted weight 0) — not in the number.

THE NUMBER, one starter
-----------------------
  share   his projected points / his five's projected points (a starter
          with no projection gets his teammates' lowest — the first-basket
          lesson of 10-25)
  lam     C x (5 x share) ^ G           (scoring chances in 3:00)
  usage   1 - exp(-lam)
  own     (his early scores + K x league rate) / (his starts + K)
  P       (1 - LAM) x usage + LAM x own
C, G, LAM, K fitted by Brier on the fit window; TESTED on the unseen
window, paired, against the league rate and his own record. Calibration
bins -> the delivered chance on the page. Only for STARTERS: a bench
player almost never plays the first three minutes.

Pure — no streamlit, no requests.
"""
import itertools
import math

from engines import model_math as mm

TARGETS = (("pts", 0, "Scores in the first 3 minutes"),
           ("fg", 1, "Makes a field goal in the first 3 minutes"))
C_GRID = (0.35, 0.45, 0.55, 0.65, 0.75, 0.9)
G_GRID = (0.6, 0.8, 1.0, 1.2)
LAM_GRID = (0.0, 0.25, 0.5, 0.75)
K_GRID = (10, 30, 60)
EDGES = (0, .2, .3, .4, .5, .6, .7, 1.0001)


class Book:
    """Walk-forward: starts, early hits per target, the league's rate."""

    def __init__(self):
        self.starts = {}
        self.hits = {t: {} for t, _i, _l in TARGETS}
        self.lg = {t: [0, 0] for t, _i, _l in TARGETS}

    def add(self, g):
        early = g.get("early") or {}
        for ps in (g.get("starters") or {}).values():
            if len(ps) != 5:
                continue
            for p in ps:
                self.starts[p] = self.starts.get(p, 0) + 1
                for t, i, _l in TARGETS:
                    y = 1 if (early.get(p) or [0, 0])[i] > 0 else 0
                    self.hits[t][p] = self.hits[t].get(p, 0) + y
                    self.lg[t][0] += y
                    self.lg[t][1] += 1

    def rate(self, t):
        a, n = self.lg[t]
        return a / n if n else 0.47

    def to_json(self):
        return {"starts": self.starts, "hits": self.hits, "lg": self.lg}

    @classmethod
    def from_json(cls, js):
        b = cls()
        for k, v in (js or {}).items():
            setattr(b, k, v)
        return b


def book_from(games):
    b = Book()
    for g in sorted(games or [], key=lambda g: g["date"]):
        b.add(g)
    return b


def price(five, proj_pts, prm, starts, hits, base):
    """{pid: P} for one team's five. starts / hits: {pid: n}; base: the
    league's starter rate for this target."""
    known = [proj_pts[p] for p in five if proj_pts.get(p) is not None]
    floor = min(known) if known else 8.0
    pts = {p: max(proj_pts[p] if proj_pts.get(p) is not None else floor, 0.1) for p in five}
    tot = sum(pts.values()) or 1.0
    out = {}
    for p in five:
        lam = prm["c"] * (5.0 * pts[p] / tot) ** prm["g"]
        usage = 1.0 - math.exp(-lam)
        own = (hits.get(p, 0) + prm["k"] * base) / (starts.get(p, 0) + prm["k"])
        out[p] = (1 - prm["lam"]) * usage + prm["lam"] * own
    return out


def _walk(games, rows_by_game, prm, target, lo, hi):
    """[(model P, league P, own P, y)] for every real starter in games in
    [lo, hi), each priced before the game is added to the book."""
    i = dict((t, j) for t, j, _l in TARGETS)[target]
    book = Book()
    out = []
    for g in games:
        st = g.get("starters") or {}
        if lo <= g["date"] < hi and len(st) == 2 and all(len(v) == 5 for v in st.values()):
            base = book.rate(target)
            early = g.get("early") or {}
            for t, five in st.items():
                rs = dict(rows_by_game.get((g["date"], t)) or [])
                pts = {p: rs[p]["mu"]["pts"] for p in five if p in rs}
                pm = price(five, pts, prm, book.starts, book.hits[target], base)
                for p in five:
                    y = 1 if (early.get(p) or [0, 0])[i] > 0 else 0
                    own = (book.hits[target].get(p, 0) + 20 * base) / (book.starts.get(p, 0) + 20)
                    out.append((pm[p], base, own, y))
        book.add(g)
    return out


def _brier(rows, k=0):
    return sum((r[k] - r[3]) ** 2 for r in rows) / max(1, len(rows))


def fit(games, rows_by_game, fit_window, test_window):
    """{target: {"params", "n_test", "brier", "league_brier", "own_brier",
    "vs_league", "vs_own", "verdict", "calibration", "base"}}. verdict =
    "beats" only when it beats BOTH baselines."""
    games = sorted(games, key=lambda g: g["date"])
    out = {}
    for t, _i, _l in TARGETS:
        best = None
        for c, gp, lam, k in itertools.product(C_GRID, G_GRID, LAM_GRID, K_GRID):
            if not lam and k != K_GRID[0]:
                continue
            prm = {"c": c, "g": gp, "lam": lam, "k": k}
            e = _brier(_walk(games, rows_by_game, prm, t, fit_window[0], fit_window[1]))
            if best is None or e < best[0]:
                best = (e, prm)
        prm = best[1]
        test = _walk(games, rows_by_game, prm, t, test_window[0], "9999")
        sq = [(r[0] - r[3]) ** 2 for r in test]
        vl = mm.paired_verdict(sq, [(r[1] - r[3]) ** 2 for r in test])
        vo = mm.paired_verdict(sq, [(r[2] - r[3]) ** 2 for r in test])
        both = "beats" if vl.get("verdict") == vo.get("verdict") == "beats" else (
            "thin" if (vl.get("z") or 0) > 0 and (vo.get("z") or 0) > 0 else "fails")
        out[t] = {"params": prm, "n_test": len(test), "brier": round(_brier(test), 4),
                  "league_brier": round(_brier(test, 1), 4),
                  "own_brier": round(_brier(test, 2), 4), "vs_league": vl, "vs_own": vo,
                  "verdict": {"verdict": both, "z": min(vl.get("z") or 0, vo.get("z") or 0)},
                  "calibration": mm.calibration_bins([(r[0], r[3]) for r in test], EDGES),
                  "base": round(sum(r[3] for r in test) / max(1, len(test)), 4)}
    return out


def game_block(book, pids):
    """What the page needs per pool player: [starts, pts hits, fg hits],
    and the league rates."""
    return {"rec": {p: [book.starts.get(p, 0)] + [book.hits[t].get(p, 0) for t, _i, _l in TARGETS]
                    for p in pids},
            "base": {t: round(book.rate(t), 4) for t, _i, _l in TARGETS}}


def page_price(block, fit_block, five, proj_pts, target):
    """{pid: raw P} for one team's five on the page."""
    rec = (block or {}).get("rec") or {}
    j = [t for t, _i, _l in TARGETS].index(target) + 1
    starts = {p: (rec.get(p) or [0, 0, 0])[0] for p in five}
    hits = {p: (rec.get(p) or [0, 0, 0])[j] for p in five}
    return price(five, proj_pts, fit_block[target]["params"], starts, hits,
                 ((block or {}).get("base") or {}).get(target, 0.47))
