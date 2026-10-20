"""
NBA game context (10-20) — engines/nba_context: the opponent (defense +
pace) and teammates out, fitted on last season and kept only where they
beat the plain projection; nba_model's deviance; the wiring into the
nightly, the simulator and the rows the pages read.

Plain script — exits non-zero on failure. Synthetic worlds in the
model's tuple shape [date, team, opp, min, pts, reb, ast, tpm, stl, blk,
tov] (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - nm.deviance replaced by the old (mu - y)^2 / mu
    -> "the fit's score is minimised at the true mean" fails
  - opp_walk adding a day's games BEFORE reading that day's factors
    -> "a game never sees its own day" fails
  - bump ignoring how many games he has already missed
    -> "a long absence adds nothing" fails
  - absences counting a traded player's gap
    -> "a trade is not an absence" fails
  - apply_tonight skipping the opponent factor
    -> "tonight's rows carry the opponent" fails
"""
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nba_context as nc  # noqa: E402
from engines import nba_model as nm  # noqa: E402

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


# --- the score the model is fitted on -----------------------------------------
g0 = random.Random(5)
ys = [pois(g0, 10.0) for _ in range(4000)]
ybar = sum(ys) / len(ys)
grid = [8 + 0.05 * k for k in range(100)]
argmin = min(grid, key=lambda mu: sum(nm.deviance(y, mu) for y in ys))
print(f"     sample mean {ybar:.2f}, deviance minimised at {argmin:.2f}")
check("the fit's score is minimised at the true mean (no reward for projecting high)",
      abs(argmin - ybar) < 0.1)

# --- 1. the opponent, walk-forward ----------------------------------------------
cfg = {st: {"hl": 60, "k": 10, "by_pos": False} for st in nm.BASE}
mean = {"pts": 10.0, "reb": 4.0, "ast": 3.0, "tpm": 1.0}
pr = {"min": 30, "mu": {"pts": 10.0, "reb": 4.0, "ast": 3.0, "tpm": 1.0}}
rows = []
for k in range(30):
    d = (date(2026, 1, 1) + timedelta(days=k)).isoformat()
    for p in range(4):
        # team "SOFT" gives up 30% more points than projected
        rows.append((f"p{p}", [d, "A", "SOFT", 30, 13, 4, 3, 1, 0, 0, 0], pr))
        rows.append((f"q{p}", [d, "B", "HARD", 30, 10, 4, 3, 1, 0, 0, 0], pr))
F, book = nc.opp_walk(rows, {}, cfg, mean)
check("no history yet: the factor is exactly 1", all(abs(v - 1) < 1e-12 for v in F[0].values()))
check("a game never sees its own day (first day's games all read 1)",
      all(abs(F[i]["pts"] - 1) < 1e-12 for i in range(8)))
f_soft = book.factor("SOFT", "F", "2026-01-31")["pts"]
f_hard = book.factor("HARD", "F", "2026-01-31")["pts"]
print(f"     after a month: vs SOFT pts x{f_soft:.3f}, vs HARD x{f_hard:.3f}")
check("a soft defense lifts points, an average one doesn't",
      1.2 < f_soft < 1.3 and abs(f_hard - 1) < 1e-9)
check("shrinkage: fewer games, closer to 1", 1 < F[8]["pts"] < F[-2]["pts"])
check("the book round-trips through JSON (the nightly can store it)",
      abs(nc.OppBook.from_json(book.to_json()).factor("SOFT", "F", "2026-01-31")["pts"]
          - f_soft) < 1e-12)
check("a stat switched off reads 1", nc.OppBook({"pts": None}, mean).factor(
    "SOFT", "F", "2026-01-31")["pts"] == 1.0)

# --- 2. a teammate out --------------------------------------------------------------
ocfg = {st: {"alpha": 0.3, "hl": 2} for st in nm.BASE}
star = {"pts": 25.0, "reb": 5.0, "ast": 6.0, "tpm": 2.0}
present = {"pts": 100.0, "reb": 40.0, "ast": 22.0, "tpm": 10.0}
b0 = nc.bump([(0, 34, star)], present, ocfg)
b8 = nc.bump([(8, 34, star)], present, ocfg)
check("first game out: 30% of his points spread over the rest (+7.5%)",
      abs(b0["pts"] - 1.075) < 1e-12)
check("a long absence adds nothing (teammates' own recent games already carry it)",
      b8["pts"] - 1 < 0.1 * (b0["pts"] - 1))
check("nobody out, or the piece switched off: no bump",
      nc.bump([], present, ocfg)["pts"] == 1.0 and nc.bump([(0, 34, star)], present,
                                                           {"pts": None})["pts"] == 1.0)

sched = {"T1": ["2026-01-0%d" % k for k in range(1, 10)],
         "T2": ["2026-01-0%d" % k for k in range(1, 10)]}
base_g = [[f"2026-01-0{k}", "T1", "X", 34, 25, 5, 6, 2, 0, 0, 0] for k in (1, 2, 3, 4, 5, 6)]
players = {"s": {"pos": "G", "games": base_g + [["2026-01-09", "T1", "X", 34, 25, 5, 6, 2, 0, 0, 0]]},
           "t": {"pos": "G", "games": base_g + [["2026-01-09", "T2", "X", 34, 25, 5, 6, 2, 0, 0, 0]]}}
model = {"hl": 3, "k": 100, "hl_long": 60, "k_long": 300,
         "league": {"G": {"pts": 0.5, "reb": 0.15, "ast": 0.15, "tpm": 0.05}}}
ab = nc.absences(players, sched, model)
check("a rotation player's missed games are counted, with how many he'd already missed",
      [m for m, _mn, _mu in ab.get(("T1", "2026-01-07"), [])] == [0]
      and [m for m, _mn, _mu in ab.get(("T1", "2026-01-08"), [])] == [1])
check("a trade is not an absence (his old team's games after he left)",
      len(ab.get(("T1", "2026-01-07"), [])) == 1 and ("T2", "2026-01-07") not in ab)

# --- 3. the fit, on a world where opponents and absences are real ------------------
def world(seed=11, teams=8, per=9, days=170):
    g = random.Random(seed)
    tough = {f"T{t}": 1.0 + 0.25 * (t % 3 - 1) for t in range(teams)}    # 0.75 / 1.0 / 1.25
    ps = {}
    for t in range(teams):
        for j in range(per):
            ps[f"{t}-{j}"] = {"name": f"P{t}-{j}", "pos": "GFC"[j % 3], "team": f"T{t}",
                              "mins": 36 - 2.5 * j, "rate": g.uniform(.35, .8), "games": []}
    finals = []
    start = date(2025, 10, 21)
    for k in range(days):
        d = (start + timedelta(days=k)).isoformat()
        order = list(range(teams))
        g.shuffle(order)
        for a, h in zip(order[::2], order[1::2]):
            finals.append({"date": d, "home": f"T{h}", "away": f"T{a}", "hs": 110, "as": 105})
            for me, opp in ((a, h), (h, a)):
                roster = [f"{me}-{j}" for j in range(per)]
                out = {x for x in roster[:3] if g.random() < 0.15}      # a starter sits
                lost = sum(ps[x]["mins"] * ps[x]["rate"] for x in out)
                share = sum(ps[x]["mins"] * ps[x]["rate"] for x in roster if x not in out)
                for x in roster:
                    if x in out:
                        continue
                    p = ps[x]
                    m = max(5.0, g.gauss(p["mins"], 3))
                    mu = m * p["rate"] * tough[f"T{opp}"] * (1 + 0.6 * lost / share)
                    p["games"].append([d, f"T{me}", f"T{opp}", round(m, 1), pois(g, mu),
                                       pois(g, m * .15), pois(g, m * .1), pois(g, m * .04),
                                       0, 0, 0])
    return {"players": {k: {kk: v for kk, v in p.items() if kk in ("name", "pos", "team", "games")}
                        for k, p in ps.items()}, "finals": finals}


W = world()
params = nm.fit(W["players"])
mdl = {k: v for k, v in params.items() if k != "fit_rows"}
ctx = nc.fit(W, mdl)
print(f"     synthetic: opponent {ctx['opp']['pts']}, out {ctx['out']['pts']}, "
      f"vs base points {ctx['vs_base']['pts']['verdict']} z={ctx['vs_base']['pts']['z']}")
check("where opponents and absences are real, both are switched on for points",
      ctx["opp"]["pts"] is not None and ctx["out"]["pts"] is not None)
check("where they are not (rebounds here), the opponent stays OFF",
      ctx["opp"]["reb"] is None)
check("the context beats the plain model on unseen games (points)",
      ctx["vs_base"]["pts"]["verdict"] == "beats")
check("sizes and the test are re-made on the adjusted numbers (curves per stat)",
      set(ctx["sizes"]) == {s for s, _l in nm.STATS}
      and all(ctx["test"][s].get("calibration") for s, _l in nm.STATS))

# --- 4. tonight ----------------------------------------------------------------------
mdl["context"] = {k: ctx[k] for k in ("opp", "mean", "out", "vs_base")}
book = nc.book_now(W["players"], mdl, mdl["context"])
tonight = [{"pid": "x", "pos": "G", "mu": {"pts": 20.0, "reb": 5.0, "ast": 4.0, "tpm": 2.0,
                                          "pra": 29.0, "pr": 25.0, "pa": 24.0, "ra": 9.0},
            "why": "X: ~34 min tonight"}]
# T2: 2 % 3 - 1 = +1 -> the soft defense
nc.apply_tonight(tonight, "T2", "SFT", book, [(0, 34, star)], ["Star Guy"], mdl["context"],
                 "2026-04-20")
r = tonight[0]
print(f"     tonight vs the soft team with a star out: pts {r['mu']['pts']:.2f} "
      f"(opp x{r['ctx']['opp']['pts']:.3f}, bump x{r['ctx']['bump']['pts']:.3f}); {r['why']}")
check("tonight's rows carry the opponent and the bump, combos re-summed",
      r["ctx"]["opp"]["pts"] > 1.05 and r["ctx"]["bump"]["pts"] > 1.0
      and abs(r["mu"]["pts"] - 20.0 * r["ctx"]["opp"]["pts"] * r["ctx"]["bump"]["pts"]) < 0.05
      and abs(r["mu"]["pra"] - (r["mu"]["pts"] + r["mu"]["reb"] + r["mu"]["ast"])) < 0.01)
check("the reason is written on the row", "vs SFT" in r["why"] and "Star Guy out" in r["why"])

# --- 5. wiring ---------------------------------------------------------------------
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly fits the context and prices with it (sizes / test replaced)",
      "nc.fit(prior, model)" in pc and 'model["sizes"], model["test"] = ctx["sizes"], ctx["test"]'
      in pc and "nc.apply_tonight(" in pc and "nc.book_now(" in pc)
sim = (ROOT / "app" / "engines" / "nba_sim.py").read_text(encoding="utf-8")
check("the simulator's links and test read the same numbers", "nc.context_rows(" in sim)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NBA context checks passed")
