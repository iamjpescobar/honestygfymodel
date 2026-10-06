"""
Edge boards (10-06) — engines/edge_boards: NHL Goal Edge, Goalies to
Target, NFL TD Edge, Defenses to Target; plus the four pages being in
the NHL / NFL navs.

Plain script — exits non-zero on failure. Fixtures carry the shapes the
nightly writes (games.json slate rows with {side}_props, {side}_env,
{side}_goalie_props, {side}_goalies, model.{home,away}_score; NFL
projection rows) — rule 5.

Negative controls, confirmed red by exit code when written (rule 4):
  - nhl_goal_rows showing the RAW chance instead of the delivered one
    -> "the chance shown is the delivered chance" fails
    (Ranking by raw vs delivered cannot differ: the curve is monotone by
    construction, so that is not a control anyone can turn red.)
  - likely_starter picking one of two tied goalies -> "a tie is a split" fails
  - nhl_goalie_rows ranking by the game's goals instead of his own
    expected goals against -> "the leakier goalie ranks first" fails
  - nfl_defense_rows ignoring the size of the hole when tied
    -> "bigger holes rank first" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import edge_boards as eb  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# A calibration curve that pulls high calls DOWN hard: a raw 0.50 call
# delivered 0.30, a raw 0.40 call delivered 0.38. The delivered order
# must win over the raw order.
BINS = [{"band": "30-39%", "n": 500, "predicted": 0.40, "actual": 0.38},
        {"band": "50-59%", "n": 500, "predicted": 0.50, "actual": 0.39}]
MODEL = {"props_validation": {"g1": {"verdict": {"verdict": "beats"}, "calibration": BINS}},
         "save_prior": {"mean": 0.900}}


def skater(name, g1, pos="C"):
    return {"pid": name, "name": name, "pos": pos, "probs": {"g1": g1, "pt1": 0.6},
            "mu": {"g": 0.4}, "exp_sog": 3.0, "ice": {"recent": 20.0, "base": 19.0},
            "dvp": {}, "why": "w"}


GAMES = [{
    "game_type": "regular", "away": "A", "home": "B", "away_abbr": "AAA", "home_abbr": "BBB",
    # The GAME expects more goals from B (3.4) — so ranking by the game's
    # goals would put A's goalies first; only his own save rate puts
    # Leaky (B's starter) on top.
    "time_et": "7:00 PM", "model": {"home_score": 3.4, "away_score": 2.8},
    "away_props": [skater("Raw-high", 0.45), skater("Raw-low", 0.40)],
    "home_props": [skater("Home-1", 0.30)],
    "away_env": {"goal_ratio": 1.05, "shot_ratio": 1.1},
    "home_env": {"goal_ratio": 0.95, "shot_ratio": 0.9},
    # B's goalies (the ones A shoots at): a clear starter
    "home_goalie_props": [{"pid": "g1", "name": "Leaky", "crease": "3 of 3", "starts": 3,
                           "sv_pct": 0.880, "exp_sa": 32.0},
                          {"pid": "g2", "name": "Backup", "crease": "0 of 3", "starts": 0,
                           "sv_pct": 0.905, "exp_sa": 32.0}],
    "home_goalies": [{"pid": "g1", "sv_pct": 0.875, "l5_sv_pct": 0.870, "gaa": 3.4, "starts": 3}],
    # A's goalies: tied crease = split
    "away_goalie_props": [{"pid": "g3", "name": "Solid", "crease": "1 of 2", "starts": 1,
                           "sv_pct": 0.915, "exp_sa": 28.0},
                          {"pid": "g4", "name": "Other", "crease": "1 of 2", "starts": 1,
                           "sv_pct": 0.905, "exp_sa": 28.0}],
}]

rows = eb.nhl_goal_rows(GAMES, MODEL)
check("every skater with a goal line is on the board", len(rows) == 3)
# raw 0.45 sits between bins -> delivered ~0.384; raw 0.40 -> 0.38. Both
# below the raw numbers, and Raw-high still slightly ahead here; the real
# check is that the chance shown IS the delivered one.
check("the chance shown is the delivered chance, not the raw one",
      abs(rows[0]["chance"] - 0.385) < 0.01 and rows[0]["basis"] == "delivered"
      and rows[0]["raw"] == 0.45)
check("ranked by the delivered chance",
      [r["chance"] for r in rows] == sorted((r["chance"] for r in rows), reverse=True))
check("a skater is matched to the goalie he SHOOTS AT (the other side's likely starter)",
      rows[0]["goalie"] == "Leaky")
home_row = next(r for r in rows if r["player"] == "Home-1")
check("a tie is a split: both names, averaged save rate, never a guess",
      "split" in (home_row["goalie"] or "") and abs(home_row["goalie_sv"] - 0.910) < 1e-9)
check("likely_starter returns None on a tie", eb.likely_starter(GAMES[0]["away_goalie_props"]) is None)
check("fair price printed for the delivered chance", rows[0]["fair"].startswith("+"))

gk = eb.nhl_goalie_rows(GAMES, MODEL, rows)
first = gk[0]
check("the leakier goalie ranks first (his own expected goals against)",
      first["goalie"] == "Leaky" and abs(first["exp_ga"] - 32.0 * 0.12) < 1e-6)
check("save rate vs league in saves per 1,000 shots", first["sv_vs_league"] == -20.0)
check("the shooters facing him are the OTHER side's best goal chances",
      first["shooters"].startswith("Raw-high"))
check("a split crease is shown as split, not likely",
      all(r["split"] and not r["likely"] for r in gk if r["team"] == "AAA"))

# ------------------------------------------------------------------ NFL
from engines import defense_matchup as dm  # noqa: E402
lines = []
for d, big in (("Bears", 1.0), ("Lions", 2.0), ("Jets", 1.5)):
    for gi in range(4):
        for grp, stat, base in (("WR", "rec_yds", 140), ("TE", "rec_yds", 50),
                                ("RB", "rush_yds", 90), ("QB", "pass_yds", 220)):
            lines.append({"season": "cur", "defense": d, "game": f"{d}{gi}", "group": grp,
                          "stats": {stat: base * (big if grp in ("WR", "TE") else 1.0)}})
for i in range(9):          # filler defenses so quartiles exist
    for gi in range(4):
        for grp, stat, base in (("WR", "rec_yds", 140), ("TE", "rec_yds", 50),
                                ("RB", "rush_yds", 90), ("QB", "pass_yds", 220)):
            lines.append({"season": "cur", "defense": f"F{i}", "game": f"F{i}{gi}", "group": grp,
                          "stats": {stat: base * (0.8 + 0.02 * i)}})
dvp = dm.build_table(lines, ("rec_yds", "rush_yds", "pass_yds", "rec", "td", "pass_td"),
                     ("QB", "RB", "WR", "TE"))
NG = [{"status": "scheduled", "home": "Bears", "away": "Lions", "home_abbr": "CHI",
       "away_abbr": "DET", "home_profile": {"pa_pg": 20.0, "ranks": {"pa_pg": 5}, "rank_of": 32},
       "away_profile": {"pa_pg": 25.0, "ranks": {"pa_pg": 20}, "rank_of": 32}},
      # NYJ allows the FEWEST points, so only the size of its holes can
      # put DET ahead of it — the tiebreak under test.
      {"status": "scheduled", "home": "Jets", "away": "F0", "home_abbr": "NYJ",
       "away_abbr": "F0", "home_profile": {"pa_pg": 15.0, "ranks": {"pa_pg": 1}, "rank_of": 32},
       "away_profile": {}}]
dr = eb.nfl_defense_rows(NG, dvp)
order = [r["defense"] for r in dr]
check("bigger holes rank first among defenses with the same number of soft spots",
      order.index("DET") < order.index("NYJ") < order.index("CHI"))
check("each soft spot names the position, stat, rank and size",
      any("WRs (rec yds" in s_ and "%" in s_ for s_ in dr[0]["spots"]))
check("the offense that attacks a defense is the other side",
      next(r for r in dr if r["defense"] == "CHI")["attack"] == "DET")

# ------------------------------------------------------------------ navs
app_src = (ROOT / "app" / "app.py").read_text()
for page in ("NHL_Goal_Edge", "NHL_Goalies_To_Target", "NFL_TD_Edge", "NFL_Defenses_To_Target"):
    check(f"{page} is in the nav and its file exists",
          f'"views/{page}.py"' in app_src and (ROOT / "app" / "views" / f"{page}.py").exists())

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
