"""
NBA five positions from ESPN team depth charts (10-30) — nba_context.
depth_slots, positions5(slots=...), nba_precompute.fetch_depth_slots.

Izzy: Naz Reid read C+ here and A+ on HOF — ESPN's roster lists him C, HOF
PF (WAS is softest vs PF). Depth charts list five slots; a player's slot
comes first, then an ESPN five-position label, then how he plays.

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - depth slots ignored in positions5 -> "a depth-chart slot overrides the
    roster's C" fails
  - a player listed twice keeping the LOWER slot -> "listed at two slots, he
    keeps the one where he sits highest" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nba_context as nc  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


site = {"depthchart": [{"name": "Base", "positions": {
    "pg": {"position": {"abbreviation": "PG"}, "athletes": [{"id": "1"}, {"id": "9"}]},
    "sg": {"position": {"abbreviation": "SG"}, "athletes": [{"id": "2"}]},
    "sf": {"position": {"abbreviation": "SF"}, "athletes": [{"id": "3"}, {"id": "2"}]},
    "pf": {"position": {"abbreviation": "PF"}, "athletes": [{"id": "4"}]},
    "c": {"position": {"abbreviation": "C"}, "athletes": [{"id": "5"}, {"id": "4"}]}}}]}
sl = nc.depth_slots(site)
check("every slot read", sl == {"1": "PG", "9": "PG", "2": "SG", "3": "SF", "4": "PF", "5": "C"})
check("listed at two slots, he keeps the one where he sits highest",
      sl["2"] == "SG" and sl["4"] == "PF")
core = {"items": [{"positions": {"pf": {"athletes": [
    {"athlete": {"$ref": "http://x/v2/sports/basketball/leagues/nba/athletes/3138196?lang=en"}}]}}}]}
check("athletes given only as links (the core feed) are read too",
      nc.depth_slots(core) == {"3138196": "PF"})
check("anything else: nothing, never a guess", nc.depth_slots({"foo": [1, 2]}) == {}
      and nc.depth_slots(None) == {})

pool = {"naz": {"pos": "C", "games": [["2026-01-01", "1", "2", 30.0, 15, 8, 2, 2]] * 20},
        "g1": {"pos": "G", "games": [["2026-01-01", "1", "2", 30.0, 15, 3, 8, 2]] * 20}}
pos, cuts = nc.positions5(pool, {"naz": "PF"})
check("a depth-chart slot overrides the roster's C", pos["naz"] == "PF")
check("without a slot, the old rule", nc.positions5(pool)[0]["naz"] == "C")

src = (ROOT / "nba_precompute.py").read_text()
check("the nightly reads every team's depth chart and logs the coverage",
      "fetch_depth_slots([str(i) for i in range(1, 31)])" in src
      and "dvp_table(pool, cur_from, slots=_slots)" in src
      and "from ESPN depth charts" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
