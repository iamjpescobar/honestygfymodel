import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

def highlight_slam(row):
    styles = ['background-color: #121212; color: #E0E0E0;'] * len(row)
    try:
        if float(row['💥 SLAM Index']) >= 65.0: 
            styles = ['background-color: #003366; color: #FFFFFF; font-weight: bold;'] * len(row)
    except: pass
    return styles

# --- 2. DATA ACQUISITION FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_games_by_date(date_str):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=probablePitcher"
    try:
        r = requests.get(url).json()
        games = r.get('dates', [{}])[0].get('games', [])
        return [{"away": g['teams']['away']['team']['name'], "home": g['teams']['home']['team']['name'], 
                 "away_pitcher": g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD'),
                 "home_pitcher": g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')} for g in games]
    except: return []

# FIX: Define the missing function here!
def get_live_team_roster(team_name):
    # Add your roster-fetching logic here
    return [{"name": "Sample Batter", "hand": "RHB"}] 

def load_real_batter_stats():
    try:
        # 1. Fetch live roster and stats
        live_batters = get_live_team_roster(opposing_team)
        real_stats_df = load_real_batter_stats()
        processed_rows = []

        # 2. Process each batter through your custom SLAM formula
        for b in live_batters:
            b_name_clean = b['name'].lower().replace('.', '').replace(',', '').replace("'", "")
            match = real_stats_df[real_stats_df['Name_Clean'] == b_name_clean] if not real_stats_df.empty else pd.DataFrame()
            
            if not match.empty:
                bbe, brl, hh, gb, pull_air = int(match['AB'].iloc[0]), float(match['Barrel%'].iloc[0]), float(match['HardHit%'].iloc[0]), float(match['GB%'].iloc[0]), float(match['FB%'].iloc[0])
            else:
                bbe, brl, hh, gb, pull_air = 50, 8.0, 40.0, 42.0, 20.0
            
            # The S.L.A.M. Index Formula
            slam_index = min(100.0, max(5.0, (brl * 3.5) + (hh * 0.5) + (pull_air * 0.3) - (gb * 0.2)))
            
            processed_rows.append({
                "Batter Name": b['name'], "Hand": b['hand'], "BBE": bbe, 
                "💥 SLAM Index": round(slam_index, 1), "Brl %": brl, "HH %": hh, "GB %": gb
            })

        # 3. Render the dynamic grid
        df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
        st.dataframe(df_lineup.style.apply(highlight_slam, axis=1), use_container_width=True)
        
    except Exception as e:
        st.error(f"Engine Error: {e}")# Add your stats-loading logic here
    return pd.DataFrame()

# --- 3. UI LAYOUT ---
with st.sidebar:
    games = get_games_by_date(datetime.today().strftime('%Y-%m-%d'))
    if games:
        idx = st.selectbox("Select Matchup:", range(len(games)), format_func=lambda x: f"{games[x]['away']} @ {games[x]['home']}")
        chosen_game = games[idx]
        pitcher = st.radio("Target Pitcher:", [chosen_game['away_pitcher'], chosen_game['home_pitcher']])
        opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
    else: pitcher = None; opposing_team = None

if pitcher and pitcher != "TBD":
    st.write(f"## 📋 Pro-Report: {pitcher}")
    st.columns(4)[0].metric("SLAM Index", "66.0")
    st.markdown("---")

    try:
        # 1. Fetch data
        live_batters = get_live_team_roster(opposing_team)
        real_stats_df = load_real_batter_stats()
        
        # DIAGNOSTIC: Uncomment this line to see your data columns in the app
        # st.write("Available Columns:", real_stats_df.columns.tolist())
        
        processed_rows = []
        
        for b in live_batters:
            # Match the cleaning logic exactly to how you processed Name_Clean
            b_name_clean = b['name'].lower().replace('.', '').replace(',', '').replace("'", "")
            
            # Use .isin() to see if we have ANY match at all
            match = real_stats_df[real_stats_df['Name_Clean'] == b_name_clean]
            
            if not match.empty:
                # Use .get() to avoid KeyError if the column name is slightly different
                bbe = int(match['AB'].iloc[0])
                brl = float(match.get('Barrel%', 0).iloc[0])
                hh = float(match.get('HardHit%', 0).iloc[0])
                gb = float(match.get('GB%', 0).iloc[0])
                pull_air = float(match.get('FB%', 0).iloc[0])
                
                slam_index = min(100.0, max(5.0, (brl * W_BRL) + (hh * W_HH) + (pull_air * W_PULL) - (gb * W_GB)))
                
                processed_rows.append({
                    "Batter Name": b['name'], "Hand": b['hand'], "BBE": bbe, 
                    "💥 SLAM Index": round(slam_index, 1), "Brl %": brl, "HH %": hh, "GB %": gb
                })
            else:
                # Keep the sample data, but label it so you know it's a fallback
                processed_rows.append({
                    "Batter Name": f"{b['name']} (No Statcast)", "Hand": b['hand'], "BBE": 0, 
                    "💥 SLAM Index": 0.0, "Brl %": 0.0, "HH %": 0.0, "GB %": 0.0
                })
        
        df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
        st.dataframe(df_lineup.style.apply(highlight_slam, axis=1), use_container_width=True)
                
    except Exception as e:
        st.error(f"Engine Error: {e}")
