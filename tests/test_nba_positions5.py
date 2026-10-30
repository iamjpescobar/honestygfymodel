"""
Five NBA positions for the matchup letters (10-30) — nba_context.positions5,
dvp_table(five=True), row_pos.

Izzy: "a team might be tough against a PG on one thing but weak against a SG
— grading by 3 positions keeps that away from us." ESPN lists nearly every
player as G / F / C; PG / SG and SF / PF are assigned from how he plays
(assists per 36 among guards, rebounds per 36 among forwards, cut at the
measured median of regulars). Measured on last season: points allowed
split-half reliability PG 0.54, SG 0.40, SF 0.00, PF 0.00, C 0.40 (G was 0.57).

Plain script — exits non-zero on failure. Synthetic pool. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - the guard split read from rebounds instead of assists -> "playmaking guards
    are PGs" fails
  - tonight's row graded at his ESPN group instead of the table's position ->
    "tonight's row is graded at the same position the table used" fails
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


def player(pos, ast, reb, games=20, mins=30.0):
    return {"pos": pos, "games": [[f"2026-01-{i + 1:02d}", "1", "2", mins, 10, reb, ast, 1]
                                  for i in range(games)]}


pool = {"pg1": player("G", 8, 3), "pg2": player("G", 7, 4), "sg1": player("G", 2, 3),
        "sg2": player("G", 1.5, 4), "pf1": player("F", 2, 10), "pf2": player("F", 2, 9),
        "sf1": player("F", 3, 4), "sf2": player("F", 2, 5), "c1": player("C", 2, 11),
        "lbl": player("SG", 9, 3), "bench": player("G", 0, 0, games=0)}
pos, cuts = nc.positions5(pool)
check("playmaking guards are PGs, the rest SGs",
      pos["pg1"] == "PG" and pos["pg2"] == "PG" and pos["sg1"] == "SG" and pos["sg2"] == "SG")
check("rebounding forwards are PFs, the rest SFs",
      pos["pf1"] == "PF" and pos["pf2"] == "PF" and pos["sf1"] == "SF" and pos["sf2"] == "SF")
check("centres stay centres; a five-position label ESPN gives is kept",
      pos["c1"] == "C" and pos["lbl"] == "SG")
check("no minutes: the group's first (PG / SF)", pos["bench"] == "PG")
check("the cut-offs are measured medians", cuts["pg_ast36"] is not None
      and cuts["pf_reb36"] is not None)

dvp = {"pos_of": {"pg1": "PG", "sg1": "SG"}, "teams": []}
check("tonight's row is graded at the same position the table used",
      nc.row_pos(dvp, {"pid": "sg1", "pos": "G"}) == "SG"
      and nc.row_pos(dvp, {"pid": "new", "pos": "F"}) == "SF"
      and nc.row_pos({"pos_of": {}}, {"pid": "x", "pos": "G"}) == "G")
check("five positions in the table by default", nc.POS5 == ("PG", "SG", "SF", "PF", "C")
      and "five=True" in (ROOT / "app" / "engines" / "nba_context.py").read_text())
src = (ROOT / "nba_precompute.py").read_text()
check("the nightly prints the assignment and every position's reliability",
      "NBA positions (five, from how they play)" in src and "for grp in nc.POS5" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
