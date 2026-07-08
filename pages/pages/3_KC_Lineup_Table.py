import streamlit as st
import pandas as pd

from engines.roster import get_live_team_roster
from engines.batter_stats import load_batting_stats, get_batter_profile
from engines.slam_engine import compute_slam_index, random_match_tag

st.set_page_config(layout="wide", page_title="KC-Style Lineup Table")

st.title("⚔️ KC-Style Lineup Analysis")
st.markdown("### 🟢 Emerald Glow = Verified Power | ⚫ Matte Grey = Small Sample Size | 🔥 Arsenal Coverage | 🎯 Top-3 Matchup Ranking")
st.markdown("---")

# ---------------------------------------------------------
# ARSENAL COVERAGE ICON LOGIC
# ---------------------------------------------------------
def coverage_icon(value):
    if value >= 0.12:   # strong affinity
        return "🔥"
    elif value >= 0.06: # weak affinity
        return "⚠️"
    return "❌"

# ---------------------------------------------------------
# MATCHUP RANK COLORING
# ---------------------------------------------------------
def matchup_color(val):
    if val == "ELITE":
        return "background-color: #00b36b; color: white; font-weight: bold;"  # Emerald
    elif val == "GOOD":
        return "background-color: #1e90ff; color: white;"  # Blue
    elif val == "Neutral":
        return ""
    elif val == "Cold":
        return "background-color: #7a7a7a; color: white;"  # Grey
    elif val == "⚠️":
        return "background-color: #ff4500; color: white;"  # Danger
    return ""

team_name = st.text_input("Enter Opposing Team:", "Baltimore Orioles")

if st.button("Load Lineup"):
    live_batters = get_live_team_roster(team_name)
    stats_df = load_batting_stats()

    processed_rows = []

    for b in live_batters:
        prof = get_batter_profile(b["name"], stats_df)
        tag = random_match_tag(b["name"])  # Top-3 matchup tag

        slam = compute_slam_index(
            brl=prof["Brl %"],
            hh=prof["HH %"],
            pull_air=prof["PullAir %"],
            gb=prof["GB %"],
            bbe=prof["BBE"],
            matchup_tag=tag,
            affinity_mult=1.0
        )

        processed_rows.append({
            "Batter": b["name"],
            "Hand": b["hand"],
            "BBE": prof["BBE"],
            "SLAM": round(slam, 1),
            "Matchup": tag,

            # Power profile
            "Brl %": prof["Brl %"],
            "HH %": prof["HH %"],
            "PullAir %": prof["PullAir %"],
            "LD %": prof["LD %"],
            "GB %": prof["GB %"],

            # Arsenal coverage icons
            "FF": coverage_icon(prof["FF Affinity"]),
            "SL": coverage_icon(prof["SL Affinity"]),
            "CH": coverage_icon(prof["CH Affinity"]),
            "SI": coverage_icon(prof["SI Affinity"]),
            "SW": coverage_icon(prof["SW Affinity"]),
            "CU": coverage_icon(prof["CU Affinity"])
        })

    df = pd.DataFrame(processed_rows).set_index("Batter")

    # ---------------------------------------------------------
    # EMERALD GLOW + MATTE GREY + MATCHUP COLORING
    # ---------------------------------------------------------
    def color_slam(val):
        if val >= 75:
            return "background-color: #00b36b; color: white; font-weight: bold;"
        elif val <= 50:
            return "background-color: #7a7a7a; color: white;"
        return ""

    def color_bbe(val):
        if val < 50:
            return "background-color: #7a7a7a; color: white;"
        return ""

    styled = df.style.applymap(color_slam, subset=["SLAM"]) \
                     .applymap(color_bbe, subset=["BBE"]) \
                     .applymap(matchup_color, subset=["Matchup"]) \
                     .format({
                         "SLAM": "{:.1f}",
                         "Brl %": "{:.1f}%",
                         "HH %": "{:.1f}%",
                         "PullAir %": "{:.1f}%",
                         "LD %": "{:.1f}%",
                         "GB %": "{:.1f}%"
                     })

    # ---------------------------------------------------------
    # DISPLAY TABLE WITH COVERAGE ICONS + MATCHUP RANK
    # ---------------------------------------------------------
    st.dataframe(
        styled,
        use_container_width=True,
        column_config={
            "FF": "FF",
            "SL": "SL",
            "CH": "CH",
            "SI": "SI",
            "SW": "SW",
            "CU": "CU"
        }
    )

    st.markdown("---")
    st.subheader("🔍 Detailed Scout Card")

    selected = st.selectbox("Select Batter:", ["--"] + list(df.index))

    if selected != "--":
        sb = df.loc[selected]

        st.markdown(f"### 📊 {selected} — Scout Breakdown")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("SLAM Index", sb["SLAM"])
        c2.metric("Barrel %", f"{sb['Brl %']}%")
        c3.metric("Hard Hit %", f"{sb['HH %']}%")
        c4.metric("BBE Sample", sb["BBE"])

        st.markdown("#### Power Profile")
        st.write(f"- **PullAir %:** {sb['PullAir %']}%")
        st.write(f"- **Line Drive %:** {sb['LD %']}%")
        st.write(f"- **Groundball %:** {sb['GB %']}%")

        st.markdown("#### Arsenal Coverage")
        st.write(f"**FF:** {sb['FF']}  |  **SL:** {sb['SL']}  |  **CH:** {sb['CH']}")
        st.write(f"**SI:** {sb['SI']}  |  **SW:** {sb['SW']}  |  **CU:** {sb['CU']}")

        st.markdown("#### Matchup Tag")
        st.write(f"**{sb['Matchup']}**")
