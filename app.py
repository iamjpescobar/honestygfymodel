import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup, batting_stats

# --- CONFIG & HELPERS ---
MLB_TEAM_IDS = {"Philadelphia Phillies": 143, "Kansas City Royals": 118, "Houston Astros": 117, "Washington Nationals": 120} # ... add your full map
PITCH_CODE_MAP = {'FF': '4-Seam Fastball', 'SL': 'Slider', 'CH': 'Changeup'} # ... add your full map

# --- DATA FETCHING (Defined early to prevent NameError) ---
@st.cache_data(ttl=3600)
def get_todays_games():
    # Use .get() to avoid KeyError if 'probablePitcher' is missing
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        data = requests.get(url).json()
        games = data.get('dates', [{}])[0].get('games', [])
        results = []
        for g in games:
            away = g['teams']['away']['team']['name']
            home = g['teams']['home']['team']['name']
            # Safety: use .get() to prevent KeyError
            away_p = g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            home_p = g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            results.append({"away": away, "home": home, "away_p": away_p, "home_p": home_p})
        return results
    except:
        return []

# --- MAIN INTERFACE ---
st.title("Los Cappers Lab 🧪")
games = get_todays_games()

if games:
    # 1. Selection logic
    game_options = [f"{g['away']} @ {g['home']}" for g in games]
    sel = st.sidebar.selectbox("Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen = games[sel]
    
    # 2. Header (The Pro-Report)
    st.subheader(f"Pro-Report: {chosen['away_p']} vs {chosen['home_p']}")
    
    # 3. Rest of your features (Pitcher data, then Lineup analysis)
    # Paste your existing code blocks here
else:
    st.info("Loading schedule...")
