"""
NBA matchup letters from defense vs position (10-28) — nba_context
dvp_lines / dvp_table / dvp_grades, apply_tonight(dvp=...).

Izzy: "we got Dean Wade at a B and on HOF he is at an A for points". The
letter used to rank the projection's opponent factor (team-wide, ~1.0
for every team — Wade @ IND x0.999) over 33 "teams" (3 exhibition
opponents). It now ranks what each defense allowed to guards / forwards /
centres a game, over the 30 NBA teams.

Plain script — exits non-zero on failure. Synthetic pool. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - no DVP_MIN_GAMES filter -> "ranked over the NBA teams only" fails
  - preseason games kept as last season -> "preseason games are left out" fails
  - every player put in one group -> "guards and centres facing the same team
    get their own letters" fails
"""
import random
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


rng = random.Random(4)
TEAMS = [str(i) for i in range(1, 31)]
# team "1" gives up a ton to guards and nothing extra to centres; "2" the reverse
G_EXTRA = {"1": 8.0, "2": -6.0}
C_EXTRA = {"1": -5.0, "2": 7.0}
pool = {}
days_prior = [f"2025-{m:02d}-{d:02d}" for m in (11, 12) for d in range(1, 29)] + \
             [f"2026-{m:02d}-{d:02d}" for m in (1, 2, 3) for d in range(1, 29)]
days_cur = [f"2026-10-{d:02d}" for d in range(21, 29)] + [f"2026-11-{d:02d}" for d in range(1, 29)]
pre = ["2026-10-05", "2026-10-08"]
for t in TEAMS:
    for k, pos in enumerate(("G", "G", "F", "F", "C")):
        pid = f"{t}-{k}"
        games = []
        for i, d in enumerate(days_prior + pre + days_cur):
            if (i + int(t)) % 2:
                continue
            opp = TEAMS[(TEAMS.index(t) + 1 + (i * 7) % 29) % 30]
            extra = G_EXTRA.get(opp, 0) if pos == "G" else (C_EXTRA.get(opp, 0) if pos == "C" else 0)
            pts = max(0.0, rng.gauss(14 + extra, 3))
            if d in pre:
                pts = 60.0          # a preseason blowout: must not count
            games.append([d, t, opp, 30.0, pts, 5.0, 3.0, 1.0, 1.0, 0.5, 2.0])
        # one exhibition game against a non-NBA club
        games.append(["2026-01-15", t, "132374", 30.0, 40.0, 5.0, 3.0, 1.0, 1.0, 0.5, 2.0])
        pool[pid] = {"name": pid, "pos": pos, "team": t, "games": games}

t = nc.dvp_table(pool, "2026-10-21")
check("ranked over the NBA teams only (exhibition clubs dropped)",
      t["of"] == 30 and "132374" not in t["teams"])
lines = nc.dvp_lines(pool, "2026-10-21")
check("preseason games are left out", not any(ln["game"] in pre for ln in lines))
check("this season and last are both read", {ln["season"] for ln in lines} == {"cur", "prior"})

gG, gC = nc.dvp_grades(t, "1", "G"), nc.dvp_grades(t, "1", "C")
check("guards and centres facing the same team get their own letters",
      gG["pts"]["grade"] == "A" and gC["pts"]["grade"] == "F")
check("and the other way round for team 2",
      nc.dvp_grades(t, "2", "G")["pts"]["grade"] == "F"
      and nc.dvp_grades(t, "2", "C")["pts"]["grade"] == "A")
check("combos are graded too", "pra" in gG and gG["pra"]["grade"])
check("a card carries the per-game number, the league's and the reliability",
      gG["pts"]["per_game"] > gG["pts"]["league"] and "reliability" in gG["pts"])

# apply_tonight: the letters come from the table
rows = [{"pid": "x", "pos": "G", "mu": {s: 10.0 for s in nm.BASE}, "min": 30},
        {"pid": "y", "pos": "C", "mu": {s: 10.0 for s in nm.BASE}, "min": 30}]
nc.apply_tonight(rows, "1", "AAA", None, [], [], {}, "2026-11-28", dvp=t)
check("tonight's guard and centre vs team 1: A and F on points",
      rows[0]["grade"]["pts"] == "A" and rows[1]["grade"]["pts"] == "F"
      and rows[0]["dvp"]["pts"]["rank"] == 1)
rows2 = [{"pid": "x", "pos": "G", "mu": {s: 10.0 for s in nm.BASE}, "min": 30}]
nc.apply_tonight(rows2, "1", "AAA", None, [], [], {}, "2026-11-28")
check("no table: no letter invented", "grade" not in rows2[0])

src = (ROOT / "nba_precompute.py").read_text()
check("the nightly builds the table and passes it to tonight's rows",
      "dvp = nc.dvp_table(pool, cur_from)" in src and "dvp=dvp)" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
