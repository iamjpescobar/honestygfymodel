import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import altair as alt

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, COLOR, footer
from styles.table_style import style_stat_table, plain_dark_table
from auth import render_account_sidebar
from engines.roster import get_live_team_roster
from engines.batter_stats import load_batting_stats, get_batter_profile
from engines.statcast_engine import get_pitcher_id, get_pitcher_statcast, build_pitch_arsenal
from engines.slam_engine import compute_slam_window

inject_kc_theme()
render_account_sidebar()

page_header("Lineup SLAM Index Analysis", "Full lineup breakdown vs today's probable pitchers")


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
    except Exception:
        return []


games = get_todays_games()

if games:
    st.markdown(card_open("Matchup Selection"), unsafe_allow_html=True)
    game_options = [f"{g['away']} @ {g['home']}" for g in games]
    selected_idx = st.selectbox("Matchup", range(len(game_options)), format_func=lambda x: game_options[x])
    chosen = games[selected_idx]

    pitcher = st.radio("Pitcher", [chosen["away_pitcher"], chosen["home_pitcher"]])
    st.markdown(card_close(), unsafe_allow_html=True)

    opposing_team = chosen["home"] if pitcher == chosen["away_pitcher"] else chosen["away"]

    # ---- GET ROSTER (roster.py returns dicts with 'bats', not 'hand') ----
    batters = get_live_team_roster(opposing_team)
    batters = [b for b in batters if not b.get("is_pitcher")]

    # ---- LOAD BATTING STATS ----
    stats_df, stats_error = load_batting_stats()

    # ---- GET PITCHER DATA ----
    pitcher_id = get_pitcher_id(pitcher)
    pitcher_data = get_pitcher_statcast(pitcher_id) if pitcher_id else {}
    arsenal_df = build_pitch_arsenal(pitcher_data) if pitcher_data else None

    def _slam_tier(score):
        """Simple tier label derived from the real SLAM score \u2014 not a
        separate matchup-affinity calculation (that engine was never
        actually implemented), just a readable bucket on the one real number."""
        if score >= 25:
            return "Elite"
        if score >= 15:
            return "Good"
        if score >= 8:
            return "Neutral"
        return "Cold"

    rows = []

    if not batters:
        st.warning(f"No lineup data available for {opposing_team} right now.")
    else:
        for b in batters:
            prof = get_batter_profile(b["name"], stats_df, stats_error)
            slam_result = compute_slam_window(b.get("id"), "season", "bbe")
            slam = slam_result["slam_score"] if slam_result["slam_score"] is not None else 0.0
            tier = _slam_tier(slam)

            raw_hand = (b.get("bats") or "").upper()
            hand = {"L": "LHB", "R": "RHB", "S": "SHB"}.get(raw_hand, "Unknown")

            rows.append({
                "Batter": b["name"],
                "Hand": hand,
                "SLAM": round(slam, 1),
                "Matchup": tier,
                "Brl %": prof.get("Brl %", 0),
                "HH %": prof.get("HH %", 0),
                "GB %": prof.get("GB %", 0),
                "LD %": prof.get("LD %", 0),
                "PullAir %": prof.get("PullAir %", 0),
            })

    if rows:
        df = pd.DataFrame(rows).set_index("Batter")

        st.markdown(card_open(f"Lineup vs {opposing_team}"), unsafe_allow_html=True)
        styled_df = style_stat_table(df, favor_high=["SLAM"])
        st.dataframe(styled_df, width="stretch")
        st.markdown(card_close(), unsafe_allow_html=True)

        st.markdown(card_open("SLAM Index by Batter"), unsafe_allow_html=True)
        slam_chart = (
            alt.Chart(df.reset_index())
            .mark_bar(color=COLOR["accent"])
            .encode(
                x=alt.X("Batter:N", axis=alt.Axis(labelColor=COLOR["text_muted"], titleColor=COLOR["text_muted"])),
                y=alt.Y("SLAM:Q", axis=alt.Axis(labelColor=COLOR["text_muted"], titleColor=COLOR["text_muted"])),
                color=alt.Color("Matchup:N", scale=alt.Scale(range=[COLOR["accent"], COLOR["cold"], COLOR["warn"], COLOR["text_faint"]]))
            )
            .configure_view(strokeWidth=0)
            .configure(background="transparent")
        )
        st.altair_chart(slam_chart, use_container_width=True)
        st.markdown(card_close(), unsafe_allow_html=True)

else:
    st.info("No games available.")

footer()
