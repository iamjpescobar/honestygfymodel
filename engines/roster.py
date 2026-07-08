import requests

def get_live_team_roster(team_name: str):
    """
    Returns the active MLB roster for a given team with:
    - fullName
    - player ID
    - batting handedness (R, L, S)
    """

    # ---- GET ALL MLB TEAMS ----
    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    teams = requests.get(teams_url).json().get("teams", [])

    team_id = None
    for t in teams:
        if t["name"].lower() == team_name.lower():
            team_id = t["id"]
            break

    if not team_id:
        return []

    # ---- GET TEAM ROSTER ----
    roster_url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
    roster_data = requests.get(roster_url).json().get("roster", [])

    batters = []

    for player in roster_data:
        pid = player["person"]["id"]

        # ---- GET FULL PLAYER INFO (WHERE HANDEDNESS LIVES) ----
        info_url = f"https://statsapi.mlb.com/api/v1/people/{pid}"
        info = requests.get(info_url).json().get("people", [{}])[0]

        full_name = info.get("fullName", "Unknown Player")

        # MLB API returns battingSide.code as: "R", "L", or "S"
        batting_side = info.get("battingSide", {}).get("code", "R")

        batters.append({
            "name": full_name,
            "id": pid,
            "hand": batting_side  # FIXED: R, L, or S
        })

    return batters
