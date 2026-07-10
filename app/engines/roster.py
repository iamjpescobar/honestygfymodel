import requests
import streamlit as st


@st.cache_data(ttl=1800)
def get_all_teams():
    """
    Returns a clean list of all MLB team names.
    """
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    teams = requests.get(url).json().get("teams", [])
    return sorted([t["name"] for t in teams])


@st.cache_data(ttl=1800)
def get_live_team_roster(team_name: str):
    """
    Returns the live 40-man roster for a given MLB team, each entry tagged
    with its real position so callers can filter pitchers vs. position
    players instead of guessing from a single mixed dropdown.
    Cached for 30 minutes to avoid hammering the MLB Stats API on every
    rerun — roster moves (trades/injuries) won't show up faster than that.
    """

    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    teams = requests.get(teams_url).json().get("teams", [])

    team_id = None
    for t in teams:
        if t["name"].lower() == team_name.lower():
            team_id = t["id"]
            break

    if not team_id:
        return []

    roster_url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
    roster_data = requests.get(roster_url).json().get("roster", [])

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
            data = requests.get(people_url).json()
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
