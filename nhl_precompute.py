"""
NHL slate + research — real data from ESPN's public NHL API (scoreboard
+ game summaries + team rosters).

What it produces, from REGULAR-SEASON finals only:
- Tonight's slate in Eastern time (or the next date with games, up to
  three weeks out — the same lookahead KBO/NPB use, which is what makes
  the tab useful during the preseason gap).
- Team profiles: W-L-OTL, points %, goals and SHOTS for/against per
  game, shot share, power play and penalty kill %, L10, home/road.
- The Crease Report: every goalie's starts, crease share of his team's
  last 10, SV%, GAA, L5 SV%, shots faced per 60, last start line.
- The Shots Lab: every skater's per-game SOG / points / goals / assists
  / TOI / hits / blocks for season, L5 and L10, plus plain hit-rate
  counts (games with 2+ and 3+ shots, games with a point).

Preseason finals are parsed and COUNTED NOWHERE — see nhl_rink.py. They
exist in the log so the parser is proven on real hockey box scores
before opening night instead of on it.
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef  # noqa: E402
from engines.nhl_rink import (  # noqa: E402
    PRESEASON_START, REGULAR_SEASON_START, phase,
)

EASTERN = ZoneInfo("America/New_York")
LEAGUE = "nhl"
OUT = Path("build_data") / "data" / "nhl"
LOOKAHEAD_DAYS = 21
# Last season, committed by the manual nhl-prior-season workflow
# (nhl_prior_season.py). Module-level so tests can point it elsewhere.
PRIOR_PATH = ROOT / "data" / "nhl" / "prior_season.json"
# Last season's PP minutes, {pid: {date: minutes}} (nhl_prior_season.py
# --pp-only, the "NHL prior PP minutes" workflow). Read beside PRIOR_PATH
# so a test that moves one moves both.
PRIOR_PP_NAME = "prior_pp.json"


def load_prior_pp(prior, prior_path=None):
    """Lay last season's PP minutes over its skaters as "pp" (in place).
    Returns how many skaters got them; 0 when the file is not there."""
    path = Path(prior_path or PRIOR_PATH).parent / PRIOR_PP_NAME
    if not path.exists() or not prior.get("skaters"):
        return 0
    pp = json.loads(path.read_text())
    n = 0
    for pid, s in prior["skaters"].items():
        if pp.get(pid):
            s["pp"] = pp[pid]
            n += 1
    return n
# Top plays record (engines/top_plays_board); module-level so tests sandbox it.
TOP_PLAYS_ROOT = ROOT / "data" / "top_plays"
# The graded model-picks record (engines/model_picks). Module-level so a
# pipeline under test writes to its sandbox, never the repo's record.
PICKS_ROOT = ROOT / "data" / "model_picks"

SKATER = {
    "g": (("goals",), ("G",)),
    "a": (("assists",), ("A",)),
    "pm": (("plusMinus",), ("+/-",)),
    "sog": (("shotsTotal", "shots"), ("S", "SOG")),
    "blk": (("blockedShots",), ("BS", "BLK")),
    "hits": (("hits",), ("HT", "HIT")),
    "pim": (("penaltyMinutes",), ("PIM",)),
    "toi": (("timeOnIce",), ("TOI",)),
    # POWER-PLAY minutes (10-09). Whether ESPN's NHL box carries this
    # column was never confirmed, so it is matched on every spelling seen
    # across feeds and is simply ABSENT when the feed lacks it (rule 6):
    # the nightly prints which skater columns it saw and how many lines
    # carried PP time, which is the probe.
    "pptoi": (("powerPlayTimeOnIce", "timeOnIcePowerPlay", "powerPlayTOI", "ppTimeOnIce"),
              ("PPTOI", "PP TOI", "PPTIME")),
}
CLOCK_STATS = ("toi", "pptoi")
# Skater box columns seen this run (keys or labels) — printed once.
SEEN_SKATER_COLUMNS = set()
GOALIE = {
    "ga": (("goalsAgainst",), ("GA",)),
    "sa": (("shotsAgainst",), ("SA",)),
    "sv": (("saves",), ("SV",)),
    "svp": (("savePct",), ("SV%",)),
    "toi": (("timeOnIce",), ("TOI",)),
}
TEAM_STATS = {
    "sog": ("shotstotal", "shots", "shotsongoal"),
    "ppg": ("powerplaygoals",),
    "ppo": ("powerplayopportunities",),
    "hits": ("hits",),
    "blk": ("blockedshots",),
    "fo_pct": ("faceoffpercent",),
    "pim": ("penaltyminutes",),
}


def _is_goalie_group(grp):
    name = str(grp.get("name") or "").lower()
    if "goal" in name:
        return True
    labels = {str(l).upper() for l in (grp.get("labels") or [])}
    keys = {str(k).lower() for k in (grp.get("keys") or [])}
    return ("SV" in labels and "SA" in labels) or ("saves" in keys)


def parse_team_box(stats):
    raw = {}
    for s in stats or []:
        raw[str(s.get("name") or "").lower().replace(" ", "")] = s.get("displayValue", s.get("value"))
    out = {}
    for ours, names in TEAM_STATS.items():
        val = next((raw[n] for n in names if n in raw), None)
        v = ef.num(val)
        if v is not None:
            out[ours] = v
    return out


def went_to_extra(summary, detail=""):
    """True for OT/SO finals — decides an OTL. None when unknowable."""
    try:
        comp = ((summary.get("header") or {}).get("competitions") or [{}])[0]
        st = comp.get("status") or {}
        per = st.get("period")
        if isinstance(per, (int, float)) and per:
            return per > 3
        d = ((st.get("type") or {}).get("shortDetail") or "")
    except Exception:
        d = ""
    d = f"{d} {detail}".upper()
    if "OT" in d or "SO" in d:
        return True
    if "FINAL" in d:
        return False
    return None


def parse_summary(summary, event_id, game_date, skaters, goalies):
    """(team_box {name: line}, n_skater_lines, n_goalie_lines)."""
    box = summary.get("boxscore") or {}
    tb = {}
    for t in box.get("teams") or []:
        nm = (t.get("team") or {}).get("displayName") or ""
        tb[nm] = parse_team_box(t.get("statistics"))
        tb[nm]["abbr"] = (t.get("team") or {}).get("abbreviation") or ""
    blocks = box.get("players") or []
    names = [((b.get("team") or {}).get("displayName") or "") for b in blocks]
    abbrs = [((b.get("team") or {}).get("abbreviation") or "") for b in blocks]
    n_s = n_g = 0
    for i, b in enumerate(blocks):
        team, opp = names[i], (names[1 - i] if len(names) == 2 else "")
        g_lines = []
        for grp in b.get("statistics") or []:
            is_g = _is_goalie_group(grp)
            idx = ef.box_group_index(grp, GOALIE if is_g else SKATER)
            if not idx:
                continue
            if not is_g:
                SEEN_SKATER_COLUMNS.update(str(k) for k in (grp.get("keys") or grp.get("labels")
                                                            or []))
            for ent in grp.get("athletes") or []:
                ath = ent.get("athlete") or {}
                stats = ent.get("stats") or []
                if not ath.get("id") or not stats:
                    continue
                line = {"event_id": str(event_id), "date": game_date, "opp": opp}
                for ours, j in idx.items():
                    if j >= len(stats):
                        continue
                    line[ours] = (ef.clock_minutes(stats[j]) if ours in CLOCK_STATS
                                  else ef.num(stats[j]))
                if not line.get("toi"):
                    continue  # dressed, did not play — not a zero game
                pid = str(ath["id"])
                store = goalies if is_g else skaters
                rec = store.setdefault(pid, {
                    "pid": pid, "name": ath.get("displayName") or ath.get("shortName"),
                    "pos": (ath.get("position") or {}).get("abbreviation") or ("G" if is_g else ""),
                    "games": {}})
                rec["team"], rec["abbr"] = team, abbrs[i]
                if is_g:
                    if line.get("sv") is None and line.get("sa") is not None \
                            and line.get("ga") is not None:
                        line["sv"] = line["sa"] - line["ga"]
                    line["starter"] = bool(ent.get("starter"))
                    g_lines.append((pid, line))
                    n_g += 1
                else:
                    if line.get("g") is not None and line.get("a") is not None:
                        line["pts"] = line["g"] + line["a"]
                    n_s += 1
                rec["games"][str(event_id)] = line
        # Exactly one start per team per game. ESPN's `starter` flag when
        # it is given; otherwise the goalie with the most ice time.
        if g_lines:
            flagged = [p for p, ln in g_lines if ln.get("starter")]
            starter = flagged[0] if len(flagged) == 1 else max(
                g_lines, key=lambda x: x[1].get("toi") or 0)[0]
            for p, ln in g_lines:
                ln["started"] = p == starter
    return tb, n_s, n_g


def _avg(vals, nd=2):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), nd) if vals else None


def _pct(num_, den):
    return round(100.0 * num_ / den, 1) if den else None


def team_research(finals):
    per = {}
    for f in sorted(finals, key=lambda x: x["date"]):
        for side, opp in (("away", "home"), ("home", "away")):
            per.setdefault(f[side], []).append({
                "date": f["date"], "home": side == "home", "opp": f[opp],
                "gf": f[f"{side}_score"], "ga": f[f"{opp}_score"],
                "extra": f.get("extra"),
                "me": f.get(f"{side}_box") or {}, "them": f.get(f"{opp}_box") or {},
            })
    out = {}
    for team, gs in per.items():
        def rec(sub):
            w = sum(1 for g in sub if g["gf"] > g["ga"])
            otl = sum(1 for g in sub if g["gf"] < g["ga"] and g["extra"] is True)
            l_ = sum(1 for g in sub if g["gf"] < g["ga"]) - otl
            return w, l_, otl
        w, l_, otl = rec(gs)
        unknown = sum(1 for g in gs if g["gf"] < g["ga"] and g["extra"] is None)
        sf = [g["me"].get("sog") for g in gs]
        sa = [g["them"].get("sog") for g in gs]
        both = [(a, b) for a, b in zip(sf, sa) if a is not None and b is not None]
        ppg = sum(g["me"].get("ppg") or 0 for g in gs if g["me"].get("ppo") is not None)
        ppo = sum(g["me"].get("ppo") or 0 for g in gs if g["me"].get("ppo") is not None)
        oppg = sum(g["them"].get("ppg") or 0 for g in gs if g["them"].get("ppo") is not None)
        oppo = sum(g["them"].get("ppo") or 0 for g in gs if g["them"].get("ppo") is not None)
        l10 = rec(gs[-10:])
        home = rec([g for g in gs if g["home"]])
        road = rec([g for g in gs if not g["home"]])
        prof = {
            "gp": len(gs),
            "record": f"{w}-{l_}-{otl}",
            "pts": 2 * w + otl,
            "pts_pct": round(100.0 * (2 * w + otl) / (2 * len(gs)), 1) if gs else None,
            "gf_pg": _avg([g["gf"] for g in gs]),
            "ga_pg": _avg([g["ga"] for g in gs]),
            "avg_total": _avg([g["gf"] + g["ga"] for g in gs]),
            "sf_pg": _avg(sf, 1),
            "sa_pg": _avg(sa, 1),
            "sf_pct": _pct(sum(a for a, _ in both), sum(a + b for a, b in both)) if both else None,
            "pp_pct": _pct(ppg, ppo),
            "pk_pct": round(100.0 - _pct(oppg, oppo), 1) if oppo else None,
            "l10": "{}-{}-{}".format(*l10),
            "home_record": "{}-{}-{}".format(*home),
            "road_record": "{}-{}-{}".format(*road),
            "results": ["W" if g["gf"] > g["ga"] else ("OTL" if g["extra"] else "L") for g in gs],
        }
        # An OT loss we could not identify is counted as a regulation
        # loss above, which would make the W-L-OTL a wrong number under
        # a right label. Say so on the profile instead of hiding it.
        if unknown:
            prof["otl_unverified"] = unknown
        out[team] = prof
    return out


def _rate(vals, cut):
    vals = [v for v in vals if v is not None]
    return round(100.0 * sum(1 for v in vals if v >= cut) / len(vals), 0) if vals else None


MULTI_SNAP_FILE = "nhl_multigoal_ranks.json"


def nhl_extra_boards(slate, model_block, skaters, date_str, root=None, now=None):
    """Grade, then log, the two nightly records beside Top Plays —
    Player of the Day (data/top_plays/nhl_potd.json) and the multi-goal
    watch (nhl_multigoal.json) — and keep the pre-game 2+ goal ranking
    (nhl_multigoal_ranks.json) so each night's two-goal scorers can be
    looked up where the board had them."""
    import top_plays_log as tpl
    from engines import edge_boards as eb
    from engines import top_plays_board as tpb
    root = Path(root or TOP_PLAYS_ROOT)
    now = now or datetime.now(timezone.utc)
    box = tpl.nhl_box_by_event(skaters)
    # names ride along for the multi-goal check (a scorer outside the kept
    # ranking still needs one); grading never reads them
    for _b in box.values():
        for _pid, _ln in (_b.get("players") or {}).items():
            _ln["name"] = (skaters.get(_pid) or {}).get("name")
    games = [g for g in slate or [] if g.get("game_type") != "preseason"]

    _pg, _pv = tpb.grade("nhl_potd", lambda eid: box.get(str(eid)), root=root)
    pick, _cands, note = eb.nhl_player_of_the_day(games, model_block)
    play = eb.potd_play(pick, date_str)
    _pn = tpb.log_plays("nhl_potd", [play] if play else [], now=now, root=root)
    print(f"  [verify] NHL Player of the Day: graded {_pg}, voided {_pv}; pick "
          f"{(pick or {}).get('player')} {round(100 * pick['chance'], 1) if pick else ''}% "
          f"1+ point ({_pn} new logged){'' if pick else ' - ' + str(note)}")

    rows = eb.nhl_goal_rows(games, model_block)
    _mg, _mv = tpb.grade("nhl_multigoal", lambda eid: box.get(str(eid)), root=root)
    watch = [{"sport": "nhl", "game_id": r["game_id"], "game": r["game"], "start": r["start"],
              "date": date_str, "player_id": r["pid"], "player": r["player"],
              "team": r["team"], "market": "g2", "label": "Goal O1.5", "stat": "g",
              "at_least": 2, "p": r["raw2"], "p_cal": round(r["chance2"], 4),
              "fair": mm_fair(r["chance2"]), "why": r.get("why")}
             for r in eb.multi_goal_watch(rows, 10) if r.get("pid") and r.get("start")]
    _mn = tpb.log_plays("nhl_multigoal", watch, now=now, root=root)

    path = root / MULTI_SNAP_FILE
    snaps = json.loads(path.read_text()) if path.exists() else {}
    graded = sum(1 for s in snaps.values() if eb.grade_multi_snapshot(s, box))
    upcoming = [r for r in rows if _not_started(r.get("start"), now)]
    added = 0
    if upcoming and date_str not in snaps:
        snaps[date_str] = eb.multi_goal_snapshot(upcoming)
        added = 1
    if graded or added:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snaps, indent=1, sort_keys=True))
    sm = eb.multi_check_summary(snaps)
    print(f"  [verify] NHL multi-goal watch: graded {_mg}, voided {_mv}, {_mn} new logged; "
          f"check: {graded} night(s) graded, {added} snapshot added; so far "
          f"{sm['caught']} of {sm['scorers']} two-goal scorers were in the top {sm['top']} "
          f"(a random {sm['top']} would catch {sm['random']})")


def mm_fair(p):
    from engines import model_math as mm
    return mm.fair_american(p) if p is not None and 0 < p < 1 else None


def _not_started(start, now):
    try:
        t = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return t.tzinfo is not None and t > now


def skater_summaries(skaters, regular_ids):
    out = {}
    for pid, rec in skaters.items():
        gs = sorted((g for eid, g in rec["games"].items() if eid in regular_ids),
                    key=lambda g: g["date"])
        if not gs:
            continue
        s = {"pid": pid, "name": rec["name"], "pos": rec.get("pos") or "",
             "team": rec.get("team"), "abbr": rec.get("abbr"), "gp": len(gs)}
        for k in ("sog", "pts", "g", "a", "toi", "pptoi", "hits", "blk"):
            nd = 1 if k == "toi" else 2
            s[k] = _avg([g.get(k) for g in gs], nd)
            s[f"l5_{k}"] = _avg([g.get(k) for g in gs[-5:]], nd)
            s[f"l10_{k}"] = _avg([g.get(k) for g in gs[-10:]], nd)
        s["sog2_rate"] = _rate([g.get("sog") for g in gs], 2)
        s["sog3_rate"] = _rate([g.get("sog") for g in gs], 3)
        s["pt1_rate"] = _rate([g.get("pts") for g in gs], 1)
        # how many of his games carried a PP-time cell at all — so 0.0
        # (no PP time) and "column missing" never read as the same thing
        s["pptoi_n"] = sum(1 for g in gs if g.get("pptoi") is not None)
        s["log"] = [{"date": g["date"], "opp": g.get("opp"), "sog": g.get("sog"),
                     "pts": g.get("pts"), "toi": g.get("toi")} for g in gs[-10:]]
        out[pid] = s
    return out


def goalie_summaries(goalies, regular_ids, team_games):
    """team_games: {team: [event_id,...]} in date order — for crease share."""
    out = {}
    for pid, rec in goalies.items():
        gs = sorted((g for eid, g in rec["games"].items() if eid in regular_ids),
                    key=lambda g: g["date"])
        if not gs:
            continue
        sa = sum(g.get("sa") or 0 for g in gs if g.get("sa") is not None)
        sv = sum(g.get("sv") or 0 for g in gs if g.get("sv") is not None)
        ga = sum(g.get("ga") or 0 for g in gs if g.get("ga") is not None)
        toi = sum(g.get("toi") or 0 for g in gs)
        starts = [g for g in gs if g.get("started")]
        last5 = starts[-5:]
        l5_sa = sum(g.get("sa") or 0 for g in last5)
        l5_sv = sum(g.get("sv") or 0 for g in last5)
        recent = (team_games.get(rec.get("team")) or [])[-10:]
        mine = sum(1 for eid in recent if (rec["games"].get(eid) or {}).get("started"))
        s = {"pid": pid, "name": rec["name"], "team": rec.get("team"),
             "abbr": rec.get("abbr"), "gp": len(gs), "starts": len(starts),
             # raw counts, for the saves model's shrunk save rate
             "sa": sa, "sv": sv,
             "sv_pct": round(sv / sa, 3) if sa else None,
             "gaa": round(ga * 60.0 / toi, 2) if toi else None,
             "sa_per60": round(sa * 60.0 / toi, 1) if toi else None,
             "l5_sv_pct": round(l5_sv / l5_sa, 3) if l5_sa else None,
             "crease_share": f"{mine} of {len(recent)}" if recent else None}
        if starts:
            ls = starts[-1]
            s["last_start"] = (f'{ls["date"]} vs {ls.get("opp") or "?"}: '
                               f'{int(ls.get("sv") or 0)}/{int(ls.get("sa") or 0)}')
        out[pid] = s
    return out


def slate_game(event, on_date):
    comp, away, home = ef.event_sides(event)
    if comp is None:
        return None
    status, completed, detail = ef.status_of(event)
    start = ef.to_et(comp.get("date") or event.get("date"))
    stype = (event.get("season") or {}).get("type") if isinstance(event.get("season"), dict) else None
    if stype in (1, 2, 3):
        gtype = {1: "preseason", 2: "regular", 3: "playoffs"}[stype]
    else:
        gtype = "regular" if on_date >= REGULAR_SEASON_START else "preseason"
    g = {"event_id": str(event.get("id") or ""), "status": status,
         "detail": detail, "game_type": gtype,
         "venue": (comp.get("venue") or {}).get("fullName") or ""}
    for side, c in (("away", away), ("home", home)):
        t = c.get("team") or {}
        g[side] = t.get("displayName") or "TBD"
        g[f"{side}_abbr"] = t.get("abbreviation") or ""
        g[f"{side}_id"] = str(t.get("id") or "")
        g[f"{side}_color"] = t.get("color")
        g[f"{side}_logo"] = ef.team_logo(t)
        if status in ("in progress", "final"):
            v = ef.num(c.get("score"))
            if v is not None:
                g[f"{side}_score"] = int(v)
    if start:
        g["start_et"] = start.isoformat()
        g["time_et"] = start.strftime("%-I:%M %p")
    o = ef.odds_of(comp)
    if o:
        g["odds"] = o
    return g


def _walk_roster(obj, out):
    if isinstance(obj, dict):
        if obj.get("id") and obj.get("displayName") and isinstance(obj.get("position"), dict):
            out[str(obj["id"])] = obj["position"].get("abbreviation") or ""
            return
        for v in obj.values():
            _walk_roster(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_roster(v, out)


def fetch_roster(team_id):
    try:
        data = ef.get_json(f"{ef.base(LEAGUE)}/teams/{team_id}/roster")
    except Exception as exc:
        print(f"  roster {team_id} failed: {exc}")
        return {}
    out = {}
    _walk_roster(data.get("athletes") or data, out)
    return out


def main(today=None):
    now_et = datetime.now(EASTERN)
    today = today or now_et.date()
    OUT.mkdir(parents=True, exist_ok=True)

    # 1) The slate: today, else the next date with games.
    slate, slate_date = [], today
    for k in range(LOOKAHEAD_DAYS + 1):
        d = today + timedelta(days=k)
        try:
            sb, _src = ef.fetch_scoreboard(LEAGUE, d.strftime("%Y%m%d"))
        except Exception as exc:
            print(f"  scoreboard {d} failed: {exc}")
            if k == 0:
                raise
            continue
        games = [g for g in (slate_game(e, d) for e in sb.get("events") or []) if g]
        if games:
            slate, slate_date = games, d
            break
    print(f"NHL: slate {slate_date} — {len(slate)} games "
          f"({sum(1 for g in slate if g['game_type'] == 'preseason')} exhibition)")

    # 2) Backfill finals from the first exhibition to yesterday/today.
    finals, skaters, goalies = [], {}, {}
    id_of = {}
    regular_ids, team_games = set(), {}
    seen = parsed = pre_parsed = 0
    first = True
    d = PRESEASON_START
    while d <= today:
        try:
            sb, _src = ef.fetch_scoreboard(LEAGUE, d.strftime("%Y%m%d"))
        except Exception as exc:
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in sb.get("events") or []:
            g = slate_game(ev, d)
            if not g or g["status"] != "final" or g.get("away_score") is None:
                continue
            seen += 1
            try:
                summ = ef.fetch_summary(LEAGUE, g["event_id"])
                tb, n_s, n_g = parse_summary(summ, g["event_id"], d.isoformat(),
                                             skaters, goalies)
            except Exception as exc:
                print(f"  summary {g['event_id']} ({d}) failed: {exc}")
                continue
            if first:
                print(f"  [verify] first final {g['away']} @ {g['home']} "
                      f"({g['game_type']}): team keys {sorted(tb.get(g['home'], {}))}; "
                      f"{n_s} skater / {n_g} goalie lines")
                first = False
            if not (n_s and n_g):
                continue
            if g["game_type"] != "regular":
                pre_parsed += 1
                continue
            parsed += 1
            regular_ids.add(g["event_id"])
            for side in ("away", "home"):
                team_games.setdefault(g[side], []).append(g["event_id"])
            finals.append({"date": d.isoformat(), "away": g["away"], "home": g["home"],
                           "away_score": g["away_score"], "home_score": g["home_score"],
                           "extra": went_to_extra(summ, g.get("detail") or ""),
                           "away_box": tb.get(g["away"]), "home_box": tb.get(g["home"]),
                           # ids for the model — names change between
                           # seasons (Utah), ids do not.
                           "away_id": g.get("away_id"), "home_id": g.get("home_id"),
                           "away_abbr": g.get("away_abbr"), "home_abbr": g.get("home_abbr"),
                           # the line recorded for this final — what the
                           # model's weight against the market is fitted
                           # on (engines/market_blend)
                           "odds": ef.recorded_line(g.get("odds"), summ) or None})
            id_of[g["away"]], id_of[g["home"]] = g.get("away_id"), g.get("home_id")
            time.sleep(0.1)
        time.sleep(0.1)
        d += timedelta(days=1)

    if seen and not (parsed or pre_parsed):
        raise RuntimeError(f"NHL: {seen} finals seen, ZERO box scores parsed. "
                           f"Refusing to publish a league with no numbers behind it.")

    teams = team_research(finals)
    sk = skater_summaries(skaters, regular_ids)
    gk = goalie_summaries(goalies, regular_ids, team_games)
    print(f"NHL: {parsed} regular-season finals parsed ({pre_parsed} exhibition "
          f"finals parsed as a parser check, counted nowhere) -> {len(teams)} teams, "
          f"{len(sk)} skaters, {len(gk)} goalies")
    if sk:
        top = max(sk.values(), key=lambda p: p.get("sog") or 0)
        print(f"  [verify] SOG leader parsed: {top['name']} ({top['abbr']}) "
              f"{top['sog']} per game over {top['gp']} GP")
    # THE PP PROBE (10-09): which columns ESPN's skater box carried, and
    # how many parsed skater-games have power-play minutes.
    print(f"  [verify] NHL skater box columns: {sorted(SEEN_SKATER_COLUMNS)}")
    _pp_lines = [ln for rec in skaters.values() for eid, ln in rec["games"].items()
                 if eid in regular_ids]
    print(f"  [verify] NHL PP time: {sum(1 for ln in _pp_lines if ln.get('pptoi') is not None)} "
          f"of {len(_pp_lines)} regular-season skater lines carry PP minutes"
          + ("" if any(ln.get("pptoi") is not None for ln in _pp_lines) else
             " -> NOT IN THE FEED; PP columns stay blank (the NHL's own API is the fallback)"))
    if gk:
        g0 = max(gk.values(), key=lambda p: p.get("starts") or 0)
        print(f"  [verify] most starts: {g0['name']} ({g0['abbr']}) "
              f"{g0['starts']} GS, SV% {g0['sv_pct']}")

    rosters = {}
    if sk:
        for g in slate:
            for side in ("away", "home"):
                tid = g.get(f"{side}_id")
                if tid and tid not in rosters:
                    rosters[tid] = fetch_roster(tid)

    for g in slate:
        for side in ("away", "home"):
            if teams.get(g[side]):
                g[f"{side}_profile"] = teams[g[side]]
            roster = rosters.get(g.get(f"{side}_id")) or {}
            pool = [p for p in sk.values() if p["team"] == g[side]
                    and (not roster or p["pid"] in roster)]
            for p in pool:
                if roster.get(p["pid"]):
                    p["pos"] = roster[p["pid"]]
            pool.sort(key=lambda p: -(p.get("toi") or 0))
            g[f"{side}_skaters"] = pool[:18]
            g[f"{side}_goalies"] = sorted(
                (x for x in gk.values() if x["team"] == g[side]),
                key=lambda x: -(x.get("starts") or 0))

    # THE MODEL (engines/nhl_model): game projection + skater props,
    # fitted on last season's committed file while this one is young.
    # A model failure costs the model block, never the slate.
    model_block = None
    try:
        from engines import nhl_model
        for g in slate:
            id_of[g["away"]], id_of[g["home"]] = g.get("away_id"), g.get("home_id")
        prior_path = PRIOR_PATH
        prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
        _npp = load_prior_pp(prior, prior_path)
        print(f"  [verify] NHL last-season PP minutes: {_npp} skaters"
              + ("" if _npp else " -> none yet: run the 'NHL prior PP minutes' workflow once "
                                 "so the PP factor can be tested"))
        if not prior:
            print("::warning::NHL model: data/nhl/prior_season.json missing - run the "
                  "'NHL prior season' workflow once. Fitting on this season alone.")
        rows = [{"date": f["date"], "home": f["home_id"], "away": f["away_id"],
                 "hs": f["home_score"], "as": f["away_score"], "extra": f.get("extra"),
                 "home_sog": (f.get("home_box") or {}).get("sog"),
                 "away_sog": (f.get("away_box") or {}).get("sog"),
                 "odds": f.get("odds"), "home_abbr": f.get("home_abbr"),
                 "away_abbr": f.get("away_abbr")}
                for f in finals if f.get("home_id") and f.get("away_id")]
        model_block = nhl_model.build(rows, prior, skaters, id_of,
                                      [g for g in slate if g.get("game_type") != "preseason"],
                                      regular_ids=regular_ids)
        if model_block:
            v = model_block["validation"]
            print(f"  [verify] NHL model fit on {model_block['params'].get('fit_on')} season: "
                  f"k={model_block['params']['shrink_k']} carryover={model_block['params'].get('carryover')} "
                  f"dispersion={model_block['params'].get('dispersion')} "
                  f"home_mult={model_block['league'].get('home_mult')} "
                  f"OT home win={model_block['league'].get('tie_home_win')}")
            if v.get("n"):
                print(f"  [verify] walk-forward {v['n']} games: log loss {v['model']['log_loss']} "
                      f"vs coin {v['coin_flip']['log_loss']} vs home-rate {v['home_rate']['log_loss']}")
            from engines import market_blend as mb
            for _m in ("moneyline", "total", "spread"):
                print(f"  [verify] NHL {mb.describe(model_block.get('blend'), _m)}")
            print(f"  [verify] NHL market coverage {(model_block.get('blend') or {}).get('coverage')}")
            _sv = model_block.get("saves_validation") or {}
            for _k, _label, *_r in nhl_model.SAVE_MARKETS:
                _x = _sv.get(_k) or {}
                print(f"  [verify] {_label} (team level) n={_x.get('n')} model {_x.get('model_brier')} "
                      f"vs own-rate {_x.get('baseline_brier')} -> {(_x.get('verdict') or {}).get('verdict')}")
            print(f"  [verify] save prior {model_block.get('save_prior')}; shot NB size "
                  f"{(model_block.get('shots') or {}).get('dispersion')}")
            pv = model_block.get("props_validation") or {}
            for k, label, *_ in nhl_model.MARKETS:
                x = pv.get(k) or {}
                print(f"  [verify] {label:9s} n={x.get('n')} model {x.get('model_brier')} vs "
                      f"his-own-rate {x.get('baseline_brier')} -> "
                      f"{'BEATS' if x.get('beats_baseline') else 'does not beat'} baseline")
            _toi = model_block.get("toi") or {}
            for _fam in nhl_model.TOI_FAMILIES:
                _x = _toi.get(_fam) or {}
                print(f"  [verify] NHL ice time ({_fam}): window {_x.get('window')} fitted alpha "
                      f"{_x.get('fitted_alpha')} -> {'IN THE NUMBER' if _x.get('adopted') else 'context only'} "
                      f"({(_x.get('verdict') or {}).get('verdict')}, z={(_x.get('verdict') or {}).get('z')}, "
                      f"n={_x.get('n')})")
            for _fam in nhl_model.TOI_FAMILIES:
                _x = ((_toi.get(_fam) or {}).get("pp")) or {}
                if _x:
                    print(f"  [verify] NHL PP-weighted minutes ({_fam}): weight {_x.get('weight')} "
                          f"strength {_x.get('fitted_alpha')} coverage {_x.get('coverage')} -> "
                          f"{'IN THE NUMBER' if _x.get('adopted') else 'context only'} "
                          f"({(_x.get('verdict') or {}).get('verdict')}, "
                          f"z={(_x.get('verdict') or {}).get('z')}, n={_x.get('n')})"
                          f"{' - ' + _x['note'] if _x.get('note') else ''}")
            _dv = model_block.get("dvp_validation") or {}
            for _fam in ("sog", "pts"):
                _x = _dv.get(_fam) or {}
                print(f"  [verify] NHL defense-vs-position ({_fam}): "
                      f"{(_x.get('verdict') or {}).get('verdict')} z={(_x.get('verdict') or {}).get('z')} "
                      f"n={_x.get('n')} -> {'IN THE NUMBER' if _x.get('in_number') else 'context only'}")
            _t = ((model_block.get("dvp") or {}).get("stats") or {}).get("sog") or {}
            print(f"  [verify] NHL DvP table: {(model_block.get('dvp') or {}).get('of')} defenses; "
                  f"SOG to C league {(_t.get('C') or {}).get('league')} weight "
                  f"{(_t.get('C') or {}).get('weight')} reliability {(_t.get('C') or {}).get('reliability')}")
            print(f"  [verify] slate games with a projection: "
                  f"{sum(1 for g in slate if g.get('model'))} of {len(slate)}; "
                  f"with a posted moneyline: {sum(1 for g in slate if (g.get('odds') or {}).get('home_ml'))}, "
                  f"total price: {sum(1 for g in slate if (g.get('odds') or {}).get('over_price'))}")
            from engines import model_picks as mpk
            _new = mpk.log_picks("nhl", [
                {"id": g["event_id"], "date": slate_date.isoformat(), "start": g.get("start_et"),
                 "home": g["home"], "away": g["away"], "proj": g.get("model"), "odds": g.get("odds")}
                for g in slate if g.get("model") and g.get("start_et")], root=PICKS_ROOT)
            print(f"  [verify] NHL value picks logged this run: {_new}")
            # TOP PLAYS: grade from the finals parsed above, then log
            # tonight's (engines/top_plays_board). Own try: a failure costs
            # the plays, never the model or the slate.
            try:
                import top_plays_log as tpl
                from engines import top_plays_board as tpb
                _box = tpl.nhl_box_by_event(skaters)
                _g, _v = tpb.grade("nhl", lambda eid: _box.get(str(eid)), root=TOP_PLAYS_ROOT)
                _plays = tpb.select(tpl.nhl_candidates(slate, slate_date.isoformat()),
                                    model_block.get("props_validation") or {})
                _n = tpb.log_plays("nhl", _plays, root=TOP_PLAYS_ROOT)
                print(f"  [verify] NHL top plays: graded {_g}, voided {_v}; {len(_plays)} "
                      f"selected, {_n} new logged")
            except Exception as exc:  # noqa: BLE001
                print(f"::warning::NHL top plays failed: {type(exc).__name__}: {exc}")
            # PLAYER OF THE DAY, MULTI-GOAL WATCH and the MULTI-GOAL CHECK
            # (10-09, engines/edge_boards). Own try: costs these, never the
            # model or the slate.
            try:
                nhl_extra_boards(slate, model_block, skaters, slate_date.isoformat())
            except Exception as exc:  # noqa: BLE001
                print(f"::warning::NHL POTD / multi-goal boards failed: "
                      f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NHL model failed: {type(exc).__name__}: {exc}")

    (OUT / "games.json").write_text(json.dumps({
        "model": model_block,
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
        "source": "ESPN public NHL API (scoreboard + game summaries + rosters)",
        "slate_date_et": slate_date.isoformat(),
        "phase": phase(today),
        "regular_season_start": REGULAR_SEASON_START.isoformat(),
        "regular_finals_parsed": parsed,
        "exhibition_finals_parsed": pre_parsed,
        "games": slate,
        "teams": teams,
        "goalies": gk,
    }, ensure_ascii=False, indent=2))
    print(f"NHL: wrote games.json ({slate_date}, {len(slate)} games)")


if __name__ == "__main__":
    main()
