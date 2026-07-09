import streamlit as st
import pandas as pd
import numpy as np

# ---------------------------------------------------------
# ENGINE IMPORTS (CLEAN + CORRECT)
# ---------------------------------------------------------
from engines.danger_zone import build_danger_zone
from engines.pitcher_danger_zone import build_pitcher_danger_zone
from engines.slam_engine import compute_slam_index
from engines.pitch_affinity_engine import compute_pitch_affinity_multiplier
from engines.matchup_engine import compute_matchup_multiplier
from engines.roster import get_all_teams, get_live_team_roster
from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)
from engines.bvp_engine import get_bvp_history
from engines.batter_stats import load_batting_stats, get_batter_profile

# ---------------------------------------------------------
# THEME IMPORT
# ---------------------------------------------------------
from styles.kc_theme import inject_kc_theme

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Los Cappers MLB Model",
    page_icon="⚾",
    layout="wide"
)

inject_kc_theme()

# ---------------------------------------------------------
# SIDEBAR — TEAM + PLAYER SELECTOR
# ---------------------------------------------------------
st.sidebar.header("Team & Player Selection")

# Step 1 — Choose Team
teams = get_all_teams()
selected_team = st.sidebar.selectbox("Choose a Team", teams)

# Step 2 — Pull Team Roster
team_roster = get_live_team_roster(selected_team)
player_list = [p["name"] for p in team_roster]

# Step 3 — Choose Player
selected_player = st.sidebar.selectbox("Choose a Player", player_list)

# ---------------------------------------------------------
# LOAD BATTER STATS + BUILD BATTER PROFILE
# ---------------------------------------------------------
stats_df = load_batting_stats()
batter_profile = get_batter_profile(selected_player, stats_df)

# ---------------------------------------------------------
# BUILD PITCHER PROFILE (STATCAST + ARSENAL)
# ---------------------------------------------------------
pitcher_id = get_pitcher_id(selected_player)
pitcher_data = get_pitcher_statcast(pitcher_id)
pitcher_arsenal = build_pitch_arsenal(pitcher_data)

pitcher_profile = {
    **pitcher_data,
    "Pitcher ID": pitcher_id,
    "Arsenal": pitcher_arsenal
}

# ---------------------------------------------------------
# MAIN HEADER
# ---------------------------------------------------------
st.markdown(
    """
    <h1 class="main-header">Los Cappers MLB Model</h1>
    <h3 class="sub-header">Advanced Sabermetric Engine</h3>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# BATTER DANGER ZONE GRID
# ---------------------------------------------------------
st.subheader("Batter Danger Zone Grid")
danger_grid = build_danger_zone(batter_profile)
st.dataframe(danger_grid, use_container_width=True)

# ---------------------------------------------------------
# PITCHER DANGER ZONE GRID
# ---------------------------------------------------------
st.subheader("Pitcher Danger Zone Grid")
pitcher_grid = build_pitcher_danger_zone(pitcher_profile)
st.dataframe(pitcher_grid, use_container_width=True)

# ---------------------------------------------------------
# MATCHUP ENGINE
# ---------------------------------------------------------
st.subheader("Matchup Engine")
matchup_mult, matchup_tag = compute_matchup_multiplier(
    batter_profile,
    pitcher_profile
)
st.write(f"Matchup Multiplier: {matchup_mult:.2f} — {matchup_tag}")

# ---------------------------------------------------------
# BVP ENGINE
# ---------------------------------------------------------
st.subheader("BVP History")
bvp_history = get_bvp_history(selected_player, selected_player)
st.dataframe(bvp_history, use_container_width=True)

# ---------------------------------------------------------
# SLAM ENGINE
# ---------------------------------------------------------
st.subheader("SLAM Engine")
slam_score = compute_slam_index(batter_profile, pitcher_profile)
st.write(f"SLAM Score: {slam_score:.2f}")

# ---------------------------------------------------------
# PITCH AFFINITY ENGINE
# ---------------------------------------------------------
st.subheader("Pitch Affinity")
affinity_mult = compute_pitch_affinity_multiplier(
    batter_profile,
    pitcher_arsenal
)
st.write(f"Pitch Affinity Multiplier: {affinity_mult:.2f}")

# ---------------------------------------------------------
# STATCAST SUMMARY (ARSENAL TABLE)
# ---------------------------------------------------------
st.subheader("Pitcher Statcast Arsenal")
st.dataframe(pitcher_arsenal, use_container_width=True)
