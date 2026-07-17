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
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")
SEASON_START = date(2026, 4, 3)
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
}

OUT = Path("build_data") / "data" / "wnba"

STATUS_MAP = {
    "STATUS_SCHEDULED": "scheduled",
    "STATUS_IN_PROGRESS": "in progress",
    "STATUS_HALFTIME": "in progress",
    "STATUS_END_PERIOD": "in progress",
    "STATUS_FINAL": "final",
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "postponed",
}

LEADER_CATS = {"points": "PTS", "rebounds": "REB", "assists": "AST"}


def get_json(url):
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.json()


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
            "away_color": (away.get("team") or {}).get("color"),
            "home_color": (home.get("team") or {}).get("color"),
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


def parse_boxscore(event_id, game_date, logs, debug=False):
    data = get_json(f"{BASE}/summary?event={event_id}")
    blocks = (data.get("boxscore") or {}).get("players", []) or []
    names = [(b.get("team") or {}).get("displayName", "") for b in blocks]
    for i, team_block in enumerate(blocks):
        team_name = names[i]
        opp_name = names[1 - i] if len(names) == 2 else ""
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
                line = {"date": game_date, "team": team_name, "opp": opp_name}
                for k, i2 in idx.items():
                    line[k.lower()] = _num(stats[i2])
                def _made_att(i, mk, ak):
                    if i is not None and len(stats) > i:
                        parts = str(stats[i]).split("-")
                        if len(parts) == 2:
                            line[mk], line[ak] = _num(parts[0]), _num(parts[1])
                _made_att(tpt_i, "tpm", "tpa")
                _made_att(fg_i, "fgm", "fga")
                _made_att(ft_i, "ftm", "fta")
                if line.get("pts") is not None:
                    line["pra"] = (line.get("pts") or 0) + (line.get("reb") or 0) + (line.get("ast") or 0)
                    line["pr"] = (line.get("pts") or 0) + (line.get("reb") or 0)
                    line["pa"] = (line.get("pts") or 0) + (line.get("ast") or 0)
                if line.get("reb") is not None and line.get("ast") is not None:
                    line["ra"] = (line.get("reb") or 0) + (line.get("ast") or 0)
                if line.get("stl") is not None or line.get("blk") is not None:
                    line["stocks"] = (line.get("stl") or 0) + (line.get("blk") or 0)
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


def team_research(finals):
    """Per-team: PF/PA per game, last-10 record, avg total — arithmetic
    on real final scores."""
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
        out[team] = {
            "pf_pg": _avg(t["pf"]), "pa_pg": _avg(t["pa"]),
            "avg_total": _avg([a + b for a, b in zip(t["pf"], t["pa"])]),
            "l10": f'{last10.count("W")}-{last10.count("L")}',
        }
    return out


def team_h2h(finals, away, home):
    """Season series between tonight's two teams, from real finals."""
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
    """Attempts-weighted shooting percentage over a set of game logs —
    total makes / total attempts, NOT an average of per-game
    percentages (which would let a 1-for-1 night count the same as a
    10-for-20 one). None when there are no attempts."""
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
    """A player's real averages specifically vs tonight's opponent."""
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

    sb = get_json(f"{BASE}/scoreboard?dates={today.replace('-', '')}")
    todays = [g for _, _, _, g in parse_scoreboard_events(sb)]
    print(f"WNBA: slate for {today} ET — {len(todays)} games")

    logs, finals = {}, []
    finals_count = 0
    d = SEASON_START
    first_debug = True
    while d <= now_et.date():
        try:
            day_sb = get_json(f"{BASE}/scoreboard?dates={d.strftime('%Y%m%d')}")
        except Exception as exc:
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

    players = player_summaries(logs)
    teams = team_research(finals)
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

    for g in todays:
        for side, opp_side in (("away", "home"), ("home", "away")):
            t = teams.get(g[side])
            if t:
                g[f"{side}_pf_pg"] = t["pf_pg"]
                g[f"{side}_pa_pg"] = t["pa_pg"]
                g[f"{side}_avg_total"] = t["avg_total"]
                g[f"{side}_l10"] = t["l10"]

            opponent = g[opp_side]
            picks = [p for p in by_team.get(g[side], []) if p["gp"] >= 3][:9]
            row_keys = ("name", "pos", "gp", "min",
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
                        "fg_pct", "tp_pct")
            h2h_keys = ("h2h_ppg", "h2h_rpg", "h2h_apg", "h2h_tpm", "h2h_pra",
                        "h2h_pr", "h2h_pa", "h2h_ra",
                        "h2h_stocks", "h2h_fga", "h2h_gp")
            rows = []
            for p in picks:
                row = {k: p.get(k) for k in row_keys}
                hh = player_h2h(logs, p["pid"], opponent) or {}
                for k in h2h_keys:
                    row[k] = hh.get(k)
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
    print(f"WNBA: wrote games.json ({len(todays)} games) and players.json "
          f"({len(players)} players)")


if __name__ == "__main__":
    main()