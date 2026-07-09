from styles.kc_theme import inject_kc_theme
inject_kc_theme()

import streamlit as st
import pandas as pd
import altair as alt

from engines.roster import get_live_team_roster
from engines.batter_stats import load_batting_stats, get_batter_profile
from engines.slam_engine import compute_slam_index
from engines.pitcher_stats import get_pitch_arsenal, get_pitcher_profile
from engines.bvp_engine import get_bvp_history
from engines.danger_zone import build_danger_zone
from engines.pitcher_danger_zone import build_pitcher_danger_zone

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Los Cappers Lab — Lineup Hub")

# ---------------------------------------------------------
# GLOBAL CUSTOM CSS (SOFT MATTE + ULTRA-TIGHT ROWS + SHADOWED CARD)
# ---------------------------------------------------------
st.markdown(
    """
    <style>
    body {
        background-color: #050812;
        color: #e5e5e5;
    }

    .main-header {
        text-align: center;
        font-size: 32px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center;
        font-size: 16px;
        color: #a0a0ff;
        margin-bottom: 1.5rem;
    }

    div[data-testid="stDataFrame"] table {
        background-color: #0b0f1a;
        border-collapse: collapse;
    }
    div[data-testid="stDataFrame"] table td,
    div[data-testid="stDataFrame"] table th {
        padding: 4px 6px;
        border-bottom: 1px solid #1b2233;
        font-size: 12px;
    }

    .arsenal-card {
        background: #0b0f1a;
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 0 18px rgba(125, 60, 255, 0.35);
        border: 1px solid #1f2640;
        margin-bottom: 20px;
    }
    .arsenal-title {
        font-weight: 700;
        font-size: 18px;
        margin-bottom: 8px;
        color: #e5e5ff;
    }
    .arsenal-subtitle {
        font-size: 13px;
        color: #b0b0d0;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.markdown('<div class="main-header">LOS CAPPERS LAB</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">The Advanced S.L.A.M. Index Analytics Hub</div>', unsafe_allow_html=True)

st.markdown("### 💜 Purple Glow | Deep Navy Matte | Gold/Silver Matchups | Custom Arsenal Icons")
st.markdown("---")

# ---------------------------------------------------------
# PITCH ARSENAL CARD + PITCHER DANGER ZONE
# ---------------------------------------------------------
pitcher_name = st.text_input("Pitcher Name:", "Spencer Arrighetti")

if pitcher_name:
    arsenal = get_pitch_arsenal(pitcher_name)          # real pitch mix data
    pitcher_profile = get_pitcher_profile(pitcher_name)  # real pitcher metrics

    st.markdown('<div class="arsenal-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="arsenal-title">Pro-Report: {pitcher_name}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="arsenal-subtitle">Verified Pitch Arsenal Distribution</div>',
        unsafe_allow_html=True,
    )

    st.dataframe(arsenal, use_container_width=True)

    st.markdown("### 🔥 Pitcher Danger Zone Heatmap")

    pdz = build_pitcher_danger_zone(pitcher_profile)
    pdz_reset = pdz.reset_index().melt(id_vars="index")
    pdz_reset.columns = ["Vertical", "Horizontal", "Danger"]

    pitcher_heatmap = (
        alt.Chart(pdz_reset)
        .mark_rect()
        .encode(
            x=alt.X("Horizontal:N", title="Horizontal Zone"),
            y=alt.Y("Vertical:N", title="Vertical Zone"),
            color=alt.Color(
                "Danger:Q",
                scale=alt.Scale(scheme="reds"),
                title="Vulnerability Level",
            ),
            tooltip=["Vertical", "Horizontal", "Danger"],
        )
        .properties(width=300, height=300, title="Pitcher Danger Zone Map")
    )

    st.altair_chart(pitcher_heatmap, use_container_width=False)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("### Intent-To-Homer Lineup Analysis")
st.markdown("#### Legend: 💜 SLAM Glow = High Volume Verified Power | Deep Navy = Small Sample Size")
st.markdown("---")

# ---------------------------------------------------------
# ICONS + MATCHUP COLORS
# ---------------------------------------------------------
def coverage_icon(value: float) -> str:
    if value >= 0.12:
        return "🦾"
    elif value >= 0.06:
        return "👌🏾"
    return "🧑🏾‍🦯"


def matchup_color(val: str) -> str:
    if val == "ELITE":
        return "background-color: #d4af37; color: black; font-weight: bold;"
    elif val == "GOOD":
        return "background-color: #c0c0c0; color: black;"
    elif val == "Neutral":
        return ""
    elif val == "Cold":
        return "background-color: #1e90ff; color: white;"
    elif val == "⚠️":
        return "background-color: #7d3cff; color: white;"
    return ""

# ---------------------------------------------------------
# TEAM INPUT + LINEUP TABLE
# ---------------------------------------------------------
team_name = st.text_input("Enter Opposing Team:", "Washington Nationals")

if st.button("Load Lineup"):
    live_batters = get_live_team_roster(team_name)   # real live roster
    stats_df = load_batting_stats()                  # real batting stats

    processed_rows = []

    for b in live_batters:
        prof = get_batter_profile(b["name"], stats_df)  # real batter profile

        slam = compute_slam_index(
            brl=prof["Brl %"],
            hh=prof["HH %"],
            pull_air=prof["PullAir %"],
            gb=prof["GB %"],
            bbe=prof["BBE"],
            matchup_tag=prof["Matchup Tag"],  # MUST come from real data
            affinity_mult=1.0,
        )

        processed_rows.append(
            {
                "Batter": b["name"],
                "Hand": b["hand"],
                "BBE": prof["BBE"],
                "SLAM": round(slam, 1),
                "Top 3 Matchup": prof["Matchup Tag"],
                "Brl %": prof["Brl %"],
                "HH %": prof["HH %"],
                "PullAir %": prof["PullAir %"],
                "LD %": prof["LD %"],
                "GB %": prof["GB %"],
                "FF": coverage_icon(prof["FF Affinity"]),
                "SL": coverage_icon(prof["SL Affinity"]),
                "CH": coverage_icon(prof["CH Affinity"]),
                "SI": coverage_icon(prof["SI Affinity"]),
                "SW": coverage_icon(prof["SW Affinity"]),
                "CU": coverage_icon(prof["CU Affinity"]),
            }
        )

    df = pd.DataFrame(processed_rows).set_index("Batter")

    def color_slam(val: float) -> str:
        if val >= 75:
            return "background-color: #7d3cff; color: white; font-weight: bold;"
        elif val <= 50:
            return "background-color: #0a1a2f; color: white;"
        return ""

    def color_bbe(val: float) -> str:
        if val < 50:
            return "background-color: #0a1a2f; color: white;"
        return ""

    styled = (
        df.style.applymap(color_slam, subset=["SLAM"])
        .applymap(color_bbe, subset=["BBE"])
        .applymap(matchup_color, subset=["Top 3 Matchup"])
        .format(
            {
                "SLAM": "{:.1f}",
                "Brl %": "{:.1f}%",
                "HH %": "{:.1f}%",
                "PullAir %": "{:.1f}%",
                "LD %": "{:.1f}%",
                "GB %": "{:.1f}%",
            }
        )
    )

    st.dataframe(
        styled,
        use_container_width=True,
        column_config={
            "Top 3 Matchup": "Top 3 Matchup",
            "FF": "FF",
            "SL": "SL",
            "CH": "CH",
            "SI": "SI",
            "SW": "SW",
            "CU": "CU",
        },
    )

    st.markdown("---")
    st.subheader("🔍 Full KC Scout Card — Custom Theme")

    selected = st.selectbox("Select Batter:", ["--"] + list(df.index))

    if selected != "--":
        sb = df.loc[selected]

        st.markdown(f"### 📊 {selected} — Full KC Scout Breakdown")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("SLAM Index", sb["SLAM"])
        c2.metric("Barrel %", f"{sb['Brl %']}%")
        c3.metric("Hard Hit %", f"{sb['HH %']}%")
        c4.metric("BBE Sample", sb["BBE"])

        st.markdown("### 🔋 Power Profile")
        st.write(f"- **PullAir %:** {sb['PullAir %']}%")
        st.write(f"- **Line Drive %:** {sb['LD %']}%")
        st.write(f"- **Groundball %:** {sb['GB %']}%")

        st.markdown("### 🎯 Arsenal Coverage")
        st.write(f"**FF:** {sb['FF']}  |  **SL:** {sb['SL']}  |  **CH:** {sb['CH']}")
        st.write(f"**SI:** {sb['SI']}  |  **SW:** {sb['SW']}  |  **CU:** {sb['CU']}")

        st.markdown("### ⚔️ Matchup Tag")
        st.write(f"**{sb['Top 3 Matchup']}**")

        st.markdown("### ⚾ Batter vs Pitcher History")
        bvp = get_bvp_history(pitcher_name, selected)  # should hit your real BvP data

        if bvp.empty:
            st.info("No historical matchup data available.")
        else:
            st.dataframe(bvp, use_container_width=True)

        st.markdown("### 🔥 Danger Zone Heatmap")

        dz = build_danger_zone(sb)
        dz_reset = dz.reset_index().melt(id_vars="index")
        dz_reset.columns = ["Vertical", "Horizontal", "Danger"]

        heatmap = (
            alt.Chart(dz_reset)
            .mark_rect()
            .encode(
                x=alt.X("Horizontal:N", title="Horizontal Zone"),
                y=alt.Y("Vertical:N", title="Vertical Zone"),
                color=alt.Color(
                    "Danger:Q",
                    scale=alt.Scale(scheme="purples"),
                    title="Danger Level",
                ),
                tooltip=["Vertical", "Horizontal", "Danger"],
            )
            .properties(width=300, height=300, title="Danger Zone Map")
        )

        st.altair_chart(heatmap, use_container_width=False)

        st.markdown("### 📈 Historical Performance Snapshot")
        st.info("Historical performance charts, heatmaps, and pitch-type danger zones can be added here.")
