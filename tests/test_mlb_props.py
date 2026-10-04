"""
MLB prop model — engines/mlb_props.py (reader) and mlb_prop_precompute.py
(nightly builder + walk-forward validation).

Plain script — exits non-zero on failure. The fixture is a simulated
season of plate appearances in the SEASON FRAME's real shape (game_date,
game_pk, at_bat_number, events with Statcast's own event names, batter,
pitcher, inning_topbot "Top"/"Bot"), with known batter and pitcher skill
and starters pulled after a known number of batters.

Negative controls, confirmed red by exit code when written (rule 4):
  - combine() ignoring the pitcher -> "a tougher starter lowers the hit
    chance" fails
  - slot_pa off by one (T - slot + 1) // 9 -> the exact-arithmetic
    section fails
  - the validation baseline computed from games INCLUDING the one being
    predicted -> "hits markets beat the player's own frequency" fails
    (a peeking baseline scores too well to be beaten). The separate
    baseline_brier > 0.19 floor stayed GREEN under that control — it is
    a sanity floor, not the guard; the comparison is.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import mlb_props as mp       # noqa: E402
import mlb_prop_precompute as mpp          # noqa: E402

# Never read the repo's real last-season file from a fixture test (rule 5:
# the fixture's players are not real players). test_prior_season.py
# tests the prior path with its own fixture.
mpp.PRIOR_PATH = Path(__file__).resolve().parent / "_no_such_prior.json"

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# ------------------------------------------------- 1. exact arithmetic
check("slot 1 bats 5 times when the team sends 37", mp.slot_pa(1, 37) == 5)
check("slot 9 bats 4 times when the team sends 37", mp.slot_pa(9, 37) == 4)
check("slot 2 bats 4 times when the team sends 37", mp.slot_pa(2, 37) == 4)
check("slot 9 bats 3 times when the team sends 35", mp.slot_pa(9, 35) == 3)
check("2-hole vs a starter: twice if he faces 19, three times if he faces 20 (PA #2, #11, #20)",
      mp.pa_vs_starter(2, 4, 19) == 2 and mp.pa_vs_starter(2, 4, 20) == 3)
check("statcast event names map to outcomes",
      mp.classify("home_run") == "HR" and mp.classify("strikeout_double_play") == "K"
      and mp.classify("hit_by_pitch") == "BB" and mp.classify("grounded_into_double_play") == "OUT"
      and mp.classify("truncated_pa") is None and mp.classify(None) is None)

# --------------------------------------------- fixture: a PA-level season
EV = {"1B": "single", "2B": "double", "3B": "triple", "HR": "home_run",
      "BB": "walk", "K": "strikeout", "OUT": "field_out"}
LG = {"1B": .14, "2B": .045, "3B": .004, "HR": .03, "BB": .09, "K": .22, "OUT": .471}


def season(seed=5, days=75, teams=16):
    g = random.Random(seed)

    def skill(sd):
        m = {o: v * g.lognormvariate(0, sd) for o, v in LG.items()}
        t = sum(m.values())
        return {o: v / t for o, v in m.items()}
    bat = {t: [10000 + t * 20 + i for i in range(11)] for t in range(teams)}
    bs = {b: skill(.25) for t in bat for b in bat[t]}
    rot = {t: [50000 + t * 10 + i for i in range(5)] for t in range(teams)}
    pen = {t: [60000 + t * 10 + i for i in range(4)] for t in range(teams)}
    ps = {p: skill(.22) for t in rot for p in rot[t] + pen[t]}
    rows, gpk, nxt = [], 0, {t: 0 for t in range(teams)}
    from collections import defaultdict as _dd
    score = _dd(int)
    for d in range(days):
        day = (date(2026, 4, 1) + timedelta(d)).isoformat()
        ts = list(range(teams))
        g.shuffle(ts)
        for i in range(0, teams, 2):
            gpk += 1
            ab = 0
            h, a = ts[i], ts[i + 1]
            sp = {"home": rot[h][nxt[h] % 5], "away": rot[a][nxt[a] % 5]}
            nxt[h] += 1
            nxt[a] += 1
            order = {"home": g.sample(bat[h], 9), "away": g.sample(bat[a], 9)}
            idx = {"home": 0, "away": 0}
            faced = {"home": 0, "away": 0}
            lim = {"home": g.randint(18, 28), "away": g.randint(18, 28)}
            for inning in range(1, 10):
                for half, bside, fside, pteam in (("Top", "away", "home", h), ("Bot", "home", "away", a)):
                    outs = 0
                    while outs < 3:
                        b = order[bside][idx[bside] % 9]
                        idx[bside] += 1
                        p = sp[fside] if faced[bside] < lim[bside] else pen[pteam][inning % 4]
                        faced[bside] += 1
                        raw = {o: bs[b][o] * ps[p][o] / LG[o] for o in LG}
                        r, acc = g.random() * sum(raw.values()), 0.0
                        for o, v in raw.items():
                            acc += v
                            if r <= acc:
                                break
                        outs += o in ("K", "OUT")
                        ab += 1
                        # runs on the play, from a KNOWN conditional the
                        # RBI table must recover (HR always drives one in)
                        u = g.random()
                        rbi = {"HR": 1 + (u < .40) + (u < .15) + (u < .03),
                               "1B": int(u < .15), "2B": int(u < .30), "3B": int(u < .50),
                               "BB": int(u < .02), "OUT": int(u < .04), "K": 0}[o]
                        before = score[(gpk, bside)]
                        score[(gpk, bside)] = before + rbi
                        rows.append({"game_date": day, "game_pk": gpk, "at_bat_number": ab,
                                     "pitch_number": 1, "events": EV[o], "batter": b,
                                     "pitcher": p, "inning_topbot": half,
                                     "bat_score": before, "post_bat_score": before + rbi})
    return pd.DataFrame(rows), bs, ps


df, bs, ps = season()

# ------------------------------------------------ 2. measurement + priors
pa = mpp.plate_appearances(df)
check("one row per PA, every outcome classified", len(pa) == len(df) and pa["outcome"].notna().all())
lus = mpp.lineups(pa)
check("lineups recovered: nine distinct bats per side",
      lus and all(len(set(v)) == 9 for v in lus.values()))
starts = mpp.starts_table(pa)
check("one starter per side per game, BF within the fixture's 18-28 window",
      all(18 <= s[4] <= 28 for s in starts) and len(starts) == 2 * pa["game_pk"].nunique())
try:
    mpp.plate_appearances(df.drop(columns=["inning_topbot"]))
    check("a frame without inning_topbot is REFUSED, not guessed", False)
except ValueError:
    check("a frame without inning_topbot is REFUSED, not guessed", True)

out_dir = Path(__file__).resolve().parent / "_tmp_prop_model"
model = mpp.build_prop_model(df, out_dir)
try:
    (out_dir / "prop_model.json").unlink()
    out_dir.rmdir()
except OSError:
    pass
check("model built", model is not None)
check("league HR rate measured near the fixture's 3%", abs(model["league_rates"]["HR"] - 0.03) < 0.004)

# ------------------------------------------------------ 3. the reader
avg = {o: int(LG[o] * 600) for o in mp.OUTCOMES}
avg["PA"] = sum(avg[o] for o in mp.OUTCOMES)
good = dict(avg, **{"1B": avg["1B"] + 40, "OUT": avg["OUT"] - 40})
tough = dict(avg, **{"1B": avg["1B"] - 40, "K": avg["K"] + 40})
bfd = mp.starter_bf_dist([24] * 20, model)
base = mp.project_batter(3, avg, avg, model, bfd)
check("a better hitter has a higher hit chance",
      mp.project_batter(3, good, avg, model, bfd)["probs"]["h1"] > base["probs"]["h1"])
check("a tougher starter lowers the hit chance and raises the K chance",
      mp.project_batter(3, avg, tough, model, bfd)["probs"]["h1"] < base["probs"]["h1"]
      and mp.project_batter(3, avg, tough, model, bfd)["probs"]["k1"] > base["probs"]["k1"])
check("leadoff expects more PAs than the 9-hole",
      mp.project_batter(1, avg, avg, model, bfd)["exp_pa"]
      > mp.project_batter(9, avg, avg, model, bfd)["exp_pa"])
check("2+ hits is always rarer than 1+",
      all(mp.project_batter(s, avg, avg, model, bfd)["probs"]["h2"]
          < mp.project_batter(s, avg, avg, model, bfd)["probs"]["h1"] for s in range(1, 10)))

# ----------------------------------------------- 4. walk-forward honesty
v = model["validation"]
for k, label, *_ in mp.MARKETS:
    cal = [c for c in v[k]["calibration"] if c["n"] >= 150]
    check(f"{label}: calibrated within 6 points in every band with 150+ games",
          cal and all(abs(c["predicted"] - c["actual"]) < 0.06 for c in cal))
check("hits markets beat the player's own frequency (the fixture has real skill)",
      v["h1"]["beats_baseline"] and v["h2"]["beats_baseline"])
check("beats_baseline is exactly the Brier comparison",
      all(v[k]["beats_baseline"] == (v[k]["model_brier"] < v[k]["baseline_brier"])
          for k, *_ in mp.MARKETS if v[k]["n"]))
rg = model["rbi_given"]
check("RBI table recovered: a home run always drives one in, ~40% drive in 2+",
      rg and rg["all"]["HR"][0] == 0.0 and abs(sum(rg["all"]["HR"][2:]) - 0.40) < 0.04)
check("...a single drives one in ~15% of the time, a strikeout never",
      abs(rg["all"]["1B"][1] - 0.15) < 0.02 and rg["all"]["K"][0] == 1.0)
avg_c = {o: int(1000 * LG[o]) for o in LG}
avg_c["PA"] = sum(avg_c.values())
bfd0 = mp.starter_bf_dist([22] * 10, model)
pj = mp.project_batter(4, avg_c, avg_c, model, bfd0)
check("every stat's pmf sums to 1", all(abs(sum(v) - 1) < 1e-4 for v in pj["pmfs"].values()))
check("any-line agrees with the table: P(TB >= 2) from the pmf IS the TB O1.5 cell",
      abs(mp.mm.prob_at_least(pj["pmfs"]["tb"], 2) - pj["probs"]["tb2"]) < 1e-4)
check("RBI priced only because the season measured it (the table exists)", "rbi1" in pj["probs"])
no_rbi = dict(model, rbi_given=None)
check("no RBI table -> no RBI market (left out, never zero)",
      "rbi1" not in mp.project_batter(4, avg_c, avg_c, no_rbi, bfd0)["probs"])
pv = model["pitcher_validation"]
check("every starter market was scored on the same few hundred starts",
      len({pv[k]["n"] for k, *_ in mp.PITCHER_MARKETS}) == 1 and pv["pk5"]["n"] > 300)
# Calibration bands on ~480 starts are too noisy to hold to a few points
# (the TRUE probabilities miss by 11 in one band on this fixture), so the
# check is against the truth itself: start by start, the model's expected
# strikeouts must track what the fixture's real skills imply.
_pa = mpp.plate_appearances(df)
_bcum, _pcum = mpp._cum_before(_pa, "batter"), mpp._cum_before(_pa, "pitcher")
_lus = mpp.lineups(_pa)
_hist = {}
for _g, _s, _sp, _d, _bf in sorted(mpp.starts_table(_pa), key=lambda x: x[3]):
    _hist.setdefault(_sp, []).append((_d, _bf))
_cut = sorted(_pa["game_date"].unique())[-30]
_m, _t = [], []
for _g, _s, _sp, _d, _bf in mpp.starts_table(_pa):
    _order = _lus.get((_g, _s))
    _before = [b for dd, b in _hist[_sp] if dd < _d]
    _pc = mpp._counts_at(_pcum, _sp, _d)
    if _d < _cut or not _order or not _before or not _pc:
        continue
    _bfd = mp.starter_bf_dist(_before, model)
    _pr = mp.project_pitcher([mpp._counts_at(_bcum, b, _d) for b in _order], _pc, model, _bfd)
    _true = 0.0
    for _bfv, _w in _bfd.items():
        for j in range(int(_bfv)):
            _b = _order[j % 9]
            _raw = {o: bs[_b][o] * ps[_sp][o] / LG[o] for o in LG}
            _true += _w * _raw["K"] / sum(_raw.values())
    _m.append(_pr["exp"]["k"])
    _t.append(_true)
_mm, _mt = sum(_m) / len(_m), sum(_t) / len(_t)
_cov = sum((a - _mm) * (b - _mt) for a, b in zip(_m, _t))
_corr = _cov / ((sum((a - _mm) ** 2 for a in _m) * sum((b - _mt) ** 2 for b in _t)) ** 0.5)
check(f"starter K: no bias against the truth (model {_mm:.2f} vs true {_mt:.2f} per start)",
      abs(_mm - _mt) < 0.15)
check(f"starter K: tracks the true expectation start by start (r = {_corr:.2f})", _corr > 0.8)
check("starter K props beat his own strikeout frequency (the fixture has real skill)",
      pv["pk5"]["model_brier"] < pv["pk5"]["baseline_brier"])
ace = {o: int(1000 * v) for o, v in {"1B": .12, "2B": .04, "3B": .003, "HR": .02, "BB": .06,
                                      "K": .32, "OUT": .437}.items()}
ace["PA"] = sum(ace.values())
p_avg = mp.project_pitcher([avg_c] * 9, avg_c, model, bfd0)
p_ace = mp.project_pitcher([avg_c] * 9, ace, model, bfd0)
check("an ace's strikeout line is higher and his hits-allowed line lower",
      p_ace["exp"]["k"] > p_avg["exp"]["k"] and p_ace["exp"]["h"] < p_avg["exp"]["h"])
check("a starter who goes deeper faces more batters and strikes out more",
      mp.project_pitcher([avg_c] * 9, avg_c, model, mp.starter_bf_dist([27] * 30, model))["exp"]["k"]
      > mp.project_pitcher([avg_c] * 9, avg_c, model, mp.starter_bf_dist([18] * 30, model))["exp"]["k"])
# This fixture gives every starter the same 18-28 BF window, so the
# fitted strength is huge (his own record says nothing) — correct. With a
# small strength his own history must move the number.
_own = dict(model, bf_strength_starts=1.0)
check("expected batters faced follows his own history when the fit says it should",
      abs(mp.project_pitcher([avg_c] * 9, avg_c, _own,
                             mp.starter_bf_dist([22] * 30, _own))["exp_bf"] - 22) < 0.6)
check("...and the league's when the fit says his own record carries nothing",
      abs(p_avg["exp_bf"] - 23) < 0.6)

# A baseline that peeks at the game it predicts would score impossibly
# well; with honest (earlier-games-only) frequencies the baseline Brier
# on 1+ hit must stay near the irreducible ~0.22, not collapse toward 0.
check("the baseline does not see the game it is predicting",
      v["h1"]["baseline_brier"] > 0.19)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
