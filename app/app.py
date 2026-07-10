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
from styles.kc_theme import inject_kc_theme, badge, card_open, card_close
from styles.table_style import style_stat_table

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
stats_df, stats_load_error = load_batting_stats()
batter_profile = get_batter_profile(selected_player, stats_df, stats_load_error)

if batter_profile.get("_error"):
    st.error(f"⚠️ Batter data did not load: {batter_profile['_error']}")
elif batter_profile.get("_source"):
    st.caption(f"Batter data source: {batter_profile['_source']}")

# ---------------------------------------------------------
# BUILD PITCHER PROFILE (STATCAST + ARSENAL)
# ---------------------------------------------------------
pitcher_id = get_pitcher_id(selected_player)
pitcher_data = get_pitcher_statcast(pitcher_id)
pitcher_arsenal = build_pitch_arsenal(pitcher_data)

if pitcher_data.get("_error"):
    st.error(f"⚠️ Pitcher data did not load: {pitcher_data['_error']}")
elif pitcher_data.get("BBE", 0) == 0:
    st.warning(f"⚠️ No batted-ball events found for '{selected_player}' in this date range — stats below will show as 0, not because the pitcher is unhittable, but because there's no real data to compute from yet.")

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
st.markdown(card_open("Batter Danger Zone Grid", "Green = higher damage potential for the batter"), unsafe_allow_html=True)
danger_grid = build_danger_zone(batter_profile)
styled_danger = style_stat_table(danger_grid, favor_high=list(danger_grid.columns))
st.dataframe(styled_danger, width='stretch')
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# PITCHER DANGER ZONE GRID
# ---------------------------------------------------------
st.markdown(card_open("Pitcher Danger Zone Grid", "Green = higher vulnerability (favorable for the batter)"), unsafe_allow_html=True)
pitcher_grid = build_pitcher_danger_zone(pitcher_profile)
styled_pitcher_grid = style_stat_table(pitcher_grid, favor_high=list(pitcher_grid.columns))
st.dataframe(styled_pitcher_grid, width='stretch')
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# MATCHUP ENGINE
# ---------------------------------------------------------
matchup_mult, matchup_tag = compute_matchup_multiplier(
    batter_profile,
    pitcher_profile
)
tag_style = {
    "ELITE": "good", "GOOD": "good",
    "Neutral": "neutral",
    "Cold": "bad", "⚠️": "bad"
}.get(matchup_tag, "neutral")

st.markdown(card_open("Matchup Engine"), unsafe_allow_html=True)
st.markdown(
    badge(f"Multiplier {matchup_mult:.2f}", "accent") + badge(matchup_tag, tag_style),
    unsafe_allow_html=True
)
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# BVP ENGINE
# ---------------------------------------------------------
st.markdown(card_open("BVP History"), unsafe_allow_html=True)
bvp_history = get_bvp_history(selected_player, selected_player)
st.dataframe(bvp_history, width='stretch')
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# SLAM ENGINE
# ---------------------------------------------------------
slam_score = compute_slam_index(batter_profile, pitcher_profile)
st.markdown(card_open("SLAM Engine"), unsafe_allow_html=True)
st.markdown(
    f'<div class="pf-metric-value">{slam_score:.2f}</div><div class="pf-metric-label">SLAM Score</div>',
    unsafe_allow_html=True
)
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# PITCH AFFINITY ENGINE
# ---------------------------------------------------------
affinity_mult = compute_pitch_affinity_multiplier(
    batter_profile,
    pitcher_arsenal
)
st.markdown(card_open("Pitch Affinity"), unsafe_allow_html=True)
st.markdown(badge(f"Multiplier {affinity_mult:.2f}", "accent"), unsafe_allow_html=True)
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# STATCAST SUMMARY (ARSENAL TABLE)
# ---------------------------------------------------------
st.markdown(card_open("Pitcher Statcast Arsenal"), unsafe_allow_html=True)
st.dataframe(pitcher_arsenal, width='stretch')
st.markdown(card_close(), unsafe_allow_html=True)
