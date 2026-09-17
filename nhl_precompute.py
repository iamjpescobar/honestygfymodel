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
from datetime import datetime, timedelta
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

SKATER = {
    "g": (("goals",), ("G",)),
    "a": (("assists",), ("A",)),
    "pm": (("plusMinus",), ("+/-",)),
    "sog": (("shotsTotal", "shots"), ("S", "SOG")),
    "blk": (("blockedShots",), ("BS", "BLK")),
    "hits": (("hits",), ("HT", "HIT")),
    "pim": (("penaltyMinutes",), ("PIM",)),
    "toi": (("timeOnIce",), ("TOI",)),
}
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
            for ent in grp.get("athletes") or []:
                ath = ent.get("athlete") or {}
                stats = ent.get("stats") or []
                if not ath.get("id") or not stats:
                    continue
                line = {"event_id": str(event_id), "date": game_date, "opp": opp}
                for ours, j in idx.items():
                    if j >= len(stats):
                        continue
                    line[ours] = (ef.clock_minutes(stats[j]) if ours == "toi"
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


def skater_summaries(skaters, regular_ids):
    out = {}
    for pid, rec in skaters.items():
        gs = sorted((g for eid, g in rec["games"].items() if eid in regular_ids),
                    key=lambda g: g["date"])
        if not gs:
            continue
        s = {"pid": pid, "name": rec["name"], "pos": rec.get("pos") or "",
             "team": rec.get("team"), "abbr": rec.get("abbr"), "gp": len(gs)}
        for k in ("sog", "pts", "g", "a", "toi", "hits", "blk"):
            nd = 1 if k == "toi" else 2
            s[k] = _avg([g.get(k) for g in gs], nd)
            s[f"l5_{k}"] = _avg([g.get(k) for g in gs[-5:]], nd)
            s[f"l10_{k}"] = _avg([g.get(k) for g in gs[-10:]], nd)
        s["sog2_rate"] = _rate([g.get("sog") for g in gs], 2)
        s["sog3_rate"] = _rate([g.get("sog") for g in gs], 3)
        s["pt1_rate"] = _rate([g.get("pts") for g in gs], 1)
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
                           "away_box": tb.get(g["away"]), "home_box": tb.get(g["home"])})
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

    (OUT / "games.json").write_text(json.dumps({
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
