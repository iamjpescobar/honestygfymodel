"""
Live props (10-18) — engines/live_props and views/Live.py.

Plain script — exits non-zero on failure. Summaries carry ESPN's game
summary shape (header.competitions[0].status / competitors, boxscore.
players[].statistics[] with keys / labels / athletes) — rule 5.

Negative controls, confirmed red by exit code when written (rule 4):
  - remaining() ignoring the period (clock only)
  - clock_min reading only "M:SS" (the 10-20 halftime bug)
    -> "NBA's last-minute clock" and "NBA halftime" fail
    -> "NHL: 10:00 left in the 2nd is half the game" fails
  - rest_pmf('nb') without the update on what he has done
    -> "a hot first half raises the rest of his game" fails
  - need() ignoring what he already has
    -> "a goal already scored cashes Over 0.5" fails
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import live_props as lp  # noqa: E402
from engines import model_math as mm  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- the clock ------------------------------------------------------------
check("NHL: 10:00 left in the 2nd is half the game",
      abs(lp.remaining("nhl", "in", 2, "10:00") - 0.5) < 1e-9)
check("NHL: before the start is the whole game", lp.remaining("nhl", "pre", None, None) == 1.0)
check("NHL: overtime is not priced", lp.remaining("nhl", "in", 4, "3:00") is None)
check("NFL: 7:30 left in the 3rd is 37.5% of the game",
      abs(lp.remaining("nfl", "in", 3, "7:30") - 0.375) < 1e-9)
check("an unreadable clock is not priced", lp.remaining("nfl", "in", 2, "??") is None)
check("NBA's last-minute clock '45.3' is 45 seconds, not unreadable",
      abs((lp.clock_min("45.3") or -1) - 45.3 / 60) < 1e-9 and lp.clock_min("0.0") == 0.0
      and abs((lp.clock_min("1:05.5") or -1) - (1 + 5.5 / 60)) < 1e-9)
check("NBA halftime: half the game left (clock '0.0' or none at all)",
      abs((lp.remaining("nba", "in", 2, "0.0", "Halftime") or -1) - 0.5) < 1e-9
      and abs((lp.remaining("nba", "in", 2, None, "Halftime") or -1) - 0.5) < 1e-9
      and abs((lp.remaining("nba", "in", 3, "0.4", "End of 3rd") or -1) - 0.25 - 0.4 / 60 / 48)
      < 1e-9)
check("still: overtime is not priced, a clockless mid-period is not priced",
      lp.remaining("nba", "in", 5, "3:00", "OT") is None
      and lp.remaining("nba", "in", 2, None, "In Progress") is None)
live = (ROOT / "app" / "views" / "Live.py").read_text(encoding="utf-8")
check("the Live page passes the status words and says what each sport's number lacks",
      'gs.get("clock"), gs.get("detail"))' in live and '"nba": "the score (a blowout' in live)

# --- what is left -----------------------------------------------------------
mu_g = -math.log(1 - 0.24)                      # a 24% pregame anytime goal
ch, nd = lp.nhl_chance({"g": mu_g, "a": 0.3}, "g", 0.5, 0, 0.5)
check("24% pregame, no goal at the halfway mark -> about 12.8% for the rest",
      abs(ch - (1 - math.exp(-mu_g * 0.5))) < 1e-6 and nd == 1)
ch, nd = lp.nhl_chance({"g": mu_g, "a": 0.3}, "g", 0.5, 1, 0.5)
check("a goal already scored cashes Over 0.5", ch == 1.0 and nd <= 0)
ch2, nd2 = lp.nhl_chance({"g": mu_g, "a": 0.3}, "g", 1.5, 1, 0.5)
check("one goal in, Over 1.5 needs one more at the rest-of-game rate",
      nd2 == 1 and abs(ch2 - (1 - math.exp(-mu_g * 0.5))) < 1e-6)
cold = lp.rest_pmf("nb", 3.0, 0.5, have=0, size=6.0)
hot = lp.rest_pmf("nb", 3.0, 0.5, have=4, size=6.0)
mean = lambda p: sum(k * x for k, x in enumerate(p))  # noqa: E731
check("a hot first half raises the rest of his game", mean(hot) > 1.5 > mean(cold))
check("...and the rest-of-game spread is a real distribution",
      abs(sum(hot) - 1) < 1e-6 and abs(sum(cold) - 1) < 1e-6)
spreads = {"Passing yards": {"kind": "yards", "cv": 0.3}}
qb, need = lp.nfl_chance(240.0, "Passing yards", spreads, 249.5, 200, 0.5)
check("NFL: 200 yards at the half, Over 249.5 needs 50 of a 120-yard half: likely",
      need == 50 and qb > 0.85)
qb2, _ = lp.nfl_chance(240.0, "Passing yards", spreads, 249.5, 80, 0.5)
check("...80 at the half needs 170 of a 120-yard half: unlikely (~16%)", 0.10 < qb2 < 0.20)
check("a market with no measured spread is not priced",
      lp.nfl_chance(50.0, "Receptions", {}, 4.5, 2, 0.5)[0] is None)
td, _ = lp.nfl_chance(0.5, None, {}, 0.5, 0, 0.25)
check("NFL anytime TD: Poisson on the time left", abs(td - (1 - math.exp(-0.125))) < 1e-9)

# --- ESPN's live summary ---------------------------------------------------
summ = {"header": {"competitions": [{
    "status": {"period": 2, "displayClock": "10:00",
               "type": {"state": "in", "shortDetail": "10:00 - 2nd"}},
    "competitors": [{"homeAway": "home", "score": "2", "team": {"abbreviation": "BOS"}},
                    {"homeAway": "away", "score": "1", "team": {"abbreviation": "NYR"}}]}]},
    "boxscore": {"players": [{"statistics": [
        {"name": "forwards", "keys": ["goals", "assists", "shotsTotal", "timeOnIce"],
         "athletes": [{"athlete": {"id": "7"}, "stats": ["1", "0", "3", "9:12"]}]},
        {"name": "goalies", "labels": ["SA", "SV"],
         "athletes": [{"athlete": {"id": "9"}, "stats": ["20", "19"]}]}]}]}}
gs = lp.game_state(summ)
check("the header reads the period, clock and score",
      gs["state"] == "in" and gs["period"] == 2 and gs["clock"] == "10:00"
      and gs["home"] == "BOS" and gs["home_score"] == 2 and gs["away_score"] == 1)
check("skaters' goals / assists / points / shots so far; goalies skipped",
      lp.nhl_box(summ) == {"7": {"g": 1, "a": 0, "pts": 1, "sog": 3}})
nsum = {"boxscore": {"players": [{"statistics": [
    {"name": "passing", "keys": ["completions/passingAttempts", "passingYards",
                                 "passingTouchdowns", "interceptions"],
     "athletes": [{"athlete": {"id": "1"}, "stats": ["15/22", "188", "1", "0"]}]},
    {"name": "rushing", "keys": ["rushingAttempts", "rushingYards", "rushingTouchdowns"],
     "athletes": [{"athlete": {"id": "2"}, "stats": ["9", "41", "1"]}]},
    {"name": "receiving", "keys": ["receptions", "receivingYards", "receivingTouchdowns",
                                   "receivingTargets"],
     "athletes": [{"athlete": {"id": "2"}, "stats": ["3", "22", "0", "4"]}]}]}]}}
nb = lp.nfl_box(nsum)
check("NFL box: passing line", nb["1"]["pass_yds"] == 188 and nb["1"]["pass_cmp"] == 15
      and nb["1"]["pass_att"] == 22)
check("NFL box: rush + rec combine into scrimmage yards and TDs",
      nb["2"]["scrim_yds"] == 63 and nb["2"]["td"] == 1 and nb["2"]["rec"] == 3)

# --- the page ----------------------------------------------------------------
page = (ROOT / "app" / "views" / "Live.py").read_text(encoding="utf-8")
check("every live call goes through the guard as UNTESTED (THIN at most)",
      "bf.judge(" in page and "lp.UNTESTED" in page)
check("the page says it is untested", "Not yet tested on past games" in page)
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("Live is in the NHL, NFL and NBA navs", app.count('("Live", "views/Live.py")') == 3)
from engines import model_view as mv  # noqa: E402
from engines import value as vl  # noqa: E402
check("an untested 12-point gap is CHECK, a 6-point one THIN, never STRONG",
      mv.guarded_tier(vl.assess(0.36, 300), 300, None, lp.UNTESTED)[0] == "check"
      and mv.guarded_tier(vl.assess(0.31, 300), 300, None, lp.UNTESTED)[0] == "thin")

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall live prop checks passed")
