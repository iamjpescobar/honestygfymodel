"""
NBA player props (10-20) — minutes x per-minute rates, a negative
binomial around it, tested walk-forward on last season before any call
on the site may carry more than THIN.

THE NUMBER
----------
For each player, before each game:

  minutes  = his recency-weighted minutes (half-life HL games)
  rate     = his recent production per minute (half-life HL games),
             shrunk by K minutes toward HIS OWN long-run rate (half-life
             HL_LONG games), which is itself shrunk by K_LONG minutes
             toward his position group's league rate (10-20 (4)):
               own  = (sum_long w*stat + K_LONG * league) / (sum_long w*min + K_LONG)
               rate = (sum w*stat + K * own) / (sum w*min + K)
             One level (straight to the league rate) pulled every star
             toward an average player: top-2 scorers on a team went over
             their line 49% of the time against 45% delivered.
  mean     = minutes x rate, per stat (points, rebounds, assists, 3PM);
             combos (PRA, P+R, P+A, R+A) are the sums of their parts.
  spread   = negative binomial, size r per stat, MEASURED on the
             fitting window's residuals (method of moments) — minutes
             swings (blowouts, foul trouble) live in that spread.

Last season carries into this one at CARRY (the running sums are cut to
that share at the offseason gap), so a player's October number is
mostly last year and his own games take over as they come.

HL, K, HL_LONG and K_LONG are FITTED (grid) on the 45 days before the
test window, by Poisson deviance of the means; never on the test window.

THE TEST (rule 1)
-----------------
The last TEST_DAYS days of last season, walk-forward: for every
player-game, the line is his own last-10 average set at the half point
(how books hang a line on a player), the model's over chance against it,
against his OWN hit rate over that line in his last 20 games. Paired on
squared error (mm.paired_verdict); calibration bins per stat ("@stat"
curves, the same shape the NFL props use, so the site's guard reads
them unchanged).

NOT IN THE NUMBER (said on the pages): tonight's opponent and pace, a
teammate out (the Next Man Up page shows what happened before when he
sat), rest / back-to-backs, the coach's rotation tonight.

Pure — no streamlit, no requests.
"""
import math

from engines import model_math as mm

# Player game tuple (prior_season.json / the nightly's logs):
#   [date, team_id, opp_id, min, pts, reb, ast, tpm, stl, blk, tov]
IDX = {"min": 3, "pts": 4, "reb": 5, "ast": 6, "tpm": 7, "stl": 8, "blk": 9, "tov": 10}
BASE = ("pts", "reb", "ast", "tpm")
COMBOS = {"pra": ("pts", "reb", "ast"), "pr": ("pts", "reb"), "pa": ("pts", "ast"),
          "ra": ("reb", "ast")}
STATS = (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
         ("tpm", "3-pointers made"), ("pra", "Pts + Reb + Ast"), ("pr", "Pts + Reb"),
         ("pa", "Pts + Ast"), ("ra", "Reb + Ast"))
LABEL = dict(STATS)
FIT_HL = (1, 2, 3, 5, 10)
FIT_K = (100, 300, 600, 1200)
FIT_HL_LONG = (30, 60, 120)
FIT_K_LONG = (100, 300, 1000)
CARRY = 0.5
SEASON_GAP_DAYS = 60
TEST_DAYS = 45
FIT_DAYS = 45
MIN_PRIOR_GAMES = 5
MIN_PROJ_MIN = 10.0


def group(pos):
    p = str(pos or "").upper()
    if p in ("C", "FC"):
        return "C"
    if p in ("PG", "SG", "G", "GF"):
        return "G"
    return "F"


def val(g, stat):
    if stat in COMBOS:
        parts = [val(g, s) for s in COMBOS[stat]]
        return None if any(x is None for x in parts) else sum(parts)
    v = g[IDX[stat]] if len(g) > IDX[stat] else None
    return None if v is None else float(v)


def _days(a, b):
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def league_rates(players, before=None):
    """{group: {stat: per-minute rate}} over every game (before a date)."""
    tot = {}
    for p in (players or {}).values():
        g_ = group(p.get("pos"))
        t = tot.setdefault(g_, {"min": 0.0, **{s: 0.0 for s in BASE}})
        for g in p.get("games") or []:
            if before and g[0] >= before:
                continue
            m = val(g, "min")
            if not m:
                continue
            if any(val(g, s) is None for s in BASE):
                continue
            t["min"] += m
            for s in BASE:
                t[s] += val(g, s)
    return {g_: {s: (t[s] / t["min"] if t["min"] else 0.0) for s in BASE}
            for g_, t in tot.items()}


class Running:
    """Recency-weighted sums for one player, game by game."""

    def __init__(self, hl, hl_long=None):
        self.long = Running(hl_long) if hl_long else None
        self.decay = 0.5 ** (1.0 / hl)
        self.w = 0.0
        self.m = 0.0
        self.s = {k: 0.0 for k in BASE}
        self.n = 0
        self.last = None

    def add(self, g):
        if self.last and _days(self.last, g[0]) > SEASON_GAP_DAYS:
            self.offseason()
        if self.long is not None:
            self.long.add(g)
        m = val(g, "min")
        self.last = g[0]
        if not m or any(val(g, k) is None for k in BASE):
            return
        self.w = self.w * self.decay + 1.0
        self.m = self.m * self.decay + m
        for k in BASE:
            self.s[k] = self.s[k] * self.decay + val(g, k)
        self.n += 1

    def offseason(self):
        """The cut at a season gap (and before a projection made across one).
        ACROSS THE OFFSEASON the recent window restarts from his long-run
        averages, at CARRY weight: last season's final weeks (stars rested,
        tanking, a playoff push) are not October — with a 2-game half-life
        the old cut projected a star off his last two April games. NOT
        MEASURED: last season's file has no offseason in it; this season's
        games will test it. Without a long tracker: the plain CARRY cut."""
        if self.long is not None and self.long.w > 0:
            scale = self.w * CARRY / self.long.w
            self.m = self.long.m * scale
            for k in BASE:
                self.s[k] = self.long.s[k] * scale
        else:
            self.m *= CARRY
            for k in BASE:
                self.s[k] *= CARRY
        self.w *= CARRY

    def rate(self, st, k_min, toward):
        return (self.s[st] + k_min * toward) / (self.m + k_min) if (self.m + k_min) else 0.0

    def project(self, k_min, lr, k_long=None):
        """k_long given (and a long tracker): two levels — recent toward
        his own long-run rate, that toward the league; else one level."""
        if self.w <= 0 or self.n == 0:
            return None
        minutes = self.m / self.w
        mu = {}
        for st in BASE:
            toward = lr.get(st, 0.0)
            if self.long is not None and k_long is not None:
                toward = self.long.rate(st, k_long, toward)
            mu[st] = minutes * self.rate(st, k_min, toward)
        for c, parts in COMBOS.items():
            mu[c] = sum(mu[p] for p in parts)
        return {"min": minutes, "mu": mu}


def walk(players, hl, k_min, lr, lo, hi, hl_long=None, k_long=None):
    """[(pid, game, projection, prior_games)] for every game in [lo, hi)
    with at least MIN_PRIOR_GAMES before it. hl_long / k_long: the
    two-level shrink (None = one level, straight to the league)."""
    out = []
    for pid, p in (players or {}).items():
        games = sorted(p.get("games") or [], key=lambda g: g[0])
        run = Running(hl, hl_long)
        lrg = lr.get(group(p.get("pos"))) or {}
        for i, g in enumerate(games):
            if lo <= g[0] < hi and run.n >= MIN_PRIOR_GAMES:
                pr = run.project(k_min, lrg, k_long)
                if pr and pr["min"] >= MIN_PROJ_MIN and val(g, "min"):
                    out.append((pid, g, pr, games[:i]))
            run.add(g)
    return out


def deviance(y, mu):
    """Poisson deviance of a mean against a count — a proper score for a
    mean. (The old (mu - y)^2 / mu grew its denominator with mu, so it
    rewarded projecting HIGH: measured 10-20, it called a redistribution
    that made every Brier worse a 10% improvement.)"""
    mu = max(float(mu), 1e-6)
    return 2.0 * ((y * math.log(y / mu) if y > 0 else 0.0) - (y - mu))


def _sse(rows):
    tot = 0.0
    for _pid, g, pr, _h in rows:
        for st in BASE:
            y = val(g, st)
            if y is not None:
                tot += deviance(y, pr["mu"][st])
    return tot / max(1, len(rows))


def nb_size(rows, stat):
    """Method-of-moments NB size from (mean, actual) pairs; None = Poisson."""
    num = den = 0.0
    for _pid, g, pr, _h in rows:
        y = val(g, stat)
        if y is None:
            continue
        mu = pr["mu"][stat]
        num += mu * mu
        den += (y - mu) ** 2 - mu
    if den <= 0:
        return None
    return round(num / den, 3)


def pmf(mean, size):
    if mean is None or mean <= 0:
        return None
    top = max(30, int(mean * 3 + 20))
    return mm.nb_pmf(mean, size, top)


def over(mean, size, line):
    p = pmf(mean, size)
    return mm.prob_at_least(p, int(math.floor(line)) + 1) if p else None


def half_line(vals):
    """A book-like line: the average set at the half point."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return math.floor(sum(vals) / len(vals)) + 0.5


def fit(players):
    """{"hl", "k", "sizes", "league", "fit_window", "test_window", "test"}
    from last season's player games, or {"note"} when too short."""
    dates = sorted({g[0] for p in (players or {}).values() for g in p.get("games") or []})
    if len(dates) < TEST_DAYS + FIT_DAYS + 30:
        return {"note": "season too short to fit / test"}
    test_lo = dates[-TEST_DAYS]
    fit_lo = dates[-(TEST_DAYS + FIT_DAYS)]
    lr = league_rates(players, before=test_lo)
    best = None
    for hl in FIT_HL:
        for k in FIT_K:
            for hl2 in FIT_HL_LONG:
                for k2 in FIT_K_LONG:
                    rows = walk(players, hl, k, lr, fit_lo, test_lo, hl2, k2)
                    e = _sse(rows)
                    if best is None or e < best[0]:
                        best = (e, hl, k, hl2, k2, rows)
    _e, hl, k, hl2, k2, fit_rows = best
    sizes = {st: nb_size(fit_rows, st) for st, _l in STATS}
    test_rows = walk(players, hl, k, lr, test_lo, "9999", hl2, k2)
    return {"hl": hl, "k": k, "hl_long": hl2, "k_long": k2, "sizes": sizes, "league": lr,
            "carry": CARRY,
            "fit_window": [fit_lo, test_lo], "test_window": [test_lo, dates[-1]],
            "fit_rows": len(fit_rows), "test": test(test_rows, sizes),
            "ladder": test_ladder(test_rows, sizes),
            "minutes": minutes_check(test_rows)}


def test(rows, sizes):
    """{stat: {n, model_brier, baseline_brier, verdict, calibration}}."""
    out = {}
    for st, _l in STATS:
        preds, base = [], []
        for _pid, g, pr, hist in rows:
            y = val(g, st)
            hv = [val(h, st) for h in hist if val(h, "min")]
            hv = [v for v in hv if v is not None]
            if y is None or len(hv) < MIN_PRIOR_GAMES:
                continue
            line = half_line(hv[-10:])
            p = over(pr["mu"][st], sizes.get(st), line)
            if p is None or line is None:
                continue
            last = hv[-20:]
            preds.append((p, 1 if y > line else 0))
            base.append((sum(1 for v in last if v > line) / len(last), 1 if y > line else 0))
        m, b = mm.score_predictions(preds), mm.score_predictions(base)
        out[st] = {"n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
                   "verdict": mm.paired_verdict([(q - y) ** 2 for q, y in preds],
                                                [(q - y) ** 2 for q, y in base]),
                   "calibration": mm.calibration_bins(preds)}
    return out


# THE LADDER (10-20): the alternate lines a long shot lives on — "30+
# points", "10+ rebounds", "5+ threes". The main test grades each player
# at HIS line (chances near 50%); a +800 call is a 10% call, a range that
# test never reaches. So every test-window player-game is also graded at
# every rung, with finer bins at the low end, against his own last-20
# hit rate at that rung.
LADDER = {"pts": (10, 15, 20, 25, 30, 35, 40, 45, 50),
          "reb": (4, 6, 8, 10, 12, 14, 16),
          "ast": (2, 4, 6, 8, 10, 12, 14),
          "tpm": (1, 2, 3, 4, 5, 6, 7),
          "pra": (20, 25, 30, 35, 40, 45, 50, 55, 60)}
LADDER_LABEL = {"pts": "points", "reb": "rebounds", "ast": "assists", "tpm": "threes",
                "pra": "pts + reb + ast"}
LADDER_EDGES = (0, .02, .04, .06, .08, .10, .13, .16, .20, .25, .30, .40, .50, .60, .70, .80,
                .90, 1.0001)


def test_ladder(rows, sizes):
    """{stat: {n, model_brier, baseline_brier, verdict, calibration}} —
    every rung of LADDER on every test row (its pmf computed once)."""
    out = {}
    for st, rungs in LADDER.items():
        preds, base = [], []
        for _pid, g, pr, hist in rows:
            y = val(g, st)
            last = [val(h, st) for h in hist if val(h, "min")]
            last = [v for v in last if v is not None][-20:]
            if y is None or len(last) < MIN_PRIOR_GAMES:
                continue
            pm = pmf(pr["mu"][st], sizes.get(st))
            if not pm:
                continue
            for n in rungs:
                p = mm.prob_at_least(pm, n)
                hit = 1 if y >= n else 0
                preds.append((p, hit))
                base.append((sum(1 for v in last if v >= n) / len(last), hit))
        m, b = mm.score_predictions(preds), mm.score_predictions(base)
        out[st] = {"n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
                   "verdict": mm.paired_verdict([(q - y) ** 2 for q, y in preds],
                                                [(q - y) ** 2 for q, y in base]),
                   "calibration": mm.calibration_bins(preds, LADDER_EDGES)}
    return out


def minutes_check(rows):
    """Mean absolute minutes error: the weighted projection vs his plain
    average so far."""
    a = b = n = 0
    for _pid, g, pr, hist in rows:
        m = val(g, "min")
        hm = [val(h, "min") for h in hist if val(h, "min")]
        if not m or not hm:
            continue
        a += abs(pr["min"] - m)
        b += abs(sum(hm) / len(hm) - m)
        n += 1
    return {"n": n, "model_mae": round(a / n, 2) if n else None,
            "season_avg_mae": round(b / n, 2) if n else None}


def project_now(games, params, pos, today=None):
    """Tonight's projection for one player from every game he has played
    (last season + this one, date order). `today` past the offseason gap
    since his last game -> the offseason cut first (opening night is not
    his last two April games)."""
    run = Running(params["hl"], params.get("hl_long"))
    for g in sorted(games or [], key=lambda x: x[0]):
        run.add(g)
    if run.n < 1:
        return None
    if today and run.last and _days(run.last, str(today)) > SEASON_GAP_DAYS:
        run.offseason()
        if run.long is not None:
            run.long.offseason()
    lr = (params.get("league") or {}).get(group(pos)) or {}
    return run.project(params["k"], lr, params.get("k_long"))


def calibration(params):
    """{"@stat": bins} — what model_view.curve_for reads."""
    return {f"@{k}": v["calibration"] for k, v in ((params or {}).get("test") or {}).items()
            if isinstance(v, dict) and v.get("calibration")}


def player_pmfs(mu, sizes):
    """{stat: pmf} for one projection — what the Bet Finder prices."""
    out = {}
    for st, _l in STATS:
        p = pmf((mu or {}).get(st), (sizes or {}).get(st))
        if p:
            out[st] = p
    return out


# ----------------------------------------------------------------------
# Next Man Up — what a teammate did when the man out tonight sat before
# ----------------------------------------------------------------------
NMU_MIN_WITHOUT = 3
NMU_STATS = ("min", "pts", "reb", "ast", "pra")


def next_man_up(players, team_id, out_pid, since=None):
    """[{pid, name, with: {stat: avg}, without: {...}, delta: {...},
    n_with, n_without}] for every teammate, biggest points bump first.
    Games are this TEAM's games (team id on the line), so a traded
    player's old team never counts; `since` limits to recent seasons."""
    team_id = str(team_id)
    dates = set()
    out_dates = set()
    for pid, p in (players or {}).items():
        for g in p.get("games") or []:
            if str(g[1]) != team_id or (since and g[0] < since) or not val(g, "min"):
                continue
            dates.add(g[0])
            if str(pid) == str(out_pid):
                out_dates.add(g[0])
    if not out_dates:
        return []
    rows = []
    for pid, p in (players or {}).items():
        if str(pid) == str(out_pid):
            continue
        w, wo = [], []
        for g in p.get("games") or []:
            if str(g[1]) != team_id or (since and g[0] < since) or not val(g, "min"):
                continue
            (w if g[0] in out_dates else wo).append(g)
        if len(wo) < NMU_MIN_WITHOUT or not w:
            continue

        def avg(gs, st):
            v = [val(g, st) for g in gs if val(g, st) is not None]
            return round(sum(v) / len(v), 1) if v else None
        a = {st: avg(w, st) for st in NMU_STATS}
        b = {st: avg(wo, st) for st in NMU_STATS}
        rows.append({"pid": str(pid), "name": p.get("name"), "with": a, "without": b,
                     "delta": {st: (None if a[st] is None or b[st] is None
                                    else round(b[st] - a[st], 1)) for st in NMU_STATS},
                     "n_with": len(w), "n_without": len(wo)})
    rows.sort(key=lambda r: -(r["delta"].get("pts") or 0))
    return rows
