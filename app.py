import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, batting_stats

# --- 1. CONFIG & TEAM MAPS ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

# --- 2. DATA ACQUISITION ---
@st.cache_data(ttl=3600)
def get_todays_games():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games_list = response.get('dates', [{}])[0].get('games', [])
        matchups = []
        for g in games_list:
            matchups.append({
                "away": g['teams']['away']['team']['name'],
                "home": g['teams']['home']['team']['name'],
                "away_p": g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD'),
                "home_p": g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            })
        return matchups
    except:
        return []

# --- 3. MAIN UI ---
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

games = get_todays_games()

if games:
    tabs = st.tabs([f"{g['away']} @ {g['home']}" for g in games])
    
    for i, game in enumerate(games):
        with tabs[i]:
            st.subheader(f"Pro-Report: {game['away_p']} vs {game['home_p']}")
            # PASTE YOUR ANALYTICAL LOGIC HERE
            # IMPORTANT: Search for .applymap and change it to .map
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
    if not team_id: return []
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    try:
        response = requests.get(url).json()
        players = []
        for p in response.get('roster', []):
            person = p.get('person', {})
            side_code = person.get('batSide', {}).get('code', 'R')
            # Proper hand mapping
            hand_label = "LHB" if side_code == 'L' else ("SHB" if side_code == 'S' else "RHB")
            if p.get('position', {}).get('code') != '1':
                players.append({"name": person.get('fullName'), "hand": hand_label})
        return players
    except Exception as e:
        st.error(f"Error: {e}")
        return []

# --- 2. CORRECTED LINEUP PROCESSING ---
live_batters = get_live_team_roster(opposing_team)
processed_rows = []
for b in live_batters:
    # ... (your logic for bbe, brl, hh, etc.) ...
    processed_rows.append({
        "Batter Name": b['name'], "Hand": b['hand'], "BBE": bbe, 
        "💥 SLAM Index": round(slam_index, 1), "Brl %": brl, 
        "HH %": hh, "GB %": gb
    })

# Convert list to DataFrame BEFORE applying styles
if processed_rows:
    df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
   if processed_rows:
    df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
    # Apply styling to the DataFrame
    styled_df = df_lineup.style.map(highlight_slam)
    st.dataframe(styled_df, use_container_width=True)
                df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")
                
                selected_scout = st.selectbox(
                    "🔍 Click to inspect detailed historical performance breakdown:",
                    ["-- Active Lineup Roster Overview --"] + list(df_lineup.index)
                )
                
                if selected_scout != "-- Active Lineup Roster Overview --":
                    st.session_state.selected_batter = selected_scout
                else:
                    st.session_state.selected_batter = None
                    
                if st.session_state.selected_batter:
                    sb = st.session_state.selected_batter
                    if sb in df_lineup.index:
                        stats = df_lineup.loc[sb]
                        st.markdown(f"#### 📊 Detailed Scout Matrix: {sb}")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Calculated SLAM Rating", f"{stats['💥 SLAM Index']}")
                        c2.metric("Barrel Execution Rate", f"{stats['Brl %']}%")
                        c3.metric("Hard Hit Metric", f"{stats['HH %']}%")
                        c4.metric("Total BBE Sample Size", f"{stats['BBE']}")
                        st.markdown("---")
                
                styled_df = df_lineup.style.format({
                    "BBE": "{:d}", "💥 SLAM Index": "{:.1f}", "Brl %": "{:.1f}%", 
                    "PullAir %": "{:.1f}%", "HH %": "{:.1f}%", "LD %": "{:.1f}%", "GB %": "{:.1f}%"
                }).apply(highlight_slam, axis=1)
                
                st.dataframe(styled_df, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error processing layout configurations: {e}")
else:
    st.info("Awaiting live MLB schedule initialization data streams.")
    st.warning("No games found for today's slate.")
