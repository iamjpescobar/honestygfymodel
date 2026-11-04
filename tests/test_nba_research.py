"""
NBA player research (11-02) — the shot profile and team ranks on NBA
Trends: nba_box FG / FT / OREB, nba_pbp.shots / team_box,
engines/nba_research, nba_precompute.build_research, the Trends page.

Izzy (11-02): "make our NBA research page similar to this — I love that
shot profile thing". Built from the play-by-play the nightly already reads.
ESPN is blocked in the sandbox, so the coordinate format is NOT verified:
the parser finds the basket from where layups and dunks sit, checks each
game's coordinates against the distance written in the play, and falls
back to that distance when they disagree. The nightly prints a
"[verify] NBA SHOTS" line.

Plain script — exits non-zero on failure. Synthetic ESPN summaries. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - the calibration assuming x is always the side-to-side axis -> "a feed
    with the axes the other way round reads the same zones" fails
  - a blocked shot credited to the first participant (the blocker) ->
    "a blocked shot is the shooter's miss" fails
  - the defense counting its OWN team's shots -> "a defense is what its
    opponents shot" fails
  - zone ranks the wrong way round -> "1st = the lowest FG% allowed" fails
  - (11-04) the defense counting an unchecked player's shots -> "a player
    whose shots don't check out is left out" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nba_box as nb  # noqa: E402
from engines import nba_pbp as pb  # noqa: E402
from engines import nba_research as nr  # noqa: E402
from engines import nba_view as nv  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


# where each zone's shot sits: (lateral, along from the baseline), feet;
# the basket at (25, 5.25). ESPN is assumed NOTHING about beyond "a court".
SPOT = {"rim": (25, 5.25, 1, "driving layup"), "paint": (30, 15, 11, "jumper"),
        "mid": (40, 17, 19, "pullup jump shot"), "corner3": (47, 7, 22, "three point jumper"),
        "above3": (25, 30, 25, "three point jumper")}


def play(pid, name, zone, made, team, axes="xy", end=0, block_by=None, blocker_first=False,
         coords=True, dist_override=None):
    lat, along, d, what = SPOT[zone]
    if end:
        along = 94 - along                    # the other basket
    x, y = (lat, along) if axes == "xy" else (along, lat)
    d = dist_override if dist_override is not None else d
    word = "makes" if made else "misses"
    txt = f"{name} {word} {d}-foot {what}"
    parts = [{"athlete": {"id": pid}}]
    if block_by:
        txt = f"{block_by[1]} blocks {name} 's {d}-foot {what}"
        parts = ([{"athlete": {"id": block_by[0]}}, {"athlete": {"id": pid}}] if blocker_first
                 else [{"athlete": {"id": pid}}, {"athlete": {"id": block_by[0]}}])
    p = {"type": {"text": "Jump Shot"}, "text": txt, "shootingPlay": True,
         "scoringPlay": made, "scoreValue": (3 if "three" in what else 2) if made else 0,
         "team": {"id": team}, "participants": parts, "period": {"number": 1},
         "clock": {"displayValue": "10:00"}}
    if coords:
        p["coordinate"] = {"x": x, "y": y}
    return p


def summary(plays, box_rows):
    """box_rows: [(team, pid, name, fgm, fga, tpm, tpa, ftm, fta, oreb, reb, tov, pts, min)]"""
    blocks = []
    for team in ("1", "2"):
        ath = []
        for t, pid, name, fgm, fga, tpm, tpa, ftm, fta, oreb, reb, tov, pts, mn in box_rows:
            if t != team:
                continue
            ath.append({"athlete": {"id": pid, "displayName": name, "position": {"abbreviation": "G"}},
                        "starter": True,
                        "stats": [str(mn), f"{fgm}-{fga}", f"{tpm}-{tpa}", f"{ftm}-{fta}",
                                  str(oreb), str(reb), "2", "1", "0", str(tov), str(pts)]})
        blocks.append({"team": {"id": team, "abbreviation": f"T{team}"},
                       "statistics": [{"labels": ["MIN", "FG", "3PT", "FT", "OREB", "REB", "AST",
                                                  "STL", "BLK", "TO", "PTS"], "athletes": ath}]})
    return {"boxscore": {"players": blocks}, "plays": plays,
            "header": {"competitions": [{"competitors": []}]}}


def game(axes="xy", both_ends=False, coords=True, bad_xy=False):
    """Team 1: player A takes 6 rim (4 made), 3 paint, 2 mid, 2 corner3, 4
    above3, and one blocked layup; player B 5 rim shots. Team 2: player C
    takes 8 above3 (2 made) and 4 rim (4 made)."""
    pl = []
    k = 0

    def add(pid, name, zone, made, team, **kw):
        nonlocal k
        k += 1
        pl.append(play(pid, name, zone, made, team, axes=axes,
                       end=(k % 2 if both_ends else 0), coords=coords,
                       dist_override=(40 if bad_xy and zone != "rim" else None), **kw))
    for i in range(6):
        add("A", "Al Able", "rim", i < 4, "1")
    for i in range(3):
        add("A", "Al Able", "paint", i < 1, "1")
    for i in range(2):
        add("A", "Al Able", "mid", i < 1, "1")
    for i in range(2):
        add("A", "Al Able", "corner3", i < 1, "1")
    for i in range(4):
        add("A", "Al Able", "above3", i < 2, "1")
    add("A", "Al Able", "rim", False, "1", block_by=("C", "Cy Cee"), blocker_first=True)
    for i in range(5):
        add("B", "Bo Bee", "rim", True, "1")
    for i in range(8):
        add("C", "Cy Cee", "above3", i < 2, "2")
    for i in range(4):
        add("C", "Cy Cee", "rim", True, "2")
    pl.append({"type": {"text": "Free Throw - 1 of 2"}, "text": "Al Able makes free throw 1 of 2",
               "shootingPlay": True, "scoringPlay": True, "scoreValue": 1, "team": {"id": "1"},
               "participants": [{"athlete": {"id": "A"}}], "coordinate": {"x": -214748340,
                                                                          "y": -214748365}})
    box = [("1", "A", "Al Able", 9, 18, 3, 6, 1, 2, 1, 6, 2, 22, 34),
           ("1", "B", "Bo Bee", 5, 5, 0, 0, 0, 0, 2, 9, 1, 10, 28),
           ("2", "C", "Cy Cee", 6, 12, 2, 8, 3, 4, 0, 4, 3, 17, 36)]
    return summary(pl, box)


s = game()
box = nb.parse(s)
check("the box score reads FG / FT / 3PT made-att and offensive rebounds",
      box["A"]["fgm"] == 9 and box["A"]["fga"] == 18 and box["A"]["tpa"] == 6
      and box["A"]["fta"] == 2 and box["A"]["oreb"] == 1 and box["A"]["tpm"] == 3)
check("the model's game tuple is unchanged by the new columns",
      nb.as_tuple("2026-11-01", box["A"]) == ["2026-11-01", "1", "2", 34, 22, 6, 2, 3, 1, 0, 2])
r = pb.parse(s)
A = r["shots"]["A"]
check("coordinates checked against the written distance: read by x/y", r["shot_src"] == "xy")
check("every zone lands where it was taken", A["rim"] == [7, 4] and A["paint"] == [3, 1]
      and A["mid"] == [2, 1] and A["corner3"] == [2, 1] and A["above3"] == [4, 2])
check("a blocked shot is the shooter's miss", A["rim"][0] == 7 and "rim" not in
      (r["shots"].get("C") or {}).keys() - {"rim"} and r["shots"]["C"]["rim"] == [4, 4])
check("free throws are not field goals", sum(v[0] for v in A.values()) == 18)
check("players whose shots add up to the box are checked; both teams are",
      sorted(r["shots_ok"]) == ["A", "B", "C"] and r["teams_shots_ok"] == ["1", "2"])
check("team box totals", r["team_box"]["1"]["fga"] == 23 and r["team_box"]["1"]["oreb"] == 3
      and r["team_box"]["2"]["pts"] == 17)
check("a feed with the axes the other way round reads the same zones",
      pb.parse(game(axes="yx"))["shots"]["A"] == A)
check("shots at both ends of the floor read the same zones",
      pb.parse(game(both_ends=True))["shots"]["A"] == A)
t = pb.parse(game(coords=False))
check("no coordinates: zones from the written distance, threes 'side unknown'",
      t["shot_src"] == "text" and t["shots"]["A"]["three"] == [6, 3]
      and t["shots"]["A"]["rim"] == [7, 4] and "corner3" not in t["shots"]["A"])
bx = pb.parse(game(bad_xy=True))
check("coordinates that disagree with the written distance are not used", bx["shot_src"] == "text")
s2 = game()
s2["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][1] = "9-19"
r2 = pb.parse(s2)
check("a player whose shots don't add up is left out, and so is his team",
      "A" not in r2["shots_ok"] and "1" not in r2["teams_shots_ok"] and "2" in r2["teams_shots_ok"])

# --- research ---------------------------------------------------------
g1 = dict(pb.parse(game()), date="2026-10-25", home="1", away="2")
prof = nr.profile(nr.player_zones([g1], "A"))
check("his profile: shares add to 100%, FG% per zone",
      abs(sum(z["share"] for z in prof) - 1) < 1e-9
      and [z for z in prof if z["zone"] == "rim"][0]["fg"] == 4 / 7)
dz = nr.defense_zones([g1])
check("a defense is what its opponents shot",
      dz["2"]["zones"]["rim"] == [12, 9] and dz["1"]["zones"]["above3"] == [8, 2]
      and "paint" not in dz["1"]["zones"])
g_bad = dict(pb.parse(s2), date="2026-10-26", home="1", away="2")
d2 = nr.defense_zones([g1, g_bad])
check("a player whose shots don't check out is left out (missing is not zero); his "
      "checked teammates still count",
      nr.player_zones([g1, g_bad], "A")["games"] == 1
      and d2["2"]["games"] == 2 and d2["2"]["zones"]["rim"] == [17, 14])
fake = {"X": {"zones": {"rim": [10, 5]}, "games": 3}, "Y": {"zones": {"rim": [10, 8]}, "games": 3},
        "Z": {"zones": {"rim": [10, 6]}, "games": 3}}
tb = nr.defense_table(fake)
check("1st = the lowest FG% allowed (toughest)",
      tb["teams"]["X"]["rim"]["rank"] == 1 and tb["teams"]["Y"]["rim"]["rank"] == 3
      and tb["teams"]["X"]["rim"]["of"] == 3 and abs(tb["league"]["rim"]["fg"] - 19 / 30) < 1e-9)
tt = {"X": {"off": {"rtg": [110.0, 1], "pace": [100.0, 1]}, "def": {"rtg": [105.0, 1],
                                                                    "pace": [99.0, 1]}, "games": 1},
      "Y": {"off": {"rtg": [120.0, 1], "pace": [95.0, 1]}, "def": {"rtg": [115.0, 1],
                                                                   "pace": [97.0, 1]}, "games": 1}}
rk = nr.team_ranks(tt)
check("team ranks: offense 1st = most, defense 1st = least allowed, pace 1st = fastest",
      rk["Y"]["rtg"]["off_rank"] == 1 and rk["X"]["rtg"]["def_rank"] == 1
      and rk["X"]["pace"]["off_rank"] == 1 and rk["X"]["pace"]["def_rank"] == 1)
tot = nr.team_totals([g1])
p1 = 23 - 3 + 3 + 0.44 * 2
check("possessions = FGA - OREB + TO + 0.44 FTA; paint points from checked shots",
      abs(tot["1"]["off"]["rtg"][0] - 100 * 32 / p1) < 1e-6
      and tot["1"]["off"]["paint"][0] == 2 * (4 + 1 + 5) and tot["2"]["def"]["paint"][0] == 20)
blk = nr.season_block([g1], pids=["A", "ZZ"])
check("a season block: the slate's players, the defense table, the ranks, the sources",
      blk["players"]["A"]["games"] == 1 and blk["players"]["ZZ"]["games"] == 0
      and blk["src"]["xy"] == 1 and "1" in blk["ranks"])
check("the nightly prints what it read", "NBA SHOTS this season: 1 games (1 by coordinates"
      in nr.verify_line("this season", [g1]))

# --- the Trends page's new windows -------------------------------------
row = {"opp": "BOS", "trend": [
    {"date": "2026-03-01", "opp": "BOS", "tag": "LAST", "pts": 20, "min": 30},
    {"date": "2026-10-22", "opp": "NYK", "tag": "REG", "pts": 15, "min": 28},
    {"date": "2026-10-28", "opp": "BOS", "tag": "REG", "pts": 25, "min": 35},
    {"date": "2026-10-10", "opp": "BOS", "tag": "PRE", "pts": 40, "min": 20}]}
h = nv.h2h_values(row, "pts")
check("H2H: his regular games vs tonight's opponent, both seasons, no preseason",
      [v for _l, v, _t in h] == [20, 25])
check("the minutes line follows the shown games",
      nv.trend_minutes(row, ["03/01 BOS", "10/22 NYK", "x"]) == [30, 28, None])

src = (ROOT / "nba_precompute.py").read_text()
page = (ROOT / "app" / "views" / "NBA_Trends.py").read_text()
check("the nightly builds it and ships it in games.json",
      "research = build_research(slate, cur_pbp, cur_from)" in src
      and '"research": research,' in src)
check("NBA Trends shows the court, the zone table and the team ranks",
      "_rv.court_img(_cells)" in page and "_rv.zone_rows(" in page and "_rv.rank_rows(" in page
      and '"H2H"' in page)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
