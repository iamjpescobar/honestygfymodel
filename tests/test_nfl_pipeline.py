"""NFL week pipeline, end to end, against ESPN-shaped fixtures.

The scoreboard fixture is the FLATTENED /scoreboard/header shape — the
one measured answering from Actions for WNBA (no `competitions`, team
fields on the competitor, record as a bare string, odds as ONE object).
That is rule 5: a fixture that is not production's shape tests nothing.

Checks:
  1. week math: kickoff Wed Sep 9 is week 1; Tue Sep 15 starts week 2.
  2. main() builds the week, parses box scores into team profiles with
     OFFENSE and ALLOWED numbers on the same definitions, and ranks them.
  3. a QB who never ran the ball has NO rushing average (missing != 0).
  4. a week whose finals parse into nothing REFUSES to publish.
  5. load_week blanks a stale week; mismatches() ranks the biggest gap.
"""
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import nfl_precompute as npc  # noqa: E402
from engines import espn_feed as ef  # noqa: E402
from engines import nfl_week as nw  # noqa: E402

failures = []

# THE REAL PROJECTION LOG, SNAPSHOTTED BEFORE ANYTHING RUNS.
#
# The check at the bottom compares this against the same directory
# afterwards. The FIRST version asserted the directory was EMPTY, which
# was the wrong property and took the nightly down: main() writes a file
# there on every successful run and the workflow commits it, so from the
# first good night onward the checkout contains one, the gate failed,
# and the job refused to fetch — for every league, not just football.
#
# What this actually means to guard is that running the pipeline UNDER
# TEST adds nothing to the real record. Guard the thing you mean.
# CONTENTS, not just filenames. A leak writes to TODAY's filename, and
# on any day the nightly has already committed one, a set of names is
# identical before and after while the real record has been silently
# overwritten with fixture data. Both negative controls came back green
# against exactly that — a check that cannot tell the two behaviours
# apart (rule 4).
_REPO_LOG = ROOT / "data" / "nfl" / "projections"


def _log_state():
    if not _REPO_LOG.exists():
        return {}
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in _REPO_LOG.glob("*.json")}


_LOG_BEFORE = _log_state()


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------- 1
check("Sep 8 2026 is week 1 (Tuesday start)", nw.week_of(date(2026, 9, 8)) == 1)
check("kickoff Sep 9 is week 1", nw.week_of(date(2026, 9, 9)) == 1)
check("Mon Sep 14 is still week 1", nw.week_of(date(2026, 9, 14)) == 1)
check("Tue Sep 15 is week 2", nw.week_of(date(2026, 9, 15)) == 2)
check("before kickoff week is None", nw.week_of(date(2026, 9, 1)) is None)
check("week 2 window is Sep 15..21",
      nw.week_window(2) == (date(2026, 9, 15), date(2026, 9, 21)))
from datetime import datetime as _dt  # noqa: E402
check("1:00 PM Sunday is Sunday Early",
      nw.tv_window(_dt(2026, 9, 20, 13, 0, tzinfo=nw.EASTERN)) == "Sunday Early")
check("8:20 PM Sunday is Sunday Night",
      nw.tv_window(_dt(2026, 9, 20, 20, 20, tzinfo=nw.EASTERN)) == "Sunday Night")

# ---------------------------------------------------------------- fixtures
TEAMS = {
    "1": ("Buffalo Bills", "BUF", "00338d"), "2": ("Miami Dolphins", "MIA", "008e97"),
    "3": ("Kansas City Chiefs", "KC", "e31837"), "4": ("Denver Broncos", "DEN", "fb4f14"),
}


def _comp(tid, side, score, rec):
    n, a, c = TEAMS[tid]
    return {"homeAway": side, "score": str(score), "id": tid, "displayName": n,
            "abbreviation": a, "color": c, "logo": f"https://x/{a}.png", "record": rec}


def _event(eid, iso, status, away, home, a_s="0", h_s="0"):
    return {"id": eid, "date": iso, "location": "Somewhere Stadium",
            "fullStatus": {"type": {"name": status, "completed": status == "STATUS_FINAL",
                                    "shortDetail": "Final" if status == "STATUS_FINAL" else ""}},
            "competitors": [_comp(away, "away", a_s, "1-0"), _comp(home, "home", h_s, "0-1")],
            "odds": {"details": "BUF -3.5", "overUnder": 47.5},
            "broadcasts": ["CBS"]}


def header(events):
    return {"sports": [{"leagues": [{"events": events}]}]}


DAYS = {
    # week 1 finals
    "20260913": [_event("101", "2026-09-13T17:00Z", "STATUS_FINAL", "1", "2", 31, 10),
                 _event("102", "2026-09-13T20:25Z", "STATUS_FINAL", "3", "4", 20, 24)],
    # week 2 (built on Tue Sep 15)
    "20260920": [_event("201", "2026-09-20T17:00Z", "STATUS_SCHEDULED", "2", "3"),
                 _event("202", "2026-09-21T00:20Z", "STATUS_SCHEDULED", "4", "1")],
}


def _team_stats(yds, pas, rush, to, third, rz, sacked):
    return [{"name": "totalYards", "displayValue": str(yds)},
            {"name": "netPassingYards", "displayValue": str(pas)},
            {"name": "rushingYards", "displayValue": str(rush)},
            {"name": "turnovers", "displayValue": str(to)},
            {"name": "thirdDownEff", "displayValue": third},
            {"name": "redZoneAttempts", "displayValue": rz},
            {"name": "sacksYardsLost", "displayValue": sacked},
            {"name": "possessionTime", "displayValue": "31:30"}]


def _players(tid, qb_line, rush_rows, rec_rows):
    n = TEAMS[tid][0]
    groups = [{"name": "passing",
               "keys": ["completions/passingAttempts", "passingYards", "yardsPerPassAttempt",
                        "passingTouchdowns", "interceptions", "sacks-sackYardsLost"],
               "labels": ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS"],
               "athletes": [qb_line]},
              {"name": "rushing",
               "keys": ["rushingAttempts", "rushingYards", "yardsPerRushAttempt",
                        "rushingTouchdowns", "longRushing"],
               "labels": ["CAR", "YDS", "AVG", "TD", "LONG"], "athletes": rush_rows},
              # receiving WITHOUT keys — labels only, to exercise the fallback.
              {"name": "receiving",
               "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"], "athletes": rec_rows}]
    return {"team": {"id": tid, "displayName": n}, "statistics": groups}


def _ath(pid, name, stats):
    return {"athlete": {"id": pid, "displayName": name}, "stats": stats}


SUMMARIES = {
    "101": {"boxscore": {
        "teams": [{"team": {"id": "1", "displayName": "Buffalo Bills"},
                   "statistics": _team_stats(420, 300, 120, 0, "7-12", "3-4", "1-6")},
                  {"team": {"id": "2", "displayName": "Miami Dolphins"},
                   "statistics": _team_stats(250, 190, 60, 3, "3-11", "1-3", "4-30")}],
        "players": [
            _players("1", _ath("q1", "Josh Allen", ["24/33", "300", "9.1", "3", "0", "1-6"]),
                     [_ath("r1", "James Cook", ["18", "95", "5.3", "1", "22"]),
                      _ath("q1", "Josh Allen", ["5", "25", "5.0", "0", "10"])],
                     [_ath("w1", "Khalil Shakir", ["7", "88", "12.6", "1", "30", "9"])]),
            _players("2", _ath("q2", "Tua Tagovailoa", ["20/30", "210", "7.0", "1", "2", "4-30"]),
                     [_ath("r2", "De'Von Achane", ["12", "60", "5.0", "0", "15"])],
                     [_ath("w2", "Tyreek Hill", ["6", "80", "13.3", "0", "28", "10"])])]}},
    "102": {"boxscore": {
        "teams": [{"team": {"id": "3", "displayName": "Kansas City Chiefs"},
                   "statistics": _team_stats(330, 250, 80, 1, "5-12", "2-3", "2-10")},
                  {"team": {"id": "4", "displayName": "Denver Broncos"},
                   "statistics": _team_stats(360, 230, 130, 1, "6-13", "3-4", "2-12")}],
        "players": [
            _players("3", _ath("q3", "Patrick Mahomes", ["22/35", "260", "7.4", "2", "1", "2-10"]),
                     [_ath("r3", "Isiah Pacheco", ["14", "70", "5.0", "0", "12"])],
                     [_ath("w3", "Travis Kelce", ["8", "90", "11.3", "1", "25", "11"])]),
            _players("4", _ath("q4", "Bo Nix", ["21/31", "240", "7.7", "2", "0", "2-12"]),
                     [_ath("r4", "J.K. Dobbins", ["20", "110", "5.5", "1", "30"])],
                     [_ath("w4", "Courtland Sutton", ["6", "95", "15.8", "1", "40", "8"])])]}},
    "201": {"gameInfo": {"venue": {"fullName": "Arrowhead", "indoor": False},
                         "weather": {"temperature": 71, "displayValue": "Sunny", "gust": 22}},
            "injuries": [{"team": {"displayName": "Miami Dolphins"},
                          "injuries": [{"athlete": {"displayName": "Jaylen Waddle",
                                                    "position": {"abbreviation": "WR"}},
                                        "status": "Questionable"}]}]},
    "202": {"gameInfo": {"venue": {"fullName": "Highmark", "indoor": True}}},
}

ROSTER = {"athletes": [{"position": "offense", "items": [
    {"id": pid, "displayName": nm, "position": {"abbreviation": pos}}
    for pid, nm, pos in (("q1", "Josh Allen", "QB"), ("r1", "James Cook", "RB"),
                         ("w1", "Khalil Shakir", "WR"), ("q2", "Tua Tagovailoa", "QB"),
                         ("r2", "De'Von Achane", "RB"), ("w2", "Tyreek Hill", "WR"),
                         ("q3", "Patrick Mahomes", "QB"), ("r3", "Isiah Pacheco", "RB"),
                         ("w3", "Travis Kelce", "TE"), ("q4", "Bo Nix", "QB"),
                         ("r4", "J.K. Dobbins", "RB"), ("w4", "Courtland Sutton", "WR"))]}]}


def fake_get(url, _attempts=3, summaries=None):
    summaries = SUMMARIES if summaries is None else summaries
    if "scoreboard/header" in url:
        d = url.rsplit("dates=", 1)[1]
        return header(DAYS.get(d, []))
    if "/summary?event=" in url:
        return summaries.get(url.rsplit("=", 1)[1], {})
    if "/roster" in url:
        return ROSTER
    raise RuntimeError("unexpected url " + url)


def run(get, today):
    saved = (ef.get_json, npc.time.sleep, npc.PROJECTION_LOG, npc.PRIOR_PATH,
             npc.PRIOR_PLAYERS_PATH)
    ef.get_json = get
    npc.time.sleep = lambda *_a: None
    ef._PREFERRED.clear()
    cwd = os.getcwd()
    tmp = tempfile.mkdtemp()
    # THE PROJECTION LOG GOES TO THE TEMP DIR, NOT THE REPO. main()
    # writes it to a repo path on purpose so CI can commit it, which
    # means an un-redirected test run drops fixture projections into the
    # real record — see the note on npc.PROJECTION_LOG.
    npc.PROJECTION_LOG = Path(tmp) / "projlog"
    # Same for the game model's 2025 file: written once when missing, so
    # a pipeline under test must write it to its sandbox, never the repo.
    npc.PRIOR_PATH = Path(tmp) / "prior_season.json"
    npc.PRIOR_PLAYERS_PATH = Path(tmp) / "prior_players.json"
    npc.PICKS_ROOT = Path(tmp) / "model_picks"
    os.chdir(tmp)
    try:
        npc.main(today=today)
        return json.loads((Path(tmp) / "build_data/data/nfl/games.json").read_text())
    finally:
        os.chdir(cwd)
        (ef.get_json, npc.time.sleep, npc.PROJECTION_LOG, npc.PRIOR_PATH,
         npc.PRIOR_PLAYERS_PATH) = saved


# ---------------------------------------------------------------- 2
out = run(fake_get, date(2026, 9, 15))
check("week 2 built", out.get("week") == 2 and out.get("week_start_et") == "2026-09-15")
check("two games this week", len(out["games"]) == 2)
check("two finals parsed", out.get("finals_parsed") == 2)
buf = out["teams"].get("Buffalo Bills") or {}
check("BUF offense pass yds 300", buf.get("pass_ypg") == 300)
check("BUF pass ALLOWED is MIA's 190", buf.get("pass_allowed") == 190)
check("BUF takeaways = MIA turnovers (3)", buf.get("takeaways_pg") == 3)
check("BUF 3rd down 7/12 = 58.3%", buf.get("third_pct") == 58.3)
check("BUF sacks = MIA sacked (4)", buf.get("sacks_pg") == 4)
check("BUF record 1-0", buf.get("record") == "1-0")
check("BUF ranked #1 in points", (buf.get("ranks") or {}).get("pf_pg") == 1)
check("BUF ranked #1 in fewest pass yds allowed",
      (buf.get("ranks") or {}).get("pass_allowed") == 1)
g201 = next(g for g in out["games"] if g["event_id"] == "201")
check("header string record read", g201.get("away_record") == "1-0")
check("header odds OBJECT read", (g201.get("odds") or {}).get("total") == 47.5)
check("header broadcast strings read", g201.get("network") == "CBS")
check("window assigned from ET kickoff", g201.get("window") == "Sunday Early")
check("SNF window", next(g for g in out["games"] if g["event_id"] == "202")["window"] == "Sunday Night")
check("weather read from summary", g201.get("temp_f") == 71 and g201.get("gust_mph") == 22)
check("injury read", g201.get("injuries", {}).get("Miami Dolphins", [{}])[0].get("status") == "Questionable")
check("indoor flag read", next(g for g in out["games"] if g["event_id"] == "202").get("indoor") is True)
check("team profile attached to game", (g201.get("away_profile") or {}).get("gp") == 1)

# ---------------------------------------------------------------- 3
buf_players = next(g for g in out["games"] if g["event_id"] == "202")["home_players"]
allen = next(p for p in buf_players if p["name"] == "Josh Allen")
check("Allen role is QB (volume, not label)", allen["role"] == "QB")
check("Allen pass yds 300 and rush yds 25", allen.get("pass_yds") == 300 and allen.get("rush_yds") == 25)
mahomes = next(p for p in g201["home_players"] if p["name"] == "Patrick Mahomes")
check("Mahomes has NO rushing average — he has no rushing line",
      "rush_yds" not in mahomes)
shakir = next(p for p in buf_players if p["name"] == "Khalil Shakir")
check("receiving parsed from LABELS when keys absent",
      shakir.get("rece_yds") == 88 and shakir.get("rece_tgt") == 9)
check("roster position attached", shakir.get("pos") == "WR")

# ---------------------------------------------------------------- 4
empty = {k: ({} if k in ("101", "102") else v) for k, v in SUMMARIES.items()}
try:
    run(lambda u, _attempts=3: fake_get(u, _attempts, empty), date(2026, 9, 15))
    check("unparseable finals refuse to publish", False)
except RuntimeError as exc:
    check("unparseable finals refuse to publish", "ZERO box scores" in str(exc))

pre = run(fake_get, date(2026, 9, 1))
check("before kickoff writes an honest preseason file",
      pre.get("phase") == "preseason" and pre.get("games") == [])

# ---------------------------------------------------------------- 5
p, stt = nw.load_week(date(2026, 9, 22), _payload=out)
check("week 2 file on Sep 22 is stale and shows no games", stt == "stale" and p["games"] == [])
p, stt = nw.load_week(date(2026, 9, 17), _payload=out)
check("week 2 file on Sep 17 is current", stt == "current" and len(p["games"]) == 2)
check("stale note names both weeks",
      "week 2" in nw.staleness_note(out, "stale", date(2026, 9, 22))
      and "week 3" in nw.staleness_note(out, "stale", date(2026, 9, 22)))
mm = nw.mismatches(out["games"])
check("mismatches only pair ranked units", all(r["att_rank"] and r["def_rank"] for r in mm))
check("mismatches sorted biggest edge first",
      all(mm[i]["edge"] >= mm[i + 1]["edge"] for i in range(len(mm) - 1)))
check("edge = defender rank - attacker rank",
      all(r["edge"] == r["def_rank"] - r["att_rank"] for r in mm))
rows = nw.prop_rows(out["games"], "QB")
check("prop rows: 4 QBs, most pass yards first",
      len(rows) == 4 and rows[0]["Player"] == "Josh Allen")
check("edge tiers scale with league size",
      nw.edge_tier(20, 32) == "Glaring" and nw.edge_tier(2, 4) == "Strong")

# ---------------------------------------------------------------- 6
# THE LIVE OVERLAY BUG: Thursday night's final never reached the card,
# because the view asked the live feed about TODAY only. On Friday that
# is no day at all, so a finished game sat there as "scheduled" with a
# kickoff two days in the past.
_wk = [
    {"kick_date_et": "2026-09-17", "status": "scheduled"},   # TNF, played
    {"kick_date_et": "2026-09-20", "status": "scheduled"},   # Sunday, ahead
    {"kick_date_et": "2026-09-21", "status": "scheduled"},   # MNF, ahead
]
check("Friday still asks about Thursday's game",
      nw.live_days(_wk, date(2026, 9, 18)) == ("2026-09-17",))
check("a day in the future is never asked about",
      nw.live_days(_wk, date(2026, 9, 16)) == ())
check("Sunday asks about both days that have started",
      nw.live_days(_wk, date(2026, 9, 20)) == ("2026-09-17", "2026-09-20"))
check("a day already recorded final is not re-asked",
      nw.live_days([dict(_wk[0], status="final")], date(2026, 9, 18)) == ())
check("live_days returns a tuple (it is used as a cache key)",
      isinstance(nw.live_days(_wk, date(2026, 9, 18)), tuple))

# ---------------------------------------------------------------- 7
# THE SUITE MUST NOT WRITE INTO THE REAL PROJECTION LOG. main() writes
# it to a repo path deliberately so CI commits it; a test run that is
# not redirected therefore files synthetic projections under today's
# date, indistinguishable from a real record, for a grader to score
# later as claims the site never made.
_log_after = _log_state()
_touched = sorted(n for n in set(_log_after) | set(_LOG_BEFORE)
                  if _log_after.get(n) != _LOG_BEFORE.get(n))
check("running the pipeline neither added to nor overwrote the real "
      "projection log", not _touched)
if _touched:
    print(f"      touched: {_touched}")
check("the log path is redirectable at all (a module constant, not inline)",
      hasattr(npc, "PROJECTION_LOG"))

# ---------------------------------------------------------------- 8
# THE REAL FAILURE, REPLAYED: ESPN answers every date inside the current
# week with the WHOLE week's fixtures. Production returned 49 entries
# for 16 games and every board showed each player three or four times.
#
# The fixture above gives each day its own games, so it could never
# catch this. This one returns the same two week-2 fixtures for EVERY
# day of that week, which is what the live feed actually does.
_WEEK_WIDE = {d: DAYS["20260920"] for d in
              ("20260915", "20260916", "20260917", "20260918",
               "20260919", "20260920", "20260921")}
_WEEK_WIDE["20260913"] = DAYS["20260913"]


def _wide_get(url, _attempts=3):
    if "scoreboard/header" in url:
        return header(_WEEK_WIDE.get(url.rsplit("dates=", 1)[1], []))
    return fake_get(url, _attempts)


_dup = run(_wide_get, date(2026, 9, 15))
_ids = [g["event_id"] for g in _dup["games"]]
check("a week returned on all seven days still yields each game ONCE",
      len(_ids) == len(set(_ids)) == 2)
_names = [p["name"] for g in _dup["games"] for s in ("away", "home")
          for p in g.get(f"{s}_players") or []]
check("...and each player appears once, not seven times",
      len(_names) == len(set(_names)))
check("the finals behind the numbers are not multiplied either",
      _dup.get("finals_parsed") == 2)
check("league constants still rest on the right sample",
      (_dup.get("league") or {}).get("team_games") == 4)

# THE EXIT GATE MUST BE THE LAST THING IN THIS FILE. Checks appended
# below it record into `failures` after the only code that reads
# `failures` has already run, which sends controls back green against
# deliberately broken code.
if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nAll NFL pipeline checks passed.")
