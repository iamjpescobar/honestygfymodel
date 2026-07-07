import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup, batting_stats

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

PITCH_CODE_MAP = {'FF': '4-Seam Fastball', 'SL': 'Slider', 'CH': 'Changeup', 'SI': 'Sinker', 'CU': 'Curveball', 'FC': 'Cutter', 'ST': 'Sweeper', 'FS': 'Splitter', 'KC': 'Knuckle-Curve'}

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
            away_team = g['teams']['away']['team']['name']
            home_team = g['teams']['home']['team']['name']
            away_p = g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            home_p = g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            matchups.append({"game_id": g['gamePk'], "away": away_team, "home": home_team, "away_p": away_p, "home_p": home_p})
        return matchups if matchups else [{"game_id": 1, "away": "Phillies", "home": "Royals", "away_p": "Cristopher Sanchez", "home_p": "Noah Cameron"}]
    except:
        return []

@st.cache_data(ttl=3600)
def get_live_team_roster(team_name):
    # (Keep your existing roster logic here)
    return [{"name": "Sample Player", "hand": "RHB"}]

@st.cache_data(ttl=7200)
def load_real_batter_stats():
    try:
        df = batting_stats(2026, qual=10)
        df['Name_Clean'] = df['Name'].str.lower().str.replace('[.,\']', '', regex=True)
        return df
    except:
        return pd.DataFrame()

# --- 3. MAIN UI ---
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

games = get_todays_games()

if games:
    tabs = st.tabs([f"{g['away']} @ {g['home']}" for g in games])
    
    for i, game in enumerate(games):
        with tabs[i]:
            st.subheader(f"Pro-Report: {game['away_p']} vs {game['home_p']}")
            # PASTE YOUR ANALYTICAL CODE HERE
            # REMEMBER: Change all .applymap(...) to .map(...)
            st.write("Analytics engine active.")
else:
    st.warning("No games found for today's slate.")
