"""
NHL game simulator (10-22) — engines/nhl_sim: the links measured on last
season, one simulated game (shots, goals from shots, assists, overtime,
saves), the same-game parlay kinds and their guard, the test, and the
wiring (nightly, nav, page).

Plain script — exits non-zero on failure. Skater lines in last season's
shape [date, opp, sog, g, a, toi]; finals {date, home, away, hs, as,
home_sog, away_sog} (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - fit_links reading the assist shares from the mean alone (p0 = 0)
    -> "the 0 / 1 / 2 assist shares are measured" fails
  - simulate without the fit to the game model's goals
    -> "the team's goals average the game model's" fails
  - goals drawn without the player's shots (Poisson on his goal mean)
    -> "a scorer needs a shot" fails
  - simulate with no assists drawn
    -> "linemates' points move together" fails
  - sgp_support ignoring the kind's verdict
    -> "a kind that has not beaten stays THIN" fails
  - combo_kind accepting a win leg for the OTHER team
    -> "a goal + the OTHER team's win is not the graded kind" fails
"""
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nhl_sim as hs  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


# --- 1. the links ---------------------------------------------------------------
g = random.Random(4)
finals, gpred, spred, skaters = [], [], [], {}
for k in range(900):
    d = f"2025-{10 + k // 300:02d}-{1 + (k % 300) // 10:02d}-{k}"
    h, a = f"H{k % 16}", f"A{k % 16}"
    zs = {s: max(0.5, g.gauss(1, 0.12)) for s in ("h", "a")}
    sh, sa = round(30 * zs["h"] + g.gauss(0, 5.4)), round(30 * zs["a"] + g.gauss(0, 5.4))
    gh = sum(1 for _ in range(sh) if g.random() < 0.1)
    ga = sum(1 for _ in range(sa) if g.random() < 0.1)
    finals.append({"date": d, "home": h, "away": a, "hs": gh, "as": ga,
                   "home_sog": sh, "away_sog": sa})
    gpred.append({"date": d, "home": h, "away": a, "mu_h": 3.0, "mu_a": 3.0})
    spred.append({"date": d, "home": h, "away": a, "mu_h": 30.0, "mu_a": 30.0})
    for team, opp, goals in ((h, a, gh), (a, h, ga)):
        ast = [0] * 6
        for _ in range(goals):
            u = g.random()
            for _j in range(0 if u < 0.1 else (1 if u < 0.3 else 2)):
                ast[g.randrange(6)] += 1
        for j in range(6):
            skaters.setdefault(f"{team}-{j}", {"games": []})["games"].append(
                [d, opp, 2.0, goals if j == 0 else 0, ast[j], 18.0])
L = hs.fit_links(finals, gpred, spred, skaters, tie_home_win=0.6)
print(f"     synthetic links: {L}")
check("the 0 / 1 / 2 assist shares are measured (0.1 / 0.2 / 0.7 in this world)",
      abs(L["assists"][0] - 0.1) < 0.04 and abs(L["assists"][2] - 0.7) < 0.05)
check("goals rise with shots (one-for-one in this world), and the shot environment is "
      "measured past the Poisson part", 0.6 < L["e_goals"] < 1.4 and 0.005 < L["shot_var"] < 0.03)

# --- 2. one simulated game ---------------------------------------------------------
sk = ([{"pid": f"h{i}", "side": "home", "mu": {"sog": 3.0 - 0.12 * i, "g": 0.35 - 0.015 * i,
                                                "a": 0.5 - 0.02 * i}} for i in range(18)]
      + [{"pid": f"a{i}", "side": "away", "mu": {"sog": 2.6 - 0.1 * i, "g": 0.25 - 0.01 * i,
                                                  "a": 0.4 - 0.015 * i}} for i in range(18)])
GAME = {"mu_home": 3.3, "mu_away": 2.7, "shots_home": 32.0, "shots_away": 28.0}
LK = dict(hs.DEFAULT_LINKS, tie_home_win=0.65)
sim = hs.simulate(GAME, sk, LK, 8.0, n=40000, seed=3)
reg_h, reg_a = sim["home_reg"].mean(), sim["away_reg"].mean()
print(f"     regulation goals {reg_h:.3f} / {reg_a:.3f} (game model 3.3 / 2.7); listed skaters "
      f"project {sum(p['mu']['g'] for p in sk if p['side'] == 'home'):.2f} / "
      f"{sum(p['mu']['g'] for p in sk if p['side'] == 'away'):.2f}")
check("the team's goals average the game model's (even when the dressed skaters add to more)",
      abs(reg_h - 3.3) < 0.08 and abs(reg_a - 2.7) < 0.08)
bad = any(((sim["stats"][p["pid"]]["g"] > sim["stats"][p["pid"]]["sog"]).any()) for p in sk)
check("a scorer needs a shot (never more goals than shots)", not bad)
tie = sim["ot"]
check("a tie goes to overtime: nobody draws, the home side wins it at the measured rate",
      not (sim["home"] == sim["away"]).any()
      and abs(float((sim["home"] > sim["away"])[tie].mean()) - 0.65) < 0.03 and tie.mean() > 0.1)
ga = sum(sim["stats"][p["pid"]]["a"].sum() for p in sk if p["side"] == "home")
gg = sum(sim["stats"][p["pid"]]["g"].sum() for p in sk if p["side"] == "home")
m_ast = LK["assists"][1] + 2 * LK["assists"][2]
check("about 1.7 assists per goal, nearly all to listed teammates",
      1.2 * gg < ga <= m_ast * sim["home_reg"].sum() * 1.02)
check("saves = the other side's shots minus its goals",
      (sim["saves"]["home"] == np.clip(sim["shots"]["away"] - sim["away_reg"], 0, None)).all())


def lift(a, b, st="pts"):
    x, y = sim["stats"][a][st] > 0, sim["stats"][b][st] > 0
    return float((x & y).mean()) / (float(x.mean()) * float(y.mean()))


lt, lo = lift("h0", "h1"), lift("h0", "a0")
print(f"     lift: linemates' points {lt:.3f}, opponents' {lo:.3f}")
check("linemates' points move together (one's goal is the other's assist)", lt > 1.05)
check("opponents' points are nearly independent", abs(lo - 1) < 0.04)
check("the puck line and totals read the final score",
      bool((hs.leg_hits(sim, {"pid": "_game", "stat": "home_margin", "line": 1.5})
            == (sim["home"] - sim["away"] >= 2)).all())
      and bool((hs.leg_hits(sim, {"pid": "_game", "stat": "total", "line": 5.5, "side": "Under"})
                == (sim["home"] + sim["away"] <= 5)).all()))
jp = hs.joint_precise(GAME, sk, LK, 8.0, [{"pid": "h0", "stat": "pts", "line": 0.5},
                                          {"pid": "h1", "stat": "pts", "line": 0.5}],
                      n=40000, chunk=20000)
check("the parlay run gives a lift with its Monte Carlo error",
      jp["lift"] > 1.0 and 0 < jp["lift_se"] < 0.05 and jp["n"] == 40000)

# --- 3. the kinds and the guard ------------------------------------------------------
side_of = {p["pid"]: p["side"] for p in sk}
P = {"stat": "pts", "line": 0.5, "side": "Over"}
check("two teammates' points: PP; one from each side: PPopp; three: PPP",
      hs.combo_kind([dict(P, pid="h0"), dict(P, pid="h1")], side_of) == "PP"
      and hs.combo_kind([dict(P, pid="h0"), dict(P, pid="a1")], side_of) == "PPopp"
      and hs.combo_kind([dict(P, pid=x) for x in ("h0", "h1", "h2")], side_of) == "PPP")
W = {"pid": "_game", "stat": "home_win", "line": 0.5, "side": "Over"}
check("a goal + his team wins: GW",
      hs.combo_kind([{"pid": "h0", "stat": "g", "line": 0.5}, W], side_of) == "GW")
check("a goal + the OTHER team's win is not the graded kind",
      hs.combo_kind([{"pid": "a0", "stat": "g", "line": 0.5}, W], side_of) is None)
check("an under, a 2+ points leg, or a total is never a graded kind",
      hs.combo_kind([dict(P, pid="h0", side="Under"), dict(P, pid="h1")], side_of) is None
      and hs.combo_kind([dict(P, pid="h0", line=1.5), dict(P, pid="h1")], side_of) is None
      and hs.combo_kind([dict(P, pid="h0"), {"pid": "_game", "stat": "total", "line": 5.5}],
                        side_of) is None)
combos = {"PP": {"n": 968, "verdict": {"verdict": "beats"}},
          "PPP": {"n": 60, "verdict": {"verdict": "beats"}},
          "GG": {"n": 968, "verdict": {"verdict": "fails"}}}
s1 = hs.sgp_support(combos, [dict(P, pid="h0"), dict(P, pid="h1")], side_of)
s2 = hs.sgp_support(combos, [dict(P, pid=x) for x in ("h0", "h1", "h2")], side_of)
s3 = hs.sgp_support(combos, [{"pid": "h0", "stat": "g", "line": .5},
                             {"pid": "h1", "stat": "g", "line": .5}], side_of)
s4 = hs.sgp_support(combos, [dict(P, pid="h0"), {"pid": "_game", "stat": "total",
                                                  "line": 5.5}], side_of)
check("a kind that beat with 100+ graded can reach STRONG; with fewer, VALUE at most",
      s1["measured"] and s1["in_range"] and s2["measured"] and not s2["in_range"])
check("a kind that has not beaten stays THIN; an ungraded kind too, and the page says why",
      s3["untested"] and s3["why"] == "not_beaten" and s4["untested"] and s4["why"] == "untested"
      and hs.sgp_guard(s3, "thin") and hs.sgp_guard(s2, "value"))

# --- 4. the test's shape on a small graded set -------------------------------------------
rows = {}
gr = random.Random(9)
for k in range(30):
    pl = []
    for side in ("home", "away"):
        for i in range(6):
            pl.append((f"{side}{k}-{i}", side, {"sog": 2.5, "g": 0.3, "a": 0.45}, 2.5,
                       {"sog": gr.randrange(6), "g": int(gr.random() < .25),
                        "a": int(gr.random() < .35), "pts": 0}))
    pl = [(a, b, c, d, dict(e, pts=e["g"] + e["a"])) for a, b, c, d, e in pl]
    rows[(f"2026-01-{k:02d}", "H")] = {"home": "H", "away": "A", "hs": gr.randrange(6),
                                       "as": gr.randrange(5), "mu_h": 3.0, "mu_a": 2.8,
                                       "p_home": 0.55, "s_h": 30.0, "s_a": 28.0, "players": pl}
tc = hs.test_combos(rows, LK, 8.0, {}, n=4000)
check("the test grades each kind (n, verdict, lift, predicted vs actual)",
      {"PP", "PPP", "PW", "GW", "PPopp", "SS"} <= set(tc)
      and all({"n", "verdict", "avg_lift", "actual"} <= set(x) for x in tc.values())
      and tc["PP"]["avg_lift"] > 1.0)

# --- 5. wiring ------------------------------------------------------------------------------
pc = (ROOT / "nhl_precompute.py").read_text(encoding="utf-8")
check("the nightly builds the simulator block and ships it",
      "sim_block = nhl_sim_block(prior, model_block, skaters, id_of, regular_ids, rows)" in pc
      and '"sim": sim_block,' in pc and "nhl_sim.build(prior, model_block, pool, rows)" in pc)
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("the Simulator is in the NHL nav", '("Simulator", "views/NHL_Sim.py")' in app)
pg = (ROOT / "app" / "views" / "NHL_Sim.py").read_text(encoding="utf-8")
check("the page prices SGPs with the graded guard and logs / slips them",
      "hs.sgp_support(combos, legs, side_of)" in pg and "hs.sgp_guard(" in pg
      and "_blu.log_button(\"NHL\"" in pg and "pl.add_leg(" in pg)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NHL simulator checks passed")
