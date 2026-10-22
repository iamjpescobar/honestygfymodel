"""
MLB game simulator (10-22) — engines/mlb_sim (base-out transitions
measured from plate appearances, one simulated game PA by PA, the parlay
kinds and their guard), mlb_prop_precompute.build_sim (the transitions
and the graded same-game parlays, walked forward) and the wiring.

Plain script — exits non-zero on failure. A synthetic season in
Statcast's plate-appearance shape (game_pk, at_bat_number, events,
batter, pitcher, game_date, inning, inning_topbot, outs_when_up, on_1b /
on_2b / on_3b, bat_score, post_bat_score) played by known rules (rule 5).
No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - state_rows comparing pandas' NA directly (no _na) -> "Statcast's
    nullable columns ... read exactly like plain ones" fails (10-22)
  - state_rows ending a half-inning's last PA with the next half's state
    -> "the last PA of a half-inning ends it" fails
  - _move putting the batter out before the lead runner on a hit (a
    runner thrown out at third)
    -> "a single scores the lead runner and puts the batter on first" fails
  - simulate never crediting runs to runners
    -> "every run is credited to the man who scored it" fails
  - simulate playing the bottom of the ninth when the home team leads
    -> "no bottom of the ninth when the home team leads" fails
  - sgp_support ignoring the kind's verdict
    -> "a kind that has not beaten stays THIN" fails
"""
import random
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import mlb_sim as ms  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


# --- a synthetic season played by known base-running rules ---------------------------

EV = {"1B": "single", "2B": "double", "3B": "triple", "HR": "home_run", "BB": "walk",
      "K": "strikeout", "OUT": "field_out"}


def advance(bases, outs, oc, g):
    on = [bool(bases & 1), bool(bases & 2), bool(bases & 4)]
    if oc == "HR":
        return 0, sum(on) + 1, 0
    if oc == "BB":
        n2 = on[1] or on[0]
        n3 = on[2] or (on[0] and on[1])
        return 1 | (2 if n2 else 0) | (4 if n3 else 0), int(all(on)), 0
    if oc == "1B":
        s2 = on[1] and g.random() < 0.6
        runs = int(on[2]) + int(s2)
        n3 = (on[1] and not s2) or (on[0] and g.random() < 0.3)
        n2 = on[0] and not (on[0] and n3 and not (on[1] and not s2))
        return 1 | (2 if n2 else 0) | (4 if n3 else 0), runs, 0
    if oc == "2B":
        s1 = on[0] and g.random() < 0.4
        return 2 | (4 if on[0] and not s1 else 0), int(on[2]) + int(on[1]) + int(s1), 0
    if oc == "3B":
        return 4, sum(on), 0
    if oc == "OUT" and on[0] and outs < 2 and g.random() < 0.15:
        return bases & 6, 0, 2
    if oc == "OUT" and on[2] and outs < 2 and g.random() < 0.35:
        return bases & 3, 1, 1
    return bases, 0, 1


def season(days=70, teams=6, seed=3):
    g = random.Random(seed)
    lg = {"1B": .142, "2B": .041, "3B": .004, "HR": .03, "BB": .101, "K": .222, "OUT": .46}
    bats, sps = {}, {}
    for t in range(teams):
        for i in range(9):
            pid = 100 * (t + 1) + i
            hr = g.choice((0.5, 1.0, 2.2))
            k = g.choice((0.7, 1.0, 1.4))
            r = dict(lg, HR=lg["HR"] * hr, K=lg["K"] * k)
            s = sum(r.values())
            bats[pid] = {o: v / s for o, v in r.items()}
        for j in range(2):
            pid = 9000 + 10 * t + j
            kk = g.choice((0.75, 1.0, 1.35))
            r = dict(lg, K=lg["K"] * kk)
            s = sum(r.values())
            sps[pid] = ({o: v / s for o, v in r.items()}, g.choice((18, 22, 26)))
    rows, gpk = [], 1000
    for day in range(days):
        d = (pd.Timestamp("2026-07-01") + pd.Timedelta(days=day)).strftime("%Y-%m-%d")
        order = list(range(teams))
        g.shuffle(order)
        for a, h in zip(order[::2], order[1::2]):
            gpk += 1
            ab = 0
            score = {"home": 0, "away": 0}
            pos = {"home": 0, "away": 0}
            bf = {"home": 0, "away": 0}
            sp = {"home": 9000 + 10 * h + day % 2, "away": 9000 + 10 * a + day % 2}
            team = {"home": h, "away": a}
            for inn in range(1, 10):
                for side, pit in (("away", "home"), ("home", "away")):
                    if side == "home" and inn == 9 and score["home"] > score["away"]:
                        continue
                    outs, bases = 0, 0
                    while outs < 3:
                        b = 100 * (team[side] + 1) + pos[side]
                        prat, lim = sps[sp[pit]]
                        vs = bf[pit] < lim
                        br = bats[b]
                        if vs:
                            raw = {o: br[o] * prat[o] / lg[o] for o in lg}
                        else:
                            raw = dict(br)
                        s = sum(raw.values())
                        oc = g.choices(list(raw), [v / s for v in raw.values()])[0]
                        nb, runs, add = advance(bases, outs, oc, g)
                        add = min(add, 3 - outs)
                        ab += 1
                        rows.append({"game_pk": gpk, "at_bat_number": ab, "events": EV[oc],
                                     "batter": b, "pitcher": sp[pit] if vs else 8000 + team[pit],
                                     "game_date": d, "home_team": f"T{h}",
                                     "inning_topbot": "Top" if side == "away" else "Bot",
                                     "inning": inn, "outs_when_up": outs,
                                     "on_1b": 1.0 if bases & 1 else None,
                                     "on_2b": 1.0 if bases & 2 else None,
                                     "on_3b": 1.0 if bases & 4 else None,
                                     "bat_score": score[side], "post_bat_score": score[side] + runs})
                        score[side] += runs
                        bf[pit] += 1
                        pos[side] = (pos[side] + 1) % 9
                        outs += add
                        bases = nb if outs < 3 else 0
                        if side == "home" and inn == 9 and score["home"] > score["away"]:
                            break
    return pd.DataFrame(rows)


DF = season(days=70)
import mlb_prop_precompute as mpp  # noqa: E402
PA = mpp.plate_appearances(DF)

# --- 1. the transitions -----------------------------------------------------------------
rows = ms.state_rows(PA)
check("every plate appearance with a state becomes a transition",
      len(rows) == len(PA) and all(0 <= r[1] <= 2 for r in rows))
# Statcast hands these columns over as pandas' nullable integers: an empty
# base is pd.NA, whose truth value raises (the 10-22 nightly died on it)
PA_NA = PA.copy()
for _c in ("on_1b", "on_2b", "on_3b", "outs_when_up", "inning", "bat_score", "post_bat_score"):
    PA_NA[_c] = pd.to_numeric(PA_NA[_c], errors="coerce").astype("Int64")
try:
    _same = ms.state_rows(PA_NA) == rows and mpp._final_scores(PA_NA) == mpp._final_scores(PA)
except TypeError as exc:
    print(f"     {type(exc).__name__}: {exc}")
    _same = False
check("Statcast's nullable columns (an empty base is pandas' NA) read exactly like plain ones",
      _same and PA_NA["on_1b"].isna().any())
one = PA[PA["game_pk"] == PA["game_pk"].iloc[0]].sort_values("at_bat_number")
n_top1 = int(((one["inning"] == 1) & (one["inning_topbot"] == "Top")).sum())
last = ms.state_rows(one)[n_top1 - 1]               # followed by the bottom of the 1st
check("the last PA of a half-inning ends it (outs to 3, bases cleared)",
      last[1] + last[5] == 3 and last[3] == 0)
tr = ms.measure_transitions(rows)
T = tr["T"]
c = {(r[0], r[2], r[4]) for r in rows if r[0] == 0 and r[2] == "HR"}
check("a homer with the bases empty scores exactly one, every time",
      all(x[1] == 1 and x[0] == 0 for x in T["0|0|HR"]) and c == {(0, "HR", 1)})
s1 = T.get("2|0|1B") or []
p_score = sum(x[3] for x in s1 if x[1] == 1) / max(1, sum(x[3] for x in s1))
check("a single with a man on second scores him as often as this world does (60%)",
      abs(p_score - 0.6) < 0.06)
check("the single: the runner from second scores, the batter goes to first",
      ms._move(2, 1, 1, 0, "1B") == [-1, 4, -1, 1])
check("a single scores the lead runner and puts the batter on first (1st and 3rd -> 1st, 3rd "
      "scored, the man on first to second)", ms._move(5, 3, 1, 0, "1B") == [4, -1, 2, 1]
      and ms._move(1, 1, 0, 1, "1B") == [-1, -1, 0, 1])
check("a double play: the runner on first and the batter are out",
      ms._move(1, 0, 0, 2, "OUT") == [-1, -1, 0, 0])
check("a homer clears the bases: everyone scores", ms._move(7, 0, 4, 0, "HR") == [4, 4, 4, 4])

# --- 2. one simulated game ----------------------------------------------------------------
tab = ms.tables(tr)
lg = PA["outcome"].value_counts(normalize=True).to_dict()
side = lambda t: {"pids": [f"{t}{i}" for i in range(9)], "vs_sp": [lg] * 9, "vs_pen": [lg] * 9,
                  "bf": {22: 1.0}}
sim = ms.simulate({"home": side("h"), "away": side("a")}, tab, n=20000, seed=4)
runs_world = PA.groupby(["game_pk", "side"])["post_bat_score"].max().mean()
print(f"     runs a team: simulated {sim['home'].mean():.2f} / {sim['away'].mean():.2f}, "
      f"the season {runs_world:.2f}")
check("the simulated game scores like the season it was measured on (within 8%)",
      abs((sim["home"].mean() + sim["away"].mean()) / 2 / runs_world - 1) < 0.08)
r_sum = sum(sim["stats"][f"h{i}"]["r"].astype(int) for i in range(9))
rbi_sum = sum(sim["stats"][f"h{i}"]["rbi"].astype(int) for i in range(9))
reg = sim["inn"]["home"].sum(axis=1)
check("every run is credited to the man who scored it, and an RBI to the batter",
      bool((r_sum == reg).all()) and bool((rbi_sum == reg).all()))
inn = sim["inn"]
lead8 = inn["home"][:, :8].sum(axis=1) > inn["away"][:, :9].sum(axis=1)
check("no bottom of the ninth when the home team leads", bool((inn["home"][lead8, 8] == 0).all()))
check("nobody ties; some games go to extra innings",
      not (sim["home"] == sim["away"]).any() and (inn["home"][:, 9:].sum() + inn["away"][:, 9:]
                                                  .sum()) > 0)
sp = sim["sp"]["home"]
check("the starter pitches until his batters-faced runs out (22 BF: about 15-17 outs)",
      14 <= sp["outs"].mean() <= 18.5 and sp["k"].mean() > 3)
ab = {"home": side("h"), "away": dict(side("a"), vs_sp=[dict(lg, K=lg["K"] * 1.6)] * 9)}
sim2 = ms.simulate(ab, tab, n=20000, seed=4)
check("a strikeout starter strikes out more (the starter is in the PA odds)",
      sim2["sp"]["home"]["k"].mean() > sp["k"].mean() + 1)
hh = ms.joint(sim, [{"pid": "h0", "stat": "h", "line": .5}, {"pid": "h1", "stat": "h",
                                                              "line": .5}])
hw = ms.joint(sim, [{"pid": "h3", "stat": "hr", "line": .5},
                    {"pid": "_game", "stat": "home_win", "line": .5}])
print(f"     lifts: two teammates' hits {hh['lift']:.3f}; a homer + the win {hw['lift']:.3f}")
check("a homer and his team's win move together", hw["lift"] > 1.1)
f5 = ms.leg_hits(sim, {"pid": "_game", "stat": "f5_total", "line": 4.5})
check("first-five legs read innings 1-5",
      bool((f5 == ((inn["home"][:, :5].sum(1) + inn["away"][:, :5].sum(1)) > 4.5)).all()))

# --- 3. the kinds and the guard ----------------------------------------------------------
so = {f"h{i}": "home" for i in range(9)} | {f"a{i}": "away" for i in range(9)}
H = {"stat": "h", "line": 0.5, "side": "Over"}
W = {"pid": "_game", "stat": "home_win", "line": 0.5}
check("two teammates' hits: HH; from each side: HHopp; a homer + his team's win: RW; the "
      "starter's Ks + his win: KW",
      ms.combo_kind([dict(H, pid="h0"), dict(H, pid="h1")], so) == "HH"
      and ms.combo_kind([dict(H, pid="h0"), dict(H, pid="a1")], so) == "HHopp"
      and ms.combo_kind([{"pid": "h3", "stat": "hr", "line": .5}, W], so) == "RW"
      and ms.combo_kind([{"pid": "_sp_home", "stat": "k", "line": 5.5}, W], so) == "KW")
check("the other team's win, an under, or runs scored are never a graded kind",
      ms.combo_kind([{"pid": "a3", "stat": "hr", "line": .5}, W], so) is None
      and ms.combo_kind([dict(H, pid="h0", side="Under"), dict(H, pid="h1")], so) is None
      and ms.combo_kind([{"pid": "h0", "stat": "r", "line": .5}, dict(H, pid="h1")], so) is None)
cmb = {"HH": {"n": 300, "verdict": {"verdict": "beats"}},
       "RW": {"n": 300, "verdict": {"verdict": "thin"}}}
s1_ = ms.sgp_support(cmb, [dict(H, pid="h0"), dict(H, pid="h1")], so)
s2_ = ms.sgp_support(cmb, [{"pid": "h3", "stat": "hr", "line": .5}, W], so)
check("a kind that has not beaten stays THIN; a beaten one with 100+ can reach STRONG",
      s1_["in_range"] and s2_["untested"] and s2_["why"] == "not_beaten")

# --- 4. the nightly's build -----------------------------------------------------------------
mpp.SIM_MIN_STATES = 5000
mpp.SIM_TEST_N = 1200
model = mpp.build_prop_model(DF, tempfile.mkdtemp(), validation_days=20, prior={})
blk = model.get("sim") or {}
print(f"     build: {blk.get('n_games')} games graded, runs check {blk.get('runs_check')}, kinds "
      f"{sorted((blk.get('combos') or {}))}")
check("the nightly measures the transitions and grades every kind on the window",
      (blk.get("transitions") or {}).get("n", 0) > 5000 and blk.get("n_games", 0) >= 40
      and {"HH", "HHH", "TT", "HW", "RW", "KW", "HHopp"} <= set(blk.get("combos") or {})
      and abs(blk["runs_check"]["sim"] / blk["runs_check"]["actual"] - 1) < 0.12)
small = mpp.build_sim(PA.head(3000), model, 20)
check("too few plate appearances with a state: a note, not a simulator", "note" in small)

# --- 5. wiring ------------------------------------------------------------------------------
import ast  # noqa: E402
_tree = ast.parse((ROOT / "precompute.py").read_text(encoding="utf-8"))
_mc = next(ast.literal_eval(n.value) for n in _tree.body if isinstance(n, ast.Assign)
           and getattr(n.targets[0], "id", None) == "MODEL_COLS")
check("the nightly's season frame carries the base-out state",
      {"inning", "outs_when_up", "on_1b", "on_2b", "on_3b"} <= set(_mc)
      and set(mpp.STATE_COLS) <= set(mpp.EXTRA_COLS))
check("the prop model build runs the simulator in its own try",
      "model[\"sim\"] = build_sim(pa, model, validation_days)" in
      (ROOT / "mlb_prop_precompute.py").read_text(encoding="utf-8"))
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
pg = (ROOT / "app" / "views" / "MLB_Sim.py").read_text(encoding="utf-8")
check("the Simulator is in the MLB nav and prices SGPs with the graded guard",
      '("Simulator", "views/MLB_Sim.py")' in app and "ms.sgp_support(combos, legs, info)" in pg
      and "ms.sgp_guard(" in pg and '_blu.log_button("MLB"' in pg)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall MLB simulator checks passed")
