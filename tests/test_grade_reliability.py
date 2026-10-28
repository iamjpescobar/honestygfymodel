"""
The A-F letter adjusted for how much of a defense's standing is real
(10-28) — defense_matchup.reliability_grade, used by card() for NBA, NHL
and NFL defense-vs-position letters.

Found comparing with HOF: PHI vs forwards read "F" on 4 games this season
(25.8 pts a game) with last season worth ~0 (points allowed to forwards
repeat across a season's halves at 0.003); last season PHI was 18th.

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - z without the sqrt(reliability) factor -> "a standing that does not
    repeat earns a C" fails
  - effective games ignoring last season (n_cur only) -> "last season's games
    count at their fitted weight" fails
  - card() keeping the plain rank letter -> "the 10-28 PHI-vs-forwards card
    reads C, not F" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import defense_matchup as dm  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


SP = [41.0, 2.0]          # defenses' mean and sd
g, r = dm.reliability_grade(41.0 + 3 * 2.0, SP, 0.999, 82, 10_000)
check("fully reliable: the old fifths (3 sd above = A)", g == "A" and r > 0.99)
check("fully reliable, 0.5 sd above = B; 0.5 below = D",
      dm.reliability_grade(42.0, SP, 0.999, 82, 10_000)[0] == "B"
      and dm.reliability_grade(40.0, SP, 0.999, 82, 10_000)[0] == "D")
check("a standing that does not repeat earns a C, however far out",
      dm.reliability_grade(25.8, SP, 0.003, 82, 4.2)[0] == "C")
lo = dm.reliability_grade(45.0, SP, 0.57, 82, 4)
hi = dm.reliability_grade(45.0, SP, 0.57, 82, 60)
check("more games behind the same number: a stronger letter",
      hi[1] > lo[1] and "ABCDF".index(hi[0]) <= "ABCDF".index(lo[0]) and hi[0] == "A")
check("a missing piece: no adjusted letter (the caller keeps the rank)",
      dm.reliability_grade(45.0, SP, None, 82, 10) == (None, None))


def table(weight, rel, cur, prior, n_cur=4, n_prior=82):
    teams = {}
    vals = {}
    for i in range(30):
        teams[str(i)] = {"n_cur": n_cur, "n_prior": n_prior, "cur": 41.0, "prior": 41.0,
                         "blend": 41.0 + (i - 15) * 0.2, "rank": 30 - i,
                         "rank_cur": 30 - i, "rank_prior": 30 - i}
        vals[str(i)] = teams[str(i)]["blend"]
    teams["X"] = {"n_cur": n_cur, "n_prior": n_prior, "cur": cur, "prior": prior,
                  "blend": cur, "rank": 31, "rank_cur": 31, "rank_prior": 18}
    vals["X"] = cur
    v = list(vals.values())
    m = sum(v) / len(v)
    sd = (sum((x - m) ** 2 for x in v) / (len(v) - 1)) ** 0.5
    return {"stats": {"pts": {"F": {"teams": teams, "ranked": {"blend": 31, "cur": 31, "prior": 31},
                                    "league": 41.2, "league_cur": 41.2, "league_prior": 41.2,
                                    "weight": weight, "reliability": rel, "games_full": 82.0,
                                    "spread": {"blend": [m, sd], "cur": [m, sd],
                                               "prior": [m, sd]}}}}}


c = dm.card(table(0.0026, 0.003, 25.75, 40.61), "X", "F", "pts")
check("the 10-28 PHI-vs-forwards card reads C, not F (rank stays 31st of 31)",
      c["grade"] == "C" and c["rank"] == 31 and c["grade_reliability"] < 0.01)
c2 = dm.card(table(0.5, 0.57, 36.0, 36.0), "X", "F", "pts")
check("last season's games count at their fitted weight",
      abs(c2["n_eff"] - (4 + 0.5 * 82)) < 0.11 and c2["grade"] == "F")
check("the card keeps the rank beside the letter", c2["rank"] == 31 and c2["of"] == 31)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
