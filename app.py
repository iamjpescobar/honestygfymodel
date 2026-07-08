import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pybaseball import batting_stats

# --- 1. CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

# --- 2. DATA FUNCTIONS (Defined once, cached) ---
@st.cache_data(ttl=3600)
def get_live_team_roster(team_name):
    # Mapping logic for team IDs
    team_ids = {"Toronto Blue Jays": 141, "San Francisco Giants": 137, "Los Angeles Dodgers": 119}
    tid = team_ids.get(team_name, 141)
    url = f"https://statsapi.mlb.com/api/v1/teams/{tid}/roster?rosterType=active"
    try:
        data = requests.get(url).json()
        return [{"name": p['person']['fullName'], "hand": "LHB" if p['person'].get('batSide', {}).get('code') == 'L' else "RHB"} for p in data.get('roster', [])]
    except: return []

@st.cache_data(ttl=86400)
def load_real_batter_stats():
    try:
        df = batting_stats(2026, qual=10)
        df['Name_Clean'] = df['Name'].str.lower().str.replace('[.,\']', '', regex=True)
        return df
    except: return pd.DataFrame()

# --- 3. UI LAYOUT ---
with st.sidebar:
    st.markdown("## 📅 Matchup Slate")
    # Simplify game fetching to avoid circular calls
    games = [{"away": "Toronto Blue Jays", "home": "San Francisco Giants", "away_pitcher": "Dylan Cease", "home_pitcher": "Logan Webb"}]
    selected = st.selectbox("Select Matchup:", range(len(games)), format_func=lambda i: f"{games[i]['away']} @ {games[i]['home']}")
    game = games[selected]
    pitcher = st.radio("Select Pitcher:", [game['away_pitcher'], game['home_pitcher']])
    opposing_team = game['home'] if pitcher == game['away_pitcher'] else game['away']

st.write(f"## 📋 Pro-Report: {pitcher}")

# --- 4. ENGINE (The try block) ---
try:
    # Use the functions defined above
    live_batters = get_live_team_roster(opposing_team)
    real_stats = load_real_batter_stats()
    
    processed = []
    for b in live_batters:
        name_clean = b['name'].lower().replace('.', '').replace(',', '').replace("'", "")
        match = real_stats[real_stats['Name_Clean'] == name_clean]
        
        # Calculate values safely
        brl = float(match['Barrel%'].iloc[0]) if not match.empty else 8.0
        hh = float(match['HardHit%'].iloc[0]) if not match.empty else 40.0
        
        processed.append({
            "Batter Name": b['name'], 
            "Hand": b['hand'], 
            "💥 SLAM Index": round((brl * 3.5) + (hh * 0.5), 1)
        })

    st.dataframe(pd.DataFrame(processed).set_index("Batter Name"), use_container_width=True)

except Exception as e:
    st.error(f"Engine Error: {e}")
