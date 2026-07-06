import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide")

# --- 📱 MOBILE VIEWPORT ZOOM RESPONSIVENESS FIX ---
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.4rem !important;
        padding-right: 0.4rem !important;
    }
    .stDataFrame div[data-testid="stTable"] {
        font-size: 11px !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 18px !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 11px !important;
    }
    div[data-testid="stRadio"] > label {
        font-size: 13px !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")
st.markdown("---")

# --- 2. CONFIGURATION REFERENCE TABLES ---
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

if 'selected_batter' not in st.session_state:
    st.session_state.selected_batter = None

# --- 3. DATA ACQUISITION PIPELINES ---
@st.cache_data(ttl=60)
def get_todays_games():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        dates = response.get('dates', [])
        if not dates:
            return get_backup_games()
        games_list = dates[0].get('games', [])
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
        return matchups if matchups else get_backup_games()
    except Exception:
        return get_backup_games()

def get_backup_games():
    return [
        {"game_id": 1, "away": "Philadelphia Phillies", "home": "Kansas City Royals", "away_pitcher": "Cristopher Sanchez", "home_pitcher": "Noah Cameron"},
        {"game_id": 2, "away": "Houston Astros", "home": "Washington Nationals", "away_pitcher": "Mike Burrows", "home_pitcher": "Miles Mikolas"}
    ]

@st.cache_data(ttl=300)
def get_live_team_roster(team_name):
    team_id = MLB_TEAM_IDS.get(team_name)
    if not team_id:
        return get_backup_roster(team_name)
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
        return players if players else get_backup_roster(team_name)
    except Exception:
        return get_backup_roster(team_name)

def get_backup_roster(team_name):
    if "Royals" in team_name:
        return [
            {"name": "Jac Caglianone", "hand": "LHB"}, {"name": "Luke Maile", "hand": "RHB"}, 
            {"name": "Nick Loftin", "hand": "RHB"}, {"name": "Salvador Perez", "hand": "RHB"},
            {"name": "Kameron Misner", "hand": "LHB"}, {"name": "Michael Massey", "hand": "LHB"}
        ]
    return [
        {"name": "Andrés Chaparro", "hand": "RHB"}, {"name": "CJ Abrams", "hand": "LHB"}, 
        {"name": "Curtis Mead", "hand": "RHB"}
    ]

# --- 4. CONDITIONAL HEATMAP MATRIX DEFINITIONS ---
def highlight_slam(row):
    styles = [''] * len(row)
    try:
        slam_val = float(row['💥 SLAM Index'])
        brl_val = float(row['Brl %'])
        hh_val = float(row['HH %'])
        gb_val = float(row['GB %'])
        bbe_val = int(row['BBE'])
        
        if bbe_val < 45:
            for i in range(len(row)):
                styles[i] = 'background-color: #22222b; color: #7c7c8c; font-style: italic; opacity: 0.5;'
            return styles
            
        if slam_val >= 70.0 and brl_val >= 10.0 and hh_val >= 35.0 and gb_val <= 35.0:
            for i in range(len(row)):
                styles[i] = 'background-color: #0f401b; color: #a3ffb4; font-weight: bold;'
        elif slam_val < 45.0 or brl_val < 7.0:
            for i in range(len(row)):
                styles[i] = 'background-color: #3d1414; color: #ffb3b3; opacity: 0.8;'
    except:
        pass
    return styles

# --- 5. APPLICATION RUNNER ---
games = get_todays_games()

if games:
    game_options = [f"{g['away']} ({g['away_pitcher']}) @ {g['home']} ({g['home_pitcher']})" for g in games]
    selected_idx = st.selectbox("Select Today's Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen_game = games[selected_idx]
    
    pitcher = st.radio("Select Pitcher to Target:", [chosen_game['away_pitcher'], chosen_game['home_pitcher']])
    opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
    
    if pitcher and pitcher != "TBD":
        st.write(f"## 📋 Pro-Report: {pitcher}")
        
        clean_name = pitcher.encode('ascii', 'ignore').decode('utf-8').replace('.', '').replace(',', '')
        names = clean_name.split(" ")
        first, last = names[0], names[-1]
        if "Cristopher" in pitcher: first, last = "Cristopher", "Sanchez"
        
        id_df = playerid_lookup(last, first)
        lhb_pitches, rhb_pitches, total_pitches = 0, 0, 0
        
        if not id_df.empty:
            try:
                pitcher_id = id_df.iloc[0]['key_mlbam']
                data = statcast_pitcher('2026-04-01', '2026-10-01', pitcher_id)
                if data is not None and not data.empty:
                    lhb_pitches =
