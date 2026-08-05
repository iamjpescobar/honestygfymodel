"""
Does stats.wnba.com publish STARTING LINEUPS, and when?

WHY THIS EXISTS

ESPN does not. The roster probe established that `today_starter` is
never populated for the WNBA, so every START badge on the site was the
app's own minutes inference — since relabelled to LIKELY, which is
honest but is not the same as knowing.

stats.wnba.com is the league's own stats API, the WNBA sibling of
stats.nba.com. It is undocumented and unsupported, and it may refuse
this runner outright. That is a result too. The point is to find out
what it returns BEFORE anything is designed around it, rather than
after.

WHAT WOULD COUNT AS A WIN

A field naming who starts, available BEFORE tip. boxscoretraditionalv2
carries STARTER_POSITION, but a box score exists only once a game has
started, which would make it useless for a pick published at 5 PM. So
the probe fetches the same game at whatever state it is in and prints
which result sets and columns come back, and the reading of it is: does
any pre-game endpoint name five players per side?

MUST RUN FROM ACTIONS. These hosts filter by IP range and by header,
and a laptop result predicts nothing about what the pipeline sees.

Touches nothing: no commit, no release, no deploy hook.
"""
import json
import sys
import time

import requests

BASE = "https://stats.wnba.com/stats"

# stats.nba.com-family hosts reject anything that does not look like the
# site's own XHR. These exact headers are the difference between JSON and
# a hang; if this probe times out everywhere, suspect these first.
HEADERS = {
    "Host": "stats.wnba.com",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wnba.com/",
    "Origin": "https://www.wnba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Connection": "keep-alive",
}

LEAGUE_ID = "10"  # WNBA. 00 is NBA, 20 is G League.


def get(path, params, label):
    """GET and report honestly. A dead endpoint is a finding."""
    url = f"{BASE}/{path}"
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    except Exception as exc:
        print(f"  {label}: request failed ({type(exc).__name__}: {exc})")
        return None
    print(f"  {label}: HTTP {r.status_code}  {len(r.content):,} bytes")
    if r.status_code != 200:
        print(f"    body starts: {r.text[:200]!r}")
        return None
    try:
        return r.json()
    except Exception:
        print(f"    200 but not JSON. starts: {r.text[:200]!r}")
        return None


def show_sets(data, want=()):
    """Print every resultSet name and its columns.

    The column list is the whole answer: if no pre-game endpoint has a
    starter column, no amount of parsing invents one.
    """
    sets = data.get("resultSets") or data.get("resultSet") or []
    if isinstance(sets, dict):
        sets = [sets]
    if not sets:
        print(f"    no resultSets. top-level keys: {sorted(data)[:12]}")
        return {}
    out = {}
    for s in sets:
        name = s.get("name", "?")
        hdrs = s.get("headers") or []
        rows = s.get("rowSet") or []
        out[name] = (hdrs, rows)
        flag = ""
        for w in want:
            if any(w in str(h).upper() for h in hdrs):
                flag = f"   <-- has {w}"
        print(f"    {name}: {len(rows)} rows, {len(hdrs)} cols{flag}")
        if flag or name in ("GameHeader", "LineScore"):
            print(f"      cols: {hdrs}")
    return out


def main(date_str):
    mm, dd, yyyy = date_str[5:7], date_str[8:10], date_str[0:4]
    us_date = f"{mm}/{dd}/{yyyy}"
    print("=" * 70)
    print(f"stats.wnba.com probe - {date_str}")
    print("=" * 70)

    print("\n[1] scoreboardv2 - the day's games, and whether it reaches us")
    sb = get("scoreboardv2",
             {"GameDate": us_date, "LeagueID": LEAGUE_ID, "DayOffset": "0"},
             "scoreboardv2")
    game_ids, team_ids = [], []
    if sb:
        sets = show_sets(sb)
        hdrs, rows = sets.get("GameHeader", ([], []))
        if hdrs:
            gi = hdrs.index("GAME_ID") if "GAME_ID" in hdrs else None
            hi = hdrs.index("HOME_TEAM_ID") if "HOME_TEAM_ID" in hdrs else None
            vi = (hdrs.index("VISITOR_TEAM_ID")
                  if "VISITOR_TEAM_ID" in hdrs else None)
            for row in rows:
                if gi is not None:
                    game_ids.append(row[gi])
                for idx in (hi, vi):
                    if idx is not None and row[idx] not in team_ids:
                        team_ids.append(row[idx])
        print(f"    -> {len(game_ids)} games, {len(team_ids)} teams")

    if not sb:
        print("\nscoreboardv2 did not answer. Everything below depends on it,")
        print("so stopping here rather than printing a wall of failures.")
        print("If this is a 403 or a timeout, the host is refusing the")
        print("runner and this whole avenue is closed from CI.")
        return 0

    time.sleep(0.6)
    print("\n[2] scoreboardv3 - newer shape, sometimes richer")
    v3 = get("scoreboardv3", {"GameDate": date_str, "LeagueID": LEAGUE_ID},
             "scoreboardv3")
    if v3:
        print(f"    top-level keys: {sorted(v3)[:12]}")
        print(json.dumps(v3, indent=2)[:1200])

    if game_ids:
        gid = game_ids[0]
        time.sleep(0.6)
        print(f"\n[3] boxscoresummaryv2 - game {gid}")
        summ = get("boxscoresummaryv2", {"GameID": gid}, "boxscoresummaryv2")
        if summ:
            show_sets(summ, want=("STARTER", "LINEUP", "POSITION"))

        time.sleep(0.6)
        print(f"\n[4] boxscoretraditionalv2 - game {gid}")
        print("    THE KEY QUESTION: does STARTER_POSITION arrive before")
        print("    tip, or only once the game is under way?")
        box = get("boxscoretraditionalv2",
                  {"GameID": gid, "StartPeriod": "0", "EndPeriod": "10",
                   "StartRange": "0", "EndRange": "0", "RangeType": "0"},
                  "boxscoretraditionalv2")
        if box:
            sets = show_sets(box, want=("STARTER", "POSITION"))
            hdrs, rows = sets.get("PlayerStats", ([], []))
            if hdrs and "START_POSITION" in hdrs:
                si = hdrs.index("START_POSITION")
                ni = hdrs.index("PLAYER_NAME") if "PLAYER_NAME" in hdrs else 0
                named = [(r[ni], r[si]) for r in rows if str(r[si]).strip()]
                print(f"    players with a START_POSITION: {len(named)}")
                for n, p in named[:12]:
                    print(f"      {p:>3}  {n}")

    if team_ids:
        tid = team_ids[0]
        time.sleep(0.6)
        print(f"\n[5] commonteamroster - team {tid}")
        ros = get("commonteamroster",
                  {"TeamID": tid, "Season": date_str[:4],
                   "LeagueID": LEAGUE_ID}, "commonteamroster")
        if ros:
            show_sets(ros, want=("STARTER", "POSITION"))

    print("\n" + "=" * 70)
    print("Done. Download the log zip and send the whole thing.")
    print("Reading it: if nothing here names five players a side BEFORE")
    print("tip, LIKELY is the honest final answer and this closes.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-08-03"))
