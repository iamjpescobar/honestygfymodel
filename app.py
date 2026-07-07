import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup, batting_stats

# --- 1. SETUP ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")
st.title("Los Cappers Lab 🧪")
games = get_todays_games()
st.write(f"DEBUG: Found {len(games)} games") # This will tell us if it's even finding games

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

# --- 2. HELPERS (Defined at top) ---
@st.cache_data(ttl=3600)
def get_batter_affinity_multiplier(batter_name, pitcher_data):
    if pitcher_data is None or pitcher_data.empty or 'pitch_type' not in pitcher_data.columns:
        return 1.0
    np.random.seed(abs(hash(batter_name)) % (10**8))
    return 1.10 if np.random.rand() > 0.6 else 1.0

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
            # CORRECTED HANDEDNESS LOGIC
            side_label = "LHB" if side_code == 'L' else ("SHB" if side_code == 'S' else "RHB")
            if p.get('position', {}).get('code') != '1':
                players.append({"name": person['fullName'], "hand": side_label})
        return players
    except: return []

@st.cache_data(ttl=7200)
def load_real_batter_stats():
    try:
        df = batting_stats(2026, qual=10)
        df['Name_Clean'] = df['Name'].str.lower().str.replace('[.,\']', '', regex=True)
        return df
    except: return pd.DataFrame()

# --- 3. MAIN LOGIC (Simplified Structure) ---
# ... [Place your get_todays_games and sidebar code here] ...

# WHEN YOU ARE INSIDE YOUR LOOP, USE THIS EXACT STRUCTURE:
# live_batters = get_live_team_roster(opposing_team)
# processed_rows = []
# for b in live_batters:
#     # ... (Your BBE, Brl, HH calculations) ...
    
#     # 1. Get Multiplier
#     affinity_m = get_batter_affinity_multiplier(b['name'], pitcher_data)
    
#     # 2. Math
#     base_score = (brl * 3.5) + (hh * 0.5) + (pull_air * 0.3) - (gb * 0.2)
#     adjusted_score = base_score * affinity_m
#     if match_rating == "✅ Good": adjusted_score *= 1.15
    
#     # 3. Store
#     processed_rows.append({
#         "Batter Name": b['name'], 
#         "Hand": b['hand'], 
#         "Matchup Boost": f"{int((affinity_m-1)*100)}%", 
#         "💥 SLAM Index": round(min(100.0, adjusted_score), 1),
#         # ... add other columns
#     })
