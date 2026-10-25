"""
NBA Trends team-first picker (10-25) — engines/nba_view.slate_teams,
team_players, player_label and the page wiring.

Izzy: "search by team and than choose a player available to play that day".

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - team_players keeping ruled-out rows -> "Out player not offered" fails
  - slate_teams listing a team twice     -> "each team once" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import nba_view as nv  # noqa: E402

FAILS = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


games = [{"away_abbr": "NYK", "home_abbr": "BOS", "time_et": "7:30 PM",
          "away_props": [{"name": "Jalen Brunson", "min": 35, "status": None},
                         {"name": "Bench Guy", "min": 8, "status": None}],
          "home_props": [{"name": "Jayson Tatum", "min": 36, "status": "Out"},
                         {"name": "Jaylen Brown", "min": 34, "status": "Questionable"},
                         {"name": "Derrick White", "min": 32, "status": "Day-To-Day"},
                         {"name": "Kristaps P", "min": 25, "status": "Out (calf)"}]},
         {"away_abbr": "LAL", "home_abbr": "GSW", "time_et": "10:00 PM",
          "away_props": [{"name": "LeBron", "min": 33}], "home_props": []}]
rows = nv.all_props(games)

teams = nv.slate_teams(rows)
check("each team once, game-time order", [t for t, _ in teams] == ["NYK", "BOS", "LAL"])
check("team label names the opponent and time", teams[1][1] == "BOS vs NYK · 7:30 PM")

ok, out = nv.team_players(rows, "BOS")
names = [r["name"] for r in ok]
check("Out player not offered", "Jayson Tatum" not in names and "Kristaps P" not in names)
check("ruled-out players are named, not silently dropped", out == ["Jayson Tatum", "Kristaps P"])
check("questionable / day-to-day stay available", names == ["Jaylen Brown", "Derrick White"])
check("only that team's players", all(r["team"] == "BOS" for r in ok))
ok2, _ = nv.team_players(rows, "NYK")
check("most minutes first", [r["name"] for r in ok2] == ["Jalen Brunson", "Bench Guy"])
check("label carries minutes and the doubt", nv.player_label(ok[0]) ==
      "Jaylen Brown · ~34 min · Questionable")
check("clean player label", nv.player_label(ok2[0]) == "Jalen Brunson · ~35 min")
check("team with nobody left -> empty, page says so", nv.team_players(rows, "GSW") == ([], []))

page = (ROOT / "app/views/NBA_Trends.py").read_text()
check("page picks the team first", page.index('"Team"') < page.index("Player (available tonight)"))
check("page reads team_players", "nv.team_players(rows" in page)
check("page names the ruled-out", "Ruled out tonight" in page)

if FAILS:
    print(f"{len(FAILS)} failed")
    sys.exit(1)
print("all passed")
