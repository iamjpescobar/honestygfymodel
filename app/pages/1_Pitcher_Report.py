import streamlit as st
import pandas as pd

# ---------------------------------------------------------
# THEME
# ---------------------------------------------------------
from app.styles.kc_theme import inject_kc_theme

# ---------------------------------------------------------
# ENGINES
# ---------------------------------------------------------
from app.engines.roster import get_all_teams, get_live_team_roster
from app.engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)
from app.engines.pitcher_danger_zone import build_pitcher_danger_zone
from app.engines.matchup_engine import compute_matchup_multiplier
from app.engines.slam_engine import compute_slam_index
from app.engines.pitch_affinity_engine import compute_pitch_affinity_multiplier
from app.engines.bvp_engine import get_bvp_history
from app.engines.batter_stats import load_batting_stats, get_batter_profile

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Pitcher Report",
    page_icon="🎯",
    layout="wide"
)

inject_kc_theme()

# ---------------------------------------------------------
# SIDEBAR — TEAM + PITCHER SELECTOR
# ---------------------------------------------------------
st.sidebar.header("Pitcher Report")

teams = get_all_teams()
selected_team = st.sidebar.selectbox("Choose a Team", teams)

team_roster = get_live_team_roster(selected_team)
pitcher_list = [p["name"] for p in team_roster]  # you can later filter to pitchers only

selected_pitcher = st.sidebar.selectbox("Choose a Pitcher", pitcher_list)

# ---------------------------------------------------------
# BUILD PITCHER STATCAST PROFILE
# ---------------------------------------------------------
pitcher_id = get_pitcher_id(selected_pitcher)
pitcher_data = get_pitcher_statcast(pitcher_id)
pitcher_arsenal = build_pitch_arsenal(pitcher_data)

pitcher_profile = {
    "Pitcher ID": pitcher_id,
    "Arsenal": pitcher_arsenal
}

# ---------------------------------------------------------
# OPTIONAL: BUILD A GENERIC BATTER PROFILE FOR MATCHUP/SLAM
# ---------------------------------------------------------
stats_df = load_batting_stats()
# For now, use the league‑average style batter profile by reusing the pitcher name
# (you can later swap this to a specific batter you’re studying)
batter_profile = get_batter_profile(selected_pitcher, stats_df)

# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.markdown(
    """
    <h1 class="main-header">Pitcher Report</h1>
    <h3 class="sub-header">Los Cappers Sabermetric Model</h3>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# PITCHER DANGER ZONE
# ---------------------------------------------------------
st.subheader("Pitcher Danger Zone")
pitcher_grid = build_pitcher_danger_zone(pitcher_profile)
st.dataframe(pitcher_grid, use_container_width=True)

# ---------------------------------------------------------
# PITCHER ARSENAL
# ---------------------------------------------------------
st.subheader("Pitcher Statcast Arsenal")
st.dataframe(pitcher_arsenal, use_container_width=True)

# ---------------------------------------------------------
# MATCHUP / SLAM / AFFINITY (VS GENERIC BATTER PROFILE)
# ---------------------------------------------------------
st.subheader("Matchup & SLAM (vs Batter Profile)")
matchup_mult, matchup_tag = compute_matchup_multiplier(
    batter_profile,
    pitcher_profile
)
slam_score = compute_slam_index(batter_profile, pitcher_profile)
affinity_mult = compute_pitch_affinity_multiplier(
    batter_profile,
    pitcher_arsenal
)

st.write(f"Matchup Multiplier: {matchup_mult:.2f} — {matchup_tag}")
st.write(f"SLAM Score: {slam_score:.2f}")
st.write(f"Pitch Affinity Multiplier: {affinity_mult:.2f}")

# ---------------------------------------------------------
# BVP HISTORY (PITCHER‑CENTRIC VIEW)
# ---------------------------------------------------------
st.subheader("BVP History (Pitcher View)")
bvp_history = get_bvp_history(selected_pitcher, selected_pitcher)
st.dataframe(bvp_history, use_container_width=True)
