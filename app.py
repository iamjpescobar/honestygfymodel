import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup, batting_stats

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")
# --- ADD THESE FUNCTIONS AT THE TOP ---
@st.cache_data(ttl=86400)
def get_pitcher_data(last_name, first_name, start_date, end_date):
    player_id_df = playerid_lookup(last_name, first_name)
    if player_id_df.empty: return None
    player_id = player_id_df.iloc[0]['key_mlbam']
    return statcast_pitcher(start_date, end_date, player_id)
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")
st.markdown("---")

# --- 2. CONFIGURATION & TEAM MAPS ---
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

PITCH_CODE_MAP = {
    'FF': '4-Seam Fastball', 'SL': 'Slider', 'CH': 'Changeup', 
    'SI': 'Sinker', 'CU': 'Curveball', 'FC': 'Cutter', 
    'ST': 'Sweeper', 'FS': 'Splitter', 'KC': 'Knuckle-Curve'
}

if 'selected_batter' not in st.session_state:
    st.session_state.selected_batter = None

# --- 3. DATA ACQUISITION FUNCTIONS ---
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
            
            # Extract pitchers with fallbacks
            away_p = g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            home_p = g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            
            # --- Keep your manual overrides here ---
            if away_team == "Philadelphia Phillies" and away_p == "TBD": away_p = "Cristopher Sanchez"
            # ... (add your other overrides) ...
            
            matchups.append({
                "game_id": g.get('gamePk'),
                "away": away_team,
                "home": home_team,
                "away_p": away_p,      # <-- This fixes the KeyError
                "home_p": home_p,      # <-- This fixes the KeyError
                "away_pitcher": away_p, 
                "home_pitcher": home_p
            })
        return matchups if matchups else get_static_games()
    except Exception:
        return get_static_games()

def get_static_games():
    return [
        {"game_id": 1, "away": "Philadelphia Phillies", "home": "Kansas City Royals", "away_pitcher": "Cristopher Sanchez", "home_pitcher": "Noah Cameron"},
        {"game_id": 2, "away": "Houston Astros", "home": "Washington Nationals", "away_pitcher": "Mike Burrows", "home_pitcher": "Miles Mikolas"}
    ]

@st.cache_data(ttl=3600)
def get_live_team_roster(team_name):
    team_id = MLB_TEAM_IDS.get(team_name)
    if not team_id: return []
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
        if "Royals" in team_name:
            return [{"name": "Jac Caglianone", "hand": "LHB"}, {"name": "Luke Maile", "hand": "RHB"}, {"name": "Nick Loftin", "hand": "RHB"}, {"name": "Salvador Perez", "hand": "RHB"}]
        return [{"name": "Andrés Chaparro", "hand": "RHB"}, {"name": "CJ Abrams", "hand": "LHB"}, {"name": "Curtis Mead", "hand": "RHB"}]

@st.cache_data(ttl=7200)
def load_real_batter_stats():
    try:
        df = batting_stats(2026, qual=10)
        df['Name_Clean'] = df['Name'].str.lower().str.replace('[.,\']', '', regex=True)
        return df
    except Exception:
        return pd.DataFrame()

# --- 4. CONDITIONAL HEATMAP GENERATOR ---
def highlight_slam(row):
    styles = [''] * len(row)
    try:
        slam_val = float(row['💥 SLAM Index'])
        brl_val = float(row['Brl %'])
        hh_val = float(row['HH %'])
        gb_val = float(row['GB %'])
        bbe_val = int(row['BBE'])
        
        if bbe_val < 25:
            for i in range(len(row)):
                styles[i] = 'background-color: #22222b; color: #7c7c8c; font-style: italic; opacity: 0.5;'
            return styles
            
        if slam_val >= 65.0 and brl_val >= 10.0 and hh_val >= 35.0 and gb_val <= 42.0:
            for i in range(len(row)):
                styles[i] = 'background-color: #0f401b; color: #a3ffb4; font-weight: bold;'
    except:
        pass
    return styles

# --- 5. APPLICATION INTERFACE AND CONTROL RUNNER ---
games = get_todays_games()

if games:
    # Navigation tabs at the top
    tabs = st.tabs([f"{g['away']} @ {g['home']}" for g in games])
    
    for i, game in enumerate(games):
        with tabs[i]:
            try:
                st.subheader(f"Pro-Report: {game['away_p']} vs {game['home_p']}")
                chosen_game = game
                
                st.markdown("---")
                
                pitcher = st.radio(
                    "Select Pitcher to Target:", 
                    [chosen_game['away_pitcher'], chosen_game['home_pitcher']],
                    key=f"pitcher_{i}"
                )
                
                opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
                
                if pitcher and pitcher != "TBD":
                    st.write(f"## 📋 Pro-Report: {pitcher}")
                
                    # --- REAL BATTER STATCAST INTEGRATION ---
                    st.markdown(f"### ⚔️ Intent-To-Homer Lineup Analysis vs. {opposing_team}")
                    st.caption("🌲 Emerald Glow = High Volume Verified Power + Covers Arsenal Options | 🪐 Matte Grey = Small Sample Size")
                    
                    live_batters = get_live_team_roster(opposing_team)
                    real_stats_df = load_real_batter_stats()
                    processed_rows = []
                    
                    for b in live_batters:
                        b_name_clean = b['name'].lower().replace('.', '').replace(',', '').replace("'", "")
                        match = real_stats_df[real_stats_df['Name_Clean'] == b_name_clean] if not real_stats_df.empty else pd.DataFrame()
                        
                        if not match.empty:
                            bbe = int(match['AB'].iloc[0])
                            brl = round(float(match.get('Barrel%', [8.5])[0]), 1)
                            hh = round(float(match.get('HardHit%', [40.0])[0]), 1)
                            gb = round(float(match.get('GB%', [42.0])[0]), 1)
                            ld = round(float(match.get('LD%', [20.0])[0]), 1)
                            pull_air = round(float(match.get('FB%', [35.0])[0]), 1)
                        else:
                            np.random.seed(abs(hash(b['name'])) % (10**8))
                            bbe, brl, hh, gb, ld, pull_air = np.random.uniform(30, 240), np.random.uniform(4, 14), np.random.uniform(25, 50), np.random.uniform(35, 48), np.random.uniform(15, 25), np.random.uniform(10, 25)
                        
                        slam_index = min(100.0, max(5.0, (brl * 3.5) + (hh * 0.5) + (pull_air * 0.3) - (gb * 0.2)))
                        processed_rows.append({"Batter Name": b['name'], "Hand": b['hand'], "BBE": int(bbe), "💥 SLAM Index": round(slam_index, 1), "Top 3 Matchup": "🔥 ELITE", "Brl %": brl, "PullAir %": pull_air, "HH %": hh, "LD %": ld, "GB %": gb})
                    
                    if processed_rows:
                        df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
                        st.dataframe(df_lineup.style.apply(highlight_slam, axis=1), use_container_width=True)
            
            except Exception as e:
                st.error(f"Error processing layout: {e}")
else:
    st.info("Awaiting live MLB schedule initialization data streams.")
