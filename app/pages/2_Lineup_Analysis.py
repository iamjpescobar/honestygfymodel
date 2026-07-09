import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import altair as alt

from app.engines.roster import get_live_team_roster
from app.engines.batter_stats import load_batting_stats, get_batter_profile
from app.engines.statcast_engine import get_pitcher_id, get_pitcher_statcast, build_pitch_arsenal
from app.engines.slam_engine import (
    compute_slam_index,
    random_match_tag,
    compute_matchup_affinity,
    pitcher_affinity_score
)

st.title("⚔️ Lineup SLAM Index Analysis")
st.markdown("----")

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

if games:
    game_options = [f"{g['away']} @ {g['home']}" for g in games]
    selected_idx = st.selectbox("Select Matchup:", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen = games[selected_idx]

    pitcher = st.radio("Select Pitcher:", [chosen["away_pitcher"], chosen["home_pitcher"]])

    opposing_team = chosen["home"] if pitcher == chosen["away_pitcher"] else chosen["away"]

    st.subheader(f"Lineup Analysis vs {opposing_team}")

    # ---- GET ROSTER (NOW RETURNS CORRECT L/R/S) ----
    batters = get_live_team_roster(opposing_team)

    # ---- LOAD BATTING STATS ----
    stats_df = load_batting_stats()

    # ---- GET PITCHER DATA ----
    pitcher_id = get_pitcher_id(pitcher)
    pitcher_data = get_pitcher_statcast(pitcher_id)
    arsenal_df = build_pitch_arsenal(pitcher_data) if pitcher_data is not None else None

    primary_pitch = None
    if arsenal_df is not None and not arsenal_df.empty:
        primary_pitch = arsenal_df.sort_values("Raw Count", ascending=False).iloc[0]["Pitch Type"]

    rows = []

    for b in batters:
        prof = get_batter_profile(b["name"], stats_df)
        tag = random_match_tag(b["name"])

        matchup_mult = compute_matchup_affinity(arsenal_df, prof) if arsenal_df is not None else 1.0
        affinity_mult = pitcher_affinity_score(primary_pitch, prof) if primary_pitch else 1.0

        slam = compute_slam_index(
            brl=prof["Brl %"],
            hh=prof["HH %"],
            pull_air=prof["PullAir %"],
            gb=prof["GB %"],
            bbe=prof["BBE"],
            matchup_tag=tag,
            affinity_mult=matchup_mult * affinity_mult
        )

        # ⭐ FINAL FIX: Convert L/R/S → LHB/RHB/SHB
        raw_hand = str(b["hand"]).upper()

        if raw_hand == "L":
            hand = "LHB"
        elif raw_hand == "R":
            hand = "RHB"
        elif raw_hand == "S":
            hand = "SHB"
        else:
            hand = "RHB"

        rows.append({
            "Batter": b["name"],
            "Hand": hand,
            "SLAM": round(slam, 1),
            "Matchup": tag,
            "BBE": prof["BBE"],
            "Brl %": prof["Brl %"],
            "HH %": prof["HH %"],
            "GB %": prof["GB %"],
            "LD %": prof["LD %"],
            "PullAir %": prof["PullAir %"]
        })

    df = pd.DataFrame(rows).set_index("Batter")
    st.dataframe(df, use_container_width=True)

    slam_chart = (
        alt.Chart(df.reset_index())
        .mark_bar()
        .encode(
            x="Batter:N",
            y="SLAM:Q",
            color="Matchup:N"
        )
        .properties(title="SLAM Index by Batter")
    )
    st.altair_chart(slam_chart, use_container_width=True)

else:
    st.info("No games available.")
