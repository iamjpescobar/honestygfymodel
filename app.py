import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide")

st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")
st.markdown("---")

# --- 2. CONFIGURATION & MAPS ---
MLB_TEAM_IDS = {
    "Arizona Diamondbacks": 109, "Atlanta Braves": 144, "Baltimore Orioles": 110,
    "Boston Red Sox": 111, "Chicago Cubs": 112, "Chicago White Sox": 145,
    "Cincinnati Reds": 113, "Cleveland Guardians": 114, "Colorado Rockies": 115,
    "Detroit Tigers": 116, "Houston Astros": 117, "Kansas City Royals": 118,
    "Los Angeles Angels": 108, "Los Angeles Dodgers": 119, "Miami Marlins": 146,
    "Milwaukee Brewers": 158, "Minnesota Twins": 142, "New York Mets": 121,
    "New York Yankees": 147, "Athletics": 133, "Philadelphia Phillies": 143,
    "Pittsburgh Pirates": 134, "San Diego Padres": 135, "San Francisco Giants": 137,
    "Seattle Mariners": 136, "St. Louis Cardinals": 138, "Tampa Bay Rays": 139,
    "Texas Rangers": 140, "Toronto Blue Jays": 141, "Washington Nationals": 120
}

PITCH_CODE_MAP = {
    'FF': '4-Seam Fastball', 'SL': 'Slider', 'CH': 'Changeup', 
    'SI': 'Sinker', 'CU': 'Curveball', 'FC': 'Cutter', 
    'ST': 'Sweeper', 'FS': 'Splitter', 'KC': 'Knuckle-Curve'
}

# --- 3. PERSISTENT STATE MANAGEMENT FOR DRILL-DOWN ---
if 'selected_batter' not in st.session_state:
    st.session_state.selected_batter = None

# --- 4. DATA FETCHING FUNCTIONS ---
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
            away_p = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            home_p = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            
            if away_team == "Philadelphia Phillies" and away_p == "TBD": away_p = "Cristopher Sanchez"
            if home_team == "Kansas City Royals" and home_p == "TBD": home_p = "Noah Cameron"
            if away_team == "New York Yankees" and away_p == "TBD": away_p = "Cam Schlittler"
            if home_team == "Tampa Bay Rays" and home_p == "TBD": home_p = "Griffin Jax"
                
            matchups.append({
                "game_id": game['gamePk'], "away": away_team, "home": home_team,
                "away_pitcher": away_p, "home_pitcher": home_p
            })
        return matchups
    except Exception:
        return []

@st.cache_data(ttl=300)
def get_live_team_roster(team_name):
    team_id = MLB_TEAM_IDS.get(team_name)
    if not team_id:
        return []
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    try:
        response = requests.get(url).json()
        roster = response.get('roster', [])
        players = []
        for p in roster:
            person = p.get('person', {})
            pos = p.get('position', {})
            if pos.get('code') != '1' and person.get('fullName'):
                players.append({
                    "name": person['fullName'],
                    "hand": "LHB" if person.get('batSide', {}).get('code') == 'L' else "RHB"
                })
        return players
    except Exception:
        return []

# --- 5. CONDITIONAL VISUAL HEATMAP ENGINE ---
def highlight_slam(row):
    styles = [''] * len(row)
    try:
        slam_val = float(row['💥 SLAM Index'])
        brl_val = float(row['Brl %'])
        hh_val = float(row['HH %'])
        gb_val = float(row['GB %'])
        bbe_val = int(row['BBE'])
        match_val = row['Top 3 Matchup']
        
        if bbe_val < 45:
            for i in range(len(row)):
                styles[i] = 'background-color: #22222b; color: #7c7c8c; font-style: italic; opacity: 0.5;'
            return styles
            
        if slam_val >= 75.0 and brl_val >= 10.0 and hh_val >= 35.0 and gb_val <= 35.0 and match_val == "🔥 ELITE":
            for i in range(len(row)):
                styles[i] = 'background-color: #0f401b; color: #a3ffb4; font-weight: bold; border: 2px solid #a3ffb4;'
        elif slam_val >= 70.0 and brl_val >= 10.0 and gb_val <= 35.0:
            for i in range(len(row)):
                styles[i] = 'background-color: #1b4d22; color: #deff9a; font-weight: bold;'
        elif slam_val < 45.0 or brl_val < 10.0 or gb_val > 42.0:
            for i in range(len(row)):
                styles[i] = 'background-color: #3d1414; color: #ffb3b3; opacity: 0.7;'
    except:
        pass
    return styles

# --- 6. CORE LOGIC EXECUTION ENGINE ---
games = get_todays_games()

if games:
    game_options = [f"{g['away']} ({g['away_pitcher']}) @ {g['home']} ({g['home_pitcher']})" for g in games]
    selected_idx = st.selectbox("Select Today's Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen_game = games[selected_idx]
    
    pitcher = st.radio("Select Pitcher to Target:",
