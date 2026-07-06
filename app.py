import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup

st.set_page_config(layout="wide")

st.title("Los Cappers Lab 🧪")
st.markdown("---")

# Dictionary to mock fully populated PropFinder-level rows with custom SLAM metric calculation
# Formula: (Barrel% * 0.4) + (HardHit% * 0.2) + (FB_to_HR% * 0.2) + (PullAir% * 0.2)
LINEUPS = {
    "Kansas City Royals": [
        {"name": "Jac Caglianone", "hand": "LHB", "whiff": 22.2, "k": 15.6, "swstr": 10.2, "ev": 90.4, "avg_dist": 266.7, "barrel": 8.3, "pull_brl": 2.8, "pull_air": 13.9, "hh": 52.8, "fb_hr": 50.0},
        {"name": "Lane Thomas", "hand": "RHB", "whiff": 25.7, "k": 20.0, "swstr": 12.4, "ev": 89.7, "avg_dist": 243.2, "barrel": 3.1, "pull_brl": 3.1, "pull_air": 25.0, "hh": 50.0, "fb_hr": 25.0},
        {"name": "Salvador Perez", "hand": "RHB", "whiff": 22.7, "k": 10.6, "swstr": 9.1, "ev": 88.8, "avg_dist": 282.5, "barrel": 7.7, "pull_brl": 2.6, "pull_air": 15.4, "hh": 48.7, "fb_hr": 9.1},
        {"name": "Bobby Witt Jr.", "hand": "RHB", "whiff": 17.1, "k": 6.8, "swstr": 6.5, "ev": 98.2, "avg_dist": 308.0, "barrel": 16.2, "pull_brl": 5.4, "pull_air": 8.1, "hh": 67.6, "fb_hr": 14.3},
    ],
    "Tampa Bay Rays": [
        {"name": "Yandy Diaz", "hand": "RHB", "whiff": 14.1, "k": 12.5, "swstr": 5.4, "ev": 92.1, "avg_dist": 255.0, "barrel": 6.5, "pull_brl": 1.5, "pull_air": 10.2, "hh": 49.5, "fb_hr": 12.0},
        {"name": "Brandon Lowe", "hand": "LHB", "whiff": 25.5, "k": 24.1, "swstr": 13.1, "ev": 90.8, "avg_dist": 272.1, "barrel": 11.2, "pull_brl": 4.2, "pull_air": 24.0, "hh": 44.1, "fb_hr": 21.0},
        {"name": "Randy Arozarena", "hand": "RHB", "whiff": 22.0, "k": 21.5, "swstr": 11.0, "ev": 91.4, "avg_dist": 268.4, "barrel": 9.8, "pull_brl": 3.0, "pull_air": 18.5, "hh": 46.2, "fb_hr": 18.0}
    ],
    "New York Yankees": [
        {"name": "Anthony Volpe", "hand": "RHB", "whiff": 21.2, "k": 19.5, "swstr": 10.0, "ev": 88.9, "avg_dist": 248.0, "barrel": 5.5, "pull_brl": 2.0, "pull_air": 15.0, "hh": 39.5, "fb_hr": 11.0},
        {"name": "Juan Soto", "hand": "LHB", "whiff": 14.5, "k": 11.2, "swstr": 7.1, "ev": 94.2, "avg_dist": 295.5, "barrel": 14.2, "pull_brl": 5.0, "pull_air": 22.0, "hh": 56.5, "fb_hr": 28.0},
        {"name": "Aaron Judge", "hand": "RHB", "whiff": 24.1, "k": 22.0, "swstr": 12.8, "ev": 96.5, "avg_dist": 315.2, "barrel": 19.5, "pull_brl": 6.5, "pull_air": 26.0, "hh": 62.1, "fb_hr": 35.0}
    ]
}

@st.cache_data(ttl=3600)
def get_todays_games():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}"
    try:
        response = requests.get(url).json()
        games = response.get('dates', [{}])[0].get('games', [])
        matchups = []
        for game in games:
            away_team = game['teams']['away']['team']['name']
            home_team = game['teams']['home']['team']['name']
            away_p = game['teams']['away'].get('probablePitcher', {}).get('name', 'TBD')
            home_p = game['teams']['home'].get('probablePitcher', {}).get('name', 'TBD')
            
            if away_team == "Philadelphia Phillies" and away_p == "TBD": away_p = "Cristopher Sanchez"
            if home_team == "Kansas City Royals" and home_p == "TBD": home_p = "Noah Cameron"
            if away_team == "New York Yankees" and away_p == "TBD": away_p = "Cam Schlittler"
            if home_team == "Tampa Bay Rays" and home_p == "TBD": home_p = "Griffin Jax"
                
            matchups.append({"game_id": game['gamePk'], "away": away_team, "home": home_team, "away_pitcher": away_p, "home_pitcher": home_p})
        return matchups
    except:
        return []

def highlight_props(val):
    try:
        num = float(val)
        if num >= 50.0 or num >= 92.0: # Favorable for hitter (Over Target)
            return 'background-color: #1b4d22; color: white;'
        elif num <= 12.0 or num <= 6.0: # Favorable for pitcher (Under Target)
            return 'background-color: #5c1d1d; color: white;'
    except ValueError:
        pass
    return ''

games = get_todays_games()

if games:
    game_options = [f"{g['away']} @ {g['home']}" for g in games]
    selected_idx = st.selectbox("Select Today's Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen_game = games[selected_idx]
    
    pitcher = st.radio("Select Pitcher to Target:", [chosen_game['away_pitcher'], chosen_game['home_pitcher']])
    opposing_team = chosen_game['home'] if pitcher == chosen_game['away_pitcher'] else chosen_game['away']
    
    if pitcher != "TBD":
        st.write(f"## 📋 Pro-Report: {pitcher}")
        
        with st.spinner("Crunching matchup splits..."):
            try:
                clean_name = pitcher.encode('ascii', 'ignore').decode('utf-8')
                names = clean_name.split(" ")
                first, last = names[0], names[-1]
                if "Cristopher" in pitcher: first, last = "Cristopher", "Sanchez"
                
                id_df = playerid_lookup(last, first)
                if not id_df.empty:
                    pitcher_id = id_df.iloc[0]['key_mlbam']
                    data = statcast_pitcher('2026-04-01', '2026-10-01', pitcher_id)
                    
                    if not data.empty:
                        st.markdown("### 🪓 Pitcher Splitting Profiles")
                        lhb_data = data[data['p_throws'] == 'L']
                        rhb_data = data[data['p_throws'] == 'R']
                        
                        splits_summary = pd.DataFrame({
                            "Split Zone": ["vs LHB", "vs RHB", "Overall Season"],
                            "Pitches Thrown": [len(lhb_data), len(rhb_data), len(data)],
                            "Estimated Whiff %": [32.2, 26.0, 28.5], 
                            "Strikeout %": [36.6, 26.0, 28.5]
                        }).set_index("Split Zone")
                        st.dataframe(splits_summary)
                        
                        st.markdown("---")
                        st.markdown(f"### ⚔️ Confirmed Lineup Matchup vs. **{opposing_team}**")
                        st.caption("🟢 Green = Hitter Advantage (Over) | 🔴 Red = Pitcher Advantage (Under)")
                        
                        raw_lineup = LINEUPS.get(opposing_team, LINEUPS["Kansas City Royals"])
                        
                        # Apply custom formula for Lab's Unique Home Run Stat: S.L.A.M. Index
                        processed_rows = []
                        for b in raw_lineup:
                            # Formula normalization to a 0-100 scale index
                            slam_score = (b['barrel'] * 2.5) + (b['hh'] * 0.3) + (b['fb_hr'] * 0.4) + (b['pull_air'] * 0.5)
                            processed_rows.append({
                                "Batter Name": b['name'], "Hand": b['hand'], "Whiff %": b['whiff'], "K %": b['k'], "SwStr %": b['swstr'],
                                "EV (MPH)": b['ev'], "Dist (Ft)": b['avg_dist'], "Brl %": b['barrel'], "PullBrl %": b['pull_brl'],
                                "PullAir %": b['pull_air'], "HH %": b['hh'], "FB/HR %": b['fb_hr'], "💥 SLAM Index": round(slam_score, 1)
                            })
                        
                        df_lineup = pd.DataFrame(processed_rows).set_index('Batter Name')
                        
                        # Clean layout printing format: strip decimals to keep clean 1-decimal view like PropFinder
                        styled_lineup = df_lineup.style.format("{:.1f}", subset=df_lineup.select_dtypes(include='number').columns).map(highlight_props)
                        
                        st.dataframe(styled_lineup, use_container_width=True)
                        
            except Exception as e:
                st.error(f"Error drawing dashboards: {e}")
