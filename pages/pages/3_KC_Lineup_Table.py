import streamlit as st
import pandas as pd

from engines.roster import get_live_team_roster
from engines.batter_stats import load_batting_stats, get_batter_profile
from engines.slam_engine import compute_slam_index, random_match_tag

st.set_page_config(layout="wide", page_title="KC-Style Lineup Table")

st.title("⚔️ KC-Style Lineup Analysis — Custom Theme")
st.markdown("### 💜 Purple Glow | Deep Navy Matte | Gold/Silver Matchups | Custom Arsenal Icons")
st.markdown("---")

# ---------------------------------------------------------
# ARSENAL COVERAGE ICON LOGIC (CUSTOM)
# ---------------------------------------------------------
def coverage_icon(value):
    if value >= 0.12:
        return "🦾"      # Strong
    elif value >= 0.06:
        return "👌🏾"     # Weak
    return "🧑🏾‍🦯"       # None

# ---------------------------------------------------------
# MATCHUP RANK COLORING (CUSTOM)
# ---------------------------------------------------------
def matchup_color(val):
    if val == "ELITE":
        return "background-color: #d4af37; color: black; font-weight: bold;"  # Gold
    elif val == "GOOD":
        return "background-color: #c0c0c0; color: black;"  # Silver
    elif val == "Neutral":
        return ""
    elif val == "Cold":
        return "background-color: #1e90ff; color: white;"  # Blue
    elif val == "⚠️":
        return "background-color: #7d3cff; color: white;"  # Purple Danger
    return ""

team_name = st.text_input("Enter Opposing Team:", "Baltimore Orioles")

if st.button("Load Lineup"):
    live_batters = get_live_team_roster(team_name)
    stats_df = load_batting_stats()

    processed_rows = []

    for b in live_batters:
        prof = get_batter_profile(b["name"], stats_df)
        tag = random_match_tag(b["name"])

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
    # EMERALD GLOW + MATTE GREY (CUSTOM PURPLE + NAVY)
    # ---------------------------------------------------------
    def color_slam(val):
        if val >= 75:
            return "background-color: #7d3cff; color: white; font-weight: bold;"  # Purple Glow
        elif val <= 50:
            return "background-color: #0a1a2f; color: white;"  # Deep Navy Matte
        return ""

    def color_bbe(val):
        if val < 50:
            return "background-color: #0a1a2f; color: white;"  # Deep Navy Matte
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
    # DISPLAY TABLE
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
    st.subheader("🔍 Full KC Scout Card — Custom Theme")

    selected = st.selectbox("Select Batter:", ["--"] + list(df.index))

    if selected != "--":
        sb = df.loc[selected]

        st.markdown(f"### 📊 {selected} — Full KC Scout Breakdown")

        # ---------------------------------------------------------
        # TOP METRICS
        # ---------------------------------------------------------
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("SLAM Index", sb["SLAM"])
        c2.metric("Barrel %", f"{sb['Brl %']}%")
        c3.metric("Hard Hit %", f"{sb['HH %']}%")
        c4.metric("BBE Sample", sb["BBE"])

        # ---------------------------------------------------------
        # POWER PROFILE SECTION
        # ---------------------------------------------------------
        st.markdown("### 🔋 Power Profile")
        st.write(f"- **PullAir %:** {sb['PullAir %']}%")
        st.write(f"- **Line Drive %:** {sb['LD %']}%")
        st.write(f"- **Groundball %:** {sb['GB %']}%")

        # ---------------------------------------------------------
        # ARSENAL COVERAGE SECTION
        # ---------------------------------------------------------
        st.markdown("### 🎯 Arsenal Coverage")
        st.write(f"**FF:** {sb['FF']}  |  **SL:** {sb['SL']}  |  **CH:** {sb['CH']}")
        st.write(f"**SI:** {sb['SI']}  |  **SW:** {sb['SW']}  |  **CU:** {sb['CU']}")

        # ---------------------------------------------------------
        # MATCHUP TAG SECTION
        # ---------------------------------------------------------
        st.markdown("### ⚔️ Matchup Tag")
        st.write(f"**{sb['Matchup']}**")

        # ---------------------------------------------------------
        # HISTORICAL PERFORMANCE SECTION
        # ---------------------------------------------------------
        st.markdown("### 📈 Historical Performance Snapshot")
        st.info("Historical performance charts, heatmaps, and pitch-type danger zones can be added here.")
