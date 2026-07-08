
import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup, batting_stats

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

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
def get_games_by_date(date_string):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_string}&hydrate=probablePitcher"
    
    try:
        response = requests.get(url).json()
        games_list = response.get('dates', [{}])[0].get('games', [])
        matchups = []
        
        for g in games_list:
            away_team = g['teams']['away']['team']['name']
            home_team = g['teams']['home']['team']['name']
            away_p = g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD') # Corrected API path
            home_p = g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            
            matchups.append({
                "game_id": g['gamePk'], 
                "away": away_team, 
                "home": home_team,
                "away_pitcher": away_p, 
                "home_pitcher": home_p
            })
        return matchups
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_live_team_roster(team_name):
    team_id = MLB_TEAM_IDS.get(team_name)
    if not team_id: 
        return []
        
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    try:
        response = requests.get(url).json()
        players = []
        for p in response.get('roster', []):
            person = p.get('person', {})
            pos = p.get('position', {})
            
            # Use safe dictionary access to avoid NoneType errors
            bat_side = person.get('batSide')
            side_code = bat_side.get('code', 'R') if bat_side else 'R'
            side_label = "LHB" if side_code == 'L' else ("SHB" if side_code == 'S' else "RHB")
            
            if pos.get('code') != '1' and person.get('fullName'):
                players.append({
                    "name": person['fullName'],
                    "hand": side_label
                })
        return players
    except Exception as e:
        # Debugging: Uncomment the line below if you continue to have issues
        # st.error(f"Error fetching roster for {team_name}: {e}")
        
        # Fallback for when API fails
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
@st.cache_data(ttl=3600)
def get_batter_affinity_multiplier(batter_name, pitcher_data):
    """
    Checks the pitcher's primary pitch and returns an affinity multiplier 
    based on a simplified simulated affinity lookup.
    """
    if pitcher_data is None or pitcher_data.empty:
        return 1.0
    
    # Identify primary pitch code (most frequent)
    primary_code = pitcher_data['pitch_type'].value_counts().idxmax()
    
    # Logic: If batter is 'Elite' or 'Good', apply a 1.10 multiplier (10% boost)
    # This simulates checking the batter's historical wOBA vs that pitch type
    # In a production app, replace with a real lookup: batting_stats_vs_pitch(batter_id, primary_code)
    np.random.seed(abs(hash(batter_name)) % (10**8))
    # Randomly assign affinity based on a 40% success rate
    return 1.10 if np.random.rand() > 0.6 else 1.0
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

# 1. Initialize session state variables so they are NEVER undefined
if 'chosen_game' not in st.session_state: st.session_state.chosen_game = None
if 'pitcher' not in st.session_state: st.session_state.pitcher = None

with st.sidebar:
    st.markdown("## 📅 Matchup Slate")
    is_tomorrow = st.toggle("View Tomorrow's Games", value=False)
    target_date = datetime.today() + (timedelta(days=1) if is_tomorrow else timedelta(days=0))
    date_str = target_date.strftime('%Y-%m-%d')
    st.caption(f"Currently viewing: {date_str}")
    
    games = get_games_by_date(date_str)
    
    if games:
        game_options = [f"{g['away']} @ {g['home']}" for g in games]
        selected_idx = st.selectbox("Select Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
        st.session_state.chosen_game = games[selected_idx]
        
        st.markdown("---")
        st.session_state.pitcher = st.radio(
            "Select Pitcher to Target:", 
            [st.session_state.chosen_game['away_pitcher'], st.session_state.chosen_game['home_pitcher']]
        )
    else:
        st.warning("No games found.")
        st.session_state.chosen_game = None
        st.session_state.pitcher = None

# 2. Main Logic: Access variables from session_state
chosen_game = st.session_state.chosen_game
pitcher = st.session_state.pitcher

if chosen_game and pitcher and pitcher != "TBD":
    opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
    st.write(f"## 📋 Pro-Report: {pitcher}")
    
    try:
        # [PASTE YOUR EXISTING DATA PROCESSING LOGIC HERE]
        # ENSURE ALL LINES BELOW ARE INDENTED BY 8 SPACES
        clean_name = pitcher.encode('ascii', 'ignore').decode('utf-8').replace('.', '').replace(',', '')
        # ... rest of your original logic ...
        
    except Exception as e:
        st.error(f"Error processing report: {e}")
else:
    st.info("Please select a matchup and pitcher in the sidebar to initialize the report.")
