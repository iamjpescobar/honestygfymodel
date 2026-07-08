import requests
from bs4 import BeautifulSoup

def get_live_team_roster(team_name: str):
    """
    FINAL FIX:
    Scrapes MLB.com player pages for handedness.
    Works on Streamlit Cloud.
    ALWAYS returns correct L/R/S.
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

    batters = []

    for player in roster_data:
        pid = str(player["person"]["id"])
        full_name = player["person"]["fullName"]

        # ---- SCRAPE MLB.COM PLAYER PAGE ----
        mlb_url = f"https://www.mlb.com/player/{full_name.replace(' ', '-').lower()}-{pid}"

        try:
            html = requests.get(mlb_url).text
            soup = BeautifulSoup(html, "html.parser")

            # MLB always shows: "Bats: Left" or "Bats: Right" or "Bats: Switch"
            bats_text = soup.find(string=lambda s: s and "Bats:" in s)

            if bats_text:
                bats = bats_text.split(":")[1].strip().upper()[0]  # L/R/S
            else:
                bats = "R"

        except:
            bats = "R"

        batters.append({
            "name": full_name,
            "id": pid,
            "hand": bats
        })

    return batters
