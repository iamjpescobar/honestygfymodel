"""
LAST SEASON AS EVIDENCE (10-04): how much last season counts is FITTED,
never chosen — and a last season that says nothing must earn nothing.

Covers model_math.fit_prior_weight, the MLB game model's carryover and
starter weight (mlb_model_precompute), the MLB prop model's player
weights (mlb_prop_precompute), and the NFL player-prop merge
(nfl_precompute.merge_prior / nfl prior weights).

Every weight is checked twice on fixtures whose truth is KNOWN: once
where players/teams keep their skill across seasons (the weight must be
large), once where last season is SHUFFLED across players (the weight
must be ~0). The shuffle is a live negative control inside the test.

Negative controls, confirmed red by exit code when written (rule 4):
  - fit_prior_weight scoring this season against THIS season's own counts
    (x1 in the predictor) -> the shuffled check fails
  - starter_layer ignoring prior_rec -> "a starter with only last season
    on record still gets a layer" fails
  - mlb_props.with_prior ignoring the weight (adds last season at 1.0)
    -> "weight 0 leaves counts untouched" fails
"""
import json
import math
import random
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import model_math as mm       # noqa: E402
from engines import mlb_game_model as mgm  # noqa: E402
from engines import mlb_props as mp        # noqa: E402
import mlb_model_precompute as mpc         # noqa: E402
import mlb_prop_precompute as mpp          # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# ------------------------------------------------- 1. the weight itself
g = random.Random(4)
stable, shuffled = [], []
for _ in range(300):
    p = g.betavariate(40, 60)
    n0, n1 = g.randint(150, 600), g.randint(150, 600)
    stable.append(((sum(g.random() < p for _ in range(n0)), n0),
                   (sum(g.random() < p for _ in range(n1)), n1)))
lasts = [s[0] for s in stable]
g.shuffle(lasts)
shuffled = [(l, s[1]) for l, s in zip(lasts, stable)]
w_st = mm.fit_prior_weight([(stable, 0.4, 100.0)])
w_sh = mm.fit_prior_weight([(shuffled, 0.4, 100.0)])
check(f"skill that persists: last season earns a large weight ({w_st['weight']})",
      w_st["weight"] > 0.6 and w_st["loglik_gain"] > 50)
check(f"last season SHUFFLED across players earns ~nothing ({w_sh['weight']})",
      w_sh["weight"] < 0.15)
check("the rate formula: weight 0 is this season + league prior only",
      mm.prior_season_rate(50, 100, 10, 40, 0.3, 20, 0.0) == (10 + 0.3 * 20) / (40 + 20))

# --------------------------------------------- 2. statsapi season counts
counts = mpc.parse_season_counts({"stats": [{"splits": [
    {"player": {"id": 1}, "stat": {"plateAppearances": 600, "hits": 150, "doubles": 30,
                                   "triples": 2, "homeRuns": 25, "baseOnBalls": 60,
                                   "hitByPitch": 5, "strikeOuts": 120}},
    # traded: two team lines and the combined one — the combined is kept
    {"player": {"id": 2}, "stat": {"plateAppearances": 200, "hits": 50, "doubles": 10,
                                   "triples": 0, "homeRuns": 5, "baseOnBalls": 20, "strikeOuts": 40}},
    {"player": {"id": 2}, "stat": {"plateAppearances": 500, "hits": 125, "doubles": 25,
                                   "triples": 1, "homeRuns": 12, "baseOnBalls": 50, "strikeOuts": 100}},
    {"player": {"id": 3}, "stat": {"plateAppearances": 300, "hits": 70, "homeRuns": 9,
                                   "baseOnBalls": 20, "strikeOuts": 70}},     # no 2B/3B
]}]}, "hitting")
c1 = counts["1"]
check("season line -> the seven outcomes (singles = H - 2B - 3B - HR; HBP is a walk)",
      c1["1B"] == 93 and c1["BB"] == 65 and c1["K"] == 120 and c1["OUT"] == 600 - 150 - 65 - 120)
check("a traded player's largest line is kept, never the parts added to it",
      counts["2"]["PA"] == 500)
check("a line without doubles/triples is LEFT OUT, not split by a guess", "3" not in counts)

# ------------------------------------- 3. the starter layer with last season
pri = {"outs_mean": 16.0, "outs_strength_starts": 5.0, "ra9_mean": 4.5, "ra9_strength_games": 4.0}
ace_last = {"r": 50, "outs": 540, "gs": 30}
lay = mgm.starter_layer(None, pri, 4.5, ace_last, {"ra": 0.6, "outs": 0.7})
check("a starter with only LAST season on record still gets a layer", lay is not None)
check("...and an ace's last season lowers his run rate below the league's",
      lay and lay[1] < 4.5)
check("weight 0 for last season -> no record this season means no layer",
      mgm.starter_layer(None, pri, 4.5, ace_last, {"ra": 0.0, "outs": 0.0}) is None)

# ------------------------------------- 4. MLB props: with_prior and weights
cur = {"1B": 10, "2B": 3, "3B": 0, "HR": 2, "BB": 5, "K": 12, "OUT": 28, "PA": 60}
last = {"1B": 90, "2B": 30, "3B": 2, "HR": 30, "BB": 60, "K": 110, "OUT": 278, "PA": 600}
check("weight 0 leaves this season's counts untouched", mp.with_prior(cur, last, 0.0) == cur)
half = mp.with_prior(cur, last, 0.5)
check("weight 0.5 adds half of last season, and says how much of each",
      half["HR"] == 17 and half["PA"] == 360 and half["PA_last_season"] == 600)

src = (ROOT / "tests" / "test_mlb_props.py").read_text()
src = src.split("df, bs, ps = season()")[0].replace(
    "Path(__file__)", f'Path("{ROOT / "tests" / "x.py"}")')
ns = {}
exec(compile(src, "mlb_props_fixture", "exec"), ns)
df, bs, ps = ns["season"]()
LG = ns["LG"]


def last_season(skill, n_lo, n_hi, seed):
    gg = random.Random(seed)
    out = {}
    for pid, sk in skill.items():
        n = gg.randint(n_lo, n_hi)
        c = {o: 0 for o in mp.OUTCOMES}
        for _ in range(n):
            r, acc = gg.random(), 0.0
            for o, v in sk.items():
                acc += v
                if r <= acc:
                    break
            c[o] += 1
        c["PA"] = n
        out[str(pid)] = c
    return out


prior_b = last_season(bs, 300, 650, 8)
prior_p = last_season(ps, 300, 800, 9)
tmp = Path(tempfile.mkdtemp())
m_with = mpp.build_prop_model(df, tmp / "a", prior={"season": 2025, "batters": prior_b,
                                                   "pitchers": prior_p, "starters": {}})
keys = list(prior_b)
vals = list(prior_b.values())
random.Random(3).shuffle(vals)
m_shuf = mpp.build_prop_model(df, tmp / "b", prior={"season": 2025,
                                                   "batters": dict(zip(keys, vals)),
                                                   "pitchers": {}, "starters": {}})
m_none = mpp.build_prop_model(df, tmp / "c", prior={})
wb = m_with["prior_weight"]["batter"]
check(f"MLB props: a batter's real last season earns weight ({wb})", wb > 0.4)
check(f"MLB props: a SHUFFLED last season earns ~none ({m_shuf['prior_weight']['batter']})",
      m_shuf["prior_weight"]["batter"] < 0.15)
b_with = m_with["validation"]["k1"]["model_brier"]
b_none = m_none["validation"]["k1"]["model_brier"]
check(f"folding in last season improves the walk-forward (K O0.5 Brier {b_with} vs {b_none})",
      b_with < b_none)
check("the weights and last season's counts ship in prop_model.json",
      m_with["prior_batters"] and m_with["prior_season"] == 2025)


# ------------------------------- 5. MLB game model: carryover from 2025
def two_seasons(shuffle_teams=False, seed=21):
    gg = random.Random(seed)
    teams = [f"Club {i}" for i in range(20)]
    st = {t: (math.exp(gg.gauss(0, .14)), math.exp(gg.gauss(0, .12))) for t in teams}
    rot = {t: [str(1000 + i * 10 + j) for j in range(5)] for i, t in enumerate(teams)}
    spq = {p: math.exp(gg.gauss(0, .35)) for t in teams for p in rot[t]}

    def season(year, days, strength):
        games, logs = [], {}
        nxt = {t: 0 for t in teams}
        for d in range(days):
            day = (date(year, 4, 1) + timedelta(d)).isoformat()
            ts = teams[:]
            gg.shuffle(ts)
            for i in range(0, 20, 2):
                h, a = ts[i], ts[i + 1]
                hp, ap = rot[h][nxt[h] % 5], rot[a][nxt[a] % 5]
                nxt[h] += 1
                nxt[a] += 1
                dh = strength[h][1] * (1 / 3 + 2 / 3 * spq[hp])
                da = strength[a][1] * (1 / 3 + 2 / 3 * spq[ap])
                hs = ns_nb(4.5 * strength[h][0] * da * 1.03)
                as_ = ns_nb(4.5 * strength[a][0] * dh / 1.03)
                inn = 9
                while hs == as_:
                    inn += 1
                    hs += gg.random() < .3
                    as_ += gg.random() < .28
                games.append({"gamePk": len(games) + year * 10000, "officialDate": day,
                              "status": {"abstractGameState": "Final", "detailedState": "Final"},
                              "linescore": {"currentInning": inn, "scheduledInnings": 9},
                              "teams": {"home": {"team": {"name": h}, "score": hs,
                                                 "probablePitcher": {"id": int(hp), "fullName": "P" + hp}},
                                        "away": {"team": {"name": a}, "score": as_,
                                                 "probablePitcher": {"id": int(ap), "fullName": "P" + ap}}}})
                for p, ra in ((hp, as_), (ap, hs)):
                    outs = gg.randint(12, 21)
                    logs.setdefault(p, []).append({"date": day, "stat": {
                        "gamesStarted": 1, "inningsPitched": f"{outs // 3}.{outs % 3}",
                        "battersFaced": outs + gg.randint(3, 9),
                        "runs": max(0, round(ra * outs / 27 * gg.uniform(.7, 1.3)))}})
        return games, logs

    def ns_nb(mu, r=4.0):
        lam = gg.gammavariate(r, mu / r)
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= gg.random()
            if p < L:
                return k
            k += 1

    s25 = st
    if shuffle_teams:
        vals = list(st.values())
        gg.shuffle(vals)
        s25 = dict(zip(teams, vals))
    g25, l25 = season(2025, 170, s25)
    g26, l26 = season(2026, 90, st)

    def get(url):
        m = re.search(r"startDate=([\d-]+)&endDate=([\d-]+)", url)
        if m:
            s_, e_ = m.groups()
            pool = g25 if s_.startswith("2025") else g26
            return {"dates": [{"games": [x for x in pool if s_ <= x["officialDate"] <= e_]}]}
        m = re.search(r"people/(\d+)/stats.*season=(\d+)", url)
        if m:
            logs = l25 if m.group(2) == "2025" else l26
            return {"stats": [{"splits": logs.get(m.group(1), [])}]}
        if "stats=season" in url:
            return {"stats": [{"splits": []}]}
        return None
    return get


def run_mlb(get):
    d = Path(tempfile.mkdtemp())
    mpc.OUT, mpc.PRIOR_PATH = d / "model.json", d / "prior.json"
    old_min = mpc.PRIOR_MIN_FINALS
    mpc.PRIOR_MIN_FINALS = 1000              # the fixture season is 170 days
    try:
        mpc.main(today=date(2026, 7, 1), _get_json=get)
    finally:
        mpc.PRIOR_MIN_FINALS = old_min
    return json.loads((d / "model.json").read_text()), d


model, d = run_mlb(two_seasons())
check("last season's file is written once (and the test's own sandbox, not the repo)",
      (d / "prior.json").exists() and not (ROOT / "data" / "mlb" / "prior_season.json").exists())
check(f"MLB teams that keep their strength: carryover fitted well above 0 "
      f"({model['params'].get('carryover')})", (model["params"].get("carryover") or 0) > 0.3)
spw = model.get("starter_prior_weight") or {}
check(f"MLB starters who keep their quality: last season earns weight ({spw.get('ra')})",
      (spw.get("ra") or 0) > 0.3)
check("last season's starter lines ship with the model", bool(model.get("starters_prior")))
model_sh, _d2 = run_mlb(two_seasons(shuffle_teams=True))
check(f"teams SHUFFLED between seasons: carryover ~0 ({model_sh['params'].get('carryover')})",
      (model_sh["params"].get("carryover") or 0) < 0.25)

# ------------------------------------------ 6. NFL players: merge + weights
import nfl_precompute as nfp  # noqa: E402

cur = {"pid": "9", "team": "BUF", "carry_share": 0.5, "ypc": 6.0, "gp": 2,
       "tot": {"games": 2, "car": 20, "tc": 40, "tgt": 2, "tt": 60, "rec": 2, "ry": 120,
               "cy": 10, "td": 2, "td_games": 2, "opps": 22, "pa_games": 0}}
prev = {"team": "MIA", "tot": {"games": 17, "car": 170, "tc": 425, "tgt": 30, "tt": 560,
                               "rec": 24, "ry": 680, "cy": 200, "td": 6, "td_games": 17,
                               "opps": 200, "pa_games": 0}}
m0 = nfp.merge_prior(cur, prev, {k: 0.0 for k in ("share", "catch", "ypc", "ypt", "td",
                                                  "qb_rate", "ypa")})
check("NFL: weight 0 leaves his carry share and ypc where this season put them",
      m0["carry_share"] == 0.5 and m0["ypc"] == 6.0)
m1 = nfp.merge_prior(cur, prev, {"share": 1.0, "ypc": 1.0, "td": 1.0})
check("NFL: weight 1 pools the evidence (190 of 465 carries; 800 yds on 190)",
      m1["carry_share"] == round(190 / 465, 3) and m1["ypc"] == round(800 / 190, 2))
check("NFL: touchdowns become weighted sums the TD estimator reads",
      m1["td_total"] == 8 and m1["td_games"] == 19)
check("NFL: a player who changed teams is flagged with last season's team",
      m1.get("last_season_team") == "MIA" and m1["gp_last_season"] == 17)
check("NFL: no last season -> the summary is returned untouched",
      nfp.merge_prior(cur, None, {"share": 1.0}) is cur)

gq = random.Random(11)
players, prev_players, prev_shuf = {}, {}, {}
for i in range(150):
    sh = gq.betavariate(4, 12)
    tc0, tc1 = gq.randint(380, 480), gq.randint(90, 130)
    c0 = sum(gq.random() < sh for _ in range(tc0))
    c1 = sum(gq.random() < sh for _ in range(tc1))
    players[str(i)] = {"tot": {"car": c1, "tc": tc1}}
    prev_players[str(i)] = {"tot": {"car": c0, "tc": tc0}}
keys, vals = list(prev_players), list(prev_players.values())
gq.shuffle(vals)
prev_shuf = dict(zip(keys, vals))
w_real, _r = nfp.prior_weights(players, prev_players)
w_fake, _r2 = nfp.prior_weights(players, prev_shuf)
check(f"NFL: a carry share that persists earns last season real weight ({w_real['share']})",
      w_real["share"] > 0.4)
check(f"NFL: last season SHUFFLED across players earns ~none ({w_fake['share']})",
      w_fake["share"] < 0.15)
logs = {"1": {"name": "QB One", "team": "BUF", "pos": "QB", "games": {
    "e1": {"date": "2025-09-07", "event_id": "e1", "team": "BUF",
           "passing": {"att": 30, "cmp": 20, "yds": 250, "td": 2, "int": 1},
           "rushing": {"att": 4, "yds": 20, "td": 0}}}}}
summ = nfp.player_summaries(logs, nfp.team_game_usage(logs))
check("player_summaries carries raw totals for the merge",
      summ["1"]["tot"]["pa_att"] == 30 and summ["1"]["tot"]["car"] == 4)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
