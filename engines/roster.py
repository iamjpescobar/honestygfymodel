import requests
import streamlit as st

MLB_TEAM_IDS = {
    "Arizona Diamondbacks": 109, "Atlanta Braves": 144, "Baltimore Orioles": 110,
    "Boston Red Sox": 111, "Chicago Cubs": 112, "Chicago White Sox": 145,
    "Cincinnati Reds": 113, "Cleveland Guardians": 114, "Colorado Rockies": 115,
    "Detroit Tigers": 116, "Houston Astros": 117, "Kansas City Royals": 118,
    "Los Angeles Angels": 108, "Los Angeles Dodgers": 119, "Miami Marlins": 146,
    "Milwaukee Brewers": 158, "Minnesota Twins": 142, "New York Mets": 121,
    "New York Yankees": 147, "Athletics": 131, "Philadelphia Phillies": 143,
    "Pittsburgh Pirates": 134, "San Diego Padres": 135, "San Francisco Giants": 137,
    "Seattle Mariners": 136, "St. Louis Cardinals": 138, "Tampa Bay Rays": 139,
    "Texas Rangers": 140, "Toronto Blue Jays": 141, "Washington Nationals": 120
}

FALLBACK_ROSTERS = {
    "Kansas City Royals": [
        {"name": "Jac Caglianone", "hand": "LHB"},
        {"name": "Luke Maile", "hand": "RHB"},
        {"name": "Nick Loftin", "hand": "RHB"},
        {"name": "Salvador Perez", "hand": "RHB"},
    ],
    "Washington Nationals": [
        {"name": "Andrés Chaparro", "hand": "RHB"},
        {"name": "CJ Abrams", "hand": "LHB"},
        {"name": "Curtis Mead", "hand": "RHB"},
    ],
}

@st.cache_data(ttl=3600)
def get_live_team_roster(team_name: str):
    team_id = MLB_TEAM_IDS.get(team_name)
    if not team_id:
        return []

    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"

    try:
        response = requests.get(url).json()
        roster = response.get("roster", [])

        players = []
        for p in roster:
            pos_code = p.get("position", {}).get("code")
            person = p.get("person", {})

            if pos_code == "1":
                continue

            name = person.get("fullName")
            side = person.get("batSide", {}).get("code", "R")

            hand = "LHB" if side == "L" else "SHB" if side == "S" else "RHB"
            players.append({"name": name, "hand": hand})

        return players

    except Exception:
        return FALLBACK_ROSTERS.get(team_name, [])

