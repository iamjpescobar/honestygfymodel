"""
NBA First Basket (10-21) — engines/nba_first, its fit on play-by-play, the
nightly wiring and the page.

Plain script — exits non-zero on failure. Synthetic games in the
nba_pbp.parse shape (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - _walk adding a game to the book BEFORE pricing it
    -> "a game never sees itself" fails
  - starters ignoring the offseason gap (last April's rest-game five)
    -> "across the offseason the five is the projected-minutes five" fails
  - the page pricing the first-team bet as measured while its test is thin
    -> "an untested first-team call is capped at THIN" fails
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nba_first as nf  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


# --- the pieces ---------------------------------------------------------------
b = nf.Book()
b.add({"date": "2026-03-01", "starters": {"H": ["c1", "h2", "h3", "h4", "h5"],
                                          "A": ["c2", "a2", "a3", "a4", "a5"]},
       "tip": {"jumpers": ["c1", "c2"], "team": "H"},
       "first_fg": {"pid": "h2", "team": "H"}})
check("the book records the jump, the starts, the first basket",
      b.tip["c1"] == [1, 1] and b.tip["c2"] == [0, 1] and b.fb["h2"] == 1
      and b.starts["c1"] == 1 and b.jumper["H"]["c1"] == 1 and b.tip_first == [1, 1])
check("tip rate shrinks toward 50%: one win of one jump at K=2 is 2/3",
      abs(nf.tip_rate(b, "c1", 2) - 2 / 3) < 1e-12 and abs(nf.tip_rate(b, "zz", 2) - 0.5) < 1e-12)
avail = {"H": {"c1", "h2", "h3", "h4", "h5", "h6"}, "A": {"c2", "a2", "a3", "a4", "a5"}}
pmin = {p: 30 for s in avail.values() for p in s}
pmin["h6"] = 36                                   # the bench guy projects big minutes
ppts = {p: 10.0 for s in avail.values() for p in s}
ppts["h2"] = 30.0
prm = {"k_tip": 2, "c": 0.62, "rho": 0.86, "g": 1.0, "lam": 0.0, "k_hist": 20}
pg = nf.price_game(b, "H", "A", avail, pmin, ppts, {}, prm, "2026-03-03")
check("in season the five is who has been starting (not the big-minutes bench guy)",
      sorted(pg["five"]["H"]) == ["c1", "h2", "h3", "h4", "h5"])
check("the jumpers are the ones who jumped for each team",
      pg["jumpers"] == {"H": "c1", "A": "c2"})
check("team chances add to 1; the tip winner's edge carries C",
      abs(sum(pg["team"].values()) - 1) < 1e-12 and pg["team"]["H"] > 0.5)
check("players add to RHO (the rest is 'someone else'); the big scorer leads his team",
      abs(sum(v for _t, v in pg["players"].values()) - 0.86) < 1e-9
      and max((v, p) for p, (t, v) in pg["players"].items() if t == "H")[1] == "h2")
pg_oct = nf.price_game(b, "H", "A", avail, pmin, ppts, {}, prm, "2026-10-21")
check("across the offseason the five is the projected-minutes five (last spring's is stale)",
      "h6" in pg_oct["five"]["H"])


# --- the fit, on a world where tips and scorers are real -------------------------
def world(seed=3, teams=6, days=170):
    g = random.Random(seed)
    tipper = {f"T{t}": 0.3 + 0.08 * t for t in range(teams)}         # jumpers differ
    games, rows = [], {}
    start = date(2025, 10, 21)
    for k in range(days):
        d = (start + timedelta(days=k)).isoformat()
        order = list(range(teams))
        g.shuffle(order)
        for a, h in zip(order[::2], order[1::2]):
            H, A = f"T{h}", f"T{a}"
            st = {t: [f"{t}-{i}" for i in range(5)] for t in (H, A)}
            ph = tipper[H] * (1 - tipper[A])
            ph = ph / (ph + tipper[A] * (1 - tipper[H]))
            tipw = H if g.random() < ph else A
            first_t = tipw if g.random() < 0.63 else (A if tipw == H else H)
            wts = [5, 3, 2, 1, 1]                                    # the star scores first
            scorer = g.choices(st[first_t], weights=wts)[0]
            games.append({"date": d, "home": H, "away": A, "starters": st,
                          "tip": {"jumpers": [f"{H}-4", f"{A}-4"], "team": tipw},
                          "first_fg": {"pid": scorer, "team": first_t}})
            for t in (H, A):
                rows[(d, t)] = [(f"{t}-{i}", {"min": 34 - i, "mu": {"pts": 26 - 4 * i,
                                                                     "reb": 5}})
                                for i in range(7)]
    return games, rows


G, R = world()
dates = sorted({g["date"] for g in G})
fitted = nf.fit(G, R, [dates[-90], dates[-45]], [dates[-45], dates[-1]])
print(f"     synthetic: params {fitted['params']}; player {fitted['verdict']['verdict']} "
      f"z={fitted['verdict']['z']}, tip {fitted['tip']['verdict']['verdict']}, "
      f"C={fitted['params']['c']:.2f}")
check("where the star scores first and tips are real, the player call beats 'all equal'",
      fitted["verdict"]["verdict"] == "beats" and fitted["params"]["g"] > 0)
check("C is measured (the tip winner scored first ~63% in this world)",
      0.55 < fitted["params"]["c"] < 0.71)
check("a game never sees itself: the season's first game is priced with an empty book",
      nf._walk(G[:1], R, fitted["params"], "0000", "9999")[0][0]["tip"] == 0.5)
check("calibration bins come out for the delivered chance",
      fitted["calibration"] and all("predicted" in x for x in fitted["calibration"]))

# --- wiring ---------------------------------------------------------------------------
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly fits it, prices every game, reads this season's play-by-play too",
      "nf.fit(list(prior_pbp.values())" in pc and "first_basket_game(" in pc
      and "cur_pbp[g[\"event_id\"]] = dict(pbp.parse(summ)" in pc
      and '"first_basket": (' in pc)
page = (ROOT / "app" / "views" / "NBA_First_Basket.py").read_text(encoding="utf-8")
check("an untested first-team call is capped at THIN (measured only when its test beats)",
      'if tv == "beats" else UNTESTED' in page and "bf.judge(F[\"team\"][t]" in page)
check("player calls are delivered through the test's curve and judged by the guard",
      "tpb.calibrate(p, cal_c if sure else cal_p)" in page
      and "mv.curve_support(p, cal_c if sure else cal_p)" in page
      and "bf.judge(x[\"chance\"], edited.at[i, \"Your price\"], _stk, None, x[\"sup\"])" in page)
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("First Basket is in the NBA nav", '("First Basket", "views/NBA_First_Basket.py")' in app)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall first basket checks passed")
