"""
NFL: a quarterback with pass attempts but NO passing yards in the feed
(11-22) — nfl_projection.project_player.

Izzy (11-22, Sunday slate): NFL Projections (Rushing yards) and the NFL
Simulator both crashed: "TypeError: unsupported operand type(s) for /:
'NoneType' and 'float'" at ypa = p.get("pass_yds") / p.get("pass_att").
One quarterback came through with attempts and no yards; every page that
projects a whole roster died on him.

Plain script — exits non-zero on failure. No network.

Negative control, confirmed red by exit code when written (rule 4):
  - the old division back -> "a QB with attempts but no yards: no crash"
    fails (TypeError)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nfl_projection as proj  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


LEAGUE = {"ypc": 4.2, "yards_per_target": 7.8, "catch_rate": 0.65,
          "td_per_point": 0.10, "team_games": 8}
TEAM = {"carries_pg": 26.0, "targets_pg": 33.0}
OPP = {"ypc_allowed": 4.2, "ypt_allowed": 7.8, "catch_rate_allowed": 0.65}
QB = {"pid": "q1", "role": "QB", "gp": 3, "carry_share": 0.08, "target_share": 0.0,
      "ypc": 4.0, "pass_att": 31.0, "pass_yds": 232.0, "pass_gp": 3}

ok = proj.project_player(dict(QB), TEAM, OPP, LEAGUE, 24.0)
check("a normal quarterback still gets passing yards", (ok.get("pass_yds") or 0) > 150)
try:
    miss = proj.project_player(dict(QB, pass_yds=None), TEAM, OPP, LEAGUE, 24.0)
    crashed = False
except TypeError:
    miss, crashed = {}, True
check("a QB with attempts but no yards: no crash", not crashed)
check("...and no passing-yards projection invented for him (missing is not zero)",
      not crashed and miss.get("pass_yds") is None and (miss.get("pass_att") or 0) > 0)
check("a QB with no attempts on record: no yards-per-attempt either",
      proj.project_player(dict(QB, pass_att=None), TEAM, OPP, LEAGUE, 24.0).get("pass_yds")
      is None)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
