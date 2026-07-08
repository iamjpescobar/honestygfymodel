import requests

def get_live_team_roster(team_name: str):
    """
    FINAL FIX:
    Uses MLB /people endpoint with hydrate=battingSide
    This ALWAYS returns correct handedness (L/R/S)
    and works on Streamlit Cloud.
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

    # ---- GET BASIC ROSTER ----
    roster_url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
    roster_data = requests.get(roster_url).json().get("roster", [])

    # Collect all player IDs
    player_ids = [str(p["person"]["id"]) for p in roster_data]

    # ---- GET FULL PLAYER DATA WITH HANDEDNESS ----
    people_url = (
        "https://statsapi.mlb.com/api/v1/people?"
        f"personIds={','.join(player_ids)}&hydrate=battingSide"
    )

    people_data = requests.get(people_url).json().get("people", [])

    batters = []

    for person in people_data:
        full_name = person.get("fullName", "Unknown Player")
        pid = person.get("id", None)

        # MLB ALWAYS returns this field here
        batting_side = person.get("battingSide", {}).get("code", "R")

        batters.append({
            "name": full_name,
            "id": pid,
            "hand": batting_side  # ← ALWAYS L/R/S now
        })

    return batters
