import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import altair as alt

from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)

st.title("⚾ Pitcher Statcast Report")
st.markdown("----")

# ---- GET TODAY'S GAMES ----
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
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD")
            })
        return matchups
    except:
        return []

games = get_todays_games()

# ---- SIDEBAR MATCHUP SELECTOR ----
if games:
    game_options = [f"{g['away']} @ {g['home']}" for g in games]
    selected_idx = st.selectbox("Select Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen = games[selected_idx]

    pitcher = st.radio("Select Pitcher:", [chosen["away_pitcher"], chosen["home_pitcher"]])

    # ---- PITCHER REPORT ----
    if pitcher != "TBD":
        st.subheader(f"⚾ Pitcher Report: {pitcher}")

        pitcher_id = get_pitcher_id(pitcher)
        data = get_pitcher_statcast(pitcher_id)

        st.markdown("### Pitch Arsenal")
        st.table(build_pitch_arsenal(data))

        # ---- CHARTS START HERE ----

        # ---- BAR CHART: Pitch Arsenal ----
        if not data.empty and "pitch_type" in data.columns:
            arsenal_chart = (
                alt.Chart(data)
                .mark_bar()
                .encode(
                    x=alt.X("pitch_type:N", title="Pitch Type"),
                    y=alt.Y("count()", title="Total Pitches"),
                    color="pitch_type:N"
                )
                .properties(title="Pitch Arsenal Frequency")
            )
            st.altair_chart(arsenal_chart, use_container_width=True)

        # ---- VELOCITY HISTOGRAM ----
        if "release_speed" in data.columns:
            velo_chart = (
                alt.Chart(data)
                .mark_area(opacity=0.6)
                .encode(
                    x=alt.X("release_speed:Q", bin=True, title="Velocity (MPH)"),
                    y=alt.Y("count()", title="Pitch Count"),
                    color="pitch_type:N"
                )
                .properties(title="Velocity Distribution by Pitch Type")
            )
            st.altair_chart(velo_chart, use_container_width=True)

        # ---- RELEASE POINT SCATTER ----
        if "release_pos_x" in data.columns and "release_pos_z" in data.columns:
            release_chart = (
                alt.Chart(data)
                .mark_circle(size=40, opacity=0.4)
                .encode(
                    x=alt.X("release_pos_x:Q", title="Horizontal Release"),
                    y=alt.Y("release_pos_z:Q", title="Vertical Release"),
                    color="pitch_type:N"
                )
                .properties(title="Pitch Release Point Map")
            )
            st.altair_chart(release_chart, use_container_width=True)

        # ---- MOVEMENT CHART ----
        if "pfx_x" in data.columns and "pfx_z" in data.columns:
            movement_chart = (
                alt.Chart(data)
                .mark_circle(size=50, opacity=0.5)
                .encode(
                    x=alt.X("pfx_x:Q", title="Horizontal Break"),
                    y=alt.Y("pfx_z:Q", title="Vertical Break"),
                    color="pitch_type:N",
                    tooltip=["pitch_type", "pfx_x", "pfx_z", "release_speed"]
                )
                .properties(title="Pitch Movement Map")
            )
            st.altair_chart(movement_chart, use_container_width=True)

        # ---- USAGE DONUT CHART ----
        if "pitch_type" in data.columns:
            usage_df = (
                data["pitch_type"]
                .value_counts()
                .reset_index()
                .rename(columns={"index": "pitch_type", "pitch_type": "count"})
            )

            donut_chart = (
                alt.Chart(usage_df)
                .mark_arc(innerRadius=50)
                .encode(
                    theta="count:Q",
                    color="pitch_type:N",
                    tooltip=["pitch_type", "count"]
                )
                .properties(title="Pitch Usage Distribution")
            )
            st.altair_chart(donut_chart, use_container_width=True)

else:
    st.info("No games available.")
