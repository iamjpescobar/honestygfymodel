import streamlit as st
import pandas as pd
import requests
from datetime import datetime

from engines.roster import get_live_team_roster
from engines.batter_stats import load_batting_stats, get_batter_profile
from engines.slam_engine import compute_slam_index, random_match_tag

st.title("⚔️ Lineup SLAM Index Analysis")
st.markdown("---")

@st.cache_data(ttl=3600)
def get_todays_games():
    today = datetime.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games_list = response.get("dates", [{}])[0].get("games", [])
        matchups = []
        for g in games_list:
            matchups.append({
                "away": g["teams"]["away"]["team"]["name"],
                "home": g["teams"]["home"]["team"]["name"],
                "away_pitcher": g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD"),
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD"),
            })
        return matchups
    except:
        return []

games = get_todays_games()

if games:
    game_options = [f"{g['away']} @ {g['home']}" for g in games]
    selected_idx = st.selectbox("Select Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen = games[selected_idx]

    pitcher = st.radio("Select Pitcher:", [chosen["away_pitcher"], chosen["home_pitcher"]])

    opposing_team = chosen["home"] if pitcher == chosen["away_pitcher"] else chosen["away"]

    st.subheader(f"Lineup Analysis vs {opposing_team}")

    batters = get_live_team_roster(opposing_team)
    stats_df = load_batting_stats()

    rows = []
    for b in batters:
        prof = get_batter_profile(b["name"], stats_df)
        tag = random_match_tag(b["name"])
        slam = compute_slam_index(
            brl=prof["Brl %"],
            hh=prof["HH %"],
            pull_air=prof["PullAir %"],
            gb=prof["GB %"],
            bbe=prof["BBE"],
            matchup_tag=tag,
            affinity_mult=1.0
        )
        rows.append({
            "Batter": b["name"],
            "Hand": b["hand"],
            "SLAM": round(slam, 1),
            "Matchup": tag,
            "BBE": prof["BBE"],
            "Brl %": prof["Brl %"],
            "HH %": prof["HH %"],
            "GB %": prof["GB %"],
            "LD %": prof["LD %"],
            "PullAir %": prof["PullAir %"]
        })

    df = pd.DataFrame(rows).set_index("Batter")
    st.dataframe(df, use_container_width=True)
else:
    st.info("No games available.")

