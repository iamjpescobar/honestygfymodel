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
                        rows.append({"game_date": day, "game_pk": gpk, "at_bat_number": ab,
                                     "pitch_number": 1, "events": EV[o], "batter": b,
                                     "pitcher": p, "inning_topbot": half})
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
          for k, *_ in mp.MARKETS))
# A baseline that peeks at the game it predicts would score impossibly
# well; with honest (earlier-games-only) frequencies the baseline Brier
# on 1+ hit must stay near the irreducible ~0.22, not collapse toward 0.
check("the baseline does not see the game it is predicting",
      v["h1"]["baseline_brier"] > 0.19)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
