"""
Matchup grade A-F (10-26) — engines/matchup_grade and where it shows:
every "Defense vs pos" badge (NHL / NFL / MLB boards, Goal Edge, TD Edge),
the NBA opponent factor ranked tonight, the Bet Finder's Matchup column,
NBA Props / Trends, and the Site vs DraftKings check (does an A spot go
over more than the site said?).

Izzy: "DeBrincat anytime goal prop would be graded a B or whatever grade
the matchup might be — I want that to be a factor on the whole site".

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - grade() upside down (rank 1 -> F) -> "rank 1 of 32 is an A" fails
  - grade_event dropping the letter -> "the graded row carries its letter" fails
  - nba_grades ranking against itself only -> "the NBA opponent is ranked
    over every team" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import book_grade as bg  # noqa: E402
from engines import book_props as bp  # noqa: E402
from engines import defense_matchup as dm  # noqa: E402
from engines import matchup_grade as mg  # noqa: E402
from engines import nba_context as nc  # noqa: E402
from engines import nba_model as nm  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


# --- the letter -----------------------------------------------------------------------
g32 = [mg.grade(r, 32) for r in range(1, 33)]
check("rank 1 of 32 is an A, rank 32 an F", g32[0] == "A" and g32[-1] == "F")
check("32 teams (NHL / NFL) cut in fifths: 7 A, 6 B, 6 C, 6 D, 7 F; 30 (NBA / MLB) 6 each",
      [g32.count(x) for x in mg.LETTERS] == [7, 6, 6, 6, 7]
      and [[mg.grade(r, 30) for r in range(1, 31)].count(x) for x in mg.LETTERS] == [6] * 5)
check("the letters run in order (never better for a tougher defense)",
      all(mg.LETTERS.index(a) <= mg.LETTERS.index(b) for a, b in zip(g32, g32[1:])))
check("no rank, no letter (missing is never a grade)",
      mg.grade(None, 32) is None and mg.grade(5, None) is None and mg.grade(40, 32) is None
      and mg.grade(1, 1) is None)
check("from_card reads the card's grade, else its rank",
      mg.from_card({"grade": "B"}) == "B" and mg.from_card({"rank": 1, "of": 30}) == "A"
      and mg.from_card(None) is None)

# --- the shared matchup cards and badge ----------------------------------------------------
tbl = {"stats": {"g": {"W": {"teams": {"1": {"blend": 0.9, "rank": 2},
                                       "2": {"blend": 0.4, "rank": 31}},
                             "ranked": {"blend": 32, "cur": 32, "prior": 32},
                             "league": 0.6}}}}
c1, c2 = dm.card(tbl, "1", "W", "g"), dm.card(tbl, "2", "W", "g")
check("every defense-vs-position card carries its letter", c1["grade"] == "A" and c2["grade"] == "F")
check("the badge leads with the letter: 'A · 2nd-most', 'F · 2nd-fewest'",
      dm.badge(c1) == "A · 2nd-most" and dm.badge(c2) == "F · 2nd-fewest")
check("the notice says the grade", dm.notice(c1, "goals", "wingers", "MTL").startswith(
    "Matchup grade A"))
check("MLB starter and lineup cards carry it too",
      dm.mlb_lineup_card({"teams": {"a": {"k": 0.2}, "b": {"k": 0.25}, "c": {"k": 0.3}},
                          "league": {"k": 0.25}}, 0.31, "k")["grade"] == "A")


# --- NBA: the opponent factor ranked over every team -------------------------------------
class FakeBook:
    mean = {"pts": 20.0, "reb": 8.0, "ast": 5.0, "tpm": 2.0}

    def __init__(self, f):
        self.f = f

    def factor(self, t, grp, day):
        x = self.f[str(t)]
        return {"pts": x, "reb": 1.0, "ast": 2 - x, "tpm": 1.0}


teams = [str(i) for i in range(10)]
bk = FakeBook({t: 0.9 + 0.02 * int(t) for t in teams})        # team 9 allows the most points
G9 = mg.nba_grades(bk, "9", "G", "2026-10-26", teams, nm.COMBOS, bk.mean)
G0 = mg.nba_grades(bk, "0", "G", "2026-10-26", teams, nm.COMBOS, bk.mean)
check("the NBA opponent is ranked over every team", G9["pts"]["grade"] == "A"
      and G9["pts"]["rank"] == 1 and G9["pts"]["of"] == 10 and G0["pts"]["grade"] == "F")
check("assists run the other way for the same opponent", G9["ast"]["grade"] == "F")
check("a stat whose factor is the same for every team gets no grade", "reb" not in G9)
check("combos rank the mean-weighted factor of their parts",
      G9["pr"]["grade"] == "A" and "pra" in G9)
rows = [{"pos": "PG", "min": 34, "mu": {"pts": 25.0, "reb": 5.0, "ast": 7.0, "tpm": 3.0,
                                         "pra": 37.0, "pr": 30.0, "pa": 32.0, "ra": 12.0}}]
ob = nc.OppBook({"pts": {"hl": 30, "k": 10, "by_pos": False}}, {"pts": 1.0})
for t, y in (("A", 40), ("B", 10), ("C", 20)):
    ob.add(t, "G", "2026-10-20", ["2026-10-20", "X", t, 30, y, 5, 5, 2], {"pts": 20.0})
nc.apply_tonight(rows, "A", "AAA", ob, [], [], {"opp": ob.cfg}, "2026-10-26")
check("tonight's NBA rows carry their letters (the softest of three is an A)",
      rows[0]["grade"].get("pts") == "A" and rows[0]["ctx"]["grade"]["pts"]["of"] == 3)

# --- the check: graded lines carry their letter ----------------------------------------
snap = bp.merge_snapshot({}, {"e1": bp.parse([
    {"athlete": {"$ref": "x/athletes/11?"}, "type": {"id": "1", "name": "Total Points"},
     "odds": {"american": {"value": "-110"}}, "current": {"target": {"value": 24.5}}},
    {"athlete": {"$ref": "x/athletes/11?"}, "type": {"id": "1", "name": "Total Points"},
     "odds": {"american": {"value": "-110"}}, "current": {"target": {"value": 24.5}}}])}, "T")
G = bg.grade_event(dict(snap["e1"], ours=[["11", "pts", 24.5, 0.5, 0.52, "B"]]),
                   {"11": {"pts": 30}})
check("the graded row carries its letter", G and G[0][-1] == "B")
G_old = bg.grade_event(dict(snap["e1"], ours=[["11", "pts", 24.5, 0.5, 0.52]]),
                       {"11": {"pts": 30}})
check("lines captured before 10-26 (no letter) still grade", G_old and G_old[0][-1] is None)
rows_g = ([["d", "e", "p", "pts", 1, 0.5, 0.5, 1, -110, -110, "A"]] * 3
          + [["d", "e", "p", "pts", 1, 0.5, 0.5, 0, -110, -110, "F"]] * 2
          + [["d", "e", "p", "pts", 1, 0.5, 0.5, 1, -110, -110, None]])
BG = mg.by_grade(rows_g)
check("per letter: lines, our chance, the book's, how often it went over",
      BG["A"] == {"n": 3, "site": 0.5, "book": 0.5, "actual": 1.0} and BG["F"]["actual"] == 0
      and set(BG) == {"A", "F"})

# --- wiring --------------------------------------------------------------------------------
src = {p: (ROOT / p).read_text(encoding="utf-8") for p in (
    "app/views/Bet_Finder.py", "app/views/NBA_Props.py", "app/views/NBA_Trends.py",
    "app/views/Site_vs_Book.py", "book_props_grade.py", "app/engines/book_grade.py",
    "app/engines/model_view.py")}
check("the Bet Finder shows a Matchup column for the side picked (an Under flips it)",
      'base.insert(1, "Matchup", [_grade_of(r, stat, side) for r in players])'
      in src["app/views/Bet_Finder.py"]
      and 'if side == "Under" else g' in src["app/views/Bet_Finder.py"]
      and '"Matchup": r.get("grade") or "—"' in src["app/views/Bet_Finder.py"])
check("NBA Props and Trends show the letter", 'nv.grade(r, stat, side)' in
      src["app/views/NBA_Props.py"] and 'nv.grade(r, st_)' in src["app/views/NBA_Trends.py"])
check("the capture saves the letter beside the chance; the grader reports per letter",
      "round(ch, 4), letter])" in src["app/engines/book_grade.py"]
      and "mg.by_grade(" in src["book_props_grade.py"] and "MATCHUP GRADE" in
      src["book_props_grade.py"] and "Matchup grade " in src["app/views/Site_vs_Book.py"])
check("the boards colour by letter", 'GRADE_STYLE = {' in src["app/engines/model_view.py"])

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall matchup grade checks passed")
