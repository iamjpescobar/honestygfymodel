"""
Milestone watch (10-14) — engines/milestones, milestone_log, the NHL /
NFL nightly hooks, and the page.

Plain script — exits non-zero on failure. ESPN's per-season career table
is fed in its common/v3 shape (categories -> names + statistics rows with
a season label); MLB's people call in the stats API's shape; skater and
player box lines in the shapes nhl_precompute / nfl_precompute store —
rule 5. Temp dirs only.

Negative controls, confirmed red by exit code when written (rule 4):
  - parse_espn_career counting the current season's row too
    -> "this season is not counted twice" fails
  - PriorCareer.fill without the feed-shape guard
    -> "a night of 'everyone is a rookie' is not saved" fails
  - crossed() missing a mark landed on exactly
    -> "reaching exactly 300 counts" fails
  - is_current_season without the two-digit NHL label (the 10-14 bug)
    -> "ESPN's real NHL label '26-27' is this season, never a past one" fails
"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import milestones as ms  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- 1. what counts as close ---------------------------------------------
n = ms.needs({"g": 298, "a": 100, "pts": 398, "gp": 999}, {"g": 19, "pts": 30}, "nhl")
whats = {x["what"]: x["need"] for x in n}
check("2 from 300 goals is within reach", whats.get("300th career goal") == 2)
check("the 1,000th game is listed", whats.get("1,000th career game") == 1)
check("a season mark too (20th goal)", whats.get("20th goal of the season") == 1)
check("a player sitting ON a mark chases the next one",
      not any("100th career assist" in w for w in whats) and "200th career assist" not in whats)
check("3 goals away is not tonight's story",
      not any("career goal" in x["what"] for x in ms.needs({"g": 297}, None, "nhl")))
check("a stat missing from the career table is skipped, never zero",
      ms.needs({}, None, "nhl") == [] and ms.needs(None, None, "nfl") == [])
y = ms.needs({"pass_yds": 9_790}, None, "nfl")
check("yards read as yards", y and y[0]["what"] == "10,000 career passing yards"
      and ms.short(y[0]) == "210 yds from his 10,000 career passing yards")
check("ordinals", (ms.ordinal(1), ms.ordinal(2), ms.ordinal(13), ms.ordinal(300),
                   ms.ordinal(1000)) == ("1st", "2nd", "13th", "300th", "1,000th"))

# --- 2. crossed -------------------------------------------------------------
c = ms.crossed({"career": {"g": 299}, "season": {"g": 9}},
               {"career": {"g": 301}, "season": {"g": 11}}, "nhl")
check("a two-goal night past 300 is the 300th", ("career", "g", 300, "300th career goal") in c)
c = ms.crossed({"career": {"g": 299}}, {"career": {"g": 300}}, "nhl")
check("reaching exactly 300 counts", [x[2] for x in c] == [300])
check("no change, no milestone", ms.crossed({"career": {"g": 5}}, {"career": {"g": 5}}) == [])

# --- 3. ESPN's per-season table ---------------------------------------------
def espn(rows, names=("gamesPlayed", "goals", "assists", "points"), cat="skating"):
    return {"categories": [
        {"name": "averages", "names": list(names),
         "statistics": [{"season": {"displayName": lab}, "stats": ["1"] * len(names)}
                        for lab, *_ in rows]},
        {"name": cat, "names": list(names),
         "statistics": [{"season": {"displayName": lab}, "stats": [str(v) for v in vals]}
                        for lab, *vals in rows]}]}


vet = espn([("2023-24", 82, 40, 30, 70),
            ("2024-25", 30, 10, 5, 15), ("2024-25", 50, 20, 10, 30),   # traded: two teams
            ("2025-26", 80, 35, 35, 70),
            ("2026-27", 5, 3, 1, 4)])                                  # this season
got = ms.parse_espn_career(vet, "nhl", 2026)
check("this season is not counted twice", got["prior"]["g"] == 40 + 30 + 35)
check("a traded season's two rows are summed", got["prior"]["gp"] == 82 + 80 + 80)
check("an averages category is never summed as totals", got["prior"]["a"] == 30 + 15 + 35)
check("the current season was recognised", got["current_seen"])
# The label ESPN actually sends for NHL seasons (10-14 nightly probe).
real = espn([("24-25", 82, 30, 20, 50), ("25-26", 82, 40, 30, 70), ("26-27", 7, 5, 2, 7)],
            names=("games", "goals", "assists", "points"), cat="defense")
gr = ms.parse_espn_career(real, "nhl", 2026)
check("ESPN's real NHL label '26-27' is this season, never a past one",
      gr["prior"] == {"gp": 164, "g": 70, "a": 50, "pts": 120} and gr["current_seen"])
check("a file written before the fix is started over",
      ms.PriorCareer({"season": 2026, "players": {"1": {"prior": {"g": 9}}}}, 2026,
                     ms.FORMAT["nhl"]).players == {}
      and ms.PriorCareer({"season": 2026, "players": {"1": {"prior": {"g": 9}}}}, 2026,
                         ms.FORMAT["nfl"]).players != {})
comb = espn([("2024-25", 30, 10, 5, 15), ("2024-25", 50, 20, 10, 30),
             ("2024-25", 80, 30, 15, 45)])
check("ESPN's combined row is read once, not added to its parts",
      ms.parse_espn_career(comb, "nhl", 2026)["prior"]["g"] == 30)
nfl = espn([("2024", 3500, 25, 100, 2), ("2025", 4100, 30, 150, 1), ("2026", 1200, 9, 20, 0)],
           names=("passingYards", "passingTouchdowns", "rushingYards", "rushingTouchdowns"),
           cat="passing")
gn = ms.parse_espn_career(nfl, "nfl", 2026)["prior"]
check("NFL seasons by start year; 2026 is this season",
      gn["pass_yds"] == 7600 and gn["pass_td"] == 55 and gn["rush_yds"] == 250)
check("unreadable payloads are None", ms.parse_espn_career({"x": 1}, "nhl", 2026) is None
      and ms.parse_espn_career(None, "nhl", 2026) is None)
r = ms.parse_espn_career({"categories": []}, "nhl", 2026)
check("an empty table is a player with no earlier seasons", r and r["prior"]["g"] == 0)
check("career now = before + this season",
      ms.add({"g": 105, "gp": 242}, {"g": 3, "gp": 5}) == {"g": 108, "gp": 247})
check("season totals from box lines",
      ms.nhl_season([{"g": 1, "a": 1}, {"g": 0, "a": 2}]) == {"g": 1, "a": 3, "pts": 4, "gp": 2}
      and ms.nfl_season([{"passing": {"yds": 250, "td": 2}, "rushing": {"yds": 10, "td": 1},
                          "receiving": {}}])["td"] == 1)

# --- 4. the committed file ------------------------------------------------
pc = ms.PriorCareer({"season": 2025, "players": {"1": {"prior": {"g": 9}}}}, 2026)
check("last season's file is started over", pc.players == {})
pc = ms.PriorCareer({"season": 2026, "players": {"1": {"prior": {"g": 9}}}}, 2026)
pc.fill([str(i) for i in range(2, 32)], {}, lambda pid: {"categories": []}, "nhl")
check("a night of 'everyone is a rookie' is not saved",
      pc.suspect and set(pc.players) == {"1"})
pc = ms.PriorCareer({}, 2026)
pc.fill(["1", "2"], {"1": "A"}, lambda pid: vet if pid == "1" else None, "nhl")
check("a failed player is retried next night, a read one is kept",
      pc.prior("1") == {"gp": 242, "g": 105, "a": 80, "pts": 185} and pc.prior("2") is None
      and pc.failed == 1)

# --- 5. MLB's career line ---------------------------------------------------
resp = {"people": [
    {"id": 592450, "stats": [{"group": {"displayName": "hitting"},
                              "type": {"displayName": "career"},
                              "splits": [{"stat": {"homeRuns": 298, "hits": 1499,
                                                   "rbi": 760, "stolenBases": 99}}]}]},
    {"id": 1, "stats": [{"group": {"displayName": "pitching"},
                         "type": {"displayName": "career"}, "splits": [{"stat": {}}]}]}]}
mc = ms.parse_mlb_careers(resp)
check("MLB careers by id; a pitcher with no hitting line is left out",
      mc == {"592450": {"hr": 298, "h": 1499, "rbi": 760, "sb": 99}})
mn = {x["what"] for x in ms.needs(mc["592450"], None, "mlb")}
check("MLB: 2 from 300 HR, 1 from 1,500 hits, 1 from 100 steals",
      {"300th career home run", "1,500th career hit", "100th career steal"} <= mn)

# --- 6. the nightly hook, end to end (NHL) --------------------------------
import nhl_precompute as nhp  # noqa: E402

skaters = {"10": {"name": "Vet Sniper", "games": {
    "e1": {"date": "2026-10-08", "g": 1, "a": 0}, "e2": {"date": "2026-10-11", "g": 2, "a": 1},
    "x": {"date": "2026-10-01", "g": 5, "a": 5}}}}               # x: an exhibition
regular = {"e1", "e2"}
row = {"pid": "10", "name": "Vet Sniper", "mu": {"g": 0.4, "a": 0.4}}
slate = [{"away_props": [row], "home_props": []}]
calls = []


def fake(pid):
    calls.append(pid)
    return espn([("2024-25", 82, 150, 100, 250), ("2025-26", 82, 145, 100, 245),
                 ("2026-27", 2, 3, 1, 4)])


with tempfile.TemporaryDirectory() as td:
    hap = nhp.nhl_milestones(slate, skaters, regular, date(2026, 10, 12), root=td,
                             fetch=fake, pause=0)
    # prior 295 goals + this season 3 = 298 -> 2 from 300; the exhibition never counts
    items = {x["what"]: x for x in row.get("milestones") or []}
    check("the skater's row carries '2 from his 300th career goal'",
          items.get("300th career goal", {}).get("need") == 2
          and items["300th career goal"]["short"] == "2 from his 300th career goal")
    saved = json.loads((Path(td) / "nhl" / "career_prior.json").read_text())
    check("his career before this season is committed", saved["season"] == 2026
          and saved["players"]["10"]["prior"]["g"] == 295)
    row2 = {"pid": "10", "name": "Vet Sniper"}
    nhp.nhl_milestones([{"away_props": [row2], "home_props": []}], skaters, regular,
                       date(2026, 10, 12), root=td, fetch=fake, pause=0)
    check("fetched once a season: the second night reads the file", calls == ["10"])
    sk2 = {"10": {"name": "Vet Sniper", "games": {
        "e1": {"date": "2026-10-08", "g": 3, "a": 0}, "e2": {"date": "2026-10-11", "g": 2, "a": 0}}}}
    hap2 = nhp.nhl_milestones([{"away_props": [], "home_props": []}], sk2, regular,
                              date(2026, 10, 12), root=td, fetch=fake, pause=0)
    check("a 300th goal scored last night is reached lately (298 -> 300)",
          [h["what"] for h in hap2 if h["stat"] == "g" and h["scope"] == "career"]
          == ["300th career goal"])

# --- 7. wiring ----------------------------------------------------------------
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("Milestone Watch is in the MLB, NHL, NFL and NBA navs",
      app.count('("Milestone Watch", "views/Milestones.py")') == 4)
home = (ROOT / "app" / "views" / "Home.py").read_text(encoding="utf-8")
check("Home has a route to it", '("Milestone Watch", "MLB"' in home)
res = (ROOT / "app" / "views" / "Results.py").read_text(encoding="utf-8")
check("Results lists the marks reached", res.count("_render_milestones()") == 3)
nfl_src = (ROOT / "nfl_precompute.py").read_text(encoding="utf-8")
check("both nightlies publish what was reached",
      '"milestones_happened": milestones_happened' in nfl_src
      and '"milestones_happened": milestones_happened' in
      (ROOT / "nhl_precompute.py").read_text(encoding="utf-8"))
wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the nightly commits both career files",
      "data/nhl/career_prior.json" in wf and "data/nfl/career_prior.json" in wf)
page = (ROOT / "app" / "views" / "Milestones.py").read_text(encoding="utf-8")
check("the page prices through the boards' own chance", "bf.chance_at(" in page)
check("MLB postseason games never count", '"R"' in page)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall milestone checks passed")
