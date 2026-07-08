import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pybaseball import batting_stats

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

if 'chosen_game' not in st.session_state: st.session_state.chosen_game = None
if 'pitcher' not in st.session_state: st.session_state.pitcher = None

# --- 3. DATA ACQUISITION FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_games_by_date(date_str):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games_list = response.get('dates', [{}])[0].get('games', [])
        matchups = []
        for g in games_list:
            away_team = g['teams']['away']['team']['name']
            home_team = g['teams']['home']['team']['name']
            away_p = g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            home_p = g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            matchups.append({"game_id": g['gamePk'], "away": away_team, "home": home_team, "away_pitcher": away_p, "home_pitcher": home_p})
        return matchups if matchups else []
    except Exception: return []

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
            if p.get('position', {}).get('code') != '1' and person.get('fullName'):
                players.append({"name": person['fullName'], "hand": "LHB" if person.get('batSide', {}).get('code') == 'L' else "RHB"})
        return players
    except Exception: return []

@st.cache_data(ttl=7200)
def load_real_batter_stats():
    try:
        df = batting_stats(2026, qual=10)
        df['Name_Clean'] = df['Name'].str.lower().str.replace('[.,\']', '', regex=True)
        return df
    except Exception: return pd.DataFrame()

# --- 4. APPLICATION INTERFACE ---
with st.sidebar:
    st.markdown("## 📅 Matchup Slate")
    is_tomorrow = st.toggle("View Tomorrow's Games", value=False)
    target_date = datetime.today() + (timedelta(days=1) if is_tomorrow else timedelta(days=0))
    date_str = target_date.strftime('%Y-%m-%d')
    games = get_games_by_date(date_str)
    if games:
        selected_idx = st.selectbox("Select Matchup:", range(len(games)), format_func=lambda x: f"{games[x]['away']} @ {games[x]['home']}")
        st.session_state.chosen_game = games[selected_idx]
        st.session_state.pitcher = st.radio("Select Pitcher:", [st.session_state.chosen_game['away_pitcher'], st.session_state.chosen_game['home_pitcher']])

if st.session_state.chosen_game and st.session_state.pitcher:
    chosen_game = st.session_state.chosen_game
    pitcher = st.session_state.pitcher
    opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
    st.write(f"## 📋 Pro-Report: {pitcher}")
    
    try:
