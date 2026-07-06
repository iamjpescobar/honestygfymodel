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
            
            if away_team == "Philadelphia Phillies" and away_p == "TBD": away_p = "Cristopher Sanchez"
            if home_team == "Kansas City Royals" and home_p == "TBD": home_p = "Noah Cameron"
            if away_team == "Houston Astros" and away_p == "TBD": away_p = "Mike Burrows"
            if home_team == "Washington Nationals" and home_p == "TBD": home_p = "Miles Mikolas"
                
            matchups.append({
                "game_id": g['gamePk'], "away": away_team, "home": home_team,
                "away_pitcher": away_p, "home_pitcher": home_p
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

# --- 4. CONDITIONAL HEATMAP GENERATORS ---
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

def highlight_pitcher_matrix(df):
    """Applies a sportsbook-style color grid map dynamically across all sabermetric rows."""
    styled_df = df.copy()
    
    # Helper to clean strings into floats safely
    def to_num(val):
        if isinstance(val, str):
            return float(val.replace('%', ''))
        return float(val)

    # Styling template strings
    green_style = 'background-color: #0f401b; color: #a3ffb4; font-weight: bold;' # Dominant Pitching
    red_style = 'background-color: #5c1414; color: #ffb3b3; font-weight: bold;'   # Vulnerable Pitching (Great for Overs)
    neutral_style = ''

    # Create style matching grid array layout
    style_array = pd.DataFrame('', index=df.index, columns=df.columns)

    for col in df.columns:
        for idx in df.index:
            try:
                val = to_num(df.loc[idx, col])
                
                # Category Group 1: Hitters Dream / Pitcher Vulnerability (Higher = Worse Pitcher)
                if col in ['ERA', 'xERA', 'wOBA', 'SLG', 'ISO', 'WHIP', 'HR/9', 'MEATBALL%', 'BARREL%', 'HH%', 'PULLAIR%']:
                    if col in ['ERA', 'xERA'] and val >= 3.80: style_array.loc[idx, col] = red_style
                    elif col in ['ERA', 'xERA'] and val <= 2.80: style_array.loc[idx, col] = green_style
                    elif col == 'wOBA' and val >= .290: style_array.loc[idx, col] = red_style
                    elif col == 'wOBA' and val <= .210: style_array.loc[idx, col] = green_style
                    elif col == 'BARREL%' and val >= 9.0: style_array.loc[idx, col] = red_style
                    elif col == 'BARREL%' and val <= 5.0: style_array.loc[idx, col] = green_style
                    elif col == 'HH%' and val >= 44.0: style_array.loc[idx, col] = red_style
                    elif col == 'HH%' and val <= 36.0: style_array.loc[idx, col] = green_style
                    elif col == 'MEATBALL%' and val >= 7.5: style_array.loc[idx, col] = red_style
                    elif col == 'MEATBALL%' and val <= 5.8: style_array.loc[idx, col] = green_style

                # Category Group 2: Whiff/Dominance Production (Higher = Better Pitcher)
                elif col in ['K%', 'BB%', 'WHIFF%', 'PUTAWAY%', 'SWSTR%', 'K/9', '1STP S%']:
                    if col == 'K%' and val >= 30.0: style_array.loc[idx, col] = green_style
                    elif col == 'K%' and val <= 23.0: style_array.loc[idx, col] = red_style
                    elif col == 'WHIFF%' and val >= 31.5: style_array.loc[idx, col] = green_style
                    elif col == 'WHIFF%' and val <= 25.0: style_array.loc[idx, col] = red_style
                    elif col == 'SWSTR%' and val >= 15.5: style_array.loc[idx, col] = green_style
                    elif col == 'SWSTR%' and val <= 11.0: style_array.loc[idx, col] = red_style
                    elif col == 'BB%' and val >= 6.5: style_array.loc[idx, col] = red_style  # High walks = bad pitcher
                    elif col == 'BB%' and val <= 3.0: style_array.loc[idx, col] = green_style # Low walks = good pitcher

            except Exception:
                pass
                
    return style_array

# --- 5. APPLICATION INTERFACE AND CONTROL RUNNER ---
games = get_todays_games()

if games:
    with st.sidebar:
        st.markdown("## 📅 Matchup Slate")
        game_options = [f"{g['away']} @ {g['home']}" for g in games]
        selected_idx = st.selectbox(
            "Select Today's Matchup:", 
            range(len(game_options)), 
            format_func=lambda x: game_options[x]
        )
        chosen_game = games[selected_idx]
        
        st.markdown("---")
        
        pitcher = st.radio(
            "Select Pitcher to Target:", 
            [chosen_game['away_pitcher'], chosen_game['home_pitcher']]
        )
        
    opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
    
    if pitcher and pitcher != "TBD":
        st.write(f"## 📋 Pro-Report: {pitcher}")
        
        try:
            clean_name = pitcher.encode('ascii', 'ignore').decode('utf-8').replace('.', '').replace(',', '')
            names = clean_name.split(" ")
            first, last = names[0], names[-1]
            if "Cristopher" in pitcher: first, last = "Cristopher", "Sanchez"
            
            id_df = playerid_lookup(last, first)
            pitcher_data = pd.DataFrame()
            
            matrix_rows = []
            splits = ["Season", "vs LHB", "vs RHB"]
            
            base_data = {
                "Season": {"IP": 117.0, "BF": 474, "ERA": 3.40, "xERA": 3.32, "wOBA": .265, "SLG": .333, "ISO": .100, "WHIP": 1.09, "HR": 8, "HR/9": 0.62, "BB%": "4.9%", "WHIFF%": "32.2%", "K%": "28.5%", "PUTAWAY%": "27.2%", "SWSTR%": "16.5%", "K/9": 10.38, "1STP S%": "66.9%", "MEATBALL%": "6.2%", "BARREL%": "8.3%", "HH%": "43.0%", "FB%": "17.5%", "HR/FB%": "14.5%", "PULLAIR%": "13.1%"},
                "vs LHB": {"IP": 31.1, "BF": 112, "ERA": 2.14, "xERA": 2.15, "wOBA": .154, "SLG": .191, "ISO": .045, "WHIP": 0.57, "HR": 1, "HR/9": 0.29, "BB%": "1.8%", "WHIFF%": "32.0%", "K%": "36.6%", "PUTAWAY%": "38.7%", "SWSTR%": "18.0%", "K/9": 11.78, "1STP S%": "73.2%", "MEATBALL%": "8.7%", "BARREL%": "4.3%", "HH%": "34.8%", "FB%": "15.9%", "HR/FB%": "9.1%", "PULLAIR%": "7.2%"},
                "vs RHB": {"IP": 84.2, "BF": 362, "ERA": 3.84, "xERA": 3.76, "wOBA": .299, "SLG": .379, "ISO": .118, "WHIP": 1.29, "HR": 7, "
