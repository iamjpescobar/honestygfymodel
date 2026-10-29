"""
NBA matchup letters on how players do against their projections vs this
defense (10-29) — nba_context.apply_tonight / letter_teams.

Walk-forward on last season (20,333 player-games): ranking the projection's
own opponent factor across the 30 teams sorted games A +4.7% .. F -5.1% vs
the projection on points; the raw "allowed to his position" letter (10-28)
sorted them A +0.4 .. F -3.3. The position card stays as context.

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - the position card's letter taking precedence again -> "the letter is the
    opponent factor's" fails
  - letter_teams keeping exhibition clubs -> "ranked over the NBA's 30" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nba_context as nc  # noqa: E402
from engines import nba_model as nm  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


# a book over 30 NBA teams + one exhibition club: team "1" lets players beat
# their projections on points, team "30" holds them under
ob = nc.OppBook({"pts": {"hl": 60, "k": 5, "by_pos": False}}, {"pts": 15.0})
for t in [str(i) for i in range(1, 31)] + ["132374"]:
    y = 30 if t == "1" else (5 if t == "30" else (60 if t == "132374" else 15))
    for d in ("2026-10-22", "2026-10-24"):
        ob.add(t, "G", d, [d, "X", t, 30, y, 5, 5, 2], {"pts": 15.0, "reb": 5, "ast": 5,
                                                         "tpm": 2})
check("ranked over the NBA's 30 (no exhibition club)",
      nc.letter_teams(ob) == sorted(str(i) for i in range(1, 31)))
check("the defense-vs-position table's teams when there is one",
      nc.letter_teams(ob, {"teams": ["1", "2"]}) == ["1", "2"])

# the position card (context) says F for team 1; the factor says A+
dvp_card = {"grade": "F", "rank": 30, "of": 30, "per_game": 50.0, "league": 58.0,
            "vs_league_pct": -13.8}
fake_dvp = {"teams": [str(i) for i in range(1, 31)],
            "stats": {st: {"G": {"teams": {"1": {}}}} for st in nm.BASE}}
orig = nc.dvp_grades
nc.dvp_grades = lambda dvp, opp, grp: {"pts": dict(dvp_card), "reb": dict(dvp_card)}
rows = [{"pid": "x", "pos": "G", "min": 34, "mu": {"pts": 25.0, "reb": 5.0, "ast": 7.0,
                                                    "tpm": 3.0}}]
nc.apply_tonight(rows, "1", "ONE", ob, [], [], {"opp": ob.cfg}, "2026-10-26", dvp=fake_dvp)
nc.dvp_grades = orig
r = rows[0]
check("the letter is the opponent factor's (team 1 lets players beat their projections)",
      r["grade"]["pts"] == "A+" and r["ctx"]["grade"]["pts"]["basis"] == "beat-projection"
      and r["ctx"]["grade"]["pts"]["of"] == 30)
check("the position card stays on the row as context", r["dvp"]["pts"]["grade"] == "F")
check("a stat the factor is not in takes the position card's letter",
      r["grade"]["reb"] == "F" and r["ctx"]["grade"]["reb"]["basis"] == "allowed")

src = (ROOT / "app" / "engines" / "nba_context.py").read_text()
check("the walk-forward numbers are written beside the code",
      "A +4.7% / B +1.8 / C -1.3 / D -4.3 / F -5.1%" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
