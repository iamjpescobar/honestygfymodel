"""
NHL matchup letters from the matchup IN the number (10-29) — nhl_model
letter_cuts / matchup_letter / letter_cards, defense_matchup.badge.

Walk-forward on last season (36,887 skater-games): the team matchup ratio
the chance already uses sorted a skater's game vs his baseline A +6.0 ..
F -9.4% on shots and A +7.5 .. F -7.3% on goals; raw "allowed to C / W / D"
(the 10-06 letter) A +5.0 .. F -9.3% and goals out of order (B -5.1%).

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - matchup_letter reading the cut points upside down -> "a soft matchup is
    an A" fails
  - letter_cards leaving the position letter in place -> "the letter is the
    matchup's; the position letter stays as context" fails
  - shots graded on the goal ratio -> "shots read the shot ratio, goals /
    assists / points the goal ratio" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import defense_matchup as dm  # noqa: E402
from engines import nhl_model as hm  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


cuts = hm._cuts([0.80 + 0.4 * i / 999 for i in range(1000)])      # 0.80 .. 1.20, even
check("fifteen equal steps from the season's ratios", len(cuts) == 14
      and abs(cuts[6] - 0.9876) < 0.01)
check("too few games: no cut points", hm._cuts([1.0] * 100) is None)
check("a soft matchup is an A, a tough one an F, average a C",
      hm.matchup_letter(1.19, cuts) == "A+" and hm.matchup_letter(0.81, cuts) == "F-"
      and hm.matchup_letter(1.0, cuts) == "C")
check("no ratio or no cuts: no letter",
      hm.matchup_letter(None, cuts) is None and hm.matchup_letter(1.1, None) is None)

C = {"goal": cuts, "shot": cuts}
cards = {"sog": {"stat": "sog", "grade": "F", "rank": 30, "of": 32, "per_game": 5.0}}
out = hm.letter_cards(cards, 1.19, 0.81, C)
check("the letter is the matchup's; the position letter stays as context",
      out["sog"]["grade"] == "A+" and out["sog"]["position_grade"] == "F"
      and out["sog"]["rank"] == 30 and out["sog"]["letter_basis"] == "matchup")
check("shots read the shot ratio, goals / assists / points the goal ratio",
      out["sog"]["matchup_ratio"] == 1.19 and out["g"]["grade"] == "F-"
      and out["a"]["matchup_ratio"] == 0.81 and out["pts"]["grade"] == "F-")
check("a stat with no position card gets a card of its own", "g" in out and "rank" not in out["g"])
check("the badge shows the letter and the matchup", dm.badge(out["sog"]) == "A+ · x1.19")
check("cards without a matchup ratio keep the old badge",
      dm.badge({"grade": "B", "rank": 3, "of": 32}).startswith("B · 3rd"))

src = (ROOT / "app" / "engines" / "nhl_model.py").read_text()
check("tonight's rows carry the letters; the model ships the cut points",
      "cards = letter_cards(" in src and "lcuts = letter_cuts(" in src
      and '"letter_cuts": lcuts' in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
