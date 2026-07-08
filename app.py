import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pybaseball import statcast_pitcher, playerid_lookup, batting_stats

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")
st.markdown("---")

# --- 2. DATA FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_games_by_date(date_str):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games_list = response.get('dates', [{}])[0].get('games', [])
        return [{"game_id": g['gamePk'], "away": g['teams']['away']['team']['name'], "home": g['teams']['home']['team']['name'], "away_pitcher": g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD'), "home_pitcher": g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')} for g in games_list]
    except: return []

@st.cache_data(ttl=3600)
def get_live_team_roster(team_name):
    return [{"name": "Sample Batter", "hand": "RHB"}] # Placeholder for your actual roster logic

@st.cache_data(ttl=7200)
def load_real_batter_stats():
    return pd.DataFrame() # Placeholder for your actual stats logic

def highlight_slam(row):
    styles = ['background-color: #121212; color: #E0E0E0;'] * len(row)
    try:
        if float(row['💥 SLAM Index']) >= 65.0: styles = ['background-color: #003366; color: #FFFFFF; font-weight: bold;'] * len(row)
    except: pass
    return styles

# --- 3. MAIN APP ---
with st.sidebar:
    st.markdown("## 📅 Matchup Slate")
    games = get_games_by_date(datetime.today().strftime('%Y-%m-%d'))
    if games:
        idx = st.selectbox("Select Matchup:", range(len(games)), format_func=lambda x: f"{games[x]['away']} @ {games[x]['home']}")
        chosen_game = games[idx]
        pitcher = st.radio("Target Pitcher:", [chosen_game['away_pitcher'], chosen_game['home_pitcher']])
    else: pitcher = None

if pitcher and pitcher != "TBD":
    st.write(f"## 📋 Pro-Report: {pitcher}")
    st.columns(4)[0].metric("SLAM Index", "66.0")
    st.markdown("---")

    try:
        # --- YOUR DATA PROCESSING LOGIC ---
        live_batters = get_live_team_roster("Toronto Blue Jays")
        processed_rows = []
        for b in live_batters:
            processed_rows.append({"Batter Name": b['name'], "Hand": b['hand'], "BBE": 50, "💥 SLAM Index": 66.0, "Brl %": 8.0, "HH %": 40.0, "GB %": 42.0})
        
        df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
        st.dataframe(df_lineup.style.apply(highlight_slam, axis=1), use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")
