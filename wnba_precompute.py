"""
WNBA slate + full matchup research data — real data from ESPN's public
WNBA API (scoreboard + game box scores, both verified from Actions).

What this produces, all computed from real games:
- Today's ET slate: teams (with their real brand colors), arena, tip
  time, status, records, leaders, and the betting line where present.
- Team research per side: points for/against per game, last-10 record,
  and average total points in their games (the totals read).
- TEAM H2H: the season series between tonight's two teams — record,
  every meeting's score, and the average total in those meetings.
- PLAYER research: per player, season + L5/L10 MIN/PTS/REB/AST from
  real box-score logs — plus PLAYER H2H: her averages specifically in
  games against tonight's opponent, with the meeting count shown.

Every number is read from the feed or is arithmetic on it. Absent
data is omitted, never estimated. Small samples are shipped with
their sample size so the reader can judge them honestly.
"""

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
SEASON_START = date(2026, 4, 3)
# ESPN ACCESS LIVES IN ONE PLACE NOW: app/engines/espn_wnba.py.
#
# The mirror chain, the unwrappers, the header normalizer and get_json
# were all defined here, and app/views/WNBA.py quietly kept a SECOND,
# older copy — one hardcoded URL pointing at the very host this file had
# been moved off because it 403s from cloud ranges. The live-score
# overlay was dead for as long as that duplicate existed, silently,
# because the reader returned {} instead of raising.
#
# These names are re-exported rather than renamed so wnba_probe.py,
# wnba_scoreboard_probe.py and wnba_roster_probe.py keep importing them
# from here, which is where their workflows expect them.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines.espn_wnba import (  # noqa: E402
    BASE, SCOREBOARD_SOURCES, STATUS_MAP, UA, fetch_scoreboard, get_json,
    _is_scoreboard, _normalize_header_events,
)

OUT = Path("build_data") / "data" / "wnba"

LEADER_CATS = {"points": "PTS", "rebounds": "REB", "assists": "AST"}


# get_json, SCOREBOARD_SOURCES, _is_scoreboard,
# _normalize_header_events and fetch_scoreboard moved to
# app/engines/espn_wnba.py so the live page reads the same chain.
# They are imported above; STATUS_MAP is shared from there too.


def _to_et(iso_utc: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return dt.astimezone(EASTERN).strftime("%-I:%M %p")
    except Exception:
        return "TBD"


def _record(competitor):
    out = {}
    for rec in competitor.get("records", []) or []:
        name = (rec.get("name") or rec.get("type") or "").lower()
        if rec.get("summary"):
            if name == "overall":
                out["overall"] = rec["summary"]
            elif name in ("home",):
                out["home"] = rec["summary"]
            elif name in ("road", "away"):
                out["road"] = rec["summary"]
    return out


TEAM_STAT_MAP = [
    ("fieldgoalpct", "fg_pct"), ("threepointfieldgoalpct", "tp_pct"),
    ("threepointpct", "tp_pct"), ("avgrebounds", "reb_g"),
    ("avgassists", "ast_g"), ("avgturnovers", "to_g"),
]


def _team_stats(competitor):
    """Selected season stats from the feed's own statistics block —
    stored only when present, matched defensively by name."""
    out = {}
    for s in competitor.get("statistics", []) or []:
        name = (s.get("name") or "").lower().replace(" ", "")
        val = s.get("displayValue")
        if val is None:
            continue
        for needle, key in TEAM_STAT_MAP:
            if name == needle and key not in out:
                out[key] = val
    return out


def _leaders(competitor):
    out = []
    for cat in competitor.get("leaders", []) or []:
        abbrev = LEADER_CATS.get(cat.get("name"))
        if not abbrev:
            continue
        entries = cat.get("leaders") or []
        if not entries:
            continue
        athlete = entries[0].get("athlete") or {}
        name = athlete.get("shortName") or athlete.get("displayName")
        val = entries[0].get("displayValue")
        if name and val is not None:
            out.append({"cat": abbrev, "name": name, "value": val})
    return out


def _team_logo(team):
    """ESPN's own logo URL for a team block, or None.

    Prefers `logo`, falls back to the first entry in `logos`, and returns
    None when neither is present so the caller can fall back to the
    id-built path and then to plain text. Never fabricates a URL.
    """
    t = team or {}
    u = t.get("logo")
    if not u:
        for cand in (t.get("logos") or []):
            if isinstance(cand, dict) and cand.get("href"):
                return cand["href"]
    return u or None


def parse_scoreboard_events(payload):
    for event in payload.get("events", []) or []:
        comps = event.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        status_name = (((event.get("status") or {}).get("type")) or {}).get("name", "")
        status = STATUS_MAP.get(status_name, "scheduled")
        completed = (((event.get("status") or {}).get("type")) or {}).get("completed", False)

        g = {
            "away": (away.get("team") or {}).get("displayName", "TBD"),
            "home": (home.get("team") or {}).get("displayName", "TBD"),
            "away_id": str((away.get("team") or {}).get("id") or ""),
            "home_id": str((home.get("team") or {}).get("id") or ""),
            "away_color": (away.get("team") or {}).get("color"),
            "home_color": (home.get("team") or {}).get("color"),
            "away_logo": _team_logo(away.get("team")),
            "home_logo": _team_logo(home.get("team")),
            "arena": (comp.get("venue") or {}).get("fullName", ""),
            "time_et": _to_et(comp.get("date", "")),
            "status": status,
        }
        for side, c in (("away", away), ("home", home)):
            for k, v in _team_stats(c).items():
                g[f"{side}_{k}"] = v
            recs = _record(c)
            if recs.get("overall"):
                g[f"{side}_record"] = recs["overall"]
            if recs.get("home"):
                g[f"{side}_home_record"] = recs["home"]
            if recs.get("road"):
                g[f"{side}_road_record"] = recs["road"]
            lds = _leaders(c)
            if lds:
                g[f"{side}_leaders"] = lds
        g["leaders_kind"] = "game" if completed else "season"

        if completed or status == "in progress":
            try:
                a_s, h_s = int(float(away.get("score", 0))), int(float(home.get("score", 0)))
                g["away_score"], g["home_score"] = a_s, h_s
                g["final" if completed else "score"] = (
                    f'{g["away"]} {a_s} - {h_s} {g["home"]}')
            except (TypeError, ValueError):
                pass

        odds_list = comp.get("odds") or []
        if odds_list:
            odds = odds_list[0]
            bits = []
            if odds.get("details"):
                bits.append(str(odds["details"]))
            if odds.get("overUnder") is not None:
                bits.append(f'O/U {odds["overUnder"]}')
            if bits:
                g["line"] = " \u00b7 ".join(bits)

        yield event.get("id"), status, completed, g


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


_OUT_STATUSES = {"out", "injured", "suspended", "not with team", "inactive"}


def _status_text(value):
    """ESPN's athlete `status` as a plain word, whatever shape it arrives in."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("name", "description", "abbreviation", "type", "id"):
            got = value.get(key)
            if isinstance(got, str) and got.strip():
                return got.strip()
    return None


def _injury_note(athlete):
    """(status, date) from the roster payload's own injuries[] array."""
    entries = athlete.get("injuries")
    if not isinstance(entries, list):
        return None, None
    for item in entries:
        if not isinstance(item, dict):
            continue
        status = _status_text(item.get("status"))
        if status:
            return status, item.get("date")
    return None, None


_roster_shapes = {"status_kind": set(), "with_injury": 0, "players": 0}


def fetch_team_roster(team_id, debug=False):
    """{pid: {name, pos, jersey, roster_status, injury_status,
    injury_date, exp}} — every player on a team's roster, with the
    reported status ESPN already sent us.
    """
    if not team_id:
        return {}
    try:
        data = get_json(f"{BASE}/teams/{team_id}/roster")
    except Exception as exc:
        print(f"  [roster] team {team_id}: fetch failed ({exc})")
        return {}

    raw = data.get("athletes") or []
    flat = []
    for a in raw:
        if isinstance(a, dict) and isinstance(a.get("items"), list):
            flat.extend(a["items"])
        else:
            flat.append(a)

    out = {}
    for ath in flat:
        if not isinstance(ath, dict):
            continue
        pid = str(ath.get("id") or "")
        name = ath.get("displayName") or ath.get("fullName") or ath.get("shortName")
        if not pid or not name:
            continue
        pos = ((ath.get("position") or {}).get("abbreviation")
               if isinstance(ath.get("position"), dict) else "") or ""

        _inj_status, _inj_date = _injury_note(ath)
        _status = _status_text(ath.get("status"))
        _exp = ath.get("experience")
        if isinstance(_exp, dict):
            _exp = _exp.get("years")

        _jersey = ath.get("jersey")
        if _jersey is not None and not isinstance(_jersey, str):
            _jersey = str(_jersey)

        _roster_shapes["players"] += 1
        _roster_shapes["status_kind"].add(type(ath.get("status")).__name__)
        if _inj_status:
            _roster_shapes["with_injury"] += 1

        out[pid] = {
            "name": name,
            "pos": pos,
            "jersey": _jersey,
            "roster_status": _status,
            "injury_status": _inj_status,
            "injury_date": _inj_date,
            "exp": _exp if isinstance(_exp, (int, float)) else None,
        }

    _hurt = sum(1 for v in out.values() if v.get("injury_status"))
    print(f"  [roster] team {team_id}: {len(out)} players, "
          f"{_hurt} with a reported injury")
    return out


def fetch_game_availability(event_id, debug=False):
    """{pid: {"status", "out", "starter", "name", "pos"}} for one game, or {} on failure."""
    try:
        data = get_json(f"{BASE}/summary?event={event_id}")
    except Exception as exc:
        print(f"  [avail] event {event_id}: summary fetch failed ({exc})")
        return {}

    out = {}

    def _remember(ath, entry):
        nm = ath.get("displayName") or ath.get("shortName")
        if nm and not entry.get("name"):
            entry["name"] = nm
        pos = (ath.get("position") or {}).get("abbreviation")
        if pos and not entry.get("pos"):
            entry["pos"] = pos

    for team_block in data.get("injuries") or []:
        for item in team_block.get("injuries") or []:
            ath = item.get("athlete") or {}
            pid = str(ath.get("id") or "")
            if not pid:
                continue
            status = (item.get("status")
                     or (item.get("type") or {}).get("description")
                    or (item.get("type") or {}).get("name") or "")
            entry = out.setdefault(pid, {})
            entry["status"] = str(status)
            entry["out"] = str(status).strip().lower() in _OUT_STATUSES
            _remember(ath, entry)

    for team_block in data.get("rosters") or []:
        _tname = ((team_block.get("team") or {}).get("displayName") or "")
        for item in team_block.get("roster") or []:
            ath = item.get("athlete") or {}
            pid = str(ath.get("id") or "")
            if not pid:
                continue
            entry = out.setdefault(pid, {})
            if "starter" in item:
                entry["starter"] = bool(item.get("starter"))
            entry.setdefault("out", False)
            _remember(ath, entry)
            if _tname:
                entry["team"] = _tname
            entry["rostered"] = True

    if debug or out:
        n_out = sum(1 for v in out.values() if v.get("out"))
        n_start = sum(1 for v in out.values() if v.get("starter"))
        print(f"  [avail] event {event_id}: {len(out)} players, "
              f"{n_out} out, {n_start} announced starters")
    return out


def parse_boxscore(event_id, game_date, logs, debug=False):
    data = get_json(f"{BASE}/summary?event={event_id}")
    blocks = (data.get("boxscore") or {}).get("players", []) or []
    names = [(b.get("team") or {}).get("displayName", "") for b in blocks]
    ids = [(b.get("team") or {}).get("id") for b in blocks]
    _logos = []
    for b in blocks:
        t = b.get("team") or {}
        u = t.get("logo")
        if not u:
            for cand in (t.get("logos") or []):
                if isinstance(cand, dict) and cand.get("href"):
                    u = cand["href"]
                    break
        _logos.append(u)
    for i, team_block in enumerate(blocks):
        team_name = names[i]
        opp_name = names[1 - i] if len(names) == 2 else ""
        opp_id = ids[1 - i] if len(ids) == 2 else None
        for stat_group in team_block.get("statistics", []) or []:
            labels = [l.upper() for l in (stat_group.get("labels") or stat_group.get("names") or [])]
            if "PTS" not in labels:
                continue
            idx = {k: labels.index(k) for k in ("MIN", "PTS", "REB", "AST",
                                                 "STL", "BLK", "TO") if k in labels}
            tpt_i = labels.index("3PT") if "3PT" in labels else None
            fg_i = labels.index("FG") if "FG" in labels else None
            ft_i = labels.index("FT") if "FT" in labels else None
            if debug:
                print(f"  [debug] labels for event {event_id}: {labels}")
            for entry in stat_group.get("athletes", []) or []:
                if entry.get("didNotPlay"):
                    continue
                athlete = entry.get("athlete") or {}
                stats = entry.get("stats") or []
                if not athlete.get("id") or len(stats) <= max(idx.values(), default=0):
                    continue
                line = {"date": game_date, "team": team_name, "opp": opp_name,
                        "opp_id": opp_id,
                    "opp_logo": (_logos[1 - i] if len(_logos) == 2 else None)}
                for k, i2 in idx.items():
                    line[k.lower()] = _num(stats[i2])
                def _made_att(i, mk, ak):
                    if i is not None and len(stats) > i:
                        parts = str(stats[i]).split("-")
                        if len(parts) == 2:
                          line[mk], line[al] = _num(parts[0]), _num(parts[1])
                _made_att(tpt_i, "tpm", "tpa")
                _made_att(fg_i, "fgm", "fga")
                _made_att(ft_i, "ftm", "fta")
                _pts, _reb = line.get("pts"), line.get("reb")
                _ast = line.get("ast")
                if _pts is not None and _reb is not None and _ast is not None:
                    line["pra"] = _pts + _reb + _ast
                if _pts is not None and _reb is not None:
                    line["pr"] = _pts + _reb
                if _pts is not None and _ast is not None:
                    line["pa"] = _pts + _ast
                if _reb is not None and _ast is not None:
                    line["ra"] = _reb + _ast
                _stl, _blk = line.get("stl"), line.get("blk")
                if _stl is not None and _blk is not None:
                    line["stocks"] = _stl + _blk
                if line.get("min") in (None, 0):
                    continue
                rec = logs.setdefault(str(athlete["id"]), {
                    "name": athlete.get("shortName") or athlete.get("displayName"),
                    "full_name": athlete.get("displayName"),
                    "pos": (athlete.get("position") or {}).get("abbreviation", ""),
                    "games": [],
                })
                rec["team"] = team_name
                rec["games"].append(line)


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def positional_defense(logs):
    MIN_POS_GAMES = 5
    allowed = {}
    for pid, rec in logs.items():
        pos = (rec.get("pos") or "").upper()[:1]
        if pos not in ("G", "F", "C"):
            continue
        for gl in rec.get("games", []):
            opp = gl.get("opp")
            date = gl.get("date")
            if not opp or not date:
                continue
            bucket = allowed.setdefault(opp, {}).setdefault(pos, {})
            day = bucket.setdefault(date, {"pts": 0.0, "reb": 0.0, "ast": 0.0})
            day["pts"] += gl.get("pts") or 0
            day["reb"] += gl.get("reb") or 0
            day["ast"] += gl.get("ast") or 0

    out = {}
    for team, by_pos in allowed.items():
        for pos, by_date in by_pos.items():
            gp = len(by_date)
            if gp < MIN_POS_GAMES:
                continue
            out.setdefault(team, {})[pos] = {
                "pts": round(sum(d["pts"] for d in by_date.values()) / gp, 1),
                "reb": round(sum(d["reb"] for d in by_date.values()) / gp, 1),
                "ast": round(sum(d["ast"] for d in by_date.values()) / gp, 1),
                "gp": gp,
            }
    return out


def team_research(finals):
    per = {}
    for g in sorted(finals, key=lambda x: x["date"]):
        for side, opp in (("home", "away"), ("away", "home")):
            t = per.setdefault(g[side], {"pf": [], "pa": [], "results": []})
            us, them = g[f"{side}_score"], g[f"{opp}_score"]
            t["pf"].append(us)
            t["pa"].append(them)
            t["results"].append("W" if us > them else "L")
    out = {}
    for team, t in per.items():
        last10 = t["results"][-10:]

        def _form(n=None, _t=t):
            pf = _t["pf"] if n is None else _t["pf"][-n:]
            pa = _t["pa"] if n is None else _t["pa"][-n:]
            res = _t["results"] if n is None else _t["results"][-n:]
            return {
                "pf_pg": _avg(pf), "pa_pg": _avg(pa),
                "avg_total": _avg([a + b for a, b in zip(pf, pa)]),
                "record": f'{res.count("W")}-{res.count("L")}',
                "gp": len(res),
            }

        out[team] = {
            "pf_pg": _avg(t["pf"]), "pa_pg": _avg(t["pa"]),
            "avg_total": _avg([a + b for a, b in zip(t["pf"], t["pa"])]),
            "l10": f'{last10.count("W")}-{last10.count("L")}',
            "form": {"season": _form(), "l25": _form(25), "l15": _form(15),
                     "l10": _form(10), "l5": _form(5)},
        }
    return out


def team_h2h(finals, away, home):
    meetings = [g for g in finals if {g["home"], g["away"]} == {away, home}]
    if not meetings:
        return None
    a_w = h_w = 0
    totals, scorelines = [], []
    for g in sorted(meetings, key=lambda x: x["date"]):
        winner = g["home"] if g["home_score"] > g["away_score"] else g["away"]
        if winner == away:
            a_w += 1
        else:
            h_w += 1
        totals.append(g["home_score"] + g["away_score"])
        scorelines.append(f'{g["away"]} {g["away_score"]}-{g["home_score"]} {g["home"]} ({g["date"][5:]})')
    if a_w > h_w:
        summary = f"{away} lead {a_w}-{h_w}"
    elif h_w > a_w:
        summary = f"{home} lead {h_w}-{a_w}"
    else:
        summary = f"Series tied {a_w}-{h_w}"
    return {"summary": summary, "meetings": len(meetings),
            "avg_total": _avg(totals), "scorelines": scorelines}


def _shooting_pct(subset, made_key, att_key):
    made = sum(g.get(made_key) or 0 for g in subset)
    att = sum(g.get(att_key) or 0 for g in subset)
    return round(made / att * 100, 1) if att > 0 else None


def player_summaries(logs):
    out = {}
    for pid, rec in logs.items():
        games = sorted(rec["games"], key=lambda g: g["date"])
        gp = len(games)
        if gp == 0:
            continue
        def col(key, subset):
            return _avg([g.get(key) for g in subset])
        out[pid] = {
            "pid": pid,
            "name": rec["name"], "full_name": rec["full_name"],
            "pos": rec["pos"], "team": rec["team"], "gp": gp,
            "min": col("min", games),
            "ppg": col("pts", games), "l5_ppg": col("pts", games[-5:]), "l10_ppg": col("pts", games[-10:]),
            "rpg": col("reb", games), "l5_rpg": col("reb", games[-5:]), "l10_rpg": col("reb", games[-10:]),
            "apg": col("ast", games), "l5_apg": col("ast", games[-5:]), "l10_apg": col("ast", games[-10:]),
            "tpm": col("tpm", games), "l5_tpm": col("tpm", games[-5:]), "l10_tpm": col("tpm", games[-10:]),
            "pra": col("pra", games), "l5_pra": col("pra", games[-5:]), "l10_pra": col("pra", games[-10:]),
            "l15_pra": col("pra", games[-15:]), "l25_pra": col("pra", games[-25:]),
            "log": [
                {"date": gl.get("date"), "opp": gl.get("opp"),
                 "opp_id": gl.get("opp_id"),
                 "opp_logo": gl.get("opp_logo"),
                 "pts": gl.get("pts"), "reb": gl.get("reb"),
                 "ast": gl.get("ast"), "tpm": gl.get("tpm"),
                 "stl": gl.get("stl"), "blk": gl.get("blk"),
                 "to": gl.get("to"), "min": gl.get("min"),
                 "pra": gl.get("pra")}
                for gl in games[-25:]
            ],
            "l15_ppg": col("pts", games[-15:]), "l25_ppg": col("pts", games[-25:]),
            "l15_rpg": col("reb", games[-15:]), "l25_rpg": col("reb", games[-25:]),
            "l15_apg": col("ast", games[-15:]), "l25_apg": col("ast", games[-25:]),
            "pr": col("pr", games), "l5_pr": col("pr", games[-5:]), "l10_pr": col("pr", games[-10:]),
            "pa": col("pa", games), "l5_pa": col("pa", games[-5:]), "l10_pa": col("pa", games[-10:]),
            "ra": col("ra", games), "l5_ra": col("ra", games[-5:]), "l10_ra": col("ra", games[-10:]),
            "stocks": col("stocks", games), "l5_stocks": col("stocks", games[-5:]),
            "l10_stocks": col("stocks", games[-10:]),
            "stl": col("stl", games), "blk": col("blk", games),
            "to": col("to", games), "l5_to": col("to", games[-5:]), "l10_to": col("to", games[-10:]),
            "fga": col("fga", games), "l5_fga": col("fga", games[-5:]), "l10_fga": col("fga", games[-10:]),
            "fta": col("fta", games), "l5_fta": col("fta", games[-5:]), "l10_fta": col("fta", games[-10:]),
            "fg_pct": _shooting_pct(games, "fgm", "fga"),
            "tp_pct": _shooting_pct(games, "tpm", "tpa"),
        }
    return out


def player_h2h(logs, pid, opponent):
    games = [g for g in logs.get(pid, {}).get("games", []) if g.get("opp") == opponent]
    if not games:
        return None
    return {"h2h_gp": len(games),
            "h2h_ppg": _avg([g.get("pts") for g in games]),
            "h2h_rpg": _avg([g.get("reb") for g in games]),
            "h2h_apg": _avg([g.get("ast") for g in games]),
            "h2h_tpm": _avg([g.get("tpm") for g in games]),
            "h2h_pra": _avg([g.get("pra") for g in games]),
            "h2h_pr": _avg([g.get("pr") for g in games]),
            "h2h_pa": _avg([g.get("pa") for g in games]),
            "h2h_ra": _avg([g.get("ra") for g in games]),
            "h2h_stocks": _avg([g.get("stocks") for g in games]),
            "h2h_fga": _avg([g.get("fga") for g in games])}


def main():
    now_et = datetime.now(EASTERN)
    today = now_et.strftime("%Y-%m-%d")

    sb, _sb_source = fetch_scoreboard(today.replace("-", ""))
    todays = []
    for _eid, _st, _done, g in parse_scoreboard_events(sb):
        g["event_id"] = _eid
        todays.append(g)
    print(f"WNBA: slate for {today} ET — {len(todays)} games")

    logs, finals = {}, []
    finals_count = 0
    days_attempted = days_failed = 0
    d = SEASON_START
    first_debug = True
    while d <= now_et.date():
        days_attempted += 1
        try:
            day_sb, _ = fetch_scoreboard(d.strftime("%Y%m%d"),
                                         require_events=False)
        except Exception as exc:
            days_failed += 1
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for event_id, status, completed, g in parse_scoreboard_events(day_sb):
            if not completed or not event_id:
                continue
            if g.get("away_score") is not None and g.get("home_score") is not None:
                finals.append({"date": d.isoformat(), "away": g["away"], "home": g["home"],
                                "away_score": g["away_score"], "home_score": g["home_score"]})
            try:
                parse_boxscore(event_id, d.isoformat(), logs, debug=first_debug)
                first_debug = False
                finals_count += 1
            except Exception as exc:
                print(f"  boxscore {event_id} ({d}) failed: {exc}")
        time.sleep(0.15)
        d += timedelta(days=1)

    if not logs:
        raise RuntimeError(
            f"walked {days_attempted} days ({days_failed} unreachable, "
            f"{days_attempted - days_failed} answered) and parsed ZERO box "
            f"scores. A mirror answering 200 is not the same as a mirror "
            f"the parser can read — see wnba_scoreboard_probe.py. Refusing "
            f"to publish a league with no data behind it.")
    if days_failed:
        print(f"WNBA: WARNING — {days_failed}/{days_attempted} scoreboard "
              f"days were unreachable; season splits are built on the rest.")

    players = player_summaries(logs)
    teams = team_research(finals)
    pos_def = positional_defense(logs)
    print(f"WNBA: parsed {finals_count} real box scores -> "
          f"{len(players)} players with game logs; {len(teams)} teams with research")
    if players:
        sample = sorted(players.values(), key=lambda p: -(p["ppg"] or 0))[0]
        print(f"  [verify] season PPG leader parsed: {sample['full_name']} "
              f"({sample['team']}) {sample['ppg']} PPG over {sample['gp']} GP, "
              f"L5 {sample['l5_ppg']} / L10 {sample['l10_ppg']}")

    by_team = {}
    for p in players.values():
        by_team.setdefault(p["team"], []).append(p)
    for plist in by_team.values():
        plist.sort(key=lambda p: -(p["ppg"] or 0))

    _team_rosters = {}
    for g in todays:
        for side in ("away", "home"):
            tid = g.get(f"{side}_id")
            if tid and tid not in _team_rosters:
                _team_rosters[tid] = fetch_team_roster(tid)
    _roster_total = sum(len(v) for v in _team_rosters.values())
    print(f"WNBA: fetched {len(_team_rosters)} team rosters, "
          f"{_roster_total} players total")
    print(f"WNBA: roster status field types "
          f"{sorted(_roster_shapes['status_kind']) or ['none']}, "
          f"{_roster_shapes['with_injury']} of {_roster_shapes['players']} "
          f"players carry a reported injury")
    if not _roster_total:
        print("  *** WARNING: no team rosters returned. Slates will fall back "
              "to box-score history, which cannot include a player who has "
              "not appeared yet. ***")

    for g in todays:
        _avail = fetch_game_availability(g.get("event_id")) if g.get("event_id") else {}
        if _avail:
            g["availability_source"] = "espn_summary"

        for side, opp_side in (("away", "home"), ("home", "away")):
            t = teams.get(g[side])
            if t:
                g[f"{side}_pf_pg"] = t["pf_pg"]
                g[f"{side}_pa_pg"] = t["pa_pg"]
                g[f"{side}_pos_def_allowed"] = pos_def.get(g.get(side)) or {}
                g[f"{side}_avg_total"] = t["avg_total"]
                g[f"{side}_l10"] = t["l10"]
                g[f"{side}_form"] = t["form"]

            opponent = g[opp_side]
            _stats_by_pid = {str(p["pid"]): p for p in by_team.get(g[side], [])}
            _team_name = g.get(side)

            _roster = _team_rosters.get(g.get(f"{side}_id")) or {}

            picks = []
            for pid, info in _roster.items():
                p = _stats_by_pid.get(pid)
                if p is None:
                    p = {"pid": pid, "name": info["name"], "pos": info.get("pos") or "",
                         "team": _team_name, "gp": 0, "log": []}
                picks.append(p)

            if not picks:
                picks = [p for p in _stats_by_pid.values()
                         if (p.get("gp") or 0) >= 3]

            picks.sort(key=lambda p: -((p.get("min") or 0)))
            row_keys = ("pid", "name", "pos", "gp", "min",
                        "ppg", "l5_ppg", "l10_ppg",
                        "rpg", "l5_rpg", "l10_rpg",
                        "apg", "l5_apg", "l10_apg",
                        "tpm", "l5_tpm", "l10_tpm",
                        "pra", "l5_pra", "l10_pra",
                        "pr", "l5_pr", "l10_pr",
                        "pa", "l5_pa", "l10_pa",
                        "ra", "l5_ra", "l10_ra",
                        "stocks", "l5_stocks", "l10_stocks", "stl", "blk",
                        "to", "l5_to", "l10_to",
                        "fga", "l5_fga", "l10_fga",
                        "fta", "l5_fta", "l10_fta",
                        "fg_pct", "tp_pct",
                        "l15_pra", "l25_pra", "l15_ppg", "l25_ppg",
                        "l15_rpg", "l25_rpg", "l15_apg", "l25_apg", "log")
            h2h_keys = ("h2h_ppg", "h2h_rpg", "h2h_apg", "h2h_tpm", "h2h_pra",
                        "h2h_pr", "h2h_pa", "h2h_ra",
                        "h2h_stocks", "h2h_fga", "h2h_gp")
            rows = []
            for p in picks:
                row = {k: p.get(k) for k in row_keys}
                hh = player_h2h(logs, p["pid"], opponent) or {}
                for k in h2h_keys:
                    row[k] = hh.get(k)
                a = _avail.get(str(p.get("pid"))) or {}
                row["today_status"] = a.get("status")
                row["today_out"] = a.get("out")
                row["today_starter"] = a.get("starter")

                _ri = _roster.get(str(p.get("pid"))) or {}
                row["jersey"] = _ri.get("jersey")
                row["roster_status"] = _ri.get("roster_status")
                row["injury_status"] = _ri.get("injury_status")
                row["injury_date"] = _ri.get("injury_date")
                row["exp"] = _ri.get("exp")
                rows.append(row)
            if rows:
                g[f"{side}_players"] = rows

        hh = team_h2h(finals, g["away"], g["home"])
        if hh:
            g["h2h"] = hh

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "games.json").write_text(json.dumps({
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
        "source": "ESPN public WNBA API (scoreboard + game box scores)",
        "slate_date_et": today,
        "games": todays,
    }, ensure_ascii=False, indent=2))
    (OUT / "players.json").write_text(json.dumps({
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
        "players": players,
    }, ensure_ascii=False, indent=2))

    slim_logs = {}
    for pid, rec in logs.items():
        games = [
            {"date": gl.get("date"), "min": gl.get("min"),
             "pts": gl.get("pts"), "reb": gl.get("reb"),
             "ast": gl.get("ast"), "pra": gl.get("pra")}
            for gl in (rec.get("games") or []) if gl.get("date")
        ]
        if not games:
            continue
        slim_logs[pid] = {
            "name": rec.get("name"), "team": rec.get("team"),
            "pos": rec.get("pos"), "games": games,
        }
    (OUT / "player_logs.json").write_text(
        json.dumps(slim_logs, ensure_ascii=False, indent=2))

    print(f"WNBA: wrote games.json ({len(todays)} games), players.json "
          f"({len(players)} players), player_logs.json ({len(slim_logs)} players)")


if __name__ == "__main__":
    main()
