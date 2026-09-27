"""The projection engine: every number it produces, and every guard.

The fixture is a two-game week built so each quantity can be checked by
hand — shares are round, the run defence is exactly 1.2x the league, and
the pass defence is exactly neutral, so a matchup multiplier that stops
working shows up as a changed number rather than a plausible one.

Checks:
  1. implied totals are exact, and REFUSE rather than invert when the
     posted line contradicts itself;
  2. volume x rate x matchup produces the documented arithmetic;
  3. a neutral or missing defence leaves the player's own rate alone;
  4. missing inputs yield None, never 0 (rule 6);
  5. a passing TD is never counted as its own score;
  6. league constants are measured from the finals, not assumed;
  7. the walk-forward probe's slicing never leaks the target week.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import nfl_precompute as pc  # noqa: E402
from engines import nfl_projection as proj  # noqa: E402

failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------- 1
a, h, note = proj.implied_totals(
    {"total": 54.5, "spread": -5.5, "details": "BUF -5.5"}, "DET", "BUF")
check("home favourite: BUF 30.0 / DET 24.5", (a, h) == (24.5, 30.0))
check("implied totals sum back to the posted total", a + h == 54.5)
a2, h2, _ = proj.implied_totals(
    {"total": 47, "spread": 3, "details": "DET -3"}, "DET", "BUF")
check("away favourite gets the larger implied total", a2 > h2 and a2 + h2 == 47)
a3, h3, note3 = proj.implied_totals(
    {"total": 47, "spread": -3, "details": "DET -3"}, "DET", "BUF")
check("a line that contradicts itself yields NO implied totals",
      a3 is None and h3 is None and "disagrees" in note3)
a4, h4, note4 = proj.implied_totals({"total": 44}, "DET", "BUF")
check("no spread splits the total evenly and says so",
      a4 == h4 == 22.0 and "split evenly" in note4)
a5, _h5, note5 = proj.implied_totals({}, "DET", "BUF")
check("no total means no implied points", a5 is None and "no posted total" in note5)

# ---------------------------------------------------------------- 2, 3, 4
LEAGUE = {"ypc": 4.2, "yards_per_target": 7.8, "catch_rate": 0.65,
          "td_per_point": 0.10, "team_games": 8}
TEAM = {"carries_pg": 26.0, "targets_pg": 33.0}
SOFT_RUN = {"ypc_allowed": 5.04, "ypt_allowed": 7.8, "catch_rate_allowed": 0.65}
NEUTRAL = {"ypc_allowed": 4.2, "ypt_allowed": 7.8, "catch_rate_allowed": 0.65}
RB = {"pid": "r1", "role": "RB", "gp": 2, "carry_share": 0.50, "target_share": 0.10,
      "ypc": 4.5, "yards_per_target": 6.0, "catch_rate": 0.75,
      "td_total": 3, "td_games": 2, "td_share": 0.375, "team_td_total": 8}

p1 = proj.project_player(RB, TEAM, SOFT_RUN, LEAGUE, 27.0)
check("expected carries = share x team carries", p1["carries"] == 13.0)
check("matchup multiplier is allowed / league (5.04/4.2 = 1.2)",
      p1["rush_matchup"] == 1.2)
check("adjusted ypc = own rate x multiplier", p1["ypc_adj"] == 5.4)
check("rush yards = carries x adjusted rate", p1["rush_yds"] == 70.2)
check("expected targets = share x team targets", p1["targets"] == 3.3)
check("receptions apply the catch-rate matchup", p1["rec"] == round(3.3 * 0.75, 1))
check("scrimmage yards add the two projections",
      p1["scrim_yds"] == round(p1["rush_yds"] + p1["rec_yds"], 1))
check("expected team TDs = implied points x measured rate",
      p1["team_td_exp"] == 2.7)
_lam = 27.0 * 0.10 * 0.375
check("player lambda = team TDs x his share", p1["td_exp"] == round(_lam, 2))
check("anytime % is 1 - exp(-lambda)",
      p1["anytime_pct"] == round(100 * (1 - math.exp(-_lam))))

p2 = proj.project_player(RB, TEAM, NEUTRAL, LEAGUE, 27.0)
check("a league-average defence leaves the rate untouched", p2["ypc_adj"] == 4.5)
p3 = proj.project_player(RB, TEAM, {}, LEAGUE, 27.0)
check("an unmeasured defence leaves the rate untouched", p3["ypc_adj"] == 4.5)
check("...and the row says it is unadjusted", p3.get("unadjusted") is True)
check("a measured defence is NOT flagged unadjusted", "unadjusted" not in p1)

bare = {"pid": "x", "role": "RB", "gp": 0}
p4 = proj.project_player(bare, TEAM, SOFT_RUN, LEAGUE, 27.0)
for _k in ("carries", "rush_yds", "rec", "rec_yds", "anytime_pct"):
    check(f"no sample -> {_k} is None, never 0", p4.get(_k) is None)
check("no implied points -> no TD projection",
      proj.project_player(RB, TEAM, SOFT_RUN, LEAGUE, None).get("anytime_pct") is None)
check("no league constants -> nothing is projected",
      proj.project_player(RB, TEAM, SOFT_RUN, {}, 27.0).get("rush_yds") is None)

# ---------------------------------------------------------------- 5, 6
# One game: Buffalo scores 4 offensive TDs (3 through the air, 1 on the
# ground) and Miami 1. A build that adds passing TDs would say 7 and 2.
LOGS = {
    "q1": {"pid": "q1", "name": "Josh Allen", "team": "Buffalo Bills", "games": {
        "1": {"event_id": "1", "date": "2026-09-13", "week": 1, "team": "Buffalo Bills",
              "opp": "MIA", "passing": {"yds": 300, "att": 33, "cmp": 24, "td": 3},
              "rushing": {"att": 5, "yds": 25, "td": 1}}}},
    "r1": {"pid": "r1", "name": "James Cook", "team": "Buffalo Bills", "games": {
        "1": {"event_id": "1", "date": "2026-09-13", "week": 1, "team": "Buffalo Bills",
              "opp": "MIA", "rushing": {"att": 21, "yds": 105, "td": 0},
              "receiving": {"tgt": 3, "rec": 2, "yds": 12, "td": 0}}}},
    "w1": {"pid": "w1", "name": "Khalil Shakir", "team": "Buffalo Bills", "games": {
        "1": {"event_id": "1", "date": "2026-09-13", "week": 1, "team": "Buffalo Bills",
              "opp": "MIA", "receiving": {"tgt": 12, "rec": 8, "yds": 110, "td": 3}}}},
    "q2": {"pid": "q2", "name": "Tua Tagovailoa", "team": "Miami Dolphins", "games": {
        "1": {"event_id": "1", "date": "2026-09-13", "week": 1, "team": "Miami Dolphins",
              "opp": "BUF", "passing": {"yds": 210, "att": 30, "cmp": 20, "td": 1}}}},
    "w2": {"pid": "w2", "name": "Tyreek Hill", "team": "Miami Dolphins", "games": {
        "1": {"event_id": "1", "date": "2026-09-13", "week": 1, "team": "Miami Dolphins",
              "opp": "BUF", "receiving": {"tgt": 14, "rec": 9, "yds": 120, "td": 1},
              "rushing": {"att": 2, "yds": 4, "td": 0}}}},
}
USAGE = pc.team_game_usage(LOGS)
check("BUF offensive TDs counted as 4, not 7 (a passing TD is the "
      "receiver's TD)", USAGE[("1", "Buffalo Bills")]["td"] == 4)
check("MIA offensive TDs counted as 1", USAGE[("1", "Miami Dolphins")]["td"] == 1)
check("team carries summed from the player lines", USAGE[("1", "Buffalo Bills")]["carries"] == 26)
check("team targets summed from the player lines", USAGE[("1", "Buffalo Bills")]["targets"] == 15)

# team_research keys on the same names the logs carry, so the finals use
# the display names and the logs are re-keyed to match below.
FINALS = [{"date": "2026-09-13", "week": 1, "event_id": "1",
           "away": "Buffalo Bills", "home": "Miami Dolphins",
           "away_score": 31, "home_score": 10,
           "away_box": {}, "home_box": {}}]
LG = pc.league_constants(FINALS, USAGE)
check("league td_per_point measured, not assumed: 5 TD over 41 points",
      LG["td_per_point"] == round(5 / 41, 4))
check("league ypc measured from real carries",
      LG["ypc"] == round((105 + 25 + 4) / 28, 2))
check("league catch rate measured from real targets",
      LG["catch_rate"] == round((2 + 8 + 9) / 29, 3))
check("league constants report their own sample size", LG["team_games"] == 2)
check("no finals -> no constants, rather than invented ones",
      pc.league_constants([], {}) == {})

# DEFENSIVE RATES MUST COME FROM THE OPPONENT'S OFFENCE, and the fixture
# above cannot prove it — GAMES hand-writes ypc_allowed, which is exactly
# the "a fixture cannot test a constant it replaces" trap (rule 2). So
# team_research is run on the real finals and asked directly.
#
# BUF ran 26 times for 130 yards; MIA ran 2 times for 10.
TEAMS_REAL = pc.team_research(FINALS, USAGE)
check("a defence's ypc_allowed is the OPPONENT's rushing, not its own",
      TEAMS_REAL["Miami Dolphins"]["ypc_allowed"] == round(130 / 26, 2))
check("...and the two sides are not the same number",
      TEAMS_REAL["Miami Dolphins"]["ypc_allowed"]
      != TEAMS_REAL["Miami Dolphins"]["ypc"])
check("a team's own ypc is its own rushing",
      TEAMS_REAL["Miami Dolphins"]["ypc"] == round(4 / 2, 2))
check("catch rate allowed is the opponent's catches over targets",
      TEAMS_REAL["Miami Dolphins"]["catch_rate_allowed"] == round(10 / 15, 3))
check("TDs allowed is what the opponent scored",
      TEAMS_REAL["Miami Dolphins"]["td_allowed_pg"] == 4)

PLAYERS = pc.player_summaries(LOGS, USAGE)
check("carry share is season totals over team totals (21/26)",
      PLAYERS["r1"]["carry_share"] == round(21 / 26, 3))
check("target share is season totals over team totals (12/15)",
      PLAYERS["w1"]["target_share"] == round(12 / 15, 3))
check("a receiver's TDs are his own", PLAYERS["w1"]["td_total"] == 3)
check("a passer's throws are NOT his own scores",
      PLAYERS["q1"]["td_total"] == 1 and PLAYERS["q1"]["pass_td"] == 3)

GAMES = [{"away": "Buffalo Bills", "home": "Miami Dolphins",
          "away_abbr": "BUF", "home_abbr": "MIA",
          "status": "scheduled", "window": "Sunday Early",
          "odds": {"total": 47.5, "spread": 3.5, "details": "BUF -3.5"},
          "away_profile": {"carries_pg": 26.0, "targets_pg": 15.0},
          "home_profile": {"carries_pg": 2.0, "targets_pg": 14.0,
                           "ypc_allowed": 5.04, "ypt_allowed": 7.8,
                           "catch_rate_allowed": 0.65},
          "away_players": [dict(PLAYERS[k], role=pc.role_of(PLAYERS[k]))
                           for k in ("q1", "r1", "w1")],
          "home_players": [dict(PLAYERS[k], role=pc.role_of(PLAYERS[k]))
                           for k in ("q2", "w2")]}]
proj.attach_td_shares(GAMES)
_shakir = next(p for p in GAMES[0]["away_players"] if p["name"] == "Khalil Shakir")
check("TD share is his scores over his team's (3 of 4)",
      _shakir["td_share"] == 0.75 and _shakir["team_td_total"] == 4)

rows = proj.projection_rows(GAMES, LG, "Rushing yards")
check("rushing board ranks by projection",
      all(rows[i]["Proj"] >= rows[i + 1]["Proj"] for i in range(len(rows) - 1)))
check("every row carries its own matchup multiplier",
      all(r["Matchup"] is not None for r in rows))
td = proj.projection_rows(GAMES, LG, "Anytime TD")
check("anytime TD board is a percentage between 0 and 100",
      td and all(0 <= r["Proj"] <= 100 for r in td))
check("a quarterback is not on the anytime-TD board",
      not any(r["Pos"] == "QB" for r in td))
check("passing-yards board holds only quarterbacks",
      all(r["Pos"] == "QB" for r in proj.projection_rows(GAMES, LG, "Passing yards")))
# BY NAME, not td[0]. The board is sorted by probability, and a player
# with one score in one game outranks a player with three in four — which
# is the exact noise the sample column exists to expose, so the test must
# not quietly depend on which of them happens to be first.
_shak = next(r for r in td if r["Player"] == "Khalil Shakir")
check("the anytime row carries the raw TD sample, not just a share",
      _shak["TD sample"] == "3 of 4")
check("a player who has never scored still shows his sample honestly",
      next(r for r in td if r["Player"] == "James Cook")["TD sample"] == "0 of 4")
check("a one-of-one share outranks a three-of-four, and the counts say why",
      td[0]["TD sample"] == "1 of 1")
_why = proj.why(td[0], "Anytime TD")
for _bit in ("market implies", "offensive TDs", "chance of at least one"):
    check(f"the WHY line names {_bit!r}", _bit in _why)
_wr = proj.why(rows[0], "Rushing yards")
check("the rushing WHY names the share and the matchup",
      "carries" in _wr and "allows" in _wr)

# A contradictory line must remove the implied points from the row
# rather than quietly projecting the wrong side.
BAD = [dict(GAMES[0], odds={"total": 47.5, "spread": -3.5, "details": "BUF -3.5"})]
proj.attach_td_shares(BAD)
_bad = proj.projection_rows(BAD, LG, "Rushing yards")
check("a self-contradicting line leaves implied points blank",
      _bad and all(r["Implied pts"] is None for r in _bad))
check("...and the row carries the reason",
      _bad and all("disagrees" in (r["_note"] or "") for r in _bad))

# ---------------------------------------------------------------- 7
import nfl_projection_probe as probe  # noqa: E402
TWO = {"a": {"pid": "a", "name": "A", "team": "Buffalo Bills", "games": {
    "1": {"event_id": "1", "week": 1, "team": "BUF", "rushing": {"att": 10, "yds": 50}},
    "2": {"event_id": "2", "week": 2, "team": "BUF", "rushing": {"att": 12, "yds": 70}}}}}
sliced = probe.slice_logs(TWO, {1})
check("walk-forward slicing keeps only the prior week",
      list(sliced["a"]["games"]) == ["1"])
check("...and never leaks the target week",
      all(g["week"] == 1 for g in sliced["a"]["games"].values()))
check("a player with nothing in the window is dropped entirely",
      probe.slice_logs(TWO, {3}) == {})
_act = probe.actuals(TWO, 2)
check("actuals read the target week only", _act[("a", "Rushing yards")] == 70.0)

# ---------------------------------------------------------------- 8
# THE OPPORTUNITY-BASED TD ESTIMATOR — what replaced the share that the
# probe measured as roughly twice as confident as reality.
#
# Everything above this point deliberately passes NO prior, so it
# exercises the fallback. These tests supply one.
_PRIOR = pc.td_opportunity_prior(LOGS)
check("a prior is fitted from real logs at all", bool(_PRIOR))
check("TD per touch is measured, not assumed",
      0.0 < _PRIOR["td_per_opportunity"] < 1.0)
check("the fit reports what it was fitted on",
      _PRIOR["players_fitted"] > 0 and _PRIOR["touches_fitted"] > 0)
check("no logs -> no prior, rather than an invented one",
      pc.td_opportunity_prior({}) == {})

# A league where NOBODY converts differently must fit a strong prior;
# one where players differ wildly must fit a weaker one. That ordering
# is the whole mechanism — it is what makes the estimator loosen as
# real differences emerge instead of needing a hand retune.
def _synth(rates, touches=40):
    out = {}
    for i, rate in enumerate(rates):
        scores = round(rate * touches)
        out[str(i)] = {"games": {"1": {"week": 1,
                                       "rushing": {"att": touches, "td": scores},
                                       "receiving": {"tgt": 0, "td": 0}}}}
    return out


_same = pc.td_opportunity_prior(_synth([0.1] * 40))
_split = pc.td_opportunity_prior(_synth([0.02, 0.30] * 20))
check("a league of identical converters fits a STRONGER prior than a "
      "league of very different ones",
      _same["prior_strength"] > _split["prior_strength"])

_LG_PRIOR = dict(LG, **_PRIOR)
_G2 = json.loads(json.dumps(GAMES))
proj.attach_td_shares(_G2, _LG_PRIOR)
_rows = _G2[0]["away_players"]
check("every skill player gets a share, including one who has never scored",
      all(r.get("td_share") is not None for r in _rows if r.get("role") in ("RB", "REC")))
_cook2 = next(r for r in _rows if r["name"] == "James Cook")
check("a player with zero scores is NOT handed a flat zero",
      _cook2["td_share"] > 0)
check("his rate is shrunk toward the league, not left at 0",
      _cook2["td_rate"] > 0)
check("touches are counted and shown", _cook2["touches"] > 0)

# OVER EVERY ROW, not just RB/REC. A quarterback's carries score too, so
# he takes a slice of the team's expected touchdowns — he is simply not
# shown on this board, because quarterback anytime is its own market.
# Summing only the skill players would assert they absorb scores that
# are not theirs.
check("a team's shares sum to 1 (they divide the team's expected TDs)",
      abs(sum(r["td_share"] for r in _rows) - 1.0) < 0.01)
_qb = next(r for r in _rows if r.get("role") == "QB")
check("the quarterback takes a slice for his carries",
      0 < _qb["td_share"] < 1)
check("...but is not on the anytime board",
      not any(r["Pos"] == "QB"
              for r in proj.projection_rows(_G2, _LG_PRIOR, "Anytime TD")))

# The defect the probe found, reproduced directly: one score on very few
# touches must not outrank a proven high-volume back.
_ONE = [{"away": "A", "home": "B", "away_abbr": "A", "home_abbr": "B",
         "status": "scheduled", "window": "",
         "odds": {"total": 44, "spread": -3, "details": "B -3"},
         "away_profile": {"carries_pg": 25.0, "targets_pg": 30.0},
         "home_profile": {"carries_pg": 25.0, "targets_pg": 30.0,
                          "ypc_allowed": 4.2, "ypt_allowed": 7.8,
                          "catch_rate_allowed": 0.65},
         "away_players": [
             {"pid": "fluke", "name": "One Catch One Score", "role": "REC",
              "pos": "TE", "gp": 3, "opps": 3.0, "td_games": 3, "td_total": 1,
              "target_share": 0.10, "yards_per_target": 8.0, "catch_rate": 0.7},
             {"pid": "bell", "name": "Every Down Back", "role": "RB",
              "pos": "RB", "gp": 3, "opps": 22.0, "td_games": 3, "td_total": 2,
              "carry_share": 0.70, "ypc": 4.4}],
         "home_players": []}]
proj.attach_td_shares(_ONE, _LG_PRIOR)
_fluke = _ONE[0]["away_players"][0]
_bell = _ONE[0]["away_players"][1]
check("a one-score-on-nine-touches tight end no longer outranks a "
      "22-touch back", _bell["td_share"] > _fluke["td_share"])
_td_rows = proj.projection_rows(_ONE, _LG_PRIOR, "Anytime TD")
_pct = {r["Player"]: r["Proj"] for r in _td_rows}
check("...and that ordering survives into the board",
      _pct["Every Down Back"] > _pct["One Catch One Score"])
check("no player on the board is projected at a flat 0%",
      all(r["Proj"] > 0 for r in _td_rows))
check("the row shows scores ON TOUCHES, not a team share",
      "on" in (_td_rows[0]["TD sample"] or ""))

# The fallback must still work, so an older data file renders rather
# than blanking.
_G3 = json.loads(json.dumps(GAMES))
proj.attach_td_shares(_G3, {})
check("with no prior, the old realised-share path still produces shares",
      any(r.get("td_share") is not None for r in _G3[0]["away_players"]))

# ---------------------------------------------------------------- 9
# THE SAME GAME ARRIVING TWICE MUST NOT BECOME TWO ROWS.
#
# ESPN's NFL scoreboard answers any date inside the current week with
# the whole week's fixtures, so the day loop saw each game several times
# and appended it each time: 49 entries for 16 real games, every player
# three or four times on every board, and a dead page on a duplicate
# Streamlit key. The numbers were right; the ROWS multiplied.
_pc_src = (ROOT / "nfl_precompute.py").read_text()
_pc_code = "\n".join(l.split("#")[0] for l in _pc_src.splitlines())
check("the fetcher keys this week's games by event id",
      'week_events[g["event_id"]] = g' in _pc_code)
check("...and keys finals by event id too",
      'finals[g["event_id"]]' in _pc_code)
check("neither is appended to a list any more",
      "week_events.append(" not in _pc_code and "finals.append(" not in _pc_code)

# A card key must not be a player's name: names are not unique, and a
# duplicate key takes the whole page down rather than drawing one card
# badly.
_view = (ROOT / "app" / "views" / "NFL_Projections.py").read_text()
check("projection cards are keyed by position, not by player name",
      "nfl_proj_{_i}" in _view and 'nfl_proj_{r["Player"]}' not in _view)

# THE EXIT GATE MUST BE THE LAST THING IN THIS FILE. Checks appended
# below it would record into `failures` after the only code that reads
# `failures` has already run — which has happened in this repo and sent
# six negative controls back green against deliberately broken code.
if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nAll NFL projection checks passed.")
