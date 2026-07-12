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
from engines.roster import get_all_teams, get_pitchers, get_position_players
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
from styles.kc_theme import inject_kc_theme, badge, card_open, card_close, status_banner
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
# CACHED WRAPPERS (memory + speed)
#
# Streamlit reruns this entire script on EVERY interaction.
# Without caching, every selectbox change refetches all data
# and reallocates every dataframe — which is what was blowing
# past Render's 512MB limit. These wrappers make repeat runs
# reuse one shared copy instead.
#
# ttl         = seconds before a cached result expires
# max_entries = cap on stored results, so the cache itself
#               can't grow unbounded and cause the OOM
# ---------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def cached_teams():
    return get_all_teams()


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def cached_position_players(team):
    return get_position_players(team)


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def cached_pitchers(team):
    return get_pitchers(team)


@st.cache_data(ttl=1800, show_spinner="Loading batting stats...")
def cached_batting_stats():
    return load_batting_stats()


@st.cache_data(ttl=86400, max_entries=256, show_spinner=False)
def cached_pitcher_id(name):
    return get_pitcher_id(name)


@st.cache_data(ttl=7200, max_entries=8, show_spinner="Loading pitcher Statcast...")
def cached_pitcher_statcast(pid):
    return get_pitcher_statcast(pid)


@st.cache_data(ttl=7200, max_entries=8, show_spinner=False)
def cached_pitch_arsenal(pid):
    # Keyed by pitcher id so the arsenal is cached per pitcher.
    data = cached_pitcher_statcast(pid)
    return build_pitch_arsenal(data)


@st.cache_data(ttl=3600, max_entries=24, show_spinner=False)
def cached_bvp(pitcher_name, batter_name):
    return get_bvp_history(pitcher_name, batter_name)


# ---------------------------------------------------------
# SIDEBAR — SEPARATE BATTER + OPPOSING PITCHER SELECTION
# ---------------------------------------------------------
teams = cached_teams()

st.sidebar.header("Batter Selection")
batting_team = st.sidebar.selectbox("Batter's Team", teams, key="batting_team")
batters = cached_position_players(batting_team)
if not batters:
    st.sidebar.warning(f"No position players found for {batting_team} — roster data may not have loaded.")
selected_batter = st.sidebar.selectbox(
    "Choose a Batter", [p["name"] for p in batters], key="batter_select"
)

st.sidebar.header("Opposing Pitcher Selection")
pitching_team = st.sidebar.selectbox("Pitcher's Team", teams, key="pitching_team")
pitchers = cached_pitchers(pitching_team)
if not pitchers:
    st.sidebar.warning(f"No pitchers found for {pitching_team} — roster data may not have loaded.")
selected_pitcher = st.sidebar.selectbox(
    "Choose Opposing Pitcher", [p["name"] for p in pitchers], key="pitcher_select"
)

# ---------------------------------------------------------
# GUARD — don't build profiles until both selections exist
# (empty rosters would otherwise crash the engines below)
# ---------------------------------------------------------
if not selected_batter or not selected_pitcher:
    st.info("Select a batter and an opposing pitcher in the sidebar to run the model.")
    st.stop()

# ---------------------------------------------------------
# LOAD BATTER STATS + BUILD BATTER PROFILE
# ---------------------------------------------------------
stats_df, stats_load_error = cached_batting_stats()
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
pitcher_id = cached_pitcher_id(selected_pitcher)
pitcher_data = cached_pitcher_statcast(pitcher_id)
pitcher_arsenal = cached_pitch_arsenal(pitcher_id)

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
bvp_history = cached_bvp(selected_pitcher, selected_batter)
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