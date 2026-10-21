"""
NBA play-by-play (10-21) — engines/nba_pbp and the one-time backfill
nba_pbp_prior.py: the tip, the first field goal (a free throw is not a
"first basket"), quarter lines, starters, per-quarter points.

Plain script — exits non-zero on failure. A summary in ESPN's NBA shape
(header.competitions[].competitors[].linescores, plays[], boxscore) —
rule 5. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - parse counting a free throw as the first field goal
    -> "the first field goal skips the and-one free throw" fails
  - the tip team read from the jump ball itself (it names no team)
    -> "the tip goes to the team with the first possession" fails
  - the backfill writing with too few games parsed
    -> "a shape change refuses to write" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nba_pbp as pb  # noqa: E402
import nba_pbp_prior as npp  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def play(t, text, per, clock, team=None, pids=(), scoring=False, value=0):
    p = {"type": {"text": t}, "text": text, "period": {"number": per},
         "clock": {"displayValue": clock}, "scoringPlay": scoring, "scoreValue": value,
         "participants": [{"athlete": {"id": x}} for x in pids]}
    if team:
        p["team"] = {"id": team}
    return p


def box(team, rows):
    return {"team": {"id": team}, "statistics": [{
        "labels": ["MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO",
                   "PF", "+/-", "PTS"],
        "athletes": [{"athlete": {"id": pid, "displayName": f"P{pid}",
                                  "position": {"abbreviation": "G"}}, "starter": st,
                      "stats": ["30", "5-10", "1-3", "2-2", "0", "4", "4", "3", "1", "0", "2",
                                "2", "+1", str(pts)]} for pid, st, pts in rows]}]}


SUMM = {
    "header": {"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": "1"}, "linescores": [
            {"displayValue": "30"}, {"displayValue": "25"}, {"displayValue": "28"},
            {"displayValue": "27"}]},
        {"homeAway": "away", "team": {"id": "2"}, "linescores": [
            {"displayValue": "22"}, {"displayValue": "31"}, {"displayValue": "24"},
            {"displayValue": "26"}]}]}]},
    "plays": [
        play("Jumpball", "Center A vs. Center B (Guard C gains possession)", 1, "12:00",
             pids=("10", "20", "21")),
        play("Driving Layup Shot", "Guard C misses driving layup", 1, "11:41", team="2",
             pids=("21",)),
        play("Free Throw - 1 of 2", "Wing D makes free throw 1 of 2", 1, "11:20", team="1",
             pids=("11",), scoring=True, value=1),
        play("Jump Shot", "Wing D makes 18-foot jumper", 1, "10:58", team="1", pids=("11",),
             scoring=True, value=2),
        play("Three Point Jumper", "Guard C makes 26-foot three", 2, "9:00", team="2",
             pids=("21",), scoring=True, value=3),
        play("Free Throw - 1 of 1", "Guard C makes free throw", 5, "4:00", team="2",
             pids=("21",), scoring=True, value=1),
    ],
    "boxscore": {"players": [box("1", [("10", True, 12), ("11", True, 20), ("12", False, 5)]),
                             box("2", [("20", True, 9), ("21", True, 18)])]},
}

r = pb.parse(SUMM)
check("quarter lines per team", r["lines"] == {"1": [30, 25, 28, 27], "2": [22, 31, 24, 26]})
check("the tip: both jumpers, and the team with the first possession",
      r["tip"]["jumpers"] == ["10", "20"])
check("the tip goes to the team with the first possession (the jump ball names no team)",
      r["tip"]["team"] == "2")
check("the first point can be a free throw", r["first_score"]["pid"] == "11"
      and r["first_score"]["value"] == 1)
check("the first field goal skips the and-one free throw (the usual first-basket market)",
      r["first_fg"]["pid"] == "11" and r["first_fg"]["value"] == 2
      and r["first_fg"]["team"] == "1" and r["first_fg"]["clock"] == "10:58")
check("starters per team", sorted(r["starters"]["1"]) == ["10", "11"]
      and sorted(r["starters"]["2"]) == ["20", "21"])
check("points per quarter, overtime left out",
      r["qpts"]["11"] == [3, 0, 0, 0] and r["qpts"]["21"] == [0, 3, 0, 0])
check("a final that matches its quarters passes the self-check",
      pb.check(r, 110, 103, "1", "2") == [] and pb.check(r, 111, 103, "1", "2") != [])
check("missing is never zero: a summary with no plays leaves the fields empty",
      pb.parse({"header": {}})["first_fg"] is None and pb.parse({})["tip"] is None)

# the backfill: counts, and the refusal
games = {f"e{k}": dict(r, date="2026-01-01", home="1", away="2") for k in range(10)}
s = npp.summary(games, 10)
check("the backfill counts every piece and the tip-to-first-basket rate",
      s["ok"] and s["has"]["first_fg"] == 10 and s["tip_team_scores_first"] == 0.0
      and s["first_fg_by_starter"] == 1.0)
games_bad = {f"e{k}": (dict(r, date="d") if k < 7 else dict(pb.parse({}), date="d"))
             for k in range(10)}
check("a shape change refuses to write (under 80% parsed)", not npp.summary(games_bad, 10)["ok"])
wf = (ROOT / ".github" / "workflows" / "nba-pbp-prior.yml").read_text(encoding="utf-8")
check("a one-time manual workflow commits the file",
      "workflow_dispatch" in wf and "python nba_pbp_prior.py" in wf
      and "data/nba/prior_pbp.json" in wf)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NBA play-by-play checks passed")
