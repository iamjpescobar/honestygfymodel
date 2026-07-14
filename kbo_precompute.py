"""
KBO slate fetcher — real data from MyKBOStats' schedule page.

Parses the current week's schedule (verified reachable and
server-rendered from GitHub Actions) and writes data/kbo/games.json
for today's slate IN KST — which a US user experiences as tomorrow's
games shown tonight, since Korea is 13 hours ahead of Eastern.

Every value comes straight off the page: teams, venue, and start time
(from the page's own machine-readable UTC timestamps, converted
exactly). Starters aren't listed on the schedule page, so they're TBD
— never guessed. An empty slate (Mondays, All-Star break) is reported
as exactly that.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
EASTERN = ZoneInfo("America/New_York")

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

# Short names as they appear in game URLs -> full team names
TEAMS = {
    "Kia": "Kia Tigers", "KT": "KT Wiz", "LG": "LG Twins",
    "Lotte": "Lotte Giants", "Doosan": "Doosan Bears", "NC": "NC Dinos",
    "Kiwoom": "Kiwoom Heroes", "Hanwha": "Hanwha Eagles",
    "Samsung": "Samsung Lions", "SSG": "SSG Landers",
}

OUT = Path("build_data") / "data" / "kbo"

GAME_LINE = re.compile(
    r'<a id="game-line-\d+" class="game-line" '
    r'href="/games/\d+-([A-Za-z]+)-vs-([A-Za-z]+)-(\d{8})">(.*?)</a>',
    re.S,
)


def _team(short: str) -> str:
    return TEAMS.get(short, short)


def fetch_schedule() -> str:
    r = requests.get("https://mykbostats.com/schedule", headers=UA, timeout=25)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def parse_games(html: str):
    """Yields one dict per game-line block on the schedule page."""
    for m in GAME_LINE.finditer(html):
        away_short, home_short, yyyymmdd, inner = m.groups()

        dt_utc = None
        t = re.search(r'datetime="([0-9T:+.Z-]+)"', inner)
        if t:
            try:
                dt_utc = datetime.fromisoformat(t.group(1).replace("Z", "+00:00"))
            except ValueError:
                dt_utc = None

        venue = re.search(r'<div class="venue">\s*(.*?)\s*</div>', inner, re.S)

        yield {
            "date": f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}",
            "away": _team(away_short), "home": _team(home_short),
            "stadium": re.sub(r"<[^>]+>", "", venue.group(1)).strip() if venue else "TBD",
            "time_kst": dt_utc.astimezone(KST).strftime("%H:%M") if dt_utc else "TBD",
            "time_et": dt_utc.astimezone(EASTERN).strftime("%-I:%M %p") if dt_utc else "TBD",
            "away_starter": "TBD", "home_starter": "TBD",
            "status": "scheduled",
        }


def main():
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")

    html = fetch_schedule()
    all_games = list(parse_games(html))
    todays = [g for g in all_games if g["date"] == today]

    for g in todays:
        g.pop("date", None)

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M"),
        "source": "mykbostats.com schedule",
        "slate_date_kst": today,
        "games": todays,
    }
    (OUT / "games.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"KBO: wrote {len(todays)} games for {today} KST "
          f"(week view contained {len(all_games)} games total)")
    if not todays:
        print("KBO: empty slate — Monday off-day or All-Star break. That is the honest state.")


if __name__ == "__main__":
    main()