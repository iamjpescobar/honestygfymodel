"""
NFL game simulator (10-22) — engines/nfl_sim: the game-script links and
yards correlations measured on 2025, one simulated game (score, script,
correlated yards, touchdowns from the team's points), the same-game
parlay kinds and their guard, the test's shape, and the wiring.

Plain script — exits non-zero on failure. Rows in collect()'s shape
({"players": [{"pid", "side", "role", "proj", "actual", "lines"}], ...})
and the Prop Lab's projection keys (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - fit_links without the script term (score only)
    -> "the script elasticity is measured" fails
  - fit_corr on raw yards instead of residuals after the score
    -> "the QB-receiver correlation is the residual one" fails
  - simulate drawing every yards line independently (no Cholesky)
    -> "a QB's yards and his top receiver's move together" fails
  - simulate keeping the board's full spread on top of the game shocks
    -> "each line keeps the board's spread" fails
  - no passing touchdowns (q_pass 0)
    -> "the QB's passing TDs are the team's passing TDs" fails
  - combo_kind accepting a QB with the OTHER team's receiver
    -> "a QB + the other team's receiver is not the graded kind" fails
"""
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import model_math as mm  # noqa: E402
from engines import nfl_prop_odds as npo  # noqa: E402
from engines import nfl_sim as fs  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


SP = {"Passing yards": {"kind": "yards", "cv": 0.32}, "Receiving yards": {"kind": "yards",
                                                                           "cv": 0.9},
      "Rushing yards": {"kind": "yards", "cv": 0.85}, "Carries": {"kind": "count", "size": 30.0},
      "Receptions": {"kind": "count", "size": 20.0}, "Targets": {"kind": "count", "size": 20.0},
      "Pass attempts": {"kind": "count", "size": 60.0},
      "Completions": {"kind": "count", "size": 50.0},
      "Passing TDs": {"kind": "count", "size": None}, "Interceptions": {"kind": "count",
                                                                         "size": None}}

# --- 1. the links on a world with a known script and correlation --------------------
g = random.Random(7)
rows = []
for k in range(500):
    mh, ma = 23.0, 21.0
    hs, as_ = max(0, round(g.gauss(mh, 10))), max(0, round(g.gauss(ma, 10)))
    rec = {"week": 1 + k // 30, "hs": hs, "as": as_, "mu_h": mh, "mu_a": ma, "players": []}
    for side in ("home", "away"):
        tp, op = (hs, as_) if side == "home" else (as_, hs)
        tm, om = (mh, ma) if side == "home" else (ma, mh)
        x, m = tp / tm - 1, ((tp - op) - (tm - om)) / 13.4
        f = g.gauss(0, 1)
        zq = 0.55 * f + (1 - 0.55 ** 2) ** 0.5 * g.gauss(0, 1)
        zr = 0.55 * f + (1 - 0.55 ** 2) ** 0.5 * g.gauss(0, 1)       # corr 0.30
        qy = 240 * (1 + 0.5 * x - 0.15 * m) + 0.25 * 240 * zq
        ry = 70 * (1 + 0.4 * x - 0.1 * m) + 0.6 * 70 * zr
        uy = 60 * (1 + 0.1 * x + 0.12 * m) + 0.6 * 60 * g.gauss(0, 1)
        rec["players"] += [
            {"pid": f"q{side}{k}", "side": side, "role": "QB",
             "proj": {"pass_yds": 240.0, "pass_att": 34.0}, "actual": {"pass_yds": qy}},
            {"pid": f"r{side}{k}", "side": side, "role": "REC",
             "proj": {"rec_yds": 70.0}, "actual": {"rec_yds": ry}},
            {"pid": f"u{side}{k}", "side": side, "role": "RB",
             "proj": {"rush_yds": 60.0}, "actual": {"rush_yds": uy}}]
    rows.append(rec)
sp_w = dict(SP, **{"Passing yards": {"kind": "yards", "cv": 0.25 * 1.05},
                   "Receiving yards": {"kind": "yards", "cv": 0.6 * 1.05},
                   "Rushing yards": {"kind": "yards", "cv": 0.6 * 1.05}})
L = fs.fit_links(rows, 13.4, 0.107, sp_w)
print(f"     synthetic links: e {L['e']['pass_yds']} / {L['e']['rec_yds']} / {L['e']['rush_yds']};"
      f" corr {L['corr']}")
check("the score elasticity is measured (passing 0.5 in this world)",
      abs(L["e"]["pass_yds"][0] - 0.5) < 0.1 and abs(L["e"]["rec_yds"][0] - 0.4) < 0.15)
check("the script elasticity is measured (ahead: less passing, more running)",
      L["e"]["pass_yds"][1] < -0.08 and L["e"]["rush_yds"][1] > 0.05)
check("the QB-receiver correlation is the residual one (0.30 here; ~0 for the back)",
      abs(L["corr"].get("QR", 0) - 0.30) < 0.05 and abs(L["corr"].get("QU", 0)) < 0.12)

# --- 2. one simulated game ---------------------------------------------------------------
GAME = {"mu_home": 24.0, "mu_away": 20.0, "sd_margin": 13.4, "sd_total": 13.7}
LK = {"e": {"pass_yds": [0.53, -0.15], "rush_yds": [0.1, 0.1], "carries": [0.04, 0.09],
            "rec_yds": [0.44, -0.11], "rec": [0.21, -0.1], "targets": [0.12, -0.1]},
      "tpp": 0.107, "corr": {"QR": 0.27, "RR": 0.0, "QU": -0.14, "RU": -0.04, "UU": 0.0}}
PL = []
for side in ("home", "away"):
    PL += [{"pid": f"{side}QB", "side": side, "role": "QB",
            "proj": {"pass_yds": 245.0, "pass_att": 35.0, "pass_cmp": 23.0, "pass_td": 1.6,
                     "pass_int": 0.7, "rush_yds": 18.0}},
           {"pid": f"{side}RB", "side": side, "role": "RB",
            "proj": {"rush_yds": 70.0, "carries": 16.0, "rec_yds": 20.0, "rec": 2.5,
                     "targets": 3.2, "td_exp": 0.55}},
           {"pid": f"{side}WR1", "side": side, "role": "REC",
            "proj": {"rec_yds": 80.0, "rec": 6.0, "targets": 9.0, "td_exp": 0.5}},
           {"pid": f"{side}WR2", "side": side, "role": "REC",
            "proj": {"rec_yds": 50.0, "rec": 4.0, "targets": 6.0, "td_exp": 0.35}}]
sim = fs.simulate(GAME, PL, SP, LK, n=40000, seed=5)
H = sim["stats"]
qy, wy, w2 = H["homeQB"]["pass_yds"], H["homeWR1"]["rec_yds"], H["homeWR2"]["rec_yds"]
c_qw = float(np.corrcoef(qy, wy)[0, 1])
c_ww = float(np.corrcoef(wy, w2)[0, 1])
print(f"     sim: QB yds mean {qy.mean():.0f} sd {qy.std():.0f}; corr QB-WR1 {c_qw:.2f}, "
      f"WR1-WR2 {c_ww:.2f}")
check("a QB's yards and his top receiver's move together", c_qw > 0.25)
check("two receivers barely (the shared score only)", c_ww < c_qw - 0.1)
check("each line keeps the board's spread (QB sd = cv x mean, within 5%)",
      abs(qy.std() / (0.32 * 245) - 1) < 0.05 and abs(wy.mean() / 80 - 1) < 0.08)
pm = npo.stat_pmf("Passing yards", 245.0, SP)
check("on its own a line prices like the board (P over 244.5 within 3 points)",
      abs(float((qy > 244.5).mean()) - mm.over_prob_pmf(pm, 244.5)) < 0.03)
pts = sim["home"]
td_tot = H["homeRB"]["td"].astype(int) + H["homeWR1"]["td"] + H["homeWR2"]["td"]
check("touchdowns come from the team's points and teammates share them",
      abs(float(td_tot.mean()) - 1.40) < 0.35 and float(np.corrcoef(pts, td_tot)[0, 1]) > 0.3)
check("the QB's passing TDs are the team's passing TDs",
      abs(float(H["homeQB"]["pass_td"].mean()) - 1.6 * 24 * 0.107 / (24 * 0.107)) < 0.35
      and float(np.corrcoef(H["homeQB"]["pass_td"], H["homeWR1"]["td"])[0, 1]) > 0.1)
mg = sim["home"] - sim["away"]
lead, trail = mg > 10, mg < -3
check("a team that leads runs more (its back's yards), one that trails throws more per point",
      H["homeRB"]["rush_yds"][lead].mean() > H["homeRB"]["rush_yds"][trail].mean())
check("no negative yards (the board puts them on 0)",
      min(int(H[p]["rec_yds"].min()) for p in ("homeWR1", "homeWR2", "homeRB")) >= 0)

# --- 3. the kinds and the guard ------------------------------------------------------------
info = {p["pid"]: (p["side"], p["role"]) for p in PL}
Q = {"pid": "homeQB", "stat": "pass_yds", "line": 240.5, "side": "Over"}
R1 = {"pid": "homeWR1", "stat": "rec_yds", "line": 74.5, "side": "Over"}
check("QB + his receiver: QR; + two: QRR; both QBs: QQ",
      fs.combo_kind([Q, R1], info) == "QR"
      and fs.combo_kind([Q, R1, dict(R1, pid="homeWR2")], info) == "QRR"
      and fs.combo_kind([Q, dict(Q, pid="awayQB")], info) == "QQ")
check("a QB + the other team's receiver is not the graded kind",
      fs.combo_kind([Q, dict(R1, pid="awayWR1")], info) is None)
W = {"pid": "_game", "stat": "home_win", "line": 0.5, "side": "Over"}
check("a back's yards + his team wins: UW; a TD + the win: TW; two TDs: TT",
      fs.combo_kind([{"pid": "homeRB", "stat": "rush_yds", "line": 69.5}, W], info) == "UW"
      and fs.combo_kind([{"pid": "homeWR1", "stat": "td", "line": 0.5}, W], info) == "TW"
      and fs.combo_kind([{"pid": "homeWR1", "stat": "td", "line": 0.5},
                         {"pid": "homeRB", "stat": "td", "line": 0.5}], info) == "TT")
check("an under, catches, or the other team's win is never a graded kind",
      fs.combo_kind([dict(Q, side="Under"), R1], info) is None
      and fs.combo_kind([Q, {"pid": "homeWR1", "stat": "rec", "line": 5.5}], info) is None
      and fs.combo_kind([{"pid": "awayRB", "stat": "rush_yds", "line": 60.5}, W], info) is None)
cmb = {"UW": {"n": 271, "verdict": {"verdict": "beats"}},
       "QR": {"n": 259, "verdict": {"verdict": "fails"}}}
s1 = fs.sgp_support(cmb, [{"pid": "homeRB", "stat": "rush_yds", "line": 69.5}, W], info)
s2 = fs.sgp_support(cmb, [Q, R1], info)
check("a beaten kind can reach STRONG; one that failed stays THIN and says why",
      s1["measured"] and s1["in_range"] and s2["untested"] and s2["why"] == "not_beaten"
      and fs.sgp_guard(s2, "thin"))
jp = fs.joint_precise(GAME, PL, SP, LK, [Q, R1], n=40000, chunk=20000)
check("the parlay run gives a lift with its Monte Carlo error",
      jp["lift"] > 1.0 and 0 < jp["lift_se"] < 0.05)

# --- 4. the test's shape ------------------------------------------------------------------------
trows = []
for k in range(12):
    ps = []
    for p in PL:
        act = {s: (p["proj"].get(s) or 0) * g.uniform(.5, 1.5) for s in
               ("pass_yds", "rush_yds", "rec_yds")}
        act["td"] = int(g.random() < .35)
        lines = {s: p["proj"][s] - 0.5 for s in ("pass_yds", "rush_yds", "rec_yds")
                 if p["proj"].get(s)}
        ps.append(dict(p, actual=act, lines=lines))
    trows.append({"week": 12, "hs": 27, "as": 17, "mu_h": 24.0, "mu_a": 20.0, "p_home": 0.6,
                  "players": ps})
tc = fs.test_combos(trows, SP, LK, (13.4, 13.7), {}, n=3000)
check("the test grades each kind (n, verdict, lift, predicted vs actual)",
      {"QR", "QRR", "UW", "TW", "TT", "QT", "QQ"} <= set(tc)
      and all({"n", "verdict", "avg_lift", "actual"} <= set(x) for x in tc.values()))

# --- 5. wiring ------------------------------------------------------------------------------------
pc = (ROOT / "nfl_precompute.py").read_text(encoding="utf-8")
check("the nightly builds the simulator block and ships it",
      "nfl_sim.build(_plogs2, finals, logs, sys.modules[__name__], league," in pc
      and '"sim": sim_block,' in pc)
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("the Simulator is in the NFL nav", '("Simulator", "views/NFL_Sim.py")' in app)
pg = (ROOT / "app" / "views" / "NFL_Sim.py").read_text(encoding="utf-8")
check("the page prices SGPs with the graded guard and logs / slips them",
      "fs.sgp_support(combos, legs, info)" in pg and "fs.sgp_guard(" in pg
      and '_blu.log_button("NFL"' in pg and "pl.add_leg(" in pg)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NFL simulator checks passed")
