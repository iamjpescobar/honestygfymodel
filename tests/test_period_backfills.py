"""
NHL periods and NFL quarters, read from ESPN's play-by-play (10-22) —
engines/nhl_periods, engines/nfl_quarters and the one-time backfills
(nhl_periods_prior.py, nfl_quarters_prior.py, their workflows).

Plain script — exits non-zero on failure. Summaries in ESPN's shapes:
header.competitions[0].competitors[].linescores, NHL plays[] with
participants, NFL drives.previous[].plays[] with the play TEXT naming the
players and boxscore.players[] (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - nhl_periods counting the goalie on a goal as an assister
    -> "a goal's assisters are skaters, never the goalie" fails
  - nhl_periods not counting a goal as a shot on goal
    -> "every goal is also a shot on goal" fails
  - nfl_quarters taking the passer as the receiver
    -> "the catch goes to the receiver after ' to '" fails
  - nfl_quarters reading a 'No Play' (penalty) as a play
    -> "a play wiped out by a penalty counts for nobody" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nfl_quarters as nq  # noqa: E402
from engines import nhl_periods as npd  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def header(home, away, hl, al):
    return {"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": home}, "linescores": [{"displayValue": str(x)}
                                                                  for x in hl]},
        {"homeAway": "away", "team": {"id": away}, "linescores": [{"displayValue": str(x)}
                                                                  for x in al]}]}]}


def part(*ids):
    return [{"athlete": {"id": i}} for i in ids]


# --- NHL -------------------------------------------------------------------------------
nhl = {"header": header("10", "20", [1, 0, 1, 1], [0, 1, 1, 0]), "plays": [
    {"type": {"text": "Shot"}, "period": {"number": 1}, "team": {"id": "10"},
     "participants": part("h1", "gA")},
    {"type": {"text": "Goal"}, "period": {"number": 1}, "team": {"id": "10"},
     "scoringPlay": True, "participants": part("h1", "h2", "h3", "gA")},
    {"type": {"text": "Missed Shot"}, "period": {"number": 2}, "team": {"id": "20"},
     "participants": part("a1")},
    {"type": {"text": "Goal"}, "period": {"number": 2}, "team": {"id": "20"},
     "scoringPlay": True, "participants": part("a1", "gH")},
    {"type": {"text": "Shot"}, "period": {"number": 3}, "team": {"id": "20"},
     "participants": part("a2", "gH")},
    {"type": {"text": "Goal"}, "period": {"number": 3}, "team": {"id": "10"},
     "scoringPlay": True, "participants": part("h2", "h1", "gA")},
    {"type": {"text": "Goal"}, "period": {"number": 3}, "team": {"id": "20"},
     "scoringPlay": True, "participants": part("a2", "a1", "gH")},
    {"type": {"text": "Goal"}, "period": {"number": 4}, "team": {"id": "10"},
     "scoringPlay": True, "participants": part("h3", "h1", "gA")}]}
R = npd.parse(nhl, goalie_ids={"gA", "gH"})
P = R["players"]
check("period lines per team (OT kept as a fourth)",
      R["lines"] == {"10": [1, 0, 1, 1], "20": [0, 1, 1, 0]})
check("a goal's assisters are skaters, never the goalie",
      P["h2"][0][1] == 1 and P["h3"][0][1] == 1 and "gA" not in P and "gH" not in P)
check("every goal is also a shot on goal (h1: a saved shot + a goal in the 1st = 2)",
      P["h1"][0] == [1, 0, 2] and P["a1"][1] == [1, 0, 1])
check("a missed shot is not a shot on goal; team shots by period",
      R["sog"]["20"] == [0, 1, 2] and R["sog"]["10"] == [2, 0, 1])
check("overtime stays out of the three periods (h3's OT goal, h1's OT assist)",
      sum(x[0] for x in P["h3"]) == 0 and P["h1"][2][1] == 1 and sum(x[1] for x in P["h1"]) == 1)
check("the first goal: who, which team, which period",
      R["first_goal"] == {"pid": "h1", "team": "10", "period": 1})
ck = npd.check(R, {"h1": {"g": 1, "a": 1, "sog": 2}, "h3": {"g": 1, "a": 1, "sog": 1}})
check("the box check: h1 adds up; h3's OT goal is an honest miss",
      ck["players"] == 2 and ck["goals_ok"] == 1 and ck["assists_ok"] == 2 and ck["sog_ok"] == 1)

# --- NFL -------------------------------------------------------------------------------
roster = {"10": [("q1", "Jared Goff"), ("r1", "Amon-Ra St. Brown"), ("b1", "Jahmyr Gibbs"),
                 ("r2", "Marvin Harrison Jr.")],
          "20": [("q2", "Joe Burrow"), ("r3", "Ja'Marr Chase"), ("r4", "Jaxon Smith-Njigba")]}
box = {"players": [{"team": {"id": t}, "statistics": [
    {"name": "passing", "athletes": [{"athlete": {"id": i, "displayName": n}}
                                     for i, n in ps]}]} for t, ps in roster.items()]}


def play(q, typ, text, yds, pid_):
    return {"id": pid_, "period": {"number": q}, "type": {"text": typ}, "text": text,
            "statYardage": yds}


nfl = {"header": header("10", "20", [7, 3, 0, 14], [0, 7, 3, 0]), "boxscore": box, "drives": {
    "previous": [{"plays": [
        play(1, "Pass Reception", "(Shotgun) J.Goff pass short right to A.St. Brown to DET 45 "
             "for 12 yards (T.Hill).", 12, 1),
        play(1, "Rush", "J.Gibbs left end to DET 48 for 3 yards (L.Wilson).", 3, 2),
        play(1, "Pass Incompletion", "J.Goff pass incomplete deep left to M.Harrison.", 0, 3),
        play(1, "Passing Touchdown", "J.Goff pass short middle to A.St. Brown for 9 yards, "
             "TOUCHDOWN.", 9, 4),
        play(2, "Rush", "J.Gibbs up the middle to CIN 30 for 22 yards. NO PLAY (Holding).",
             22, 5),
        play(2, "Pass Reception", "J.Burrow pass deep right to Ja.Chase to DET 20 for 41 yards.",
             41, 6),
        play(2, "Pass Interception Return", "J.Goff pass short left intended for J.Gibbs "
             "INTERCEPTED by C.Taylor.", 0, 7),
        play(2, "Sack", "J.Goff sacked at DET 30 for -8 yards.", -8, 8),
        play(4, "Rushing Touchdown", "J.Gibbs 4 yard rush, TOUCHDOWN.", 4, 9),
        play(4, "Pass Reception", "TWO-POINT CONVERSION ATTEMPT. J.Goff pass to A.St. Brown is "
             "complete.", 0, 10),
        play(5, "Pass Reception", "J.Burrow pass short right to J.Smith-Njigba to DET 30 for 7 "
             "yards.", 7, 11),
        play(1, "Pass Reception", "(Shotgun) J.Goff pass short right to A.St. Brown to DET 45 "
             "for 12 yards (T.Hill).", 12, 1)]}]}}
Q = nq.parse(nfl)
G = Q["players"]


def v(pid, st, q):
    return ((G.get(pid) or {}).get(st) or [0] * nq.SLOTS)[q]


check("quarter lines per team", Q["lines"]["10"] == [7, 3, 0, 14])
check("names are found as the text writes them (A.St. Brown, Ja.Chase, J.Smith-Njigba, "
      "M.Harrison for Marvin Harrison Jr.)",
      v("r1", "rec", 0) == 2 and v("r3", "rec_yds", 1) == 41 and v("r4", "rec", 4) == 1
      and v("r2", "targets", 0) == 1)
check("the catch goes to the receiver after ' to ' (the passer gets the attempt and yards)",
      v("q1", "pass_cmp", 0) == 2 and v("q1", "pass_yds", 0) == 21 and v("q1", "pass_att", 0) == 3
      and v("r1", "rec_yds", 0) == 21 and v("q1", "rec", 0) == 0)
check("a touchdown pass: the passer's pass TD and the receiver's TD",
      v("q1", "pass_td", 0) == 1 and v("r1", "td", 0) == 1)
check("a play wiped out by a penalty counts for nobody",
      v("b1", "carries", 1) == 0 and v("b1", "rush_yds", 1) == 0)
check("a rushing touchdown; an interception is an attempt with no catch; a sack is nothing",
      v("b1", "td", 3) == 1 and v("b1", "rush_yds", 3) == 4 and v("q1", "pass_att", 1) == 1
      and v("q1", "pass_yds", 1) == 0)
check("two-point tries stay out; overtime is the fifth slot; a repeated play id counts once",
      v("q1", "pass_att", 3) == 0 and v("q2", "pass_att", 4) == 1 and v("r1", "rec", 0) == 2)
ck = nq.check(Q, {"r1": {"rec": 2, "rec_yds": 21}, "b1": {"rush_yds": 7, "carries": 2}})
check("the box check counts players whose quarters add up",
      ck["rec"] == 1 and ck["rec_yds"] == 1 and ck["rush_yds"] == 1 and ck["carries"] == 1)

# --- the backfills ----------------------------------------------------------------------
for script, out, wf in (("nhl_periods_prior.py", "data/nhl/prior_periods.json",
                         "nhl-periods-prior.yml"),
                        ("nfl_quarters_prior.py", "data/nfl/prior_quarters.json",
                         "nfl-quarters-prior.yml")):
    src = (ROOT / script).read_text(encoding="utf-8")
    w = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
    check(f"{script}: refuses to write a file that doesn't add up, and its workflow commits it",
          "Refusing to write" in src and "return 1" in src and f"python {script}" in w
          and f"git add {out}" in w and "workflow_dispatch" in w)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall period / quarter play-by-play checks passed")
