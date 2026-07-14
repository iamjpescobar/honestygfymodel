"""
WNBA slate + full player research data — real data from ESPN's public
WNBA API (scoreboard verified open from GitHub Actions; the summary
endpoint is the same public API surface).

Three jobs:
1. Today's ET slate: teams, arena, tip time, status, records, stat
   leaders, and the betting line where ESPN carries one.
2. Season crawl: every final since opening day -> every game's real
   box score -> per-player game logs (MIN/PTS/REB/AST per game).
3. Player research: per player, season averages AND last-5 / last-10
   form computed from those logs -- attached to today's matchups so
   each game card carries both rosters' real prop-relevant numbers.

Every value is read from ESPN's feeds or is arithmetic on them.
Anything absent is omitted -- never estimated. A player's L5 is the
mean of her last five REAL box-score lines, nothing else.
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")
SEASON_START = date(2026, 4, 3)   # from the feed's own season.startDate
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
    for rec in competitor.get("records", []) or []:
        if rec.get("name") == "overall" and rec.get("summary"):
            return rec["summary"]
    return None


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
    """Yields (event_id, date_str, status, game_dict) for each event."""
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
            "arena": (comp.get("venue") or {}).get("fullName", ""),
            "time_et": _to_et(comp.get("date", "")),
            "status": status,
        }
        for side, c in (("away", away), ("home", home)):
            rec = _record(c)
            if rec:
                g[f"{side}_record"] = rec
            lds = _leaders(c)
            if lds:
                g[f"{side}_leaders"] = lds
        g["leaders_kind"] = "game" if completed else "season"

        if completed or status == "in progress":
            try:
                g["final" if completed else "score"] = (
                    f'{g["away"]} {int(float(away.get("score", 0)))} - '
                    f'{int(float(home.get("score", 0)))} {g["home"]}')
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
    """Reads one game's real box score into per-player logs.
    Label-driven: stat positions are looked up from the feed's own
    labels list, never assumed."""
    data = get_json(f"{BASE}/summary?event={event_id}")
    for team_block in (data.get("boxscore") or {}).get("players", []) or []:
        team_name = (team_block.get("team") or {}).get("displayName", "")
        for stat_group in team_block.get("statistics", []) or []:
            labels = [l.upper() for l in (stat_group.get("labels") or stat_group.get("names") or [])]
            if "PTS" not in labels:
                continue
            idx = {k: labels.index(k) for k in ("MIN", "PTS", "REB", "AST") if k in labels}
            if debug:
                print(f"  [debug] labels for event {event_id}: {labels}")
            for entry in stat_group.get("athletes", []) or []:
                if entry.get("didNotPlay"):
                    continue
                athlete = entry.get("athlete") or {}
                stats = entry.get("stats") or []
                if not athlete.get("id") or len(stats) <= max(idx.values(), default=0):
                    continue
                line = {"date": game_date, "team": team_name}
                for k, i in idx.items():
                    line[k.lower()] = _num(stats[i])
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


def player_summaries(logs):
    """Season + L5/L10 lines per player, from real game logs."""
    out = {}
    for pid, rec in logs.items():
        games = sorted(rec["games"], key=lambda g: g["date"])
        gp = len(games)
        if gp == 0:
            continue
        def col(key, subset):
            return _avg([g.get(key) for g in subset])
        out[pid] = {
            "name": rec["name"], "full_name": rec["full_name"],
            "pos": rec["pos"], "team": rec["team"], "gp": gp,
            "min": col("min", games), "ppg": col("pts", games),
            "rpg": col("reb", games), "apg": col("ast", games),
            "l5_ppg": col("pts", games[-5:]), "l5_rpg": col("reb", games[-5:]),
            "l5_apg": col("ast", games[-5:]),
            "l10_ppg": col("pts", games[-10:]), "l10_rpg": col("reb", games[-10:]),
            "l10_apg": col("ast", games[-10:]),
        }
    return out


def main():
    now_et = datetime.now(EASTERN)
    today = now_et.strftime("%Y-%m-%d")

    # ---- 1. Today's slate ----
    sb = get_json(f"{BASE}/scoreboard?dates={today.replace('-', '')}")
    todays = [g for _, _, _, g in parse_scoreboard_events(sb)]
    print(f"WNBA: slate for {today} ET — {len(todays)} games")

    # ---- 2. Season crawl: every final's real box score ----
    logs = {}
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
        for event_id, status, completed, _g in parse_scoreboard_events(day_sb):
            if not completed or not event_id:
                continue
            try:
                parse_boxscore(event_id, d.isoformat(), logs, debug=first_debug)
                first_debug = False
                finals_count += 1
            except Exception as exc:
                print(f"  boxscore {event_id} ({d}) failed: {exc}")
        time.sleep(0.15)
        d += timedelta(days=1)

    players = player_summaries(logs)
    print(f"WNBA: parsed {finals_count} real box scores -> "
          f"{len(players)} players with game logs")
    if players:
        sample = sorted(players.values(), key=lambda p: -(p["ppg"] or 0))[0]
        print(f"  [verify] season PPG leader parsed: {sample['full_name']} "
              f"({sample['team']}) {sample['ppg']} PPG over {sample['gp']} GP, "
              f"L5 {sample['l5_ppg']} / L10 {sample['l10_ppg']}")

    # ---- 3. Attach both rosters' research lines to today's games ----
    by_team = {}
    for p in players.values():
        by_team.setdefault(p["team"], []).append(p)
    for team, plist in by_team.items():
        plist.sort(key=lambda p: -(p["ppg"] or 0))

    for g in todays:
        for side in ("away", "home"):
            roster = by_team.get(g[side], [])
            picks = [p for p in roster if p["gp"] >= 3][:7]
            if picks:
                g[f"{side}_players"] = [
                    {k: p[k] for k in ("name", "pos", "gp", "min", "ppg", "rpg",
                                        "apg", "l5_ppg", "l10_ppg", "l5_rpg",
                                        "l5_apg")}
                    for p in picks
                ]

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