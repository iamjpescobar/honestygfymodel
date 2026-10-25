"""
NBA First Basket revamp (10-25) — the CONFIRMED starting five.

Measured on last season's unseen games before building: every first field
goal (1,235 of 1,235) came from one of the ten starters; priced on the
real five the log loss fell 2.35 -> 2.27 per game (paired z ~17) against
the projected five, calibrated. Team scoring strength added nothing to the
first-team call (z 0.07) — not built.

Plain script — exits non-zero on failure. Synthetic data. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - reprice treating every given five as confirmed (ignoring `sure`)
    -> "a five you set but did not confirm keeps the projected rho" fails
  - rho_confirmed counted over the TEST window too
    -> "rho_confirmed is measured on the fit side only" fails
  - pregame_starters accepting four starters
    -> "four starters is not a lineup" fails
  - shares pricing a starter with no projection as a 0.1-point player
    (what the 10-25 nightly did: confirmed test thin, z 0.63)
    -> "a starter with no projection gets his teammates' lowest" fails
"""
import random
import sys
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


# --- a book and a slate game in the nightly's shape ---------------------------
b = nf.Book()
for d in ("2026-10-21", "2026-10-23"):
    b.add({"date": d, "starters": {"H": ["c1", "h2", "h3", "h4", "h5"],
                                   "A": ["c2", "a2", "a3", "a4", "a5"]},
           "tip": {"jumpers": ["c1", "c2"], "team": "H"},
           "first_fg": {"pid": "h2", "team": "H"}})
prm = {"k_tip": 2, "c": 0.62, "rho": 0.86, "rho_confirmed": 0.998, "g": 1.0, "lam": 0.5,
       "k_hist": 20}
props = {t: [{"pid": p, "name": p.upper(), "min": 30 - i, "mu": {"pts": 20 - 2 * i, "reb": 4}}
             for i, p in enumerate(ps)]
         for t, ps in (("H", ["c1", "h2", "h3", "h4", "h5", "h6", "h7"]),
                       ("A", ["c2", "a2", "a3", "a4", "a5", "a6"]))}
g = {"home_id": "H", "away_id": "A", "start_et": "2026-10-25T19:30:00",
     "home_props": props["H"], "away_props": props["A"]}
import nba_precompute as npc  # noqa: E402
F = npc.first_basket_game(g, b, prm, {})
check("the nightly ships the pool, the projected five and both team ids",
      len(F["pool"]) == 13 and sorted(F["five"]["H"]) == ["c1", "h2", "h3", "h4", "h5"]
      and F["home"] == "H" and F["away"] == "A")
check("a pool row carries what pricing needs",
      {"pid", "team", "name", "min", "pts", "reb", "fb", "starts", "tip", "jumps"}
      <= set(F["pool"][0]) and next(r for r in F["pool"] if r["pid"] == "c1")["jumps"] == 2)

R0 = nf.reprice(F, prm)
by = {x["pid"]: x["p"] for x in F["players"]}
check("with nothing confirmed the page's re-price IS the nightly's price",
      all(abs(by[x["pid"]] - x["p"]) < 1e-4 for x in R0["players"])
      and abs(R0["tip_home"] - F["tip_home"]) < 1e-4 and abs(R0["other"] - F["other"]) < 1e-3)

five_h = ["c1", "h2", "h3", "h4", "h6"]                   # h6 starts tonight, h5 sits
R1 = nf.reprice(F, prm, {"H": five_h}, {"H"})
hp = {x["pid"]: x["p"] for x in R1["players"] if x["team"] == "H"}
check("a confirmed five is priced: the new starter in, the benched one out",
      "h6" in hp and "h5" not in hp and R1["sure"] == ["H"])
check("a confirmed team carries rho_confirmed, not the projected rho",
      abs(sum(hp.values()) - R1["team"]["H"] * 0.998) < 1e-9)
ap = sum(x["p"] for x in R1["players"] if x["team"] == "A")
check("the other team, not confirmed, keeps the projected rho",
      abs(ap - R1["team"]["A"] * 0.86) < 1e-9)
R2 = nf.reprice(F, prm, {"H": five_h}, set())
hp2 = sum(x["p"] for x in R2["players"] if x["team"] == "H")
check("a five you set but did not confirm keeps the projected rho",
      abs(hp2 - R2["team"]["H"] * 0.86) < 1e-9 and R2["sure"] == [])
R3 = nf.reprice(F, prm, {"H": ["c1", "h2", "zz", "h4", "h6"]}, {"H"})
check("a five naming someone not in the pool falls back to the projected five, unconfirmed",
      sorted(R3["five"]["H"]) == ["c1", "h2", "h3", "h4", "h5"] and R3["sure"] == [])
R4 = nf.reprice(F, prm, {"H": ["h2", "h3", "h4", "h6", "h7"]}, {"H"})
check("the jumper follows the five (c1 sits -> someone in the five jumps)",
      R4["jumpers"]["H"]["pid"] in ["h2", "h3", "h4", "h6", "h7"])

sh = nf.shares(nf.Book(), ["a", "b", "c", "d", "new"], {"a": 20, "b": 15, "c": 10, "d": 8},
               1.0, 0.0, 20)
check("a starter with no projection gets his teammates' lowest, not nothing",
      abs(sh["new"] - sh["d"]) < 1e-12 and sh["new"] > 0.1)
R5 = nf.reprice(F, prm, {"H": ["c1", "h2", "h3", "h4", "zz"]}, {"H"}, {"zz": "Call Up"})
z5 = [x for x in R5["players"] if x["pid"] == "zz"]
check("ESPN's call-up starter (not in the pool) is priced by name and the five stays confirmed",
      z5 and z5[0]["name"] == "Call Up" and z5[0]["p"] > 0.01 and R5["sure"] == ["H"])
check("pregame_names reads names from the box",
      nf.pregame_names({"boxscore": {"players": [{"team": {"id": "H"}, "statistics": [
          {"athletes": [{"athlete": {"id": "9", "displayName": "Nine"}}]}]}]}}) == {"9": "Nine"})

# --- ESPN's lineup ----------------------------------------------------------------
def box(n):
    return {"boxscore": {"players": [{"team": {"id": "H"}, "statistics": [{"athletes": [
        {"athlete": {"id": f"p{i}"}, "starter": i < n} for i in range(8)]}]}]}}


check("five starters in ESPN's box -> the lineup is out", nf.pregame_starters(box(5)) ==
      {"H": ["p0", "p1", "p2", "p3", "p4"]})
check("four starters is not a lineup", nf.pregame_starters(box(4)) == {})
check("the rosters block counts too", nf.pregame_starters({"rosters": [{"team": {"id": "A"},
      "roster": [{"athlete": {"id": f"q{i}"}, "starter": i < 5} for i in range(9)]}]})
      == {"A": [f"q{i}" for i in range(5)]})
check("nothing posted -> {}", nf.pregame_starters({}) == {} and nf.pregame_starters(None) == {})


# --- the fit's confirmed test ------------------------------------------------------
def world(seed=5, days=150, bench_late=False):
    r = random.Random(seed)
    from datetime import date, timedelta
    teams = [f"T{i}" for i in range(10)]
    games, rows = [], {}
    for k in range(days):
        d = (date(2025, 10, 21) + timedelta(days=k)).isoformat()
        o = teams[:]
        r.shuffle(o)
        for a, h in zip(o[::2], o[1::2]):
            # two games in five a regular sits: the real five differs from the projection
            st = {t: [f"{t}-{i}" for i in range(5)] for t in (h, a)}
            for t in (h, a):
                if r.random() < 0.4:
                    st[t][r.randrange(5)] = f"{t}-5"
            tip = h if r.random() < 0.5 else a
            ft = tip if r.random() < 0.63 else (a if tip == h else h)
            sc = r.choices(st[ft], weights=[5, 3, 2, 1, 1])[0]
            if bench_late and k >= 100:
                sc = f"{ft}-6"                  # test window: a bench guy scores first
            games.append({"date": d, "home": h, "away": a, "starters": st,
                          "tip": {"jumpers": [st[h][4], st[a][4]], "team": tip},
                          "first_fg": {"pid": sc, "team": ft}})
            for t in (h, a):
                rows[(d, t)] = [(f"{t}-{i}", {"min": 34 - i, "mu": {"pts": 24 - 3 * i, "reb": 5}})
                                for i in range(7)]
    return games, rows


Gs, Rs = world()
ds = sorted({x["date"] for x in Gs})
fit = nf.fit(Gs, Rs, [ds[10], ds[100]], [ds[100], ds[-1]])
C = fit["confirmed"]
print(f"     synthetic confirmed: n={C['n']} loss {C['loss']} vs projected {fit['test_loss']}; "
      f"{C['verdict']}")
check("the fit tests the confirmed five on the unseen games and it beats the projected five",
      C["n"] == fit["n_test"] and C["verdict"]["verdict"] == "beats" and C["loss"] < fit["test_loss"])
check("confirmed calls get their own calibration curve", C["calibration"]
      and all("predicted" in x for x in C["calibration"]))
check("the confirmed test reports how many real starters had no projection",
      C.get("unprojected") is not None and 0 <= C["unprojected"] <= 1)
check("rho_confirmed is shipped with the params", 0.95 < fit["params"]["rho_confirmed"] < 1)
Gb, Rb = world(bench_late=True)
fb_ = nf.fit(Gb, Rb, [ds[10], ds[100]], [ds[100], ds[-1]])
check("rho_confirmed is measured on the fit side only",
      fb_["params"]["rho_confirmed"] > 0.95)

# --- the page ----------------------------------------------------------------------
page = (ROOT / "app" / "views" / "NBA_First_Basket.py").read_text(encoding="utf-8")
check("the page re-prices with the engine's own function (with ESPN's names)",
      "nf.reprice(F, prm, fives, sure, names)" in page and "nf.pregame_names(summ)" in page)
check("the page reads ESPN's lineup", "nf.pregame_starters(summ)" in page)
check("you can set the five and confirm it", "st.multiselect(" in page
      and "Lineup is out" in page and "max_selections=5" in page)
check("tonight's board sits above the game picker",
      page.index("board_box = st.container()") < page.index('st.selectbox("Game"'))
check("every row says Confirmed or Projected", page.count('"✓ Confirmed" if x["sure"] else "Projected"') == 2)

# --- the page, rendered (AppTest) ---------------------------------------------------
import json as _json  # noqa: E402
FBLOCK = {"params": prm, "calibration": fit["calibration"], "verdict": fit["verdict"],
          "team": fit["team"], "n_test": fit["n_test"],
          "confirmed": dict(C, verdict={"verdict": "beats", "z": 17})}
GAME = dict(g, event_id="E1", status="pre", home_abbr="HOU", away_abbr="ATL", time_et="7:30 PM",
            first_basket=F)
SCRIPT = """
import sys, json, runpy
sys.path.insert(0, %r)
from engines import nba_view as nv, live_injuries as li, espn_feed as ef, live_sync
FB = json.loads(%r); GAME = json.loads(%r)
nv.load = lambda: ([GAME], {}, lambda k, d=None: FB if k == "first_basket" else d)
li.render_note = lambda *a, **k: None
live_sync.sync_latest_button = lambda *a, **k: None
ef.fetch_summary = lambda lg, eid: {"boxscore": {"players": [{"team": {"id": "H"},
    "statistics": [{"athletes": [{"athlete": {"id": p}, "starter": True}
                                 for p in ("c1", "h2", "h3", "h4", "h6")]}]}]}}
runpy.run_path(%r, run_name="__main__")
""" % (str(ROOT / "app"), _json.dumps(FBLOCK), _json.dumps(GAME, default=str),
       str(ROOT / "app" / "views" / "NBA_First_Basket.py"))
try:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string(SCRIPT, default_timeout=60).run()
    if at.exception:
        print(at.exception)
    check("the page renders without an exception", not at.exception)
    frames = [d.value for d in at.dataframe]
    board = next((f for f in frames if "Game" in f.columns and "Lineup" in f.columns), None)
    check("tonight's board is drawn with a Lineup column (top three of the one game)",
          board is not None and len(board) == 3)
    md = " ".join(m.value for m in at.markdown)
    check("ESPN's posted five shows as CONFIRMED", "CONFIRMED by ESPN" in md)
    ed = [str(d.value) for d in at.get("arrow_data_frame")] + [str(f) for f in frames]
    allp = " ".join(ed)
    check("HOU's confirmed five is priced: H6 in, H5 out, rows marked Confirmed",
          "H6 (HOU)" in allp and "H5 (HOU)" not in allp and "Confirmed" in allp)
    ms = [w for w in at.multiselect]
    check("the away five (not posted) is yours to set", len(ms) == 1 and len(ms[0].value) == 5)
    tg = [t for t in at.toggle if "real five" in str(t.label)]
    tg[0].set_value(True)
    at.run()
    b2 = next((d.value for d in at.dataframe if "Lineup" in d.value.columns
               and "Game" in d.value.columns), None)
    check("flipping 'lineup is out' re-prices that team as Confirmed, no exception",
          not at.exception and b2 is not None and (b2["Lineup"] == "✓ Confirmed").all())
except ImportError as exc:
    print(f"SKIP AppTest checks ({exc}) — needs streamlit")

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall confirmed-five checks passed")
