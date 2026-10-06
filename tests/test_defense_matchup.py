"""
Defense vs position, ice time, delivered chances, and the NFL prop test
(10-06) — engines/defense_matchup, nhl_model (ice time, DvP, preseason
filter), nfl_prop_check, nfl_projection's multiplier gate,
mlb_prop_precompute's matchup tables, model_view.delivered_over.

Plain script — exits non-zero on failure.

Negative controls, confirmed red by exit code when written (rule 4):
  - _per_game counting a game with the stat unrecorded as a zero
    -> "an unrecorded stat is not a zero" fails
  - _rank_desc ranking ascending -> "rank 1 allows the most" fails
  - fit_season_weight always taking the direct fit
    -> "two games a team cannot move the weight off the reference" fails
  - pool_skaters ignoring regular_ids -> "exhibition lines stay out" fails
  - toi_scales applying the raw ratio instead of ratio ** alpha
    -> "alpha 0 leaves the rate alone" fails
  - project_player ignoring matchup_in_number -> "a failed multiplier is
    out of the number" fails
  - delivered_over returning the raw chance when a curve exists
    -> "the checker judges a price on the delivered chance" fails
  - game_values turning a missing category into 0
    -> "no rushing line is not 0 rushing yards" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from engines import defense_matchup as dm   # noqa: E402
from engines import nhl_model as nm         # noqa: E402
from engines import nfl_projection as nproj  # noqa: E402
import nfl_prop_check as npc                 # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# ------------------------------------------------- 1. the table's arithmetic
lines = [
    # game g1: two centres vs defense A, one winger; stat sog recorded
    {"season": "cur", "defense": "A", "game": "g1", "group": "C", "stats": {"sog": 3, "pts": 1}},
    {"season": "cur", "defense": "A", "game": "g1", "group": "C", "stats": {"sog": 2, "pts": None}},
    {"season": "cur", "defense": "A", "game": "g1", "group": "W", "stats": {"sog": 4, "pts": 0}},
    # game g2 vs A: only a winger, sog recorded -> centres got 0 that night
    {"season": "cur", "defense": "A", "game": "g2", "group": "W", "stats": {"sog": 1, "pts": None}},
    # game g3 vs A: nothing recorded at all for pts or sog -> not a game for either
    {"season": "cur", "defense": "A", "game": "g3", "group": "C", "stats": {"sog": None}},
    {"season": "cur", "defense": "B", "game": "g4", "group": "C", "stats": {"sog": 9, "pts": 2}},
]
games, recorded = dm._per_game(lines)
check("per game: everything a group got that night is summed",
      games[("cur", "A", "g1")]["C"]["sog"] == 5.0)
check("an unrecorded stat is not a zero (rule 6)",
      "sog" not in recorded[("cur", "A", "g3")] and "pts" not in recorded[("cur", "A", "g2")])
t = dm.build_table(lines, ("sog", "pts"), ("C", "W"))
a_c = t["stats"]["sog"]["C"]["teams"]["A"]
check("a game where the group got nothing, with the stat recorded, IS a zero",
      a_c["n_cur"] == 2 and abs(a_c["cur"] - 2.5) < 1e-9)
check("pts games count only where pts was recorded",
      t["stats"]["pts"]["C"]["teams"]["A"]["n_cur"] == 1)
check("rank 1 allows the most", t["stats"]["sog"]["C"]["teams"]["B"]["rank_cur"] == 1
      and t["stats"]["sog"]["C"]["teams"]["A"]["rank_cur"] == 2)
check("ALL is everyone the defense faced", t["stats"]["sog"]["ALL"]["teams"]["A"]["cur"] == 5.0)
check("ties share the better rank", dm._rank_desc({"x": 3, "y": 3, "z": 1}) == {"x": 1, "y": 1, "z": 3})
check("quartile tiers", (dm.tier(1, 32), dm.tier(8, 32), dm.tier(9, 32), dm.tier(25, 32),
                         dm.tier(24, 32), dm.tier(None, 32)) ==
      ("soft", "soft", "neutral", "tough", "neutral", None))
check("bottom-half ranks read as fewest",
      dm.rank_text({"rank": 31, "of": 32}) == "2nd-fewest of 32"
      and dm.rank_text({"rank": 3, "of": 32}) == "3rd-most of 32")

# ------------------------------------------- 2. last season, weighted honestly
random.seed(7)
teams = [f"T{i}" for i in range(24)]
true = {tm: random.uniform(20, 40) for tm in teams}


def season_lines(season, n_games, rate_of):
    out = []
    for tm in teams:
        for gi in range(n_games):
            lam = rate_of(tm)
            # Poisson by summing Bernoulli-ish draws (no numpy)
            x = sum(1 for _ in range(int(lam * 4)) if random.random() < 0.25)
            out.append({"season": season, "defense": tm, "game": f"{season}{tm}{gi}",
                        "group": "C", "stats": {"sog": x}})
    return out


prior = season_lines("prior", 60, lambda tm: true[tm])
young = dm.build_table(prior + season_lines("cur", 2, lambda tm: true[tm]), ("sog",), ("C",))
rep = young["stats"]["sog"]["C"]["weight_report"]
check("two games a team cannot move the weight off the reference (split-half) fit",
      rep.get("used") == "reference")
check("a persistent defense trait reads as repeatable",
      (young["stats"]["sog"]["C"]["reliability"] or 0) > 0.6)
shuffled = [dict(ln, defense=random.choice(teams)) for ln in prior]
noise = dm.build_table(shuffled, ("sog",), ("C",))
check("defenses shuffled at random read as noise, far below a real trait",
      (noise["stats"]["sog"]["C"]["reliability"] or 0)
      < (young["stats"]["sog"]["C"]["reliability"] or 0) - 0.4)
grown = dm.build_table(prior + season_lines("cur", 60, lambda tm: true[tm]), ("sog",), ("C",))
check("the weight is fitted, never 0 by habit, when last season carries over",
      (grown["stats"]["sog"]["C"]["weight"] or 0) > 0.05)


def _spearman(a, b):
    ra = dm._rank_desc(a)
    rb = dm._rank_desc(b)
    n = len(ra)
    return 1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in ra) / (n * (n * n - 1))


_bl = {tm: grown["stats"]["sog"]["C"]["teams"][tm]["blend"] for tm in teams}
check("the blended ranking recovers the true ranking", _spearman(_bl, true) > 0.85)
contrary = dm.build_table(prior + season_lines("cur", 60, lambda tm: 60 - true[tm]),
                          ("sog",), ("C",))
check("a full season that CONTRADICTS last season overrules the reference weight",
      contrary["stats"]["sog"]["C"]["weight_report"].get("used") == "direct"
      and (contrary["stats"]["sog"]["C"]["weight"] or 0) < 0.05)
c = dm.card(grown, "T0", "C", "sog")
check("a card carries both seasons, the blend and its basis",
      c and c["basis"] == "blend" and c["cur"] is not None and c["prior"] is not None
      and c["tier"] in ("soft", "neutral", "tough"))
note = dm.notice(c, "shots on goal", "centres", "T0")
check("the notice names the defense, stat, position and how repeatable it is",
      all(x in note for x in ("T0", "shots on goal", "centres", "split-half")))
check("no card for a team the table has never seen", dm.card(grown, "ZZ", "C", "sog") is None)

# ------------------------------------------------------- 3. MLB cards
pri = {"1B": [0.14, 300.0], "2B": [0.04, 1000.0], "3B": [0.004, 1000.0], "HR": [0.03, 500.0],
       "BB": [0.10, 150.0], "K": [0.22, 80.0], "OUT": [0.466, 200.0]}
base = {"1B": 70, "2B": 20, "3B": 2, "HR": 15, "BB": 50, "K": 110, "OUT": 233, "PA": 500}
leaky = dict(base, HR=40, OUT=208)
tab = dm.mlb_starter_table({"1": base, "2": leaky}, {}, 0.6, pri, ["1", "2"])
check("the starter who gives up more homers ranks 1st-most on HR",
      tab["pitchers"]["2"]["hr"]["rank"] == 1 and tab["pitchers"]["1"]["hr"]["rank"] == 2)
mc = dm.mlb_starter_card(tab, "2", "hr")
check("an MLB card is per plate appearance", mc and mc["unit"] == "per plate appearance")
tb = {"teams": {"A": {"k": 0.20}, "B": {"k": 0.25}, "C": {"k": 0.22}}, "league": {"k": 0.22}}
lc = dm.mlb_lineup_card(tb, 0.24, "k")
check("tonight's lineup is placed among team lineups", lc["rank"] == 2 and lc["of"] == 3)

# ------------------------------------------------------- 4. NHL pieces
cur = {"p1": {"name": "X", "pos": "C", "games": {
    "e_pre": {"date": "2026-09-25", "opp": "Opp", "sog": 9, "g": 0, "a": 0, "toi": 30.0},
    "e_reg": {"date": "2026-10-02", "opp": "Opp", "sog": 2, "g": 0, "a": 0, "toi": 18.0}}}}
pool = nm.pool_skaters({}, cur, {"Opp": "9"}, {"e_reg"})
check("exhibition lines stay out of the rates (they leaked in before 10-06)",
      len(pool["p1"]["games"]) == 1 and pool["p1"]["games"][0][2] == 2)
g_rows = [("d1", "9", 2, 0, 0, 20.0), ("d2", "9", 2, 0, 0, None), ("d3", "9", 2, 0, 0, 10.0)]
tr = nm.toi_ratio(g_rows, 1)
check("a missing TOI is skipped, not read as 0 minutes", tr and abs(tr[1] - 15.0) < 1e-9
      and abs(tr[0] - 10.0) < 1e-9)
check("alpha 0 leaves the rate alone",
      nm.toi_scales(g_rows, {"sog": {"alpha": 0.0, "window": 1},
                             "pts": {"alpha": 0.0, "window": 1}})["sog"] == 1.0)
sc = nm.toi_scales(g_rows, {"sog": {"alpha": 1.0, "window": 1}, "pts": {"alpha": 0.0, "window": 1}})
check("an adopted alpha scales by recent / norm minutes", abs(sc["sog"] - 10.0 / 15.0) < 1e-9
      and sc["pts"] == 1.0)
r = {"sog": 3.0, "g": 0.3, "a": 0.4, "gp": 50}
check("probs carry the ice-time scale",
      nm.probs(r, toi_sog=0.5)["_exp_sog"] == 1.5 and nm.probs(r)["_exp_sog"] == 3.0)
check("C / W / D groups", (nm.dvp_group("C"), nm.dvp_group("LW"), nm.dvp_group("RW"),
                           nm.dvp_group("D")) == ("C", "W", "W", "D"))

# ------------------------------------------------------- 5. NFL pieces
check("no rushing line is not 0 rushing yards",
      npc.game_values({"receiving": {"yds": 40, "rec": 3, "tgt": 5, "td": 0}})["rush_yds"] is None
      and npc.game_values({"receiving": {"yds": 40, "rec": 3, "tgt": 5, "td": 0}})["scrim_yds"] == 40)
check("NFL groups from roster positions; unknown is no group",
      (npc.dvp_group("FB"), npc.dvp_group("TE"), npc.dvp_group(""), npc.dvp_group("OT"))
      == ("RB", "TE", None, None))
rows = [["p9", "e1", "2025-10-01", "Bears", {"rush_yds": 50}]]
check("a player with no known position counts in ALL only",
      npc.dvp_lines(rows, "prior", {})[0]["group"] == "OTHER")
team = {"carries_pg": 25.0, "targets_pg": 30.0}
opp = {"ypc_allowed": 5.0, "ypt_allowed": 9.0, "catch_rate_allowed": 0.7}
league = {"ypc": 4.0, "yards_per_target": 7.5, "catch_rate": 0.65}
pl = {"role": "RB", "carry_share": 0.6, "ypc": 4.0, "target_share": 0.1,
      "yards_per_target": 7.0, "catch_rate": 0.7}
on = nproj.project_player(pl, team, opp, league, None)
off = nproj.project_player(pl, team, opp, dict(league, matchup_in_number={"rush": False,
                                                                          "rec": True, "pass": True}), None)
check("a failed multiplier is out of the number (and its ratio still shown)",
      on["rush_yds"] > off["rush_yds"] and abs(off["ypc_adj"] - 4.0) < 1e-9
      and off["rush_matchup"] == on["rush_matchup"])
check("an older games.json (no flags) keeps every multiplier on",
      on["matchup_in_number"] == {"rush": True, "rec": True, "pass": True})
fake = [("rush_yds", 2, "p", 0.7, 0.6, 0.5, 1)] * 30 + [("rush_yds", 2, "p", 0.3, 0.4, 0.5, 0)] * 30
mv_ = npc.matchup_verdicts(fake)
check("a multiplier that predicts better on every game goes in",
      mv_["rush"]["in_number"] is True and mv_["rec"]["in_number"] is False)
sc_ = npc.score(fake)
check("each stat gets a verdict and a calibration curve",
      sc_["rush_yds"]["calibration"] and sc_["rush_yds"]["verdict"].get("verdict"))

# ------------------------------------------------------- 6. delivered chances
try:
    from engines import model_view as mv
    bins = [{"band": "60-69%", "n": 400, "predicted": 0.65, "actual": 0.60},
            {"band": "70-79%", "n": 300, "predicted": 0.75, "actual": 0.66},
            {"band": "80-89%", "n": 200, "predicted": 0.84, "actual": 0.74}]
    markets = (("s2", "SOG O1.5", "sog", 2), ("s3", "SOG O2.5", "sog", 3))
    p, b = mv.delivered_over(0.84, "sog", 1.5, markets, {"s2": bins})
    check("the checker judges a price on the delivered chance", abs(p - 0.74) < 1e-9 and b == "exact")
    p, b = mv.delivered_over(0.84, "sog", 3.5, markets, {"s3": bins})
    check("an untested line borrows the nearest tested line's record", b == "nearest O2.5")
    p, b = mv.delivered_over(0.84, "pts", 0.5, markets, {"s2": bins})
    check("no curve -> the model's own number, labelled raw", p == 0.84 and b == "raw")
    p, b = mv.delivered_over(0.84, "rush_yds", 60.5, (), {"@rush_yds": bins})
    check("NFL stat-level curves are read", abs(p - 0.74) < 1e-9 and b == "this stat's record")
    check("chance colours follow the absolute bands",
          (mv.chance_band(0.85), mv.chance_band(0.7), mv.chance_band(0.55), mv.chance_band(0.4),
           mv.chance_band(0.1), mv.chance_band(None)) == ("elite", "good", "average", "below",
                                                           "poor", None))
except ImportError as exc:
    print(f"SKIP model_view checks ({exc}) — needs streamlit")

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
