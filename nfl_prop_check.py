"""
NFL props — defense vs position, and the walk-forward test that grades
the prop chances (10-06).

Called by nfl_precompute.main with what it already holds (finals, box
score logs, rosters, last season's players). Two jobs:

1. DEFENSE VS POSITION. What every defense allowed to QBs, RBs, WRs and
   TEs — passing, rushing and receiving yards, attempts, catches,
   targets, touchdowns — this season and last, blended at a fitted
   weight and ranked (engines/defense_matchup). Last season's player-game
   lines are parsed ONCE from the 2025 box scores (the same parser) and
   committed as data/nfl/prior_dvp.json.

   POSITIONS: ESPN box scores carry no position, so a player's group is
   his ROSTER position (every team's roster is read each night). A
   2025 player on no current roster has no known position: his lines
   count in the defense's ALL total and in no position group — never
   guessed into one (rule 6).

2. THE PROP TEST. Until today every NFL prop chance was UNTESTED. For
   every week after the first, profiles are built from the earlier
   weeks only (last season folded in at the nightly's fitted weights),
   every player who played is projected, and each stat is priced at a
   line next to his own average to date (floor + 0.5 — where books hang
   it). Scored against what happened, and against the bettor's baseline:
   how often HE cleared that line in his earlier games. Per stat: paired
   verdict, calibration curve (what the page's checker reads, so a price
   you type is judged on what calls like it DELIVERED), and the same
   test with the defense multiplier switched off — which decides whether
   the multiplier stays in the number (league["matchup_in_number"]).

   Look-ahead stated: the game-to-game scatter (prop_spreads) and the
   last-season weights are league-level numbers measured on the whole
   season so far; every PLAYER and TEAM number uses earlier weeks only.

Prints [verify] lines. Pure apart from the one-time prior fetch.
"""
import json
import sys
import time
from math import floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from engines import defense_matchup as dm          # noqa: E402
from engines import model_math as mm               # noqa: E402
from engines import nfl_projection as nproj        # noqa: E402
from engines import nfl_prop_odds as npo           # noqa: E402

PRIOR_DVP_PATH = ROOT / "data" / "nfl" / "prior_dvp.json"
DVP_GROUPS = ("QB", "RB", "WR", "TE")
# The board's stat keys (engines/nfl_prop_odds.STATS) — one table each.
DVP_STATS = ("pass_yds", "pass_cmp", "pass_att", "pass_td", "pass_int", "rush_yds",
             "carries", "rec_yds", "rec", "targets", "scrim_yds", "td")
DVP_GROUP_LABELS = {"QB": "quarterbacks", "RB": "running backs", "WR": "wide receivers",
                    "TE": "tight ends", "ALL": "all players"}
DVP_STAT_LABELS = {"pass_yds": "passing yards", "pass_cmp": "completions",
                   "pass_att": "pass attempts", "pass_td": "passing TDs",
                   "pass_int": "interceptions", "rush_yds": "rushing yards",
                   "carries": "carries", "rec_yds": "receiving yards", "rec": "receptions",
                   "targets": "targets", "scrim_yds": "rush + rec yards", "td": "touchdowns"}
# Which projection rate each matchup multiplier feeds, and the stats its
# test is pooled over.
MATCHUP_FAMILIES = {"rush": ("rush_yds",), "rec": ("rec_yds", "rec"), "pass": ("pass_yds",)}


def dvp_group(pos):
    p = str(pos or "").upper()
    if p == "QB":
        return "QB"
    if p in ("RB", "FB", "HB"):
        return "RB"
    if p in ("WR", "TE"):
        return p
    return None


def game_values(g):
    """{stat: value} for one box-score game line; a category the player
    has no line in is None for its stats (not a zero he was measured at)."""
    r, c, pa = g.get("rushing"), g.get("receiving"), g.get("passing")
    r_, c_, pa_ = r or {}, c or {}, pa or {}
    out = {
        "pass_yds": pa_.get("yds") if pa else None, "pass_cmp": pa_.get("cmp") if pa else None,
        "pass_att": pa_.get("att") if pa else None, "pass_td": pa_.get("td") if pa else None,
        "pass_int": pa_.get("int") if pa else None,
        "rush_yds": r_.get("yds") if r else None, "carries": r_.get("att") if r else None,
        "rec_yds": c_.get("yds") if c else None, "rec": c_.get("rec") if c else None,
        "targets": c_.get("tgt") if c else None,
        "scrim_yds": ((r_.get("yds") or 0) + (c_.get("yds") or 0)) if (r or c) else None,
        "td": ((r_.get("td") or 0) + (c_.get("td") or 0)) if (r or c) else None,
    }
    return out


def dvp_rows(logs):
    """Compact [pid, event_id, date, opp, {stat: value}] rows from box-score logs."""
    out = []
    for pid, rec in (logs or {}).items():
        for eid, g in (rec.get("games") or {}).items():
            if not g.get("opp"):
                continue
            vals = {k: v for k, v in game_values(g).items() if v is not None}
            if vals:
                out.append([str(pid), str(eid), g.get("date"), g["opp"], vals])
    return out


def dvp_lines(rows, season, pos_of):
    """engines/defense_matchup lines; a player with no known position is
    group "OTHER" — in the defense's ALL total, in no position group."""
    return [{"season": season, "defense": opp, "game": eid,
             "group": dvp_group((pos_of or {}).get(pid)) or "OTHER", "stats": vals}
            for pid, eid, _d, opp, vals in rows or []]


def load_or_fetch_prior_dvp(prior_finals, summary_fn, parse_fn, path=None, sleep=0.05):
    """Last season's per-player-game rows, parsed once and committed."""
    path = Path(path or PRIOR_DVP_PATH)
    if path.exists():
        try:
            return json.loads(path.read_text()).get("rows") or []
        except Exception as exc:          # noqa: BLE001
            print(f"  prior dvp file unreadable ({exc}) — refetching")
    if not prior_finals:
        return []
    logs, parsed = {}, 0
    for f in prior_finals:
        eid = f.get("event_id")
        if not eid:
            continue
        try:
            _lines, n = parse_fn(summary_fn(eid), eid, f["date"], None, logs)
            parsed += 1 if n else 0
        except Exception as exc:          # noqa: BLE001
            print(f"  prior summary {eid} failed: {exc}")
        time.sleep(sleep)
    print(f"  [verify] NFL prior defense lines: {parsed}/{len(prior_finals)} box scores parsed")
    if parsed < 0.9 * len(prior_finals):
        print("::warning::NFL prior box scores short — defense table runs on this season alone.")
        return []
    rows = dvp_rows(logs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"season": 2025, "rows": rows}, separators=(",", ":")))
    return rows


def build_dvp(cur_logs, prior_rows, pos_of):
    return dm.build_table(dvp_lines(dvp_rows(cur_logs), dm.CUR, pos_of)
                          + dvp_lines(prior_rows, dm.PRIOR, pos_of),
                          DVP_STATS, DVP_GROUPS)


# ----------------------------------------------------------------------
# The prop test
# ----------------------------------------------------------------------
def _slice(logs, weeks):
    out = {}
    for pid, rec in logs.items():
        games = {eid: g for eid, g in (rec.get("games") or {}).items() if g.get("week") in weeks}
        if games:
            out[pid] = dict(rec, games=games)
    return out


def _history(plogs, pid, stat):
    rec = plogs.get(pid) or {}
    vals = [game_values(g).get(stat) for g in sorted((rec.get("games") or {}).values(),
                                                     key=lambda g: g.get("date") or "")]
    return [v for v in vals if v is not None]


def _line_for(hist, stat):
    """A line next to his own average to date, as books hang it."""
    if stat == "td":
        return 0.5
    if not hist:
        return None
    return floor(sum(hist) / len(hist)) + 0.5


def walk_forward(finals, logs, pc, prior_players=None, prior_w=None, spreads=None, flags=None):
    """[(stat, week, pid, p_model, p_no_matchup, p_baseline, y)] — every
    player-game after week one, priced from earlier weeks only. p_model
    uses the defense multipliers `flags` switches on (default: all);
    p_no_matchup uses none."""
    all_off = {f: False for f in MATCHUP_FAMILIES}
    flags = dict(flags) if flags is not None else {f: True for f in MATCHUP_FAMILIES}
    weeks = sorted({f["week"] for f in finals if f.get("week")})
    out = []
    for w in weeks[1:]:
        prior_wks = [x for x in weeks if x < w]
        before = [f for f in finals if f.get("week") in prior_wks]
        plogs = _slice(logs, prior_wks)
        usage = pc.team_game_usage(plogs)
        league = pc.league_constants(before, usage)
        if not league:
            continue
        league.update(pc.td_opportunity_prior(plogs))
        league.update(pc.qb_rate_priors(plogs))
        teams = pc.attach_ranks(pc.team_research(before, usage))
        players = pc.player_summaries(plogs, usage)
        if prior_players and prior_w:
            players = {pid: pc.merge_prior(p, prior_players.get(pid), prior_w)
                       for pid, p in players.items()}
        for f in [x for x in finals if x.get("week") == w]:
            a_pts, h_pts, _n = nproj.implied_totals(f.get("odds") or {}, f.get("away_abbr"),
                                                    f.get("home_abbr"))
            g = {"away_players": [], "home_players": []}
            for side in ("away", "home"):
                for p in players.values():
                    if p.get("team") != f[side]:
                        continue
                    q = dict(p)
                    q["role"] = pc.role_of(q)
                    if q["role"]:
                        g[f"{side}_players"].append(q)
            nproj.attach_td_shares([g], league)
            for side, other in (("away", "home"), ("home", "away")):
                team, opp = teams.get(f[side]), teams.get(f[other])
                implied = a_pts if side == "away" else h_pts
                for p in g[f"{side}_players"]:
                    game = ((logs.get(p["pid"]) or {}).get("games") or {}).get(str(f["event_id"]))
                    if not game:
                        continue                      # did not play: void, not a miss
                    actual = game_values(game)
                    on = nproj.project_player(p, team, opp, dict(league, matchup_in_number=flags),
                                              implied)
                    off = nproj.project_player(p, team, opp, dict(league, matchup_in_number=all_off),
                                               implied)
                    for stat, _lab, key, market, roles in npo.STATS:
                        if p["role"] not in roles or actual.get(stat) is None and stat != "td":
                            continue
                        y_val = actual.get(stat) or 0
                        hist = _history(plogs, p["pid"], stat)
                        line = _line_for(hist, stat)
                        if line is None or not hist:
                            continue
                        pm_on = npo.stat_pmf(market, on.get(key), spreads)
                        pm_off = npo.stat_pmf(market, off.get(key), spreads)
                        if not pm_on or not pm_off:
                            continue
                        base = sum(1 for h in hist if h > line) / len(hist)
                        out.append((stat, w, p["pid"], mm.over_prob_pmf(pm_on, line),
                                    mm.over_prob_pmf(pm_off, line), base,
                                    1 if y_val > line else 0))
    return out


def score(rows):
    """{stat: {n, briers, verdict vs his own rate, calibration}}."""
    out = {"n": len(rows)}
    by = {}
    for stat, _w, _pid, p, _p0, b, y in rows:
        if p is None:
            continue
        by.setdefault(stat, []).append((p, b, y))
    for stat, xs in by.items():
        m = [(p, y) for p, _b, y in xs]
        base = [(min(max(b, 0.0), 1.0), y) for _p, b, y in xs]
        sm, sb = mm.score_predictions(m), mm.score_predictions(base)
        out[stat] = {"n": sm["n"], "model_brier": sm["brier"], "baseline_brier": sb["brier"],
                     "verdict": mm.paired_verdict([(p - y) ** 2 for p, y in m],
                                                  [(p - y) ** 2 for p, y in base]),
                     "calibration": mm.calibration_bins(m)}
    return out


def matchup_verdicts(rows):
    """Per family: does the defense multiplier (all on) beat none, on the
    same player-games? Log loss, paired. Only "beats" puts it in the number."""
    out = {}
    for fam, stats in MATCHUP_FAMILIES.items():
        on, off = [], []
        for stat, _w, _pid, p, p0, _b, y in rows:
            if stat in stats and p is not None and p0 is not None:
                on.append(mm.log_loss(p, y))
                off.append(mm.log_loss(p0, y))
        v = mm.paired_verdict(on, off)
        out[fam] = {"n": len(on), "verdict": v, "in_number": v.get("verdict") == "beats"}
    return out


def run(finals, logs, pc, prior_players=None, prior_w=None, spreads=None):
    """The whole test: decide the multipliers, then grade the props the
    page will actually show (with only the adopted multipliers)."""
    rows = walk_forward(finals, logs, pc, prior_players, prior_w, spreads)
    if not rows:
        return {"note": "needs two weeks of finals"}
    fam = matchup_verdicts(rows)
    flags = {f: v["in_number"] for f, v in fam.items()}
    if not all(flags.values()):
        rows = walk_forward(finals, logs, pc, prior_players, prior_w, spreads, flags)
    out = score(rows)
    out["matchup"] = fam
    out["matchup_in_number"] = flags
    out["weeks"] = sorted({r[1] for r in rows})
    return out
