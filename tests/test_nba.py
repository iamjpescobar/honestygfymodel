"""
NBA (10-20) — engines/nba_box, engines/nba_model, nba_precompute's
building blocks, and the NBA wiring across the site (Bet Finder, Live,
Milestones, live injuries, the nightly, the navs).

Plain script — exits non-zero on failure. Box scores in ESPN's NBA
summary shape (boxscore.players[].statistics[] with labels MIN PTS ... 3PT
and athletes[] with didNotPlay / starter); player games as the model's
tuples [date, team, opp, min, pts, reb, ast, tpm, stl, blk, tov] — rule 5.
No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - Running.add without the season-gap carry
    -> "last season counts at CARRY once a new season starts" fails
  - next_man_up counting every team's games, not this team's
    -> "a traded player's old team never counts" fails
  - side_props projecting an Out player
    -> "an Out player is held out, not projected" fails
  - nba_game_model not attaching its projection to the slate
    -> "tonight's games carry the game model" fails
  - Running.project ignoring k_long (one level, straight to the league)
    -> "a star's cold week is shrunk toward HIS rate" fails
  - Running.add carrying the short window across the offseason as is
    -> "after the offseason, his minutes come from his season" fails
"""
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import nba_box as nbx  # noqa: E402
from engines import nba_model as nm  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- 1. the box score -------------------------------------------------------
summ = {"boxscore": {"players": [
    {"team": {"id": "2", "abbreviation": "BOS", "displayName": "Boston Celtics"},
     "statistics": [{"labels": ["MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "STL",
                                "BLK", "TO", "PF", "+/-", "PTS"],
                     "athletes": [
                         {"athlete": {"id": "11", "displayName": "Jay T", "position":
                                      {"abbreviation": "SF"}}, "starter": True,
                          "stats": ["36", "10-21", "4-9", "3-3", "1", "7", "8", "5", "1", "0",
                                    "3", "2", "+6", "27"]},
                         {"athlete": {"id": "12", "displayName": "Bench Guy"}, "didNotPlay": True,
                          "stats": []},
                         {"athlete": {"id": "13", "displayName": "Garbage"},
                          "stats": ["0", "0-0", "0-0", "0-0", "0", "0", "0", "0", "0", "0", "0",
                                    "0", "0", "0"]}]}]},
    {"team": {"id": "18", "abbreviation": "NYK"}, "statistics": []}]}}
box = nbx.parse(summ)
check("a player's line by ESPN's labels", box["11"]["pts"] == 27 and box["11"]["reb"] == 8
      and box["11"]["ast"] == 5 and box["11"]["min"] == 36 and box["11"]["tov"] == 3)
check("threes are the made part of 3PT", box["11"]["tpm"] == 4)
check("team and opponent ids ride along", box["11"]["team_id"] == "2"
      and box["11"]["opp_id"] == "18" and box["11"]["starter"])
check("did-not-play and zero-minute lines are not games", set(box) == {"11"})
t = nbx.as_tuple("2026-10-20", box["11"])
check("the model's tuple", t == ["2026-10-20", "2", "18", 36, 27, 8, 5, 4, 1, 0, 3])

# --- 2. the model ---------------------------------------------------------------
def world(n=90, seed=3, start=date(2025, 10, 21)):
    g = random.Random(seed)
    players = {}
    for i in range(n):
        mins = g.uniform(15, 36)
        rates = [g.uniform(.3, .9), g.uniform(.1, .45), g.uniform(.05, .35), g.uniform(0, .12)]
        games = []
        for k in range(175):
            if g.random() < 0.55:
                continue
            m = max(5.0, g.gauss(mins, 5))

            def pois(mu):
                L, c, p = math.exp(-mu), 0, 1.0
                while True:
                    p *= g.random()
                    if p < L:
                        return c
                    c += 1
            stats = [pois(m * r) for r in rates]
            games.append([(start + timedelta(days=k)).isoformat(), "1", "2", round(m, 1)]
                         + stats + [0, 0, 0])
        players[str(i)] = {"name": f"P{i}", "pos": g.choice(["G", "F", "C"]), "games": games}
    return players


W = world()
fit = nm.fit(W)
check("HL and K come from the grid, fitted before the test window",
      fit["hl"] in nm.FIT_HL and fit["k"] in nm.FIT_K
      and fit["fit_window"][1] == fit["test_window"][0])
check("a spread is measured for every stat",
      set(fit["sizes"]) == {s for s, _l in nm.STATS}
      and all(v is None or v > 0 for v in fit["sizes"].values()))
check("in a world where rates are real, the model beats his own hit rate on points",
      fit["test"]["pts"]["verdict"]["verdict"] == "beats" and fit["test"]["pts"]["n"] > 500)
check("calibration curves come out per stat, as '@stat'",
      set(nm.calibration(fit)) == {f"@{s}" for s, _l in nm.STATS})
check("the line is his last-10 average at the half point",
      nm.half_line([20, 24, 26]) == 23.5 and nm.half_line([]) is None)
check("combos are the sum of their parts",
      nm.val(["d", "1", "2", 30, 20, 7, 5, 2, 0, 0, 0], "pra") == 32
      and nm.val(["d", "1", "2", 30, None, 7, 5, 2, 0, 0, 0], "pra") is None)

r = nm.Running(10)
for k in range(10):
    r.add([f"2025-03-{10 + k:02d}", "1", "2", 30, 20, 5, 5, 2, 0, 0, 0])
w_before = r.w
r.add(["2025-10-25", "1", "2", 30, 20, 5, 5, 2, 0, 0, 0])
check("last season counts at CARRY once a new season starts",
      abs(r.w - (w_before * nm.CARRY * r.decay + 1.0)) < 1e-9)
pr = nm.project_now([["2026-01-0%d" % k, "1", "2", 30, 30, 10, 5, 3, 0, 0, 0]
                     for k in range(1, 9)], {"hl": 10, "k": 0, "league": {}}, "G")
check("a steady 30-in-30 player projects 30 minutes, 30 points",
      abs(pr["min"] - 30) < 1e-9 and abs(pr["mu"]["pts"] - 30) < 1e-9
      and abs(pr["mu"]["pra"] - 45) < 1e-9)
# THE TWO-LEVEL SHRINK (10-20 (4)): a scorer who has put up 0.9 points a
# minute all season, with a cold week, is pulled toward HIS OWN 0.9 — not
# toward an average guard's 0.45. One level (k_long None) pulls him to the
# league; the fitted model must not.
star = [[f"2025-1{1 + k // 28}-{1 + k % 28:02d}", "1", "2", 34, 31, 5, 6, 3, 0, 0, 0]
        for k in range(50)]
star += [[f"2026-01-{10 + k:02d}", "1", "2", 34, 22, 5, 6, 3, 0, 0, 0] for k in range(3)]
lg = {"G": {"pts": 0.45, "reb": 0.15, "ast": 0.12, "tpm": 0.05}}
two = nm.project_now(star, {"hl": 3, "k": 600, "hl_long": 60, "k_long": 300, "league": lg}, "G")
one = nm.project_now(star, {"hl": 3, "k": 600, "league": lg}, "G")
print(f"     cold week for a 31-a-night scorer: two-level {two['mu']['pts']:.1f}, "
      f"one-level {one['mu']['pts']:.1f}")
check("a star's cold week is shrunk toward HIS rate, not the league's",
      two["mu"]["pts"] > 26 and one["mu"]["pts"] < 22 and two["mu"]["pts"] - one["mu"]["pts"] > 4)
# ACROSS THE OFFSEASON: 70 games at 34 minutes, then 3 rested April games at
# 20 — October must not be projected off those three.
season = [[(date(2026, 1, 1) + timedelta(days=k)).isoformat(), "1", "2", 34, 28, 6, 5, 3, 0, 0, 0]
          for k in range(70)]
season += [["2026-04-1%d" % k, "1", "2", 20, 10, 3, 2, 1, 0, 0, 0] for k in (0, 1, 2)]
p_apr = nm.project_now(season, {"hl": 2, "k": 600, "hl_long": 120, "k_long": 100,
                                "league": lg}, "G")
r_oct = nm.Running(2, 120)
for gm in season:
    r_oct.add(gm)
r_oct.add(["2026-10-21", "1", "2", 33, 27, 6, 5, 3, 0, 0, 0])
print(f"     rested April: {p_apr['min']:.1f} min; after one October game: "
      f"{r_oct.m / r_oct.w:.1f} min")
p_oct = nm.project_now(season, {"hl": 2, "k": 600, "hl_long": 120, "k_long": 100,
                                "league": lg}, "G", today="2026-10-21")
print(f"     opening night, before he plays: {p_oct['min']:.1f} min")
check("after the offseason, his minutes come from his season, not three rested games",
      p_apr["min"] < 26 and r_oct.m / r_oct.w > 31 and p_oct["min"] > 31)
check("the fit picks both levels from the grid",
      fit.get("hl_long") in nm.FIT_HL_LONG and fit.get("k_long") in nm.FIT_K_LONG)
check("over chance from the NB", 0.4 < nm.over(30, 8, 29.5) < 0.6
      and nm.over(None, 8, 9.5) is None)

# --- 3. Next Man Up ----------------------------------------------------------------
def gm(d, team, mn, pts):
    return [d, team, "9", mn, pts, 5, 3, 1, 0, 0, 0]


days = [f"2026-01-{k:02d}" for k in range(1, 21)]
P = {"star": {"name": "Star", "games": [gm(d, "1", 36, 30) for d in days[:12]]},
     "mate": {"name": "Mate", "games": [gm(d, "1", 20 if d in days[:12] else 30,
                                         10 if d in days[:12] else 18) for d in days]},
     "traded": {"name": "Traded", "games": [gm(d, "5", 30, 25) for d in days[:10]]
                + [gm(d, "1", 25, 12) for d in days[10:]]}}
nmu = {r_["name"]: r_ for r_ in nm.next_man_up(P, "1", "star")}
check("the teammate's bump when the star sat",
      nmu["Mate"]["delta"]["pts"] == 8.0 and nmu["Mate"]["delta"]["min"] == 10.0
      and nmu["Mate"]["n_without"] == 8 and nmu["Mate"]["n_with"] == 12)
check("a traded player's old team never counts",
      nmu["Traded"]["n_with"] == 2 and nmu["Traded"]["n_without"] == 8)
check("too few games without him is not a row",
      nm.next_man_up({"star": P["star"], "x": {"name": "X", "games": [
          gm(d, "1", 20, 10) for d in days[:14]]}}, "1", "star") == [])

# --- 4. the nightly's building blocks -------------------------------------------
import nba_precompute as npc  # noqa: E402

pool = npc.merge_pool({"a": {"name": "A", "pos": "G", "team": "1",
                             "games": [gm("2026-03-01", "1", 30, 20)]}},
                      {"a": {"name": "A", "team": "7", "games": [gm("2026-10-21", "7", 32, 22)]}})
check("this season joins last season, his newest team wins",
      len(pool["a"]["games"]) == 2 and pool["a"]["team"] == "7")
pre = {"a": {"name": "A", "team": "7", "games": [gm("2026-10-05", "7", 36, 30),
                                                 gm("2026-10-08", "7", 34, 28)]}}
rw = npc.role_watch(pre, {"a": {"games": [gm("2026-03-01", "1", 25, 15)]}})
check("the role watch: preseason minutes vs last season's",
      rw and rw[0]["min_delta"] == 10.0 and rw[0]["pre"]["gp"] == 2)
tg = npc.trend_games(pool["a"]["games"], pre["a"]["games"], {"9": "NYK"}, "2026-10-20")
check("trend games are tagged LAST / PRE / REG, in date order",
      [x["tag"] for x in tg] == ["LAST", "PRE", "PRE", "REG"] and tg[0]["opp"] == "NYK")
params = {"hl": 10, "k": 0, "league": {}}
pool2 = {"s": {"name": "Sure", "pos": "G", "team": "1",
               "games": [gm(d, "1", 30, 20) for d in days]},
         "o": {"name": "Gone", "pos": "G", "team": "1",
               "games": [gm(d, "1", 30, 20) for d in days]},
         "n": {"name": "New Guy", "pos": "F", "team": "4",
               "games": [gm(d, "4", 28, 14) for d in days]}}
roster = {"s": {"pos": "PG"}, "o": {"pos": "SG", "status": "Out"}, "n": {"pos": "SF"}}
rows, held = npc.side_props("1", pool2, {}, params, roster, {"by_id": {}, "by_name": {}},
                            {}, "2026-10-20")
names = [x["name"] for x in rows]
check("an Out player is held out, not projected", "Gone" not in names
      and held == ["Gone (Out)"])
check("the roster decides the team (an offseason trade with no game yet)",
      "New Guy" in names and "Sure" in names)

# --- 4b. the game model ------------------------------------------------------------
check("last season's finals in the game model's shape",
      npc.prior_game_rows([{"date": "2025-11-01", "home": "2", "away": "8", "hs": 110, "as": 100}])
      == [{"date": "2025-11-01", "home_id": "2", "away_id": "8", "home_score": 110,
           "away_score": 100}])
_g = random.Random(9)
_strength = {str(t): _g.gauss(0, 6) for t in range(1, 11)}
_finals = []
for k in range(900):
    h, a = _g.sample(sorted(_strength), 2)
    mu = 112 + _strength[h] / 2 - _strength[a] / 2
    hs = round(_g.gauss(mu + 1.5, 11))
    as_ = round(_g.gauss(112 - _strength[h] / 2 + _strength[a] / 2, 11))
    if hs == as_:
        hs += 1
    _finals.append({"date": (date(2025, 10, 21) + timedelta(days=k // 7)).isoformat(),
                    "home": h, "away": a, "hs": hs, "as": as_})
_best = max(_strength, key=_strength.get)
_worst = min(_strength, key=_strength.get)
_slate = [{"home_id": _best, "away_id": _worst, "home_abbr": "AAA", "away_abbr": "ZZZ",
           "odds": {"total": 224.5}}]
_blk = npc.nba_game_model(_finals, [], _slate)
check("tonight's games carry the game model", bool(_slate[0].get("model")))
check("the best team at home is the favourite, with a fair spread and total",
      _slate[0]["model"]["p_home"] > 0.6 and _slate[0]["model"]["fair_spread_home"] < 0
      and _slate[0]["model"]["total"] > 200)
check("the game model is tested on unseen games", (_blk["validation"] or {}).get("n", 0) > 500)
nba_page = (ROOT / "app" / "views" / "NBA.py").read_text(encoding="utf-8")
check("the rotation tables are coloured by the chance over his line",
      "mv.chance_css(chances[k][c])" in nba_page and "render_chance_legend" in nba_page)
check("the role watch and the verdict chips are coloured",
      "_paint_w" in nba_page and "TRUST_STYLE" in nba_page)
check("a big model-vs-book total gap reads CHECK, not a lean", "CHECK: the book likely knows"
      in nba_page and "lean" not in nba_page.replace("lean = ", "").replace("{lean}", ""))

# --- 5. Live / Milestones / wiring --------------------------------------------------
from engines import live_props as lp  # noqa: E402
from engines import milestones as ms  # noqa: E402

check("NBA live clock: 6:00 left in the 3rd is 37.5% of the game",
      abs(lp.remaining("nba", "in", 3, "6:00") - 0.375) < 1e-9)
have = lp.nba_have(summ)
check("live box: points so far and PRA", have["11"]["pts"] == 27 and have["11"]["pra"] == 40)
ch, nd = lp.nba_chance(30.0, 8.0, 29.5, 27, 0.25)
check("27 in with a quarter left, Over 29.5 needs 3: likely", nd == 3 and ch > 0.8)
check("NBA milestones: 20 points from 10,000 is within reach, hockey's 3-point reach kept",
      any(x["what"] == "10,000th career point" for x in ms.needs({"pts": 9980}, None, "nba"))
      and not any("career point" in x["what"] for x in ms.needs({"pts": 980}, None, "nhl")))
check("ESPN's made-attempted threes read as made", ms._num("1,234-3,100") == 1234.0)

app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
for page in ("NBA.py", "NBA_Props.py", "NBA_Trends.py", "NBA_Next_Man_Up.py"):
    check(f"{page} is in the NBA nav", f'"views/{page}"' in app)
bfp = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("the Bet Finder prices NBA", '"NBA": (_nba_games, _nba_groups)' in bfp)
wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the nightly builds NBA and expects its file",
      "python nba_precompute.py" in wf and '"data/nba/games.json"' in wf)
check("last season is a one-time workflow", "python nba_prior_season.py" in (
    ROOT / ".github" / "workflows" / "nba-prior-season.yml").read_text(encoding="utf-8"))
from engines import live_injuries as li  # noqa: E402
check("the live injury check covers NBA props", "nba" in li._PATHS)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NBA checks passed")
