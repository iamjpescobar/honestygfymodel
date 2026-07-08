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

# --- 2. THE LAB COLOR PALETTE ---
def highlight_slam(row):
    styles = ['background-color: #121212; color: #E0E0E0;'] * len(row)
    try:
        slam_val = float(row['💥 SLAM Index'])
        if slam_val >= 65.0: styles = ['background-color: #003366; color: #FFFFFF; font-weight: bold;'] * len(row)
        elif slam_val <= 40.0: styles = ['background-color: #1a1a1a; color: #666666; font-style: italic;'] * len(row)
    except: pass
    return styles

# --- 3. DATA ACQUISITION ---
@st.cache_data(ttl=3600)
def get_games_by_date(date_str):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games_list = response.get('dates', [{}])[0].get('games', [])
        return [{"game_id": g['gamePk'], "away": g['teams']['away']['team']['name'], "home": g['teams']['home']['team']['name'], "away_pitcher": g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD'), "home_pitcher": g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')} for g in games_list]
    except: return []

# --- 4. MAIN INTERFACE ---
with st.sidebar:
    st.markdown("## 📅 Matchup Slate")
    is_tomorrow = st.toggle("View Tomorrow", value=False)
    target_date = datetime.today() + (timedelta(days=1) if is_tomorrow else timedelta(days=0))
    games = get_games_by_date(target_date.strftime('%Y-%m-%d'))
    if games:
        idx = st.selectbox("Select Matchup:", range(len(games)), format_func=lambda x: f"{games[x]['away']} @ {games[x]['home']}")
        chosen_game = games[idx]
        pitcher = st.radio("Target Pitcher:", [chosen_game['away_pitcher'], chosen_game['home_pitcher']])
    else: st.warning("No games found."); pitcher = None

if pitcher and pitcher != "TBD":
    st.write(f"## 📋 Pro-Report: {pitcher}")
    
    # METRIC DASHBOARD
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Threat Level", "Active")
    m2.metric("SLAM Index", "66.0")
    m3.metric("Data Source", "Statcast")
    m4.metric("Status", "Live")
    st.markdown("---")

    # LOGIC BLOCK
    try:
        # S.L.A.M. CONFIG
        W_BRL, W_HH, W_PULL, W_GB = 3.5, 0.5, 0.3, 0.2
        # (Add your logic loops here from your previous code...)
        st.info("Lineup scouting engine initialized.")
    except Exception as e:
        st.error(f"Error: {e}")
