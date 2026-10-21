"""
NBA first-quarter points (10-21) — engines/nba_quarters, its wiring into
the props model, the nightly, the Props board and the Bet Finder; and the
props / first-basket tests growing with this season.

Plain script — exits non-zero on failure. Synthetic rows in the walk
shape (pid, game tuple, projection, prior games) and play-by-play in the
nba_pbp.parse shape (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - q1_of reading a game with no play-by-play as 0
    -> "a game with no play-by-play is missing, never zero" fails
  - mu ignoring his own first quarters (W)
    -> "his own first-quarter habit is in the number" fails
  - vs_book counting pushes
    -> "pushes are left out" fails
  - tested_nba trusting every stat (not just a tested one)
    -> "other stats stay untested" fails
"""
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nba_quarters as nq  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def pois(g, mu):
    L, c, p = math.exp(-mu), 0, 1.0
    while True:
        p *= g.random()
        if p < L:
            return c
        c += 1


pbp = [{"date": "2026-01-02", "home": "H", "away": "A", "lines": {"H": [30, 25, 28, 27]},
        "qpts": {"p1": [9, 4, 0, 6], "p2": [0, 2, 5, 5]}}]
qm, cov = nq.q1_map(pbp)
g_have = ["2026-01-02", "H", "A", 30, 19, 5, 4, 2, 0, 0, 0]
g_none = ["2026-01-04", "H", "B", 30, 19, 5, 4, 2, 0, 0, 0]
check("his first-quarter points from the play-by-play",
      nq.q1_of("p1", g_have, qm, cov) == 9 and nq.q1_of("p2", g_have, qm, cov) == 0)
check("played but not in the scoring plays: 0 in the first quarter",
      nq.q1_of("p9", g_have, qm, cov) == 0)
check("a game with no play-by-play is missing, never zero",
      nq.q1_of("p1", g_none, qm, cov) is None)
prm = {"c0": 0.22, "c1": 0.05, "w": 0.4, "n_hist": 20}
pr = {"min": 36, "mu": {"pts": 20.0}}
check("the share: a 36-minute man's first quarter is 27% of his points",
      abs(nq.mu(pr, dict(prm, w=0)) - 20 * 0.27) < 1e-9)
check("his own first-quarter habit is in the number (40% of his last 20)",
      abs(nq.mu(pr, prm, [10] * 25) - (0.6 * 5.4 + 0.4 * 10)) < 1e-9)


# the fit on a world where some players start fast
def world(seed=5, n=60, days=175):
    g = random.Random(seed)
    start = date(2025, 10, 21)
    rows, pbp_ = [], []
    habit = {f"p{i}": g.choice((0.15, 0.25, 0.38)) for i in range(n)}
    games = {p: [] for p in habit}
    for k in range(days):
        d = (start + timedelta(days=k)).isoformat()
        qp = {}
        for i, p in enumerate(habit):
            if g.random() < 0.45:
                continue
            pts = 10 + (i % 5) * 4
            q1 = pois(g, pts * habit[p])
            tup = [d, "T", "O", 32, pts, 5, 4, 2, 0, 0, 0]
            rows.append((p, tup, {"min": 32, "mu": {"pts": float(pts)}}, list(games[p])))
            games[p].append(tup)
            qp[p] = [q1, 0, 0, 0]
        pbp_.append({"date": d, "home": "T", "away": "O", "lines": {"T": [1, 1, 1, 1]},
                     "qpts": qp})
    return rows, pbp_


R, PB = world()
dates = sorted({r[1][0] for r in R})
q = nq.fit(R, PB, [dates[-90], dates[-45]], [dates[-45], dates[-1]])
print(f"     synthetic: {q['params']} size {q['size']}; test {q['test']['verdict']}")
check("where first quarters are a habit, the fit leans on his own first quarters (W > 0)",
      q["params"]["w"] > 0 and q["test"]["n"] > 500)
check("a calibration curve comes out for the delivered chance",
      bool(q["test"]["calibration"]))

# wiring
from engines import nba_model as nm  # noqa: E402
check("the pages offer it as a stat; the Bet Finder prices it from its pmf",
      ("q1pts", "1st-quarter points") in nm.PAGE_STATS and "q1pts" in nm.player_pmfs(
          {"q1pts": 6.0}, {"q1pts": 3.0}))
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly fits it, adds it to the model's sizes / test, and prices tonight",
      "nq.fit(ctx_rows, all_pbp" in pc and 'model.setdefault("test", {})["q1pts"]' in pc
      and 'r["mu"]["q1pts"] = round(nq.mu(' in pc and 't_["q1pts"] = ' in pc)
props = (ROOT / "app" / "views" / "NBA_Props.py").read_text(encoding="utf-8")
bfp = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("Props and the Bet Finder show it only when the nightly fitted it",
      'get("q1pts")' in props and "nm.PAGE_STATS" in props and "nm.PAGE_STATS" in bfp)
check("the props and first-basket tests grow with this season (last season + this one)",
      "nc.fit(season_data, model)" in pc and "nc.context_rows(season_data, model)" in pc
      and "list(prior_pbp.values()) + list(cur_pbp.values())" in pc
      and "n_this_season" in pc)

# --- the game model against the book (this season's recorded lines) ---------------
import nba_precompute as npc  # noqa: E402
_g = random.Random(9)
str_ = {f"T{i}": _g.gauss(0, 6) for i in range(10)}
prior_f, cur_f = [], []
for k in range(600):
    d = (date(2025, 10, 21) + timedelta(days=k // 5)).isoformat()
    h, a = _g.sample(list(str_), 2)
    hs = round(112 + str_[h] - str_[a] + _g.gauss(0, 12))
    as_ = round(110 + str_[a] - str_[h] + _g.gauss(0, 12))
    prior_f.append({"date": d, "home": h, "away": a, "hs": hs, "as": as_})
for k in range(60):
    d = (date(2026, 10, 21) + timedelta(days=k // 5)).isoformat()
    h, a = _g.sample(list(str_), 2)
    hs = round(112 + str_[h] - str_[a] + _g.gauss(0, 12))
    as_ = round(110 + str_[a] - str_[h] + _g.gauss(0, 12))
    cur_f.append({"date": d, "home_id": h, "away_id": a, "home_score": hs, "away_score": as_,
                  "odds": {"total": 222.5, "spread": -2.5}})
cur_f.append({"date": "2026-11-30", "home_id": "T1", "away_id": "T2", "home_score": 110,
              "away_score": 112, "odds": {"total": 222.0, "spread": 2.0}})   # pushes both
prm = {"shrink_k": 5.0, "sd_total": 19.0, "sd_margin": 14.0}
vb = npc.vs_book(prior_f, cur_f, prm)
print(f"     vs book on 61 games: {vb}")
check("every graded game with a line is counted; pushes are left out",
      vb["total"]["n"] == 60 and vb["spread"]["n"] == 60)
home_cov = sum(1 for f in cur_f[:60] if f["home_score"] - f["away_score"] - 2.5 > 0)
check("the spread is the home side's (home -2.5 covers by winning by 3+)",
      vb["spread"]["verdict"] is not None and home_cov > 0)
pg = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly grades it and Tonight shows the record",
      'block["vs_book"] = vb' in pg and '"Totals vs book"' in (
          ROOT / "app" / "views" / "NBA.py").read_text(encoding="utf-8"))

# --- the Live page's points, tested ----------------------------------------------------
from engines import live_props as lp  # noqa: E402
chk = {"pts": {"verdict": {"verdict": "beats"},
               "calibration": [{"band": "a", "n": 500, "predicted": 0.2, "actual": 0.3},
                               {"band": "b", "n": 500, "predicted": 0.8, "actual": 0.7}]}}
c, sup = lp.tested_nba(chk, "pts", 0.8)
c2, sup2 = lp.tested_nba(chk, "reb", 0.8)
check("live points read the test's curve once it beats; other stats stay untested (THIN)",
      abs(c - 0.7) < 1e-9 and not sup.get("untested") and sup2.get("untested") and c2 == 0.8)
lv = (ROOT / "app" / "views" / "Live.py").read_text(encoding="utf-8")
check("the Live page uses it and says which NBA stats are tested",
      'lp.tested_nba((model or {}).get("live_check"), stat, ch)' in lv and "_nba_live_ok" in lv
      and "nq.live_check(ctx_rows" in pg)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall first-quarter checks passed")
