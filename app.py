import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup, batting_stats

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The  S.L.A.M. Lab")
st.markdown("---")

# --- 2. CONFIGURATION & DATA FUNCTIONS ---
MLB_TEAM_IDS = {
    "Philadelphia Phillies": 143, "Kansas City Royals": 118, 
    "Houston Astros": 117, "Washington Nationals": 120
}

@st.cache_data(ttl=3600)
def get_todays_games():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games_list = response.get('dates', [{}])[0].get('games', [])
        return [{"game_id": g['gamePk'], "away": g['teams']['away']['team']['name'], 
                 "home": g['teams']['home']['team']['name'], 
                 "away_pitcher": g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD'),
                 "home_pitcher": g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')} 
                for g in games_list]
    except:
        return [{"game_id": 1, "away": "Philadelphia Phillies", "home": "Kansas City Royals", "away_pitcher": "Cristopher Sanchez", "home_pitcher": "Noah Cameron"}]

# --- 3. APP RUNNER ---
games = get_todays_games()

if games:
    with st.sidebar:
        game_options = [f"{g['away']} @ {g['home']}" for g in games]
        selected_idx = st.selectbox("Select Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
        chosen_game = games[selected_idx]
        pitcher = st.radio("Select Pitcher:", [chosen_game['away_pitcher'], chosen_game['home_pitcher']])

    if pitcher != "TBD":
        st.write(f"## 📋 Pro-Report: {pitcher}")
        opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
        
        # --- NEW: SMART FORECAST SECTION ---
        st.markdown(f"### 🏆 Top 3 S.L.A.M. Forecast vs {opposing_team}")
        
        # This is where we create the dummy data for the demo
        # (In your real app, this pulls from your 'processed_rows' logic)
        mock_forecast = [
            {"Name": "Batter A", "SLAM": 88.2},
            {"Name": "Batter B", "SLAM": 82.5},
            {"Name": "Batter C", "SLAM": 79.1}
        ]
        
        cols = st.columns(3)
        for i, hitter in enumerate(mock_forecast):
            with cols[i]:
                st.metric(hitter['Name'], f"{hitter['SLAM']}")
        
        st.markdown("---")
        st.info("The rest of your dashboard will appear here.")
else:
    st.info("Awaiting live MLB data.")
