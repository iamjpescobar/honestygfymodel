import streamlit as st
import pandas as pd

from app.engines.roster import get_team_roster
from app.engines.statcast_engine import get_batter_statcast, get_pitcher_statcast
from app.engines.slam_engine import build_slam_score
from app.engines.danger_zone import build_danger_zone
from app.engines.pitcher_danger_zone import build_pitcher_danger_zone
from app.engines.matchup_engine import get_matchup_rank
from app.engines.bvp_engine import get_bvp_history
from app.engines.pitch_affinity_engine import build_pitch_affinity


# ============================
# KC THEME
# ============================

def kc_header(title, subtitle=""):
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(90deg, #0a1a2f 0%, #1b2b4f 50%, #7d3cff 100%);
            padding: 18px 24px;
            border-radius: 12px;
            box-shadow: 0 0 18px rgba(125,60,255,0.6);
            color: white;
            margin-bottom: 12px;
        ">
            <h2 style="margin:0;">{title}</h2>
            <p style="margin:4px 0 0 0; color:#cfd8dc;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kc_card(content_html):
    st.markdown(
        f"""
        <div style="
            background-color:#0a1a2f;
            padding:18px;
            border-radius:12px;
            box-shadow:0px 0px 14px #7d3cff;
            color:white;
            font-size:16px;
            margin-bottom:12px;
        ">
            {content_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def kc_section(title, subtitle=""):
    st.markdown(
        f"""
        <div style="
            margin-top:18px;
            background-color:#0a1a2f;
            padding:14px;
            border-radius:10px;
            color:white;
        ">
            <b style="color:#7d3cff;">{title}</b><br>
            <span style="color:#cfd8dc;">{subtitle}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================
# PAGE CONFIG
# ============================

st.set_page_config(page_title="KC Lineup Dashboard", layout="wide")

kc_header(
    "KC Lineup Dashboard",
    "SLAM • Danger Zone • Matchup • BvP • Pitch Affinity • Whiff%"
)

# ============================
# SIDEBAR CONTROLS
# ============================

with st.sidebar:
    kc_card("<b>Select Team & Pitcher</b><br><span style='color:#cfd8dc;'>Drives the whole dashboard.</span>")

    teams = ["KC", "PHI", "NYY", "LAD", "ATL", "HOU", "BAL", "TEX"]
    team = st.selectbox("Team", teams, index=0)

    roster_df = get_team_roster(team)
    pitchers_df = roster_df[roster_df["Role"] == "P"]
    pitcher_name = st.selectbox("Pitcher", pitchers_df["Name"].tolist())


# ============================
# PITCHER PROFILE
# ============================

pitcher_row = roster_df[roster_df["Name"] == pitcher_name].iloc[0]
pitcher_id = pitcher_row.get("MLBAM_ID", 0)
pitcher_team = pitcher_row.get("Team", team)

pitcher_profile = get_pitcher_statcast(pitcher_id)
pitcher_grid = build_pitcher_danger_zone(pitcher_profile)

# ============================
# TOP ROW: PITCHER CARD + GRID
# ============================

col1, col2 = st.columns([1, 1])

with col1:
    kc_card(
        f"""
        <b style="font-size:20px;">{pitcher_name}</b><br>
        <span style="color:#cfd8dc;">{pitcher_team}</span><br><br>

        <b style="color:#ffcc00;">Vulnerability Profile</b><br>
        • HR/BBE: {pitcher_profile.get("HR/BBE", 0)}<br>
        • HH %: {pitcher_profile.get("HH %", 0)}<br>
        • LD %: {pitcher_profile.get("LD %", 0)}<br>
        • Brl %: {pitcher_profile.get("Brl %", 0)}<br>
        • ZoneContact %: {pitcher_profile.get("ZoneContact %", 0)}<br>
        • Whiff %: {pitcher_profile.get("Whiff %", 0)}<br><br>

        <b style="color:#7d3cff;">Pitch Arsenal</b><br>
        {"<br>".join([f"• {k}: {v}%" for k, v in pitcher_profile.get("Pitch Arsenal", {}).items()])}
        """
    )

with col2:
    kc_section("Pitcher Danger Zone Grid", "High / Mid / Low vs Inside / Middle / Outside")
    st.dataframe(
        pitcher_grid.style.background_gradient(cmap="inferno"),
        use_container_width=True,
    )

# ============================
# FULL LINEUP TABLE
# ============================

kc_section("Full Lineup vs Selected Pitcher", "SLAM • Danger Zone • Matchup • BvP • Statcast • Whiff%")

batters_df = roster_df[roster_df["Role"] != "P"].copy()

lineup_rows = []

for _, row in batters_df.iterrows():
    batter_name = row["Name"]
    batter_id = row["MLBAM_ID"]
    batter_pos = row.get("Pos", "")

    batter_profile = get_batter_statcast(batter_id)

    dz_score, dz_tag = build_danger_zone(batter_profile)
    slam_score, slam_tag = build_slam_score(batter_profile, pitcher_profile)
    matchup_rank, matchup_color = get_matchup_rank(batter_profile, pitcher_profile)
    bvp_history = get_bvp_history(batter_id, pitcher_id)

    lineup_rows.append(
        {
            "Name": batter_name,
            "Pos": batter_pos,
            "SLAM": slam_score,
            "DangerZone": dz_score,
            "Matchup": matchup_rank,
            "Brl%": batter_profile.get("Brl %", 0),
            "HH%": batter_profile.get("HH %", 0),
            "PullAir%": batter_profile.get("PullAir %", 0),
            "LD%": batter_profile.get("LD %", 0),
            "Whiff%": batter_profile.get("Whiff %", 0),
            "BvP": bvp_history,
        }
    )

lineup_df = pd.DataFrame(lineup_rows)


def style_lineup(df):
    return df.style.background_gradient(subset=["SLAM"], cmap="PuBu") \
                     .background_gradient(subset=["DangerZone"], cmap="YlOrBr")


st.dataframe(style_lineup(lineup_df), use_container_width=True, height=400)

# ============================
# MATCHUP BARS
# ============================

kc_section("Matchup Strength Bars", "Visual SLAM + Danger Zone comparison")

bars_df = lineup_df[["Name", "SLAM", "DangerZone"]].set_index("Name")
st.bar_chart(bars_df)

# ============================
# FOCUS BATTER DETAIL
# ============================

kc_section("Focus Batter Detail", "SLAM Gauge • Danger Zone • Whiff% • Pitch Affinity")

focus_batter = st.selectbox("Focus Batter", lineup_df["Name"].tolist())

focus_row = lineup_df[lineup_df["Name"] == focus_batter].iloc[0]
focus_batter_id = batters_df[batters_df["Name"] == focus_batter]["MLBAM_ID"].iloc[0]
focus_profile = get_batter_statcast(focus_batter_id)

affinity = build_pitch_affinity(focus_profile, pitcher_profile)
affinity_df = pd.DataFrame(
    [{"Pitch": k, "Affinity": v} for k, v in affinity.items()]
).set_index("Pitch")

colA, colB = st.columns([1, 1])

with colA:
    kc_card(
        f"""
        <b style="font-size:20px;">{focus_batter}</b><br>
        <span style="color:#cfd8dc;">vs {pitcher_name}</span><br><br>

        <b style="color:#7d3cff;">SLAM Gauge</b><br>
        """
    )
    st.progress(min(max(focus_row["SLAM"] / 100.0, 0.0), 1.0))

    kc_card(
        f"""
        <b style="color:#ffcc00;">Danger Zone Score</b><br>
        {focus_row["DangerZone"]}<br><br>
        <b style="color:#ffcc00;">Whiff %</b><br>
        {focus_profile.get("Whiff %", 0)}
        """
    )

with colB:
    kc_section("Pitch Affinity vs Arsenal", "Higher = better matchup vs that pitch type")
    st.bar_chart(affinity_df)

# ============================
# DEBUG
# ============================

with st.expander("Debug Info"):
    st.write("Pitcher Profile:", pitcher_profile)
    st.write("Lineup DataFrame:", lineup_df)
