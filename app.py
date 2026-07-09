import streamlit as st
import pandas as pd
import numpy as np

# SAFE STREAMLIT IMPORTS FOR ENGINES
import engines.danger_zone as dz
import engines.pitcher_danger_zone as pdz
import engines.slam_engine as slam
import engines.bvp_engine as bvp
import engines.matchup_engine as matchup
import engines.pitch_affinity_engine as affinity
import engines.batter_stats as batter
import engines.statcast_engine as statcast
import engines.roster as roster

# THEME
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
# SIDEBAR — PLAYER SELECTOR
# ---------------------------------------------------------
st.sidebar.header("Player Selection")

# Load roster
player_list = roster.get_player_list()
selected_player = st.sidebar.selectbox("Choose a Player", player_list)

# Load batter + pitcher profiles
batter_profile = batter.get_batter_profile(selected_player)
pitcher_profile = roster.get_pitcher_profile(selected_player)


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
# DANGER ZONE GRID (Batter)
# ---------------------------------------------------------
st.subheader("Batter Danger Zone Grid")

danger_grid = dz.build_danger_zone(batter_profile)
st.dataframe(danger_grid, use_container_width=True)


# ---------------------------------------------------------
# PITCHER DANGER ZONE GRID
# ---------------------------------------------------------
st.subheader("Pitcher Danger Zone Grid")

pitcher_grid = pdz.build_pitcher_danger_zone(pitcher_profile)
st.dataframe(pitcher_grid, use_container_width=True)


# ---------------------------------------------------------
# MATCHUP ENGINE
# ---------------------------------------------------------
st.subheader("Matchup Engine")

matchup_results = matchup.build_matchup(selected_player)
st.dataframe(matchup_results, use_container_width=True)


# ---------------------------------------------------------
# BVP ENGINE
# ---------------------------------------------------------
st.subheader("BVP History")

bvp_history = bvp.get_bvp_history(selected_player)
st.dataframe(bvp_history, use_container_width=True)


# ---------------------------------------------------------
# SLAM ENGINE
# ---------------------------------------------------------
st.subheader("SLAM Engine")

slam_results = slam.build_slam_score(selected_player)
st.dataframe(slam_results, use_container_width=True)


# ---------------------------------------------------------
# PITCH AFFINITY ENGINE
# ---------------------------------------------------------
st.subheader("Pitch Affinity")

affinity_results = affinity.build_pitch_affinity(selected_player)
st.dataframe(affinity_results, use_container_width=True)


# ---------------------------------------------------------
# STATCAST ENGINE
# ---------------------------------------------------------
st.subheader("Statcast Summary")

statcast_summary = statcast.get_statcast_summary(selected_player)
st.dataframe(statcast_summary, use_container_width=True)
