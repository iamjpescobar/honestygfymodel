import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, batting_stats

# --- 1. CONFIG & TEAM MAPS ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

# --- 2. DATA ACQUISITION ---
@st.cache_data(ttl=3600)
def get_todays_games():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games_list = response.get('dates', [{}])[0].get('games', [])
        matchups = []
        for g in games_list:
            matchups.append({
                "away": g['teams']['away']['team']['name'],
                "home": g['teams']['home']['team']['name'],
                "away_p": g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD'),
                "home_p": g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            })
        return matchups
    except:
        return []

# --- 3. MAIN UI ---
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

games = get_todays_games()

if games:
    tabs = st.tabs([f"{g['away']} @ {g['home']}" for g in games])
    
    for i, game in enumerate(games):
        with tabs[i]:
            st.subheader(f"Pro-Report: {game['away_p']} vs {game['home_p']}")
            # PASTE YOUR ANALYTICAL LOGIC HERE
            # IMPORTANT: Search for .applymap and change it to .map
            st.info("Paste your analytical logic tables here.")
else:
    st.warning("No games found for today's slate.")
