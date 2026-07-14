"""
WNBA slate + matchup data fetcher — real data from ESPN's public
scoreboard API (verified open from GitHub Actions).

Writes data/wnba/games.json for today's slate in US Eastern: teams,
arena, tip time, live status, team records, per-team stat leaders
(points / rebounds / assists — season averages for upcoming games,
actual game leaders for finals), and the betting line/total where
ESPN carries one.

Every value is read straight from the feed. Anything absent is simply
omitted — never estimated, never filled in.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")
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


def fetch_scoreboard(date_et: str) -> dict:
    url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
           f"?dates={date_et.replace('-', '')}")
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.json()


def _to_et(iso_utc: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return dt.astimezone(EASTERN).strftime("%-I:%M %p")
    except Exception:
        return "TBD"


def _record(competitor: dict):
    for rec in competitor.get("records", []) or []:
        if rec.get("name") == "overall" and rec.get("summary"):
            return rec["summary"]
    return None


def _leaders(competitor: dict):
    """Real stat leaders straight from the feed — season averages for
    upcoming games, game totals for finals."""
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


def parse_games(payload: dict):
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

        away_rec, home_rec = _record(away), _record(home)
        if away_rec:
            g["away_record"] = away_rec
        if home_rec:
            g["home_record"] = home_rec

        if completed or status == "in progress":
            try:
                g["final" if completed else "score"] = (
                    f'{g["away"]} {int(float(away.get("score", 0)))} - '
                    f'{int(float(home.get("score", 0)))} {g["home"]}'
                )
            except (TypeError, ValueError):
                pass

        away_leaders, home_leaders = _leaders(away), _leaders(home)
        if away_leaders:
            g["away_leaders"] = away_leaders
        if home_leaders:
            g["home_leaders"] = home_leaders
        g["leaders_kind"] = "game" if completed else "season"

        odds_list = comp.get("odds") or []
        if odds_list:
            odds = odds_list[0]
            details, ou = odds.get("details"), odds.get("overUnder")
            line_bits = []
            if details:
                line_bits.append(str(details))
            if ou is not None:
                line_bits.append(f"O/U {ou}")
            if line_bits:
                g["line"] = " \u00b7 ".join(line_bits)

        yield g


def main():
    now_et = datetime.now(EASTERN)
    today = now_et.strftime("%Y-%m-%d")

    payload = fetch_scoreboard(today)
    games = list(parse_games(payload))

    OUT.mkdir(parents=True, exist_ok=True)
    out = {
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
        "source": "ESPN public WNBA scoreboard API",
        "slate_date_et": today,
        "games": games,
    }
    (OUT / "games.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"WNBA: wrote {len(games)} games for {today} ET "
          f"({sum(1 for g in games if g.get('line'))} with betting lines)")
    if not games:
        print("WNBA: empty slate — league off-day. That is the honest state.")


if __name__ == "__main__":
    main()
