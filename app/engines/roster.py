import requests
import streamlit as st


@st.cache_data(ttl=300)
def get_confirmed_lineup(game_pk, side: str):
    """
    Real confirmed starting lineup for one specific game, straight from
    MLB's own boxscore endpoint — not a general roster slice. MLB
    typically posts this 1-3 hours before first pitch; before that, it
    genuinely doesn't exist yet (not a bug, a real timing constraint).

    side: "away" or "home"
    Returns (lineup, confirmed) where lineup is a list of
    {"id", "name", "position", "bats", "battingOrder"} sorted by real
    batting order, and confirmed is True only if MLB has actually
    posted a real lineup. Callers MUST check `confirmed` and label
    the data honestly if False — never silently pass off a fallback
    roster as if it were the real confirmed lineup.
    """
    if not game_pk:
        return [], False
    try:
        url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
        data = requests.get(url, timeout=10).json()
        team_data = data.get("teams", {}).get(side, {})
        players = team_data.get("players", {})
    except Exception:
        return [], False

    lineup = []
    for p in players.values():
        batting_order = p.get("battingOrder")
        if not batting_order:
            continue  # not in today's real starting lineup (bench/bullpen/unused)
        person = p.get("person", {})
        position = p.get("position", {})
        pid = person.get("id")

        # Bat side isn't reliably present on the boxscore player object
        # itself (confirmed: get_live_team_roster below has to make this
        # same separate call for the same reason) — a real per-player
        # lookup, not a guess.
        bats = "?"
        try:
            people_resp = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}", timeout=10).json()
            person_detail = people_resp.get("people", [{}])[0]
            bats = person_detail.get("batSide", {}).get("code") or "?"
        except Exception:
            pass  # leave as "?" rather than silently guessing a side

        lineup.append({
            "id": str(pid or ""),
            "name": person.get("fullName", "Unknown"),
            "position": position.get("abbreviation", ""),
            "is_pitcher": position.get("abbreviation") == "P",
            "bats": bats,
            "battingOrder": int(batting_order),
        })

    if not lineup:
        return [], False

    lineup.sort(key=lambda x: x["battingOrder"])
    return lineup, True


@st.cache_data(ttl=1800)
def get_all_teams():
    """
    Returns a clean list of all MLB team names. Returns an empty list
    (rather than crashing the page) if the MLB Stats API is unreachable —
    callers already handle an empty team list with a warning message.
    """
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        teams = resp.json().get("teams", [])
    except Exception:
        return []
    return sorted([t["name"] for t in teams])


@st.cache_data(ttl=1800)
def get_live_team_roster(team_name: str):
    """
    Returns the live 40-man roster for a given MLB team, each entry tagged
    with its real position so callers can filter pitchers vs. position
    players instead of guessing from a single mixed dropdown.
    Cached for 30 minutes to avoid hammering the MLB Stats API on every
    rerun — roster moves (trades/injuries) won't show up faster than that.
    Returns an empty list (rather than crashing the page) if the MLB
    Stats API is unreachable or returns something unexpected.
    """

    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    try:
        teams = requests.get(teams_url, timeout=10).json().get("teams", [])
    except Exception:
        return []

    team_id = None
    for t in teams:
        if t["name"].lower() == team_name.lower():
            team_id = t["id"]
            break

    if not team_id:
        return []

    roster_url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
    try:
        roster_data = requests.get(roster_url, timeout=10).json().get("roster", [])
    except Exception:
        return []

    players = []

    for player in roster_data:
        pid = str(player["person"]["id"])
        full_name = player["person"]["fullName"]
        position_code = player.get("position", {}).get("abbreviation", "?")
        position_type = player.get("position", {}).get("type", "Unknown")  # "Pitcher" or "Hitter" etc.
        is_pitcher = position_type == "Pitcher" or position_code == "P"

        people_url = f"https://statsapi.mlb.com/api/v1/people/{pid}"
        bats, throws = None, None
        try:
            data = requests.get(people_url, timeout=10).json()
            person = data["people"][0]
            bats = person.get("batSide", {}).get("code", "").upper() or None
            throws = person.get("pitchHand", {}).get("code", "").upper() or None
        except Exception:
            pass  # leave as None rather than silently guessing "R"

        players.append({
            "name": full_name,
            "id": pid,
            "position": position_code,
            "is_pitcher": is_pitcher,
            "bats": bats,     # None means "unknown, real lookup failed" — not a guess
            "throws": throws
        })

    return players


def get_pitchers(team_name: str):
    """Convenience filter: only real pitchers on the roster."""
    return [p for p in get_live_team_roster(team_name) if p["is_pitcher"]]


def get_position_players(team_name: str):
    """Convenience filter: only real position players (non-pitchers) on the roster."""
    return [p for p in get_live_team_roster(team_name) if not p["is_pitcher"]]
