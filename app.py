import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup

st.set_page_config(layout="wide")
st.title("⚾ My Free PropFinder Dashboard")
st.subheader("Automated Matchups, Pitch Mixes, & Weak Spots")

# 1. FETCH TODAY'S MATCHUPS (FREE MLB API)
@st.cache_data(ttl=3600)  # Refreshes every hour automatically
def get_todays_games():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}"
    try:
        response = requests.get(url).json()
        games = response.get('dates', [{}])[0].get('games', [])
        
        matchups = []
        for game in games:
            matchups.append({
                "game_id": game['gamePk'],
                "away": game['teams']['away']['team']['name'],
                "home": game['teams']['home']['team']['name'],
                "away_pitcher": game['teams']['away'].get('probablePitcher', {}).get('name', 'TBD'),
                "home_pitcher": game['teams']['home'].get('probablePitcher', {}).get('name', 'TBD')
            })
        return matchups
    except:
        return []

games = get_todays_games()

if not games:
    st.warning("No games found for today or MLB API is down.")
else:
    # Matchup Selection Box
    game_options = [f"{g['away']} @ {g['home']} | Pitchers: {g['away_pitcher']} vs {g['home_pitcher']}" for g in games]
    selected_game_idx = st.selectbox("Select Today's Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    
    chosen_game = games[selected_game_idx]
    
    # Select which pitcher you want to target for prop finding
    pitcher_to_analyze = st.radio("Select Pitcher to Target:", [chosen_game['away_pitcher'], chosen_game['home_pitcher']])
    
    if pitcher_to_analyze == "TBD":
        st.info("Pitcher is currently To Be Determined. Choose a different game.")
    else:
        st.write(f"### Analyzing Target: **{pitcher_to_analyze}**")
        
        # 2. PULL STATCAST PITCH MIX & WEAK SPOTS (FREE PYBASEBALL)
        with st.spinner("Crunching Statcast data for free..."):
            try:
                # Split first and last name for lookup
                names = pitcher_to_analyze.split(" ")
                first, last = names[0], names[-1]
                
                # Get MLB Player ID
                id_df = playerid_lookup(last, first)
                if not id_df.empty:
                    pitcher_id = id_df.iloc[0]['key_mlbam']
                    
                    # Fetch Statcast data from the current trailing season range
                    # (Adjust dates dynamically for your live testing)
                    data = statcast_pitcher('2026-04-01', '2026-10-01', pitcher_id)
                    
                    if not data.empty:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("#### 📊 Current Pitch Mix %")
                            pitch_counts = data['pitch_type'].value_counts(normalize=True) * 100
                            st.dataframe(pitch_counts.rename("Mix %"))
                        
                        with col2:
                            st.markdown("#### 🎯 Pitcher Weak Spots (Hard Hit Pitches)")
                            # Filter pitches hit hard (Launch speed over 95 MPH)
                            hard_hits = data[data['launch_speed'] > 95]
                            weak_pitches = hard_hits['pitch_type'].value_counts(normalize=True) * 100
                            st.write("Pitches giving up the most hard-hit contact:")
                            st.dataframe(weak_pitches.rename("Hard Hit Share %"))
                    else:
                        st.error("No recent Statcast data found for this player.")
                else:
                    st.error("Could not locate Player ID.")
            except Exception as e:
                st.error(f"Error compiling data: {e}")
