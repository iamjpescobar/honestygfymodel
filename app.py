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
        # 1. Fetch data
        live_batters = get_live_team_roster(opposing_team)
        real_stats_df = load_real_batter_stats()
        
        # 2. Safety: Create 'Name_Clean' if it's missing (Crucial Fix)
        if 'Name' in real_stats_df.columns and 'Name_Clean' not in real_stats_df.columns:
            real_stats_df['Name_Clean'] = real_stats_df['Name'].str.lower().str.replace('[.,\']', '', regex=True)

        processed_rows = []
        for b in live_batters:
            b_name_clean = b['name'].lower().replace('.', '').replace(',', '').replace("'", "")
            
            # Check if our cleaned name exists in the clean column
            match = real_stats_df[real_stats_df['Name_Clean'] == b_name_clean] if not real_stats_df.empty else pd.DataFrame()
            
            # Extract stats safely
            if not match.empty:
                # Use .get to prevent errors if a specific column is missing
                bbe = int(match['AB'].iloc[0]) if 'AB' in match.columns else 50
                brl = float(match['Barrel%'].iloc[0]) if 'Barrel%' in match.columns else 8.0
                hh = float(match['HardHit%'].iloc[0]) if 'HardHit%' in match.columns else 40.0
                gb = float(match['GB%'].iloc[0]) if 'GB%' in match.columns else 42.0
                pull_air = float(match['FB%'].iloc[0]) if 'FB%' in match.columns else 20.0
            else:
                bbe, brl, hh, gb, pull_air = 50, 8.0, 40.0, 42.0, 20.0
            
            slam_index = min(100.0, max(5.0, (brl * 3.5) + (hh * 0.5) + (pull_air * 0.3) - (gb * 0.2)))
            
            processed_rows.append({
                "Batter Name": b['name'], "Hand": b['hand'], "BBE": bbe, 
                "💥 SLAM Index": round(slam_index, 1), "Brl %": brl, "HH %": hh, "GB %": gb
            })

        df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
        st.dataframe(df_lineup.style.apply(highlight_slam, axis=1), use_container_width=True)
                
    except Exception as e:
        st.error(f"Engine Error: {e}")
