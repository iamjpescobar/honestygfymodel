"""
NHL shot attempts and scoring chances (10-22) — engines/nhl_shots (iCF,
iFF, iSF, iSCF, iHDCF from the NHL's own play-by-play), the match to
ESPN ids, the backfill (nhl_shots_prior.py + its workflow), the two
factors in engines/nhl_model (attempts -> SOG, chances -> goals: fitted,
tested, adopted only on "beats"), the nightly and the NHL Model page.

Plain script — exits non-zero on failure. Play-by-play in the NHL feed's
shape (homeTeam / awayTeam ids, rosterSpots with firstName.default,
plays with typeDescKey, periodDescriptor.periodType, details.xCoord /
yCoord / zoneCode / shootingPlayerId / scoringPlayerId,
homeTeamDefendingSide) (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - a blocked attempt counted as unblocked
    -> "a blocked attempt is in iCF only" fails
  - the shootout read as play
    -> "the shootout never counts" fails
  - the net always taken at +89 (the side each team attacks ignored)
    -> "a chance is read toward the net the shooter attacks" fails
  - the last-name fallback without the first initial
    -> "a different first initial is not a match" fails
  - shot_scales applying a fit that was not adopted
    -> "a factor that did not beat stays out of the number" fails
"""
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nhl_model as nm  # noqa: E402
from engines import nhl_shots as ns  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def spot(pid, first, last, team, pos="C"):
    return {"playerId": pid, "teamId": team, "positionCode": pos,
            "firstName": {"default": first}, "lastName": {"default": last}}


def play(kind, shooter, x, y, per=1, ptype="REG", side="left", zone="O", goal=False):
    det = {"xCoord": x, "yCoord": y, "zoneCode": zone}
    det["scoringPlayerId" if goal else "shootingPlayerId"] = shooter
    return {"typeDescKey": kind, "periodDescriptor": {"number": per, "periodType": ptype},
            "homeTeamDefendingSide": side, "details": det}


# home (10) defends LEFT in period 1 -> home attacks the net at x = +89;
# in period 2 the teams switch ends.
PBP = {"homeTeam": {"id": 10}, "awayTeam": {"id": 20},
       "rosterSpots": [spot(1, "Tim", "Stützle", 10), spot(2, "Brady", "Tkachuk", 10, "L"),
                       spot(3, "Mitchell", "Marner", 20, "R"), spot(4, "Jake", "Sanderson", 10, "D"),
                       spot(9, "Linus", "Ullmark", 10, "G")],
       "plays": [
           play("shot-on-goal", 1, 80, 2),                    # inner slot: HD + SC
           play("goal", 1, 84, -5, goal=True),                # HD goal
           play("missed-shot", 1, 60, 15),                    # 29 ft out, wide: SC not HD
           play("blocked-shot", 1, 82, 0),                    # blocked: iCF only
           play("shot-on-goal", 2, 40, 0),                    # point shot: neither
           play("shot-on-goal", 3, -80, 3),                   # away attacks -89 in P1: HD
           play("shot-on-goal", 3, 80, 3, per=2, side="right"),  # P2: away attacks +89: HD
           play("shot-on-goal", 2, -80, 3),                   # home at the WRONG end: not
           play("goal", 1, 85, 0, per=5, ptype="SO", goal=True),  # shootout: never
           play("faceoff", 1, 0, 0)]}
R = ns.parse_pbp(PBP)
S = R["shots"]
check("iCF / iFF / iSF / goals: a blocked attempt is in iCF only; a goal is a shot on goal",
      S["1"][:4] == [4, 3, 2, 1])
check("the shootout never counts", R["kinds"].get("goal") == 1 and S["1"][3] == 1)
check("a chance is read toward the net the shooter attacks (ends switch by period)",
      S["3"][4:6] == [2, 2] and S["2"][4:6] == [0, 0])
check("scoring chances vs high danger by spot; goals from each spot kept for the league rate",
      S["1"][4:8] == [3, 2, 1, 1])
pz = json.loads(json.dumps(PBP))
for p_ in pz["plays"]:
    p_.pop("homeTeamDefendingSide", None)
Z = ns.parse_pbp(pz)["shots"]
check("without the defending side, the zone code decides the net (an O-zone shot)",
      Z["1"][4:6] == [3, 2] and Z["3"][5] == 2)
check("danger(): the crease and the slot are high danger; the point and behind-the-net far "
      "out are not",
      ns.danger(86, 0, 89) == (True, True) and ns.danger(55, 0, 89) == (True, False)
      and ns.danger(30, 0, 89) == (False, False) and ns.danger(-86, 1, -89) == (True, True)
      and ns.danger(80, 20, 89) == (False, False))

# --- matching to ESPN ---------------------------------------------------------------------
espn = {"e1": "Tim Stutzle", "e2": "Brady Tkachuk", "e3": "Mitch Marner",
        "e4": "Thomas Sanderson", "e9": "Linus Ullmark"}
M = ns.match_game(R, espn)
check("names match across feeds: accents, Mitch for Mitchell (same last name and initial)",
      M.get("1") == "e1" and M.get("2") == "e2" and M.get("3") == "e3")
check("a different first initial is not a match; goalies are not skaters",
      "4" not in M and "9" not in M)
games = {"g1": {"x": "Connor McDavid", "y": "Leon Draisaitl"},
         "g2": {**espn, **{f"z{i}": f"Player {chr(97 + i)}" for i in range(6)}}}
R2 = dict(R, players=dict(R["players"], **{str(100 + i): {"name": f"Player {chr(97 + i)}", "pos": "C"}
                                            for i in range(6)}))
PBP2 = dict(PBP, rosterSpots=PBP["rosterSpots"] + [spot(100 + i, "Player", chr(97 + i), 20)
                                                   for i in range(6)])
check("the ESPN game is the one sharing the most skater names",
      ns.best_game(R2, games) == "g2" and ns.best_game(R, games) is None)
ck = ns.check({("d", "e1"): S["1"], ("d", "e3"): S["3"]}, {("d", "e1"): 2, ("d", "e3"): 5})
check("the check compares his shots on goal with ESPN's box",
      ck == {"skater_games": 2, "sog_ok": 1})

# --- the backfill, with a fake feed -------------------------------------------------------------
import nhl_shots_prior as nsp  # noqa: E402
from datetime import date  # noqa: E402
calls = []


def fake_get(url):
    calls.append(url)
    if "/schedule/" in url:
        return {"gameWeek": [{"date": "2025-10-08", "games": [
            {"id": 77, "gameType": 2, "gameState": "OFF"},
            {"id": 78, "gameType": 1, "gameState": "OFF"},
            {"id": 79, "gameType": 2, "gameState": "FUT"}]}]}
    return PBP2 if url.endswith("/77/play-by-play") else {}


gl = nsp.schedule_games(fake_get, date(2025, 10, 7), date(2025, 10, 9))
rows, st_, _s = nsp.collect(fake_get, gl, {"2025-10-08": games}, sleep=0)
check("the backfill reads finished regular-season games only, keyed (date, ESPN id)",
      gl == [("2025-10-08", 77)] and rows[("2025-10-08", "e1")] == S["1"]
      and ("2025-10-08", "e4") not in rows and st_["skater_games"] == 3)
src = (ROOT / "nhl_shots_prior.py").read_text(encoding="utf-8")
wf = (ROOT / ".github" / "workflows" / "nhl-shots-prior.yml").read_text(encoding="utf-8")
check("the backfill refuses a file that doesn't match ESPN, and its workflow commits it",
      "Refusing to write" in src and "return 1" in src and "python nhl_shots_prior.py" in wf
      and "git add data/nhl/prior_shots.json" in wf and "workflow_dispatch" in wf)

# --- the factors ---------------------------------------------------------------------------------
# A world where WHERE he shoots decides his goals: goals per attempt 0.20
# from the inner slot, 0.09 other chances, 0.025 the rest. His goal rate
# from 12 games is noisy; his chances say more.
rng = random.Random(5)
C = (0.20, 0.09, 0.025)


def pois(lam):
    k, t = 0, rng.expovariate(1.0)
    while t < lam:
        k += 1
        t += rng.expovariate(1.0)
    return k


skaters, rows_tr, rows_te = {}, [], []
for i in range(3000):
    hd_r, md_r, ld_r = rng.uniform(0.1, 1.4), rng.uniform(0.2, 1.2), rng.uniform(0.5, 2.5)
    lam = hd_r * C[0] + md_r * C[1] + ld_r * C[2]
    smap = {}
    for k in range(12):
        hd, md, ld = pois(hd_r), pois(md_r), pois(ld_r)
        ghd = sum(1 for _ in range(hd) if rng.random() < C[0])
        gmd = sum(1 for _ in range(md) if rng.random() < C[1])
        gld = sum(1 for _ in range(ld) if rng.random() < C[2])
        iff = hd + md + ld
        isf = sum(1 for _ in range(iff) if rng.random() < 0.6)
        smap[f"2025-11-{k + 1:02d}"] = [iff + pois(0.5), iff, max(isf, ghd + gmd + gld),
                                        ghd + gmd + gld, hd + md, hd, ghd + gmd, ghd]
    skaters[str(i)] = {"shots": smap}
    n, t = ns.window(smap, sorted(smap))
    r = {"sog": (t[2] + 2.0 * 3) / (n + 3), "g": (t[3] + 0.25 * 6) / (n + 6), "a": 0.3, "gp": n}
    y = pois(lam)
    row = (r, 1.0, 1.0, {"shots": (n, t)}, {"sog": pois(t[2] / n), "g": y, "a": 0, "pts": y},
           None)
    (rows_tr if i < 1000 else rows_te).append(row)
fit = nm.fit_shots(rows_tr, rows_te, {}, 8.0, skaters, "2025-12-01")
g_ = fit.get("g") or {}
print(f"     chances -> goals: strength {g_.get('fitted_strength')} verdict "
      f"{(g_.get('verdict') or {}).get('verdict')} z={(g_.get('verdict') or {}).get('z')}; league "
      f"{fit['league']}")
check("the league's goals per attempt by spot is measured (slot > other chances > the rest)",
      fit["league"]["c_hd"] > fit["league"]["c_md"] > fit["league"]["c_ld"]
      and abs(fit["league"]["c_hd"] - 0.20) < 0.03)
check("where chances decide goals, the chance factor is fitted, beats, and is adopted",
      g_.get("adopted") and g_["strength"] > 0.3)
no = nm.fit_shots(rows_tr, rows_te, {}, 8.0, {}, "2025-12-01")
check("with no attempt data loaded nothing is fitted and the page says how to get it",
      "note" in no and "sog" not in no and "NHL prior shots" in no["note"])
r0 = rows_te[0][0]
smap0 = skaters["1000"]["shots"]
games0 = [(d,) for d in sorted(smap0)]
toi_no = {"shots": dict(fit, g=dict(g_, adopted=False))}   # strength kept: adopted decides
s_no = nm.shot_scales(r0, games0, smap0, toi_no)
s_yes = nm.shot_scales(r0, games0, smap0, {"shots": fit})
check("a factor that did not beat stays out of the number (scale 1.0), its numbers shown",
      s_no["g"] == 1.0 and s_no.get("hd_pg") is not None and s_yes["g"] != 1.0)
p0 = nm.probs(r0, 1.0, 1.0, 8.0, att_sog=1.2, chance_g=1.5)
p1 = nm.probs(r0, 1.0, 1.0, 8.0)
check("the scales move the projection: SOG by the attempt scale, goals (not assists) by the "
      "chance scale",
      abs(p0["_mu"]["sog"] - 1.2 * p1["_mu"]["sog"]) < 1e-3
      and abs(p0["_mu"]["g"] - 1.5 * p1["_mu"]["g"]) < 1e-3
      and abs(p0["_mu"]["a"] - p1["_mu"]["a"]) < 1e-9)
check("under five games of attempt data he keeps today's number",
      nm.shot_ratios(r0, (4, [10] * 8), fit["league"]) is None)

# --- wiring ---------------------------------------------------------------------------------------
pc = (ROOT / "nhl_precompute.py").read_text(encoding="utf-8")
check("the nightly loads last season's file, reads this season from the NHL feed, prints the "
      "verdicts",
      "_nsh = load_prior_shots(prior, prior_path)" in pc
      and "current_shots(skaters, REGULAR_SEASON_START, today)" in pc
      and "attempts -> SOG" in pc and 'line["shots"] = row' in pc)
mdl = (ROOT / "app" / "engines" / "nhl_model.py").read_text(encoding="utf-8")
check("the model applies the factors wherever the number is made (props test, tonight)",
      mdl.count("shot_scales(r, games[:i], p.get(\"shots\"), toi)") == 1
      and "shot_scales(r, p[\"games\"], p.get(\"shots\"), toi)" in mdl
      and 'out["shots"] = fit_shots(train, test, out, disp, skaters, cut)' in mdl)
sim = (ROOT / "app" / "engines" / "nhl_sim.py").read_text(encoding="utf-8")
pg = (ROOT / "app" / "views" / "NHL_Model.py").read_text(encoding="utf-8")
check("the simulator's test rows and the NHL Model page carry them",
      "hm.shot_scales(r, games[:i], p.get(\"shots\"), toi)" in sim
      and '"Att/G", "HD/G", "xG/G"' in pg and "nm.shots_note(" in pg)
check("math sanity: league rates skip rows on/after the cut",
      ns.league_rates({"a": {"shots": {"2025-01-01": [1, 1, 1, 1, 1, 1, 1, 1],
                                       "2026-01-01": [9] * 8}}}, before="2025-06-01")["n"] == 1
      and math.isclose(nm._clip(5.0), 2.0))

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NHL shot attempt / chance checks passed")
