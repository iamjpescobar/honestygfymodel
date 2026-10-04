"""
NHL model — nhl_prior_season.py (last season's collector), engines/nhl_model
(game model + skater props) and its wiring into nhl_precompute.main.

Plain script — exits non-zero on failure. The fixture is a simulated
season with KNOWN team strengths and skater shot rates, served through
ESPN's site.web.api HEADER shape (flat competitors, fullStatus, NO
season block) and the summary box-score shape test_nhl_pipeline uses —
because that header shape is what production gets, and it drops the
season type the collector first relied on (rule 5).

Negative controls, confirmed red by exit code when written (rule 4):
  - the collector's date-window fallback removed (season type required)
    -> "header shape: every regular-season final collected" fails
  - skater props ignoring the matchup (ratios forced to 1.0) -> the
    "a weak defence raises shot chances" check fails
  - league constants measured on this season's handful of games while
    the fit is on last season -> "constants come from the fitted season"
    fails
"""
import json
import math
import os
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import nhl_precompute as hpc          # noqa: E402
import nhl_prior_season as nps        # noqa: E402
from engines import espn_feed as ef   # noqa: E402
from engines import nhl_model as nm   # noqa: E402

failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


# ------------------------------------------------------------- fixture
SEED = int(os.environ.get("NHL_FIXTURE_SEED", "11"))
RNG = random.Random(SEED)
TEAMS = {str(100 + i): (f"Club {i}", f"C{i:02d}") for i in range(16)}
STR = {t: (math.exp(RNG.gauss(0, .12)), math.exp(RNG.gauss(0, .10)),
           math.exp(RNG.gauss(0, .10)), math.exp(RNG.gauss(0, .10))) for t in TEAMS}
ROSTER = {}
for t in TEAMS:
    ROSTER[t] = []
    for j in range(12):
        pos = "D" if j < 4 else "C"
        base = 1.4 if pos == "D" else 2.4
        ROSTER[t].append((f"{t}{j:02d}", f"Skater {t}-{j}", pos,
                          base * math.exp(RNG.gauss(0, .35))))

SK_KEYS = ["goals", "assists", "plusMinus", "shotsTotal", "blockedShots", "hits",
           "penaltyMinutes", "timeOnIce"]
G_KEYS = ["goalsAgainst", "shotsAgainst", "saves", "savePct", "timeOnIce"]


def _nb(mu, r, g):
    lam = g.gammavariate(r, mu / r)
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= g.random()
        if p < L:
            return k
        k += 1


def _comp(tid, side, score):
    n, a = TEAMS[tid]
    return {"homeAway": side, "score": str(score), "id": tid, "displayName": n,
            "abbreviation": a, "color": "cc0000", "logo": f"https://x/{a}.png"}


def _ev(eid, iso, status, away, home, a_s=0, h_s=0, detail="Final", odds=None):
    return {"id": eid, "date": iso,
            "fullStatus": {"type": {"name": status, "completed": status == "STATUS_FINAL",
                                    "shortDetail": detail}},
            "competitors": [_comp(away, "away", a_s), _comp(home, "home", h_s)],
            "odds": odds or {"details": "", "overUnder": 6.0}}


def _players(tid, lines, goalie_line):
    sk = {"name": "forwards", "labels": ["G", "A", "+/-", "S", "BS", "HT", "PIM", "TOI"],
          "keys": SK_KEYS,
          "athletes": [{"athlete": {"id": pid, "displayName": nm, "position": {"abbreviation": pos}},
                        "stats": [str(g), str(a), "0", str(s), "0", "0", "0", "18:00"]}
                       for pid, nm, pos, g, a, s in lines]}
    gg = {"name": "goalies", "labels": ["GA", "SA", "SV", "SV%", "TOI"], "keys": G_KEYS,
          "athletes": [{"athlete": {"id": f"g{tid}", "displayName": f"Goalie {tid}"},
                        "starter": True, "stats": goalie_line}]}
    return {"team": {"id": tid, "displayName": TEAMS[tid][0], "abbreviation": TEAMS[tid][1]},
            "statistics": [sk, gg]}


def _side(tid, opp, home, g):
    off_s, def_s, off_g, def_g = STR[tid]
    shot_env = off_s * STR[opp][1] * (1.03 if home else 0.97)
    lines, shots = [], 0
    for pid, name, pos, rate in ROSTER[tid]:
        s = _nb(rate * shot_env, 6, g)
        shots += s
        lines.append([pid, name, pos, 0, 0, s])
    goals = _nb(3.0 * off_g * STR[opp][3] * (1.04 if home else 0.96), 30, g)
    for _ in range(goals):
        w = [ln[5] + 0.3 for ln in lines]
        i = g.choices(range(len(lines)), weights=w)[0]
        lines[i][3] += 1
        for _a in range(g.choice([0, 1, 1, 2, 2])):
            j = g.choices(range(len(lines)), weights=w)[0]
            if j != i:
                lines[j][4] += 1
    return lines, shots, goals


def make_days(start, n_days, prefix, per_day=6, scheduled_from=None):
    # NOT hash(prefix): string hashing is salted per process, so that
    # simulated a different season on every run and the suite went red
    # one run in several. A fixed seed per prefix.
    g = random.Random(sum(ord(c) * 31 ** i for i, c in enumerate(prefix)) + SEED)
    days, summaries = {}, {}
    for d in range(n_days):
        day = start + timedelta(days=d)
        ids = list(TEAMS)
        g.shuffle(ids)
        evs = []
        for k in range(per_day):
            away, home = ids[2 * k], ids[2 * k + 1]
            eid = f"{prefix}{d:03d}{k}"
            iso = f"{day.isoformat()}T23:00Z"
            if scheduled_from and day >= scheduled_from:
                evs.append(_ev(eid, iso, "STATUS_SCHEDULED", away, home,
                               odds={"details": "", "overUnder": 6.5,
                                     "homeTeamOdds": {"moneyLine": -140},
                                     "awayTeamOdds": {"moneyLine": 120}}))
                continue
            a_lines, a_sog, a_g = _side(away, home, False, g)
            h_lines, h_sog, h_g = _side(home, away, True, g)
            period = 3
            if a_g == h_g:
                period = 4
                if g.random() < 0.55:
                    h_g += 1
                else:
                    a_g += 1
            evs.append(_ev(eid, iso, "STATUS_FINAL", away, home, a_g, h_g,
                           "Final/OT" if period == 4 else "Final"))
            summaries[eid] = {
                "header": {"competitions": [{"status": {"period": period}}]},
                "boxscore": {
                    "teams": [{"team": {"id": away, "displayName": TEAMS[away][0],
                                        "abbreviation": TEAMS[away][1]},
                               "statistics": [{"name": "shotsTotal", "displayValue": str(a_sog)}]},
                              {"team": {"id": home, "displayName": TEAMS[home][0],
                                        "abbreviation": TEAMS[home][1]},
                               "statistics": [{"name": "shotsTotal", "displayValue": str(h_sog)}]}],
                    "players": [_players(away, a_lines, [str(h_g), str(h_sog), str(h_sog - h_g), ".900", "60:00"]),
                                _players(home, h_lines, [str(a_g), str(a_sog), str(a_sog - a_g), ".900", "60:00"])]}}
        days[day.strftime("%Y%m%d")] = evs
    return days, summaries


PRIOR_DAYS, PRIOR_SUMM = make_days(date(2025, 10, 7), 150, "P")
CUR_DAYS, CUR_SUMM = make_days(date(2026, 9, 29), 5, "C", scheduled_from=date(2026, 10, 3))
ALL_DAYS = {**PRIOR_DAYS, **CUR_DAYS}
ALL_SUMM = {**PRIOR_SUMM, **CUR_SUMM}


def fake_get(url, _attempts=3):
    if "scoreboard/header" in url or "scoreboard?" in url:
        return {"sports": [{"leagues": [{"events": ALL_DAYS.get(url.rsplit("dates=", 1)[1][:8], [])}]}]}
    if "/summary?event=" in url:
        return ALL_SUMM.get(url.rsplit("=", 1)[1], {})
    if "/roster" in url:
        return {"athletes": []}
    raise RuntimeError(url)


saved = (ef.get_json, hpc.time.sleep, nps.time.sleep)
ef.get_json, hpc.time.sleep, nps.time.sleep = fake_get, (lambda *_a: None), (lambda *_a: None)
ef._PREFERRED.clear()
try:
    # ---------------------------------------------- 1. prior collector
    finals, skaters, goalies, names, seen, parsed = nps.collect(
        lambda d: ef.fetch_scoreboard("nhl", d.strftime("%Y%m%d"))[0],
        lambda eid: ef.fetch_summary("nhl", eid),
        start=date(2025, 10, 1), end=date(2026, 3, 10), sleep=0)
    n_prior = sum(len(v) for v in PRIOR_DAYS.values())
    check(f"header shape: every regular-season final collected ({len(finals)} of {n_prior})",
          len(finals) == n_prior)
    check("OT finals flagged from the box score period",
          any(f["extra"] for f in finals) and any(f["extra"] is False for f in finals))
    check("team shots carried on every final",
          all(f["home_sog"] is not None for f in finals))
    check("finals keyed by team ID, not display name",
          all(f["home"] in TEAMS for f in finals))
    check("skater lines carry date, opponent ID and SOG",
          skaters and all(x[1] in TEAMS and x[2] is not None
                          for s in skaters.values() for x in s["games"]))
    prior = {"season": "2025-26", "finals": finals, "skaters": skaters,
             "goalies": goalies, "team_names": names}

    # ------------------------------------------- 2. the pipeline, wired
    tmp_prior = Path(tempfile.mkdtemp()) / "prior.json"
    tmp_prior.write_text(json.dumps(prior))
    hpc.PRIOR_PATH = tmp_prior
    hpc.PICKS_ROOT = tmp_prior.parent / "model_picks"
    hpc.TOP_PLAYS_ROOT = tmp_prior.parent / "top_plays"
    cwd, tmp = os.getcwd(), tempfile.mkdtemp()
    os.chdir(tmp)
    try:
        hpc.main(today=date(2026, 10, 3))
        out = json.loads((Path(tmp) / "build_data/data/nhl/games.json").read_text())
    finally:
        os.chdir(cwd)
    mb = out.get("model")
    check("games.json carries a model block", bool(mb))
    check("fitted on the PRIOR season while this one is days old",
          mb and mb["params"]["fit_on"] == "prior")
    check("constants come from the fitted season, not this week's handful",
          mb and mb["league"].get("from") == "prior" and mb["league"]["games"] == len(finals))
    v = mb["validation"]
    check(f"game model beats the coin flip on last season walk-forward "
          f"({v['model']['log_loss']} vs {v['coin_flip']['log_loss']})", v["beats_coin"])
    check("OT home-win rate measured (not defaulted)", mb["league"]["tie_home_win"] is not None)
    games = out["games"]
    check("every slate game projected", games and all(g.get("model") for g in games))
    g0 = games[0]
    check("market moneylines reached the projection (no-vig gap computed)",
          "edge_home" in g0["model"] and "p_over" in g0["model"])
    check("props on both sides", all(g.get("home_props") and g.get("away_props") for g in games))

    # --------------------------------------------- 3. props behave
    pv = mb["props_validation"]
    for k in ("sog2", "sog3", "sog4"):
        x = pv[k]
        check(f"{k}: beats the skater's own hit rate on last season ({x['model_brier']} vs "
              f"{x['baseline_brier']})", x["beats_baseline"])
        cal = [c for c in x["calibration"] if c["n"] >= 200]
        check(f"{k}: calibrated within 6 points where populated",
              cal and all(abs(c["predicted"] - c["actual"]) < 0.06 for c in cal))
    pri = mb["skater_priors"]
    check("defencemen and forwards get separate priors, D shoot less",
          pri["D"]["sog"][0] < pri["F"]["sog"][0])
    r = {"sog": 2.5, "g": 0.3, "a": 0.4, "gp": 50}
    base = nm.probs(r, 1.0, 1.0, pri.get("sog_dispersion"))
    soft = nm.probs(r, 1.15, 1.15, pri.get("sog_dispersion"))
    check("a weak defence (more shots/goals expected) raises shot and point chances",
          soft["sog3"] > base["sog3"] and soft["pt1"] > base["pt1"])
    env = [g.get("home_env") for g in games if g.get("home_env")]
    check("matchup ratios are live (not all 1.0)",
          env and any(abs(e["shot_ratio"] - 1) > 1e-3 for e in env))
    check("3+ shots always rarer than 2+",
          all(p["probs"]["sog3"] <= p["probs"]["sog2"] for g in games for p in g["home_props"]))
finally:
    ef.get_json, hpc.time.sleep, nps.time.sleep = saved

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
