import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- ENGINE IMPORTS ---
from engines.roster import get_live_team_roster
from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)
from engines.batter_stats import (
    load_batting_stats,
    get_batter_profile
)
from engines.slam_engine import (
    compute_slam_index,
    random_match_tag
)

# --- 1. SET LAYOUT CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")
st.markdown("---")

if "selected_batter" not in st.session_state:
    st.session_state.selected_batter = None

# --- 2. GET TODAY'S GAMES ---
@st.cache_data(ttl=3600)
def get_todays_games():
    today = datetime.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"

    try:
        response = requests.get(url).json()
        games_list = response.get("dates", [{}])[0].get("games", [])
        matchups = []

        for g in games_list:
            away_team = g["teams"]["away"]["team"]["name"]
            home_team = g["teams"]["home"]["team"]["name"]
            away_p = g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD")
            home_p = g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD")

            matchups.append({
                "game_id": g["gamePk"],
                "away": away_team,
                "home": home_team,
                "away_pitcher": away_p,
                "home_pitcher": home_p,
            })

        return matchups

    except Exception:
        return []

games = get_todays_games()

# --- 3. SIDEBAR MATCHUP SELECTOR ---
if games:
    with st.sidebar:
        st.markdown("## 📅 Matchup Slate")
        game_options = [f"{g['away']} @ {g['home']}" for g in games]

        selected_idx = st.selectbox(
            "Select Today's Matchup:",
            range(len(game_options)),
            format_func=lambda x: game_options[x],
        )

        chosen_game = games[selected_idx]

        st.markdown("---")

        pitcher = st.radio(
            "Select Pitcher to Target:",
            [chosen_game["away_pitcher"], chosen_game["home_pitcher"]],
        )

    opposing_team = (
        chosen_game["home"]
        if pitcher == chosen_game["away_pitcher"]
        else chosen_game["away"]
    )

    # --- 4. PITCHER REPORT ---
    if pitcher and pitcher != "TBD":
        st.write(f"## 📋 Pro-Report: {pitcher}")

        pitcher_id = get_pitcher_id(pitcher)
        pitcher_data = get_pitcher_statcast(pitcher_id)

        # --- PITCH ARSENAL ---
        st.markdown("### 🎯 Verified Pitch Arsenal Distribution")
        arsenal_df = build_pitch_arsenal(pitcher_data)
        st.table(arsenal_df)

        # --- 5. BATTER LINEUP ANALYSIS ---
        st.markdown(f"### ⚔️ Intent-To-Homer Lineup Analysis vs. {opposing_team}")
        st.caption(
            "🌲 Emerald Glow = High Volume Verified Power + Covers Arsenal Options | "
            "🪐 Matte Grey = Small Sample Size"
        )

        live_batters = get_live_team_roster(opposing_team)
        real_stats_df = load_batting_stats()

        processed_rows = []

        for b in live_batters:
            prof = get_batter_profile(b["name"], real_stats_df)
            match_tag = random_match_tag(b["name"])

            slam_index = compute_slam_index(
                brl=prof["Brl %"],
                hh=prof["HH %"],
                pull_air=prof["PullAir %"],
                gb=prof["GB %"],
                bbe=prof["BBE"],
                matchup_tag=match_tag,
                affinity_mult=1.0,
            )

            processed_rows.append({
                "Batter Name": b["name"],
                "Hand": b["hand"],
                "BBE": prof["BBE"],
                "💥 SLAM Index": round(slam_index, 1),
                "Top 3 Matchup": match_tag,
                "Brl %": prof["Brl %"],
                "PullAir %": prof["PullAir %"],
                "HH %": prof["HH %"],
                "LD %": prof["LD %"],
                "GB %": prof["GB %"],
            })

        if processed_rows:
            df_lineup = pd.DataFrame(processed_rows).set_index("Batter Name")

            selected_scout = st.selectbox(
                "🔍 Click to inspect detailed historical performance breakdown:",
                ["-- Active Lineup Roster Overview --"] + list(df_lineup.index),
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
                "BBE": "{:d}",
                "💥 SLAM Index": "{:.1f}",
                "Brl %": "{:.1f}%",
                "PullAir %": "{:.1f}%",
                "HH %": "{:.1f}%",
                "LD %": "{:.1f}%",
                "GB %": "{:.1f}%",
            })
            st.dataframe(styled_df, use_container_width=True)

else:
    st.info("Awaiting live MLB schedule initialization data streams.")
