"""
The live injury check (10-14) — engines/live_injuries and every NHL /
NFL page loading through it.

Plain script — exits non-zero on failure. Slates carry the nightly's
shapes (NHL {side}_props / _goalie_props / _skaters, NFL {side}_players),
the feed ESPN's league injuries payload — rule 5. No network: the fetch
is handed a fake getter.

Negative controls, confirmed red by exit code when written (rule 4):
  - overlay skipping the goalie lists
    -> "a goalie ruled out since this morning leaves the crease" fails
  - feed() ignoring its cache
    -> "read once per ten minutes, not once per page view" fails
  - overlay without the copy
    -> "the nightly's slate in memory is never changed" fails
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import live_injuries as li  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


ESPN = {"injuries": [{"displayName": "Boston Bruins", "injuries": [
    {"status": "Out", "athlete": {"id": "11", "displayName": "Scratched Today"}},
    {"status": "Out", "athlete": {"id": "21", "displayName": "Goalie Out"}},
    {"status": "Day-To-Day", "athlete": {"id": "12", "displayName": "Banged Up"}},
    {"status": "Injured Reserve", "athlete": {"id": "13", "displayName": "Already Known"}}]}]}
calls = []


def fake_get(url):
    calls.append(url)
    return ESPN


li._CACHE.clear()
f, ok, _at = li.feed("nhl", now=1000.0, _get=fake_get)
check("the live list is read", ok and f["by_id"]["11"] == "Out")

g = {"away": "Boston Bruins", "home": "San Jose Sharks",
     "away_props": [{"pid": "11", "name": "Scratched Today"},
                    {"pid": "12", "name": "Banged Up"},
                    {"pid": "14", "name": "Healthy"}],
     "away_skaters": [{"pid": "11", "name": "Scratched Today"}, {"pid": "14", "name": "Healthy"}],
     "away_goalie_props": [{"pid": "21", "name": "Goalie Out"}, {"pid": "22", "name": "Backup"}],
     "away_goalies": [{"pid": "21", "name": "Goalie Out"}, {"pid": "22", "name": "Backup"}],
     "away_held_out": ["Already Known (Injured Reserve)"],
     "home_props": []}
games = [g]
new, out = li.overlay(games, f, "nhl")
ng = new[0]
check("a skater ruled out since this morning leaves the board",
      [p["name"] for p in ng["away_props"]] == ["Banged Up", "Healthy"])
check("a goalie ruled out since this morning leaves the crease",
      [p["name"] for p in ng["away_goalie_props"]] == ["Backup"])
check("a new day-to-day keeps his number and carries the tag",
      ng["away_props"][0].get("status") == "Day-To-Day" and ng["away_props"][0]["status_live"])
check("the names ruled out since the nightly are listed once each",
      out == ["Goalie Out (Out)", "Scratched Today (Out)"])
check("...and added to the game's held-out list",
      "Scratched Today (Out) — since this morning" in ng["away_held_out"]
      and "Already Known (Injured Reserve)" in ng["away_held_out"])
check("the nightly's slate in memory is never changed", len(g["away_props"]) == 3
      and "status" not in g["away_props"][1])

nfl = [{"away_players": [{"pid": "11", "name": "Scratched Today"}, {"pid": "9", "name": "WR"}],
        "home_players": []}]
nn, nout = li.overlay(nfl, f, "nfl")
check("NFL: an inactive / Out player leaves the card", [p["name"] for p in nn[0]["away_players"]]
      == ["WR"] and nout == ["Scratched Today (Out)"])

# --- the cache -------------------------------------------------------------
n0 = len(calls)
li.feed("nhl", now=1000.0 + 300, _get=fake_get)
check("read once per ten minutes, not once per page view", len(calls) == n0)
li.feed("nhl", now=1000.0 + li.LIVE_TTL + 1, _get=fake_get)
check("read again after ten minutes", len(calls) == n0 + 1)


def broken(url):
    raise RuntimeError("blocked")


li._CACHE.clear()
f2, ok2, _ = li.feed("nfl", now=5000.0, _get=broken)
check("a failed read changes nothing and says so", not ok2 and f2 == {"by_id": {}, "by_name": {}})
li.LAST["nfl"] = {"ok": False, "read_at": 5000.0, "out": []}
check("...the page line says the morning report is shown",
      "showing this morning's report" in li.note("nfl"))
li.LAST["nhl"] = {"ok": True, "read_at": 5000.0, "out": ["Scratched Today (Out)"]}
check("the page line names who was removed", "Scratched Today (Out)" in li.note("nhl"))

# --- every page loads through it ---------------------------------------------
bad = []
for p in (ROOT / "app" / "views").glob("*.py"):
    if p.name == "Results.py":
        continue
    src = p.read_text(encoding="utf-8")
    if re.search(r'(?<![\w.])load_slate\("nhl"\)', src) or re.search(r"(?<![\w.])load_week\(\)", src):
        bad.append(p.name)
check(f"every NHL / NFL page loads through the live check {bad}", not bad)
for name in ("NHL_Goal_Edge.py", "Long_Shots.py", "Bet_Finder.py", "NFL_TD_Edge.py",
             "NHL_Player_Of_The_Day.py", "NHL_Model.py", "NFL_Projections.py", "Milestones.py"):
    check(f"{name} prints the live-check line",
          "_li.render_note(" in (ROOT / "app" / "views" / name).read_text(encoding="utf-8"))

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall live injury checks passed")
