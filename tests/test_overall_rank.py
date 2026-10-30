"""
HOF-style ranks beside the letter (10-30) — matchup_grade.tough_rank /
with_size(rank=...), nba_context.dvp_overall, the "Overall D" columns.

HOF shows a defense's rank vs the player's position AND overall, 1st =
toughest (Trae Young vs CHA, 10-30: vs PG reb 7th / ast 9th -> HOF "D").

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - tough_rank counting from the softest -> "1st = the toughest defense" fails
  - the overall rank read from his position group, not everyone -> "Overall
    is the defense against everyone" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import matchup_grade as mg  # noqa: E402
from engines import nba_context as nc  # noqa: E402
from engines import nba_model as nm  # noqa: E402
from engines import nba_view as nv  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


check("1st = the toughest defense (card rank 30 of 30 allows the least)",
      mg.tough_rank({"rank": 30, "of": 30}) == "1st"
      and mg.tough_rank({"rank": 1, "of": 30}) == "30th"
      and mg.tough_rank({"rank": 22, "of": 30}) == "9th")
check("no rank: None", mg.tough_rank({}) is None and mg.tough_rank(None) is None)
check("letter, size and rank: 'D · -4% (9th)'; the Under flips the letter, not the rank",
      mg.with_size("D", -4.2, rank="9th") == "D · -4% (9th)"
      and mg.with_size("D", -4.2, "Under", "9th") == "B · +4% (9th)")

# a table: team "1" allows guards a lot but everyone else little
rng = random.Random(1)
TEAMS = [str(i) for i in range(1, 31)]
pool = {}
for t in TEAMS:
    for k, pos in enumerate(("G", "G", "F", "F", "C")):
        games = []
        for i in range(160):
            d = (f"2025-{11 + i // 60:02d}-{1 + (i % 60) // 2:02d}" if i < 120
                 else f"2026-11-{1 + (i - 120) // 2:02d}")
            opp = TEAMS[(TEAMS.index(t) + 1 + (i * 7) % 29) % 30]
            extra = (10 if pos == "G" else -8) if opp == "1" else 0
            games.append([d, t, opp, 30.0, max(0.0, rng.gauss(14 + extra, 2)), 5.0, 3.0, 1.0,
                          1.0, 0.5, 2.0])
        pool[f"{t}-{k}"] = {"pos": pos, "team": t, "games": games}
tbl = nc.dvp_table(pool, "2026-10-21", five=False)
allc = nc.dvp_overall(tbl, "1")
g_card = nc.dvp_grades(tbl, "1", "G")["pts"]
check("Overall is the defense against everyone (team 1 is soft on guards, tough overall)",
      mg.tough_rank(g_card) == "30th" and int(allc["pts"]["rank"]) > 15)
rows = [{"pid": "x", "pos": "G", "min": 30, "mu": {s: 10.0 for s in nm.BASE}}]
nc.apply_tonight(rows, "1", "ONE", None, [], [], {}, "2026-11-30", dvp=tbl)
r = rows[0]
check("the row carries both ranks and the page shows them",
      r["grade_rank"]["pts"] == "30th vs G" and r["overall_rank"]["pts"]
      and nv.grade(r, "pts").endswith("(30th vs G)") and nv.overall(r, "pts") == r["overall_rank"]["pts"])

bf = (ROOT / "app" / "views" / "Bet_Finder.py").read_text()
nhl = (ROOT / "app" / "engines" / "nhl_model.py").read_text()
props = (ROOT / "app" / "views" / "NBA_Props.py").read_text()
check("Bet Finder, NBA Props and NHL rows carry the Overall D rank",
      'base.insert(1, "Overall D"' in bf and '"Overall D": nv.overall(' in props
      and '"dvp_all": {st: c for st in DVP_STATS' in nhl)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
