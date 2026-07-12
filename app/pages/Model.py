import streamlit as st
import pandas as pd
import numpy as np

# ---------------------------------------------------------
# ENGINE IMPORTS
# ---------------------------------------------------------
from engines.danger_zone import build_danger_zone
from engines.pitcher_danger_zone import build_pitcher_danger_zone
from engines.slam_engine import compute_slam_window
from engines.pitch_affinity_engine import compute_pitch_affinity_multiplier
from engines.matchup_engine import compute_matchup_multiplier
from engines.roster import get_all_teams, get_pitchers, get_position_players
from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)
from engines.bvp_engine import get_bvp_history
from engines.batter_stats import load_batting_stats, get_batter_profile

# ---------------------------------------------------------
# THEME + AUTH
# ---------------------------------------------------------
from styles.kc_theme import (
    inject_kc_theme, page_header, badge, card_open, card_close,
    status_banner, data_timestamp, footer
)
from styles.table_style import style_stat_table, plain_dark_table
from auth import render_account_sidebar

inject_kc_theme()
render_account_sidebar()

# ---------------------------------------------------------
# SIDEBAR — SEPARATE BATTER + OPPOSING PITCHER SELECTION
# ---------------------------------------------------------
teams = get_all_teams()
if not teams:
    st.sidebar.warning("Couldn't load the team list from the MLB Stats API right now.")
    st.stop()

st.sidebar.header("Batter Selection")
batting_team = st.sidebar.selectbox("Batter's Team", teams, key="batting_team")
batters = get_position_players(batting_team)
if not batters:
    st.sidebar.warning(f"No position players found for {batting_team} — roster data may not have loaded.")
    st.stop()
selected_batter = st.sidebar.selectbox(
    "Choose a Batter", [p["name"] for p in batters], key="batter_select"
)

st.sidebar.header("Opposing Pitcher Selection")
pitching_team = st.sidebar.selectbox("Pitcher's Team", teams, key="pitching_team")
pitchers = get_pitchers(pitching_team)
if not pitchers:
    st.sidebar.warning(f"No pitchers found for {pitching_team} — roster data may not have loaded.")
    st.stop()
selected_pitcher = st.sidebar.selectbox(
    "Choose Opposing Pitcher", [p["name"] for p in pitchers], key="pitcher_select"
)

# ---------------------------------------------------------
# LOAD BATTER STATS + BUILD BATTER PROFILE
# ---------------------------------------------------------
stats_df, stats_load_error = load_batting_stats()
batter_profile = get_batter_profile(selected_batter, stats_df, stats_load_error)

if batter_profile.get("_error"):
    status_banner(
        "error",
        f"Live batter stats aren't available for {selected_batter} right now.",
        details=batter_profile["_error"]
    )
elif batter_profile.get("_source") == "Statcast (FanGraphs unavailable)":
    status_banner("info", f"Using backup data source (Statcast) for {selected_batter} — FanGraphs is temporarily unreachable.")

# ---------------------------------------------------------
# BUILD PITCHER PROFILE (STATCAST + ARSENAL)
# ---------------------------------------------------------
pitcher_id = get_pitcher_id(selected_pitcher)
pitcher_data = get_pitcher_statcast(pitcher_id)
pitcher_arsenal = build_pitch_arsenal(pitcher_data)

if pitcher_data.get("_error"):
    status_banner(
        "error",
        f"Live pitching stats aren't available for {selected_pitcher} right now.",
        details=pitcher_data["_error"]
    )
elif pitcher_data.get("BBE", 0) == 0:
    status_banner(
        "warning",
        f"No batted-ball data found yet for {selected_pitcher} this season — stats below will show as 0 because there's nothing to calculate from, not because they're unhittable."
    )

pitcher_profile = {
    **pitcher_data,
    "Pitcher ID": pitcher_id,
    "Arsenal": pitcher_arsenal
}

# ---------------------------------------------------------
# MAIN HEADER
# ---------------------------------------------------------
page_header("Los Cappers MLB Model", "Advanced Sabermetric Engine")
data_timestamp()

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
bvp_history = get_bvp_history(selected_pitcher, selected_batter)
st.dataframe(plain_dark_table(bvp_history), width='stretch')
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# SLAM ENGINE
# ---------------------------------------------------------
selected_batter_id = next((p["id"] for p in batters if p["name"] == selected_batter), None)
slam_result = compute_slam_window(selected_batter_id, "season", "bbe")
slam_score = slam_result["slam_score"] if slam_result["slam_score"] is not None else 0.0
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
st.dataframe(plain_dark_table(pitcher_arsenal), width='stretch')
st.markdown(card_close(), unsafe_allow_html=True)

footer()
