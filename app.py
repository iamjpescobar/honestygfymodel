import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pybaseball import batting_stats

# --- 1. CONFIG ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

MLB_TEAM_IDS = {"Toronto Blue Jays": 141, "San Francisco Giants": 137, "Los Angeles Dodgers": 119}

# --- 2. DATA FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_live_team_roster(team_name):
    tid = MLB_TEAM_IDS.get(team_name, 141)
    url = f"https://statsapi.mlb.com/api/v1/teams/{tid}/roster?rosterType=active"
    try:
        data = requests.get(url).json()
        return [{"name": p['person']['fullName'], "hand": "LHB" if p['person'].get('batSide', {}).get('code') == 'L' else "RHB"} for p in data.get('roster', [])]
    except: return []

@st.cache_data(ttl=86400)
def load_stats():
    try:
        df = batting_stats(2026, qual=10)
        df['Name_Clean'] = df['Name'].str.lower().str.replace('[.,\']', '', regex=True)
        return df
    except: 
        # Return empty DF with correct columns so code doesn't break
        return pd.DataFrame(columns=['Name_Clean', 'Barrel%', 'HardHit%', 'GB%', 'FB%', 'AB'])

# --- 3. UI & LOGIC ---
games = [{"away": "Toronto Blue Jays", "home": "San Francisco Giants"}]
selected_team = st.sidebar.selectbox("Select Matchup", [g['away'] + " @ " + g['home'] for g in games])
opposing_team = selected_team.split(" @ ")[1]

st.write(f"### ⚔️ Lineup Analysis: {opposing_team}")

try:
    roster = get_live_team_roster(opposing_team)
    df_stats = load_stats()
    
    data_list = []
    for player in roster:
        name_clean = player['name'].lower().replace('.', '').replace(',', '').replace("'", "")
        match = df_stats[df_stats['Name_Clean'] == name_clean]
        
        # Use match if exists, else use hardcoded defaults
        if not match.empty:
            brl = float(match['Barrel%'].iloc[0])
            hh = float(match['HardHit%'].iloc[0])
            gb = float(match['GB%'].iloc[0])
            fb = float(match['FB%'].iloc[0])
        else:
            brl, hh, gb, fb = 8.0, 40.0, 42.0, 20.0
            
        slam = (brl * 3.5) + (hh * 0.5) + (fb * 0.3) - (gb * 0.2)
        
        data_list.append({
            "Batter Name": player['name'],
            "Hand": player['hand'],
            "💥 SLAM Index": round(slam, 1),
            "Brl %": brl,
            "HH %": hh
        })
        
    st.dataframe(pd.DataFrame(data_list).set_index("Batter Name"), use_container_width=True)

except Exception as e:
    st.error(f"Critical Engine Failure: {e}")
