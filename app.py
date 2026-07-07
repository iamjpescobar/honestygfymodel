import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# --- 1. CONFIG & TEAM MAPS ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

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

# --- 2. HELPER FUNCTIONS ---
def highlight_slam(data):
    return ['background-color: #2e7d32' if isinstance(v, (int, float)) and v > 5.0 else '' for v in data]

@st.cache_data(ttl=3600)
def get_live_team_roster(team_name):
    team_id = MLB_TEAM_IDS.get(team_name)
    if not team_id: return []
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    try:
        response = requests.get(url).json()
        players = []
        for p in response.get('roster', []):
            person = p.get('person', {})
            side_code = person.get('batSide', {}).get('code', 'R')
            hand_label = "LHB" if side_code == 'L' else ("SHB" if side_code == 'S' else "RHB")
            if p.get('position', {}).get('code') != '1':
                players.append({"name": person.get('fullName'), "hand": hand_label})
        return players
    except Exception:
        return []

# --- 3. MAIN DISPLAY LOGIC ---
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

opposing_team = st.selectbox("Select Opposing Team:", list(MLB_TEAM_IDS.keys()))

if opposing_team:
    live_batters = get_live_team_roster(opposing_team)
    processed_rows = []
    
    for b in live_batters:
        processed_rows.append({
            "Batter Name": b['name'], "Hand": b['hand'], "BBE": 0, 
            "💥 SLAM Index": 0.0, "Brl %": 0, "HH %": 0, "GB %": 0
        })

    if processed_rows:
        df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
        st.dataframe(df_lineup.style.map(highlight_slam), use_container_width=True)
