"""
NHL batch (10-09): power-play minutes, the 2+ goals line, NHL Player of
the Day, the multi-goal watch and the multi-goal check.

Plain script — exits non-zero on failure. Fixtures carry the shapes the
feed and the nightly really have: ESPN summary groups (labels, athletes,
stats), nhl_model prop rows (probs, gp, pp, last_game, team_last_game),
props_validation blocks, top_plays_log.nhl_box_by_event boxes — rule 5.
Every file written goes to a temp directory (no test writes data/).

Negative controls, confirmed red by exit code when written (rule 4):
  - nhl_player_of_the_day without the missed-last-game gate
    -> "a skater who missed his team's last game is not eligible" fails
  - grade_multi_snapshot grading while a game is still unfinished
    -> "a night is graded only when every game is final" fails
  - pp_units answering "-" for everyone when no row has PP minutes
    -> "no PP minutes in the feed is unknown, not zero" fails
"""
import json
import math
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

import nhl_precompute as npc  # noqa: E402
from engines import edge_boards as eb  # noqa: E402
from engines import nhl_model as nm  # noqa: E402
from engines import top_plays_board as tpb  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- 1. the parser: PP minutes when the feed has them, absent when not --
def summary(labels, stats):
    def team(tid, nm_):
        return {"team": {"id": tid, "displayName": nm_, "abbreviation": nm_[:3].upper()},
                "statistics": [{"name": "forwards", "labels": labels,
                                "athletes": [{"athlete": {"id": f"{tid}x", "displayName": "A B",
                                                          "position": {"abbreviation": "C"}},
                                              "stats": stats}]}]}
    return {"boxscore": {"teams": [], "players": [team("1", "Away"), team("2", "Home")]}}


sk = {}
npc.parse_summary(summary(["G", "A", "S", "TOI", "PPTOI"], ["1", "0", "3", "18:30", "2:45"]),
                  "e1", "2026-10-08", sk, {})
line = sk["1x"]["games"]["e1"]
check("PP TOI is parsed as minutes", abs(line.get("pptoi", -1) - 2.75) < 1e-9)
check("total TOI still parses", abs(line["toi"] - 18.5) < 1e-9)
sk2 = {}
npc.parse_summary(summary(["G", "A", "S", "TOI"], ["1", "0", "3", "18:30"]), "e2",
                  "2026-10-08", sk2, {})
check("no PP column means no PP value, not zero", "pptoi" not in sk2["1x"]["games"]["e2"])
check("the columns seen are recorded for the nightly probe line",
      "PPTOI" in npc.SEEN_SKATER_COLUMNS)

# --- 2. PP units ---------------------------------------------------------
rows = [{"pid": str(i), "pp": {"l5": 4.0 - 0.3 * i, "season": None}} for i in range(12)]
u = nm.pp_units(rows)
check("the top 5 by recent PP minutes are PP1",
      [u[str(i)] for i in range(5)] == ["PP1"] * 5)
check("the next 5 are PP2", [u[str(i)] for i in range(5, 10)] == ["PP2"] * 5)
check("under a minute a game is no unit", u["11"] == "-")      # 4.0 - 3.3 = 0.7
check("no PP minutes in the feed is unknown, not zero",
      nm.pp_units([{"pid": "1", "pp": {"l5": None, "season": None}}]) == {})

# --- 3. the 2+ goals line ----------------------------------------------
check("Goal O1.5 is a tested market", ("g2", "Goal O1.5", "g", 2) in nm.MARKETS)
check("the Goals board offers 1.5", dict((s, l) for s, _n, l in nm.STATS)["g"] == (0.5, 1.5))
r = {"sog": 3.0, "g": 0.45, "a": 0.5, "gp": 70}
pr = nm.probs(r)
mu = 0.45
check("2+ goals is the Poisson tail of the same goal mean",
      abs(pr["g2"] - round(1 - math.exp(-mu) * (1 + mu), 4)) < 1e-4)


# --- 4. Player of the Day ------------------------------------------------
def prop(pid, p_pt, gp=60, last="2026-10-07", team_last="2026-10-07", exp_pts=0.9):
    return {"pid": pid, "name": f"P{pid}", "pos": "C", "gp": gp,
            "probs": {"pt1": p_pt, "g1": 0.3, "g2": 0.05}, "exp_pts": exp_pts,
            "mu": {"g": 0.4}, "last_game": last, "team_last_game": team_last,
            "pp": {"unit": "PP1", "l5": 3.0}, "why": "because"}


FUTURE = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()


def slate(home_props, away_props=()):
    return [{"event_id": "g1", "game_type": "regular", "home": "Home Team",
             "away": "Away Team", "home_abbr": "HOM", "away_abbr": "AWY",
             "start_et": FUTURE, "time_et": "7:00 PM",
             "home_props": list(home_props), "away_props": list(away_props)}]


CAL = [{"band": "40-49%", "n": 500, "predicted": 0.45, "actual": 0.45},
       {"band": "60-69%", "n": 500, "predicted": 0.65, "actual": 0.60}]
model_ok = {"props_validation": {"pt1": {"verdict": {"verdict": "beats"}, "calibration": CAL},
                                 "g2": {"verdict": {"verdict": "beats"},
                                        "calibration": [{"band": "0-9%", "n": 900,
                                                         "predicted": 0.02, "actual": 0.02},
                                                        {"band": "10-19%", "n": 90,
                                                         "predicted": 0.115,
                                                         "actual": 0.065}]},
                                 "g1": {"verdict": {"verdict": "beats"}, "calibration": None}}}

pick, cands, note = eb.nhl_player_of_the_day(
    slate([prop("1", 0.62), prop("2", 0.66, gp=12), prop("3", 0.70, last="2026-10-05"),
           prop("4", 0.58)]), model_ok)
check("the best eligible 1+ point chance is the pick", pick and pick["pid"] == "1")
check("a skater under the games floor is not eligible", "2" not in [c["pid"] for c in cands])
check("a skater who missed his team's last game is not eligible",
      "3" not in [c["pid"] for c in cands])
check("the chance shown is the delivered one", abs(pick["chance"] - (0.45 + 0.15 * 0.85)) < 1e-6)
model_thin = {"props_validation": {"pt1": {"verdict": {"verdict": "thin"}, "calibration": CAL}}}
p2, c2, n2 = eb.nhl_player_of_the_day(slate([prop("1", 0.62)]), model_thin)
check("no pick off an untested 1+ point line", p2 is None and "tested" in (n2 or ""))
play = eb.potd_play(pick, "2026-10-08")
check("the logged play is a 1+ point play at the delivered chance",
      play["stat"] == "pts" and play["at_least"] == 1 and play["p_cal"] == round(pick["chance"], 4))

# --- 5. 2+ goals on Goal Edge and the multi-goal watch -----------------
gp = [dict(prop(str(i), 0.5), probs={"pt1": 0.5, "g1": 0.3, "g2": 0.02 + 0.01 * i})
      for i in range(12)]
g_rows = eb.nhl_goal_rows(slate(gp), model_ok)
w = eb.multi_goal_watch(g_rows, 3)
check("the watch is ranked by 2+ goal chance", [x["pid"] for x in w] == ["11", "10", "9"])
top = [x for x in g_rows if x["pid"] == "11"][0]
check("a 13% two-goal call is pulled to what such calls delivered",
      top["chance2"] < top["raw2"] and top["chance2"] < 0.09)

# --- 6. the multi-goal check -------------------------------------------
snap = eb.multi_goal_snapshot(g_rows, top=5)
check("the snapshot keeps the top names and how many were ranked",
      snap["n"] == 12 and len(snap["ranks"]) == 5 and snap["games"] == ["g1"])
two = {"g1": {"final": False, "players": {}}}
check("a night is graded only when every game is final",
      eb.grade_multi_snapshot(snap, two) is False and snap["scorers"] is None)
box = {"g1": {"final": True, "players": {"11": {"g": 2, "name": "P11"},
                                         "0": {"g": 3, "name": "P0"},
                                         "5": {"g": 1, "name": "P5"}}}}
check("a finished night is graded", eb.grade_multi_snapshot(snap, box) is True)
sc = {x["pid"]: x for x in snap["scorers"]}
check("two-goal scorers only", set(sc) == {"11", "0"})
check("a scorer the board had first is rank 1", sc["11"]["rank"] == 1)
check("a scorer outside the kept top has no rank", sc["0"]["rank"] is None)
sm = eb.multi_check_summary({"2026-10-08": snap}, top=5)
check("the yardstick is what a random list of the same size would catch",
      sm["caught"] == 1 and sm["scorers"] == 2 and abs(sm["random"] - 2 * 5 / 12) < 0.06)

# --- 7. the nightly, end to end, into a temp directory -----------------
with tempfile.TemporaryDirectory() as td:
    games = slate(gp)
    for r in games[0]["home_props"]:
        r["probs"]["pt1"] = 0.5 + 0.01 * int(r["pid"])
    npc.nhl_extra_boards(games, model_ok, {}, "2026-10-08", root=td)
    potd = tpb.load("nhl_potd", td)["plays"]
    mg = tpb.load("nhl_multigoal", td)["plays"]
    snaps = json.loads((Path(td) / npc.MULTI_SNAP_FILE).read_text())
    check("the nightly logs one Player of the Day", len(potd) == 1 and potd[0]["player_id"] == "11")
    check("the nightly logs the multi-goal watch (10 names)", len(mg) == 10
          and all(p["stat"] == "g" and p["at_least"] == 2 for p in mg))
    check("the nightly keeps tonight's ranking", "2026-10-08" in snaps)
    # next morning: finals in, graded
    skaters = {"11": {"name": "P11", "games": {"g1": {"g": 2, "a": 0, "sog": 5}}},
               "3": {"name": "P3", "games": {"g1": {"g": 0, "a": 1, "sog": 2}}}}
    npc.nhl_extra_boards([], model_ok, skaters, "2026-10-09", root=td)
    potd = tpb.load("nhl_potd", td)["plays"]
    snaps = json.loads((Path(td) / npc.MULTI_SNAP_FILE).read_text())
    check("the pick is graded off the box score", potd[0]["result"] == "hit")
    check("the night's two-goal scorers are recorded",
          [x["pid"] for x in snaps["2026-10-08"]["scorers"]] == ["11"])

# --- 8. wiring -----------------------------------------------------------
src = (ROOT / "nhl_precompute.py").read_text(encoding="utf-8")
check("the nightly calls the new boards",
      "nhl_extra_boards(slate, model_block, skaters, slate_date.isoformat())" in src)
wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the nightly commits the three new records",
      all(f in wf for f in ("data/top_plays/nhl_potd.json", "data/top_plays/nhl_multigoal.json",
                            "data/top_plays/nhl_multigoal_ranks.json")))
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("NHL Player of the Day is in the NHL nav",
      '("Player of the Day", "views/NHL_Player_Of_The_Day.py")' in app)
res = (ROOT / "app" / "views" / "Results.py").read_text(encoding="utf-8")
check("the scorecard judges both new records",
      '"nhl_potd"' in res and '"nhl_multigoal"' in res)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NHL batch checks passed")
