"""
The Live page's test on last season (10-18) — nhl_live_check.py, and the
Live page reading its verdict (engines/live_props.tested).

Plain script — exits non-zero on failure. Scoring plays in ESPN's NHL
summary shape (plays[] with scoringPlay, period.number, participants[]
{athlete.id, type}, team.id); skater lines in prior_season.json's shape
[date, opp_id, sog, g, a, toi] — rule 5. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - parse_scoring keeping shootout "goals" (period 5)
    -> "a shootout goal is not a goal" fails
  - have_by counting periods after the checkpoint
    -> "at the end of the 1st he has only what he scored in the 1st" fails
  - evaluate matching his game by his CURRENT team instead of the opponent
    -> "a traded player's game is found by his opponent that night" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

import nhl_live_check as lc  # noqa: E402
from engines import live_props as lp  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def play(per, team, *who, typed=True):
    parts = []
    for k, pid in enumerate(who):
        x = {"athlete": {"id": pid}}
        if typed:
            x["type"] = "scorer" if k == 0 else "assister"
        parts.append(x)
    return {"scoringPlay": True, "period": {"number": per}, "team": {"id": team},
            "participants": parts}


summ = {"plays": [play(1, "10", "A", "B", "C"), play(2, "10", "A"),
                  play(3, "20", "Z", "Y", typed=False), {"scoringPlay": False},
                  play(5, "20", "Z")]}
sc = lc.parse_scoring(summ)
check("scorer and assists by period", sc["pids"]["A"] == {1: {"g": 1, "a": 0}, 2: {"g": 1, "a": 0}}
      and sc["pids"]["B"] == {1: {"g": 0, "a": 1}})
check("untyped participants: scorer first, then assists",
      sc["pids"]["Z"] == {3: {"g": 1, "a": 0}} and sc["pids"]["Y"] == {3: {"g": 0, "a": 1}})
check("a shootout goal is not a goal", 5 not in sc["pids"].get("Z", {}) and sc["n"] == 3)
check("team goals by period", sc["teams"] == {"10": {1: 1, 2: 1}, "20": {3: 1}})
check("the scoringPlays list is read when plays is not",
      lc.parse_scoring({"scoringPlays": [play(1, "10", "A")]})["n"] == 1)
check("at the end of the 1st he has only what he scored in the 1st",
      lc.have_by(sc["pids"]["A"], 1) == {"g": 1, "a": 0, "pts": 1})

# --- the test on a toy season ------------------------------------------------
# Player A (team 10, traded later to 30 — his "team" field is the LAST one)
# plays team 20 on 2026-03-01: 1 goal in the 1st, 1 in the 2nd -> final 2 G.
prior = {"skaters": {"A": {"team": "30", "games": [
    ["2026-02-01", "40", 3, 1, 0, 18.0], ["2026-02-03", "40", 2, 0, 1, 18.0],
    ["2026-03-01", "20", 4, 2, 0, 19.0]]}}}
sc["team_ids"] = ["10", "20"]
mu = {("A", "2026-03-01"): {"g": 0.4, "a": 0.4, "sog": 3.0}}
res = lc.evaluate(prior, mu, {"2026-03-01": [sc]})
check("a traded player's game is found by his opponent that night",
      res["markets"]["g2"]["n"] == 1)
check("a cashed line is not priced (Over 0.5 after his 1st-period goal)",
      res["markets"]["g1"]["n"] == 0)
check("score state is read from team goals (his team ahead after the 1st)",
      "g2:ahead" in res["by_state"])
check("the 2+ goal call after one goal in the 1st is the rest-of-game chance",
      res["by_checkpoint"]["g2@P1"]["predicted"]
      == round(lp.nhl_chance({"g": 0.4, "a": 0.4}, "g", 1.5, 1, 2 / 3)[0], 4))

# --- the page reads the verdict ---------------------------------------------
bins = [{"band": "0-9%", "n": 900, "predicted": 0.05, "actual": 0.04},
        {"band": "10-19%", "n": 400, "predicted": 0.14, "actual": 0.12}]
beat = {"markets": {"g1": {"verdict": {"verdict": "beats"}, "calibration": bins}}}
thin = {"markets": {"g1": {"verdict": {"verdict": "thin"}, "calibration": bins}}}
ch, sup = lp.tested(beat, "g", 0.5, 0.14)
check("a market that BEAT gets its delivered chance and its support",
      abs(ch - 0.12) < 0.01 and sup["measured"] and sup["n"] == 400)
check("a market that did not beat stays UNTESTED", lp.tested(thin, "g", 0.5, 0.14)
      == (0.14, lp.UNTESTED))
check("no test file yet is untested", lp.tested({}, "g", 0.5, 0.14) == (0.14, lp.UNTESTED)
      and lp.load_check("/nonexistent.json") == {})
check("shots are never lifted by the goal test", lp.tested(beat, "sog", 2.5, 0.3)[1]
      == lp.UNTESTED)
wf = (ROOT / ".github" / "workflows" / "nhl-live-check.yml").read_text(encoding="utf-8")
check("the workflow runs the test and commits only its file",
      "python nhl_live_check.py" in wf and "git add data/nhl/live_check.json" in wf)
page = (ROOT / "app" / "views" / "Live.py").read_text(encoding="utf-8")
check("the Live page reads the verdict", "lp.tested(_check" in page)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall live test checks passed")
