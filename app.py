import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup

# 🎨 CUSTOM STYLING - THE "CAPPERS TOUCH"
st.set_page_config(page_title="Los Cappers Lab 🧪", layout="wide")

st.markdown("""
    <style>
    /* Darken the overall app container */
    .stApp {
        background-color: #0e1117;
        color: #e0e0e0;
    }
    /* Add a premium feel to the dataframe/tables */
    [data-testid="stDataFrame"] {
        border: 1px solid #1f2937;
        border-radius: 10px;
    }
    /* Style the Headers */
    h1, h2, h3 {
        color: #a3ffb4 !important;
    }
    /* Enhance the Selectbox to look like a PropFinder ticker */
    div[data-testid="stSelectbox"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")
st.markdown("---")

# [Insert your existing MLB_TEAM_IDS and PITCH_CODE_MAP here]

@st.cache_data(ttl=60)
def get_todays_games():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games = response.get('dates', [{}])[0].get('games', [])
        matchups = []
        for game in games:
            away_team = game['teams']['away']['team']['name']
            home_team = game['teams']['home']['team']['name']
            # Making the dropdown feel like PF
            away_p = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            home_p = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            
            # (Your previous logic here...)
            matchups.append({
                "display": f"{away_team} ({away_p}) @ {home_team} ({home_p})",
                "away_pitcher": away_p, "home_pitcher": home_p, 
                "away": away_team, "home": home_team
            })
        return matchups
    except Exception: return []

# 🚀 IMPROVED SELECTBOX
games = get_todays_games()
if games:
    selected_game = st.selectbox(
        "Select Matchup (Pitcher vs Pitcher):", 
        options=games, 
        format_func=lambda x: x['display']
    )
    # The rest of your logic stays the same but now feels much cleaner!
