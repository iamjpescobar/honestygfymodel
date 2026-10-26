"""
NBA first 3 minutes (10-25) — engines/nba_early, the nightly wiring and the
First Basket page's card. Izzy: "I need players to score in the first 3
minutes also that's a market I like to bet on".

Measured on last season before building (5,920 starter-games unseen):
any point beats the league rate (z 7.7) and his own record (z 2.7);
a made field goal beats the league rate, thin against his own record.

Plain script — exits non-zero on failure. Synthetic games. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - _walk adding a game to the book before pricing it
    -> "a game never sees itself" fails
  - price giving an unprojected starter 0.1 points
    -> "a starter with no projection gets his teammates' lowest" fails
  - fit calling it "beats" when only the league rate is beaten
    -> "beats needs BOTH baselines" fails
"""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nba_early as ne  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


# --- the pieces ------------------------------------------------------------------------
prm = {"c": 0.6, "g": 1.0, "lam": 0.0, "k": 20}
p = ne.price(["a", "b", "c", "d", "e"], {"a": 30, "b": 10, "c": 10, "d": 10, "e": 10}, prm,
             {}, {}, 0.47)
check("the big scorer is likelier to score early", p["a"] > p["b"] and 0 < p["b"] < p["a"] < 1)
p2 = ne.price(["a", "b", "c", "d", "new"], {"a": 20, "b": 15, "c": 10, "d": 8}, prm, {}, {}, 0.47)
check("a starter with no projection gets his teammates' lowest", abs(p2["new"] - p2["d"]) < 1e-12)
p3 = ne.price(["a"], {"a": 10}, dict(prm, lam=1.0), {"a": 40}, {"a": 30}, 0.47)
check("LAM=1 is his own record shrunk K starts to the league",
      abs(p3["a"] - (30 + 20 * 0.47) / (40 + 20)) < 1e-12)

b = ne.Book()
b.add({"starters": {"H": ["h1", "h2", "h3", "h4", "h5"], "A": ["a1", "a2", "a3", "a4", "a5"]},
       "early": {"h1": [3, 1], "a2": [1, 0]}})
check("the book counts starts and early scores per target (a free throw is a point, not a FG)",
      b.starts["h1"] == 1 and b.hits["pts"]["h1"] == 1 and b.hits["fg"]["h1"] == 1
      and b.hits["pts"]["a2"] == 1 and b.hits["fg"]["a2"] == 0 and b.lg["pts"] == [2, 10])


# --- a world where usage drives early scoring --------------------------------------------
def world(seed=7, days=160, teams=8):
    r = random.Random(seed)
    games, rows = [], {}
    use = {f"T{t}-{i}": 0.75 - 0.08 * i for t in range(teams) for i in range(5)}
    for k in range(days):
        d = (date(2025, 10, 21) + timedelta(days=k)).isoformat()
        o = list(range(teams))
        r.shuffle(o)
        for a, h in zip(o[::2], o[1::2]):
            H, A = f"T{h}", f"T{a}"
            st = {t: [f"{t}-{i}" for i in range(5)] for t in (H, A)}
            early = {}
            for t in (H, A):
                for p_ in st[t]:
                    if r.random() < use[p_]:
                        early[p_] = [2, 1]
            games.append({"date": d, "home": H, "away": A, "starters": st, "early": early})
            for t in (H, A):
                rows[(d, t)] = [(f"{t}-{i}", {"min": 34 - i, "mu": {"pts": 26 - 4 * i}})
                                for i in range(7)]
    return games, rows


G, R = world()
ds = sorted({g["date"] for g in G})
F = ne.fit(G, R, (ds[10], ds[100]), (ds[100], ds[-1]))
P = F["pts"]
print(f"     synthetic pts: {P['params']} brier {P['brier']} vs league {P['league_brier']} vs "
      f"own {P['own_brier']} -> {P['verdict']}")
check("where usage drives it, the model beats the league rate", P["vs_league"]["verdict"] == "beats")
check("both targets are fitted and tested, with calibration bins",
      set(F) == {"pts", "fg"} and all(F[t]["calibration"] for t in F))
check("a game never sees itself: the first game is priced on an empty book",
      ne._walk(G[:1], R, P["params"], "pts", "0000", "9999")[0][1] == 0.47)
v = P["verdict"]["verdict"]
check("beats needs BOTH baselines",
      (v == "beats") == (P["vs_league"]["verdict"] == P["vs_own"]["verdict"] == "beats"))

bk = ne.book_from(G)
blk = ne.game_block(bk, ["T0-0", "T0-1", "zz"])
check("the page block carries [starts, pts hits, fg hits] and the league rates",
      blk["rec"]["T0-0"][0] == bk.starts["T0-0"] and blk["rec"]["zz"] == [0, 0, 0]
      and set(blk["base"]) == {"pts", "fg"})
five = [f"T0-{i}" for i in range(5)]
pp = ne.page_price(blk, F, five, {x: 26 - 4 * i for i, x in enumerate(five)}, "pts")
ref = ne.price(five, {x: 26 - 4 * i for i, x in enumerate(five)}, F["pts"]["params"],
               {x: bk.starts.get(x, 0) for x in five}, {x: bk.hits["pts"].get(x, 0) for x in five},
               blk["base"]["pts"])
check("the page prices with the engine's own function", all(abs(pp[x] - ref[x]) < 1e-9
                                                            for x in five))

# --- wiring ----------------------------------------------------------------------------------
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly fits it on the same rows and windows, prints it, ships it",
      'ne.fit(_all, byg, model["fit_window"], model["test_window"])' in pc
      and "NBA first 3 minutes (" in pc and '"first3": early_block' in pc
      and 'g["first_basket"]["early"] = ne.game_block(' in pc)
page = (ROOT / "app" / "views" / "NBA_First_Basket.py").read_text(encoding="utf-8")
check("the page card prices the five in use, delivers through the curve, judges your price",
      "ne.page_price(E3, F3, five, pts, tgt)" in page
      and 'tpb.calibrate(raw[p], X3.get("calibration") or [])' in page
      and 'bf.judge(x["chance"], ed3.at[i, "Your price"], _stk, None, x["sup"])' in page
      and 'if v3 == "beats" else UNTESTED' in page)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall first-3-minutes checks passed")
