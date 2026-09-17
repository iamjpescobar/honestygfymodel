"""NHL pipeline, end to end, against ESPN-shaped fixtures.

Same flattened header shape as the NFL test (rule 5). Checks:
  1. the slate LOOKS AHEAD to the next date with games during the gap;
  2. exhibition finals are parsed (parser check) and counted NOWHERE;
  3. regular-season finals build W-L-OTL, shot share, PP/PK, goalie
     SV%/GAA/crease share and skater SOG/points/hit rates correctly;
  4. an OT loss is an OTL, a regulation loss is an L, and a loss whose
     length cannot be known is flagged rather than silently guessed;
  5. a dressed-but-did-not-play line is NOT a zero game;
  6. finals that parse into nothing refuse to publish;
  7. slate_guard reads the NHL file with Eastern dating.
"""
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import nhl_precompute as hpc  # noqa: E402
from engines import espn_feed as ef  # noqa: E402
from engines import nhl_rink as nr  # noqa: E402

failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


TEAMS = {"10": ("Carolina Hurricanes", "CAR"), "11": ("Florida Panthers", "FLA"),
         "12": ("Boston Bruins", "BOS"), "13": ("New York Rangers", "NYR")}


def _comp(tid, side, score):
    n, a = TEAMS[tid]
    return {"homeAway": side, "score": str(score), "id": tid, "displayName": n,
            "abbreviation": a, "color": "cc0000", "logo": f"https://x/{a}.png"}


def _ev(eid, iso, status, away, home, a_s=0, h_s=0, detail="Final"):
    return {"id": eid, "date": iso, "location": "Lenovo Center",
            "fullStatus": {"type": {"name": status, "completed": status == "STATUS_FINAL",
                                    "shortDetail": detail}},
            "competitors": [_comp(away, "away", a_s), _comp(home, "home", h_s)],
            "odds": {"details": "CAR -1.5", "overUnder": 6.0}}


DAYS = {
    "20260920": [_ev("p1", "2026-09-20T23:00Z", "STATUS_FINAL", "10", "11", 3, 2)],  # exhibition
    "20260929": [_ev("r1", "2026-09-29T21:00Z", "STATUS_FINAL", "11", "10", 2, 3, "Final/OT"),
                 _ev("r2", "2026-09-30T00:00Z", "STATUS_FINAL", "13", "12", 1, 4)],
    "20260930": [_ev("r3", "2026-09-30T23:00Z", "STATUS_FINAL", "10", "12", 2, 5, "Final")],
    "20261001": [_ev("r4", "2026-10-01T23:00Z", "STATUS_SCHEDULED", "12", "10"),
                 _ev("r5", "2026-10-01T23:30Z", "STATUS_SCHEDULED", "11", "13")],
}

SK_KEYS = ["goals", "assists", "plusMinus", "shotsTotal", "blockedShots", "hits",
           "penaltyMinutes", "timeOnIce"]
G_KEYS = ["goalsAgainst", "shotsAgainst", "saves", "savePct", "timeOnIce"]


def _team_box(tid, sog, ppg, ppo):
    return {"team": {"id": tid, "displayName": TEAMS[tid][0], "abbreviation": TEAMS[tid][1]},
            "statistics": [{"name": "shotsTotal", "displayValue": str(sog)},
                           {"name": "powerPlayGoals", "displayValue": str(ppg)},
                           {"name": "powerPlayOpportunities", "displayValue": str(ppo)}]}


def _players(tid, skaters, goalies, with_keys=True):
    sk = {"name": "forwards", "labels": ["G", "A", "+/-", "S", "BS", "HT", "PIM", "TOI"],
          "athletes": [{"athlete": {"id": pid, "displayName": nm,
                                    "position": {"abbreviation": "C"}}, "stats": st}
                       for pid, nm, st in skaters]}
    gg = {"name": "goalies", "labels": ["GA", "SA", "SV", "SV%", "TOI"],
          "athletes": [{"athlete": {"id": pid, "displayName": nm}, "starter": start, "stats": st}
                       for pid, nm, start, st in goalies]}
    if with_keys:
        sk["keys"], gg["keys"] = SK_KEYS, G_KEYS
    return {"team": {"id": tid, "displayName": TEAMS[tid][0], "abbreviation": TEAMS[tid][1]},
            "statistics": [sk, gg]}


def summ(away, home, a_sog, h_sog, a_pp, h_pp, a_sk, h_sk, a_g, h_g, period=3, keys=True):
    return {"header": {"competitions": [{"status": {"period": period}}]},
            "boxscore": {"teams": [_team_box(away, a_sog, *a_pp), _team_box(home, h_sog, *h_pp)],
                         "players": [_players(away, a_sk, a_g, keys),
                                     _players(home, h_sk, h_g, keys)]}}


SUMMARIES = {
    "p1": summ("10", "11", 30, 25, (1, 3), (0, 2),
               [("s1", "Seth Jarvis", ["2", "0", "1", "6", "0", "1", "0", "18:00"])],
               [("s3", "Sam Reinhart", ["1", "1", "0", "4", "0", "0", "0", "19:00"])],
               [("g1", "Frederik Andersen", True, ["2", "25", "23", ".920", "60:00"])],
               [("g3", "Sergei Bobrovsky", True, ["3", "30", "27", ".900", "60:00"])]),
    # FLA @ CAR, CAR wins 3-2 in OT (period 4). Label-only groups here.
    "r1": summ("11", "10", 28, 35, (1, 4), (1, 3),
               [("s3", "Sam Reinhart", ["1", "1", "0", "5", "1", "2", "0", "20:30"]),
                ("s9", "Scratch Guy", ["0", "0", "0", "0", "0", "0", "0", "--"])],
               [("s1", "Seth Jarvis", ["2", "1", "1", "4", "0", "1", "0", "19:15"]),
                ("s2", "Andrei Svechnikov", ["1", "0", "1", "3", "0", "3", "2", "18:00"])],
               [("g3", "Sergei Bobrovsky", True, ["3", "35", "32", ".914", "63:10"])],
               [("g1", "Frederik Andersen", True, ["2", "28", "26", ".929", "63:10"])],
               period=4, keys=False),
    # NYR @ BOS 1-4 regulation
    "r2": summ("13", "12", 24, 33, (0, 2), (2, 5),
               [("s7", "Artemi Panarin", ["1", "0", "-2", "3", "0", "0", "0", "21:00"])],
               [("s5", "David Pastrnak", ["2", "1", "2", "7", "0", "1", "0", "20:00"])],
               [("g7", "Igor Shesterkin", True, ["4", "33", "29", ".879", "60:00"])],
               [("g5", "Jeremy Swayman", True, ["1", "24", "23", ".958", "60:00"])]),
    # CAR @ BOS 2-5 regulation; CAR's backup starts
    "r3": summ("10", "12", 31, 29, (0, 3), (1, 2),
               [("s1", "Seth Jarvis", ["0", "0", "-1", "1", "1", "2", "0", "17:00"])],
               [("s5", "David Pastrnak", ["1", "0", "1", "2", "0", "0", "0", "19:00"])],
               # Kochetkov starts and is pulled; Andersen finishes in
               # RELIEF. Without a two-goalie game the start-crediting
               # control cannot go red (rule 4).
               [("g2", "Pyotr Kochetkov", True, ["5", "21", "16", ".762", "40:00"]),
                ("g1", "Frederik Andersen", False, ["0", "8", "8", "1.000", "20:00"])],
               [("g5", "Jeremy Swayman", True, ["2", "31", "29", ".935", "60:00"])]),
}


def fake_get(url, _attempts=3, summaries=None):
    summaries = SUMMARIES if summaries is None else summaries
    if "scoreboard/header" in url:
        return {"sports": [{"leagues": [{"events": DAYS.get(url.rsplit("dates=", 1)[1], [])}]}]}
    if "/summary?event=" in url:
        return summaries.get(url.rsplit("=", 1)[1], {})
    if "/roster" in url:
        return {"athletes": []}
    raise RuntimeError(url)


def run(get, today):
    saved = (ef.get_json, hpc.time.sleep)
    ef.get_json, hpc.time.sleep = get, (lambda *_a: None)
    ef._PREFERRED.clear()
    cwd, tmp = os.getcwd(), tempfile.mkdtemp()
    os.chdir(tmp)
    try:
        hpc.main(today=today)
        return json.loads((Path(tmp) / "build_data/data/nhl/games.json").read_text())
    finally:
        os.chdir(cwd)
        ef.get_json, hpc.time.sleep = saved


# ---------------------------------------------------------------- 1, 2
pre = run(fake_get, date(2026, 9, 15))
check("Sep 15: lookahead finds the Sep 20 exhibition slate",
      pre["slate_date_et"] == "2026-09-20" and len(pre["games"]) == 1)
check("pre-opening game typed as preseason", pre["games"][0]["game_type"] == "preseason")
check("phase is offseason on Sep 15", pre["phase"] == "offseason")

mid = run(fake_get, date(2026, 9, 22))
check("exhibition final parsed as a parser check", mid["exhibition_finals_parsed"] == 1)
check("...and counted NOWHERE", mid["teams"] == {} and mid["goalies"] == {}
      and mid["regular_finals_parsed"] == 0)

# ---------------------------------------------------------------- 3, 4
out = run(fake_get, date(2026, 10, 1))
check("Oct 1 slate is today's two games",
      out["slate_date_et"] == "2026-10-01" and len(out["games"]) == 2)
check("three regular finals parsed", out["regular_finals_parsed"] == 3)
t = out["teams"]
check("FLA lost in OT -> 0-0-1", t["Florida Panthers"]["record"] == "0-0-1")
check("CAR 1-1-0 (OT win, regulation loss)", t["Carolina Hurricanes"]["record"] == "1-1-0")
check("BOS 2-0-0, 4 pts, 100 pts%",
      t["Boston Bruins"]["record"] == "2-0-0" and t["Boston Bruins"]["pts_pct"] == 100.0)
check("FLA OTL is worth a point (50 pts%)", t["Florida Panthers"]["pts_pct"] == 50.0)
car = t["Carolina Hurricanes"]
check("CAR shots for/g = (35+31)/2", car["sf_pg"] == 33.0)
check("CAR shots against/g = (28+29)/2", car["sa_pg"] == 28.5)
check("CAR shot share = 66/123", car["sf_pct"] == round(100 * 66 / 123, 1))
check("CAR PP% = 1/6", car["pp_pct"] == round(100 / 6, 1))
check("CAR PK% = 1 - 2/6", car["pk_pct"] == round(100 - 100 * 2 / 6, 1))
check("known-length losses are not flagged", "otl_unverified" not in car)

g = out["goalies"]
check("Andersen SV% pooled over start + relief: 34/36",
      g["g1"]["sv_pct"] == round(34 / 36, 3))
check("Andersen GAA from 63:10 + 20:00 of ice",
      g["g1"]["gaa"] == round(2 * 60 / (83 + 10 / 60), 2))
check("relief appearance is a GP, not a start",
      g["g1"]["gp"] == 2 and g["g1"]["starts"] == 1)
check("L5 SV% counts STARTS only (26/28)", g["g1"]["l5_sv_pct"] == 0.929)
check("CAR crease share: Andersen 1 of 2, Kochetkov 1 of 2",
      g["g1"]["crease_share"] == "1 of 2" and g["g2"]["crease_share"] == "1 of 2")
check("exhibition start NOT in Andersen's sample (2 regular GP, not 3)", g["g1"]["gp"] == 2)
check("Swayman 2 starts, 52/55", g["g5"]["starts"] == 2 and g["g5"]["sv_pct"] == round(52 / 55, 3))

bos_game = next(x for x in out["games"] if x["event_id"] == "r4")
pas = next(p for p in bos_game["away_skaters"] if p["name"] == "David Pastrnak")
check("Pastrnak 4.5 SOG/G, 2.0 P/G", pas["sog"] == 4.5 and pas["pts"] == 2.0)
check("Pastrnak 2+ SOG in 2 of 2 games = 100%", pas["sog2_rate"] == 100)
check("Pastrnak 3+ SOG in 1 of 2 = 50%", pas["sog3_rate"] == 50)
jar = next(p for p in bos_game["home_skaters"] if p["name"] == "Seth Jarvis")
check("Jarvis: exhibition hat-trick of shots NOT counted (gp 2)", jar["gp"] == 2)
check("Jarvis 1+ PT in 1 of 2", jar["pt1_rate"] == 50)
all_sk = [p for x in out["games"] for s in ("away", "home") for p in x[f"{s}_skaters"]]
check("dressed-not-played skater is not a zero game",
      not any(p["name"] == "Scratch Guy" for p in all_sk))
check("goalies attached to the card, most starts first",
      [x["name"] for x in bos_game["away_goalies"]][0] == "Jeremy Swayman")

# unknowable OT: strip period AND detail
unk = json.loads(json.dumps(SUMMARIES))
unk["r3"]["header"] = {}
DAYS_SAVED = json.loads(json.dumps(DAYS))
DAYS["20260930"][0]["fullStatus"]["type"]["shortDetail"] = ""
try:
    u = run(lambda url, _attempts=3: fake_get(url, _attempts, unk), date(2026, 10, 1))
finally:
    DAYS.clear()
    DAYS.update(DAYS_SAVED)
check("a loss of unknowable length is FLAGGED, not silently a regulation L",
      u["teams"]["Carolina Hurricanes"].get("otl_unverified") == 1)
check("went_to_extra: period 4 True, 3 False, unknown None",
      hpc.went_to_extra({"header": {"competitions": [{"status": {"period": 4}}]}}) is True
      and hpc.went_to_extra({"header": {"competitions": [{"status": {"period": 3}}]}}) is False
      and hpc.went_to_extra({}, "") is None)

# ---------------------------------------------------------------- 6
dead = {k: {} for k in SUMMARIES}
try:
    run(lambda url, _attempts=3: fake_get(url, _attempts, dead), date(2026, 10, 1))
    check("unparseable finals refuse to publish", False)
except RuntimeError as exc:
    check("unparseable finals refuse to publish", "ZERO box scores" in str(exc))

# ---------------------------------------------------------------- 7
from engines.slate_guard import _LEAGUES, payload_field  # noqa: E402
check("slate_guard knows NHL with Eastern dating",
      _LEAGUES.get("nhl") == ("slate_date_et", "generated_at_et", "America/New_York"))
check("payload_field is callable", callable(payload_field))
check("phase boundaries", nr.phase(date(2026, 9, 18)) == "offseason"
      and nr.phase(date(2026, 9, 19)) == "preseason"
      and nr.phase(date(2026, 9, 29)) == "regular")
check("countdown on Sep 15 says 14 days", nr.countdown_text(date(2026, 9, 15)).startswith("14 days"))
check("save pct prints hockey-style", nr.fmt_svp(0.9123) == ".912" and nr.fmt_svp(None) == "\u2014")
rows = nr.shots_rows(out["games"], "season", 1)
check("shots rows sorted by SOG/G (Reinhart 5.0 over Pastrnak 4.5)",
      [r["Skater"] for r in rows[:2]] == ["Sam Reinhart", "David Pastrnak"])
check("Reinhart's 4-shot EXHIBITION game is not in his sample",
      rows[0]["GP"] == 1 and rows[0]["SOG/G"] == 5.0)
check("crease rows filter to tonight",
      all(r["Team"] in ("CAR", "BOS", "FLA", "NYR") for r in
          nr.crease_rows(out["goalies"], {"Carolina Hurricanes"}))
      and len(nr.crease_rows(out["goalies"], {"Carolina Hurricanes"})) == 2)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nAll NHL pipeline checks passed.")
