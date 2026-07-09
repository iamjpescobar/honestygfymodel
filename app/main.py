import streamlit as st
import pandas as pd
import numpy as np
import sys
import os

# ---------------------------------------------------------
# FIX: Ensure Python can find the repo root
# ---------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ---------------------------------------------------------
# SAFE STREAMLIT IMPORTS FOR ENGINES
# ---------------------------------------------------------
from engines import danger_zone as dz
from engines import pitcher_danger_zone as pdz
from engines import slam_engine as slam
from engines import bvp_engine as bvp
from engines import matchup_engine as matchup
from engines import pitch_affinity_engine as affinity
from engines import batter_stats as batter
from engines import statcast_engine as statcast
from engines import roster as roster

# ---------------------------------------------------------
# THEME
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
# SIDEBAR — PLAYER SELECTOR
# ---------------------------------------------------------
st.sidebar.header("Player Selection")

player_list = roster.get_player_list()
selected_player = st.sidebar.selectbox("Choose a Player", player_list)

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
# BATTER DANGER ZONE GRID
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
