import streamlit as st
import pandas as pd

# ---------------------------------------------------------
# THEME
# ---------------------------------------------------------
from styles.kc_theme import inject_kc_theme, page_header, badge, card_open, card_close, footer
from styles.table_style import style_stat_table, plain_dark_table
from auth import render_account_sidebar

# ---------------------------------------------------------
# ENGINES
# ---------------------------------------------------------
from engines.roster import get_all_teams, get_live_team_roster
from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)
from engines.pitcher_danger_zone import build_pitcher_danger_zone
from engines.matchup_engine import compute_matchup_multiplier
from engines.pitch_affinity_engine import compute_pitch_affinity_multiplier
from engines.bvp_engine import get_bvp_history
from engines.batter_stats import load_batting_stats, get_batter_profile

inject_kc_theme()
render_account_sidebar()

# ---------------------------------------------------------
# SIDEBAR — TEAM + PITCHER SELECTOR
# ---------------------------------------------------------
st.sidebar.header("Pitcher Report")

teams = get_all_teams()
if not teams:
    st.sidebar.warning("Couldn't load the team list from the MLB Stats API right now.")
    st.stop()

selected_team = st.sidebar.selectbox("Choose a Team", teams)

team_roster = get_live_team_roster(selected_team)
pitcher_list = [p["name"] for p in team_roster if p.get("is_pitcher")]

if not pitcher_list:
    st.sidebar.warning(f"No pitchers found for {selected_team} right now.")
    st.stop()

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
# GENERIC BATTER PROFILE FOR MATCHUP/SLAM
# ---------------------------------------------------------
stats_df, stats_load_error = load_batting_stats()
# League-average style batter profile, reusing the pitcher name as a stand-in
batter_profile = get_batter_profile(selected_pitcher, stats_df, stats_load_error)

# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
page_header(selected_pitcher, "Los Cappers Sabermetric Model \u2014 Pitcher Report", eyebrow="PITCHER REPORT")

# ---------------------------------------------------------
# PITCHER DANGER ZONE
# ---------------------------------------------------------
st.markdown(card_open("Pitcher Danger Zone", "Green = higher vulnerability (favorable for the batter)"), unsafe_allow_html=True)
pitcher_grid = build_pitcher_danger_zone(pitcher_profile)
styled_grid = style_stat_table(pitcher_grid, favor_high=list(pitcher_grid.columns))
st.dataframe(styled_grid, width="stretch")
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# PITCHER ARSENAL
# ---------------------------------------------------------
st.markdown(card_open("Pitcher Statcast Arsenal"), unsafe_allow_html=True)
st.dataframe(plain_dark_table(pitcher_arsenal), width="stretch")
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# MATCHUP / SLAM / AFFINITY (VS GENERIC BATTER PROFILE)
# ---------------------------------------------------------
matchup_mult, matchup_tag = compute_matchup_multiplier(
    batter_profile,
    pitcher_profile
)
affinity_mult = compute_pitch_affinity_multiplier(
    batter_profile,
    pitcher_arsenal
)

tag_style = {
    "ELITE": "good", "GOOD": "good",
    "Neutral": "neutral",
    "Cold": "bad", "\u26a0\ufe0f": "bad"
}.get(matchup_tag, "neutral")

st.markdown(card_open("Matchup & Pitch Affinity", "vs. league-average batter profile"), unsafe_allow_html=True)
st.markdown(
    badge(f"Matchup {matchup_mult:.2f}", "accent")
    + badge(matchup_tag, tag_style)
    + badge(f"Pitch Affinity {affinity_mult:.2f}", "accent"),
    unsafe_allow_html=True,
)
st.markdown(card_close(), unsafe_allow_html=True)

# ---------------------------------------------------------
# BVP HISTORY (PITCHER-CENTRIC VIEW)
# ---------------------------------------------------------
st.markdown(card_open("BVP History", "Pitcher view"), unsafe_allow_html=True)
bvp_history = get_bvp_history(selected_pitcher, selected_pitcher)
st.dataframe(plain_dark_table(bvp_history), width="stretch")
st.markdown(card_close(), unsafe_allow_html=True)

footer()
