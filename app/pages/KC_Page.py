import streamlit as st
import pandas as pd

from engines.roster import get_all_teams, get_live_team_roster
from engines.statcast_engine import get_batter_statcast, get_pitcher_statcast
from engines.slam_engine import compute_slam_window
from engines.danger_zone import build_danger_zone
from engines.pitcher_danger_zone import build_pitcher_danger_zone
from engines.matchup_engine import compute_matchup_multiplier
from engines.bvp_engine import get_bvp_history
from engines.pitch_affinity_engine import compute_pitch_affinity_multiplier

from styles.kc_theme import inject_kc_theme, page_header, badge, card_open, card_close, footer
from styles.table_style import style_stat_table, plain_dark_table
from auth import render_account_sidebar

# ============================
# THEME
# ============================

inject_kc_theme()
render_account_sidebar()

page_header(
    "KC Lineup Dashboard",
    "SLAM \u2022 Danger Zone \u2022 Matchup \u2022 BvP \u2022 Pitch Affinity \u2022 Whiff%"
)

# ============================
# SIDEBAR CONTROLS
# ============================

with st.sidebar:
    st.header("Team & Pitcher")
    st.caption("Drives the whole dashboard.")

    teams = get_all_teams()
    if not teams:
        st.warning("Couldn't load the team list from the MLB Stats API right now.")
        st.stop()

    team = st.selectbox("Team", teams)

    roster = get_live_team_roster(team)
    pitchers = [p for p in roster if p.get("is_pitcher")]
    if not pitchers:
        st.warning(f"No pitchers found for {team} right now.")
        st.stop()

    pitcher_name = st.selectbox("Pitcher", [p["name"] for p in pitchers])


# ============================
# PITCHER PROFILE
# ============================

pitcher_row = next(p for p in pitchers if p["name"] == pitcher_name)
pitcher_id = pitcher_row.get("id")

pitcher_profile = get_pitcher_statcast(pitcher_id)
pitcher_grid = build_pitcher_danger_zone(pitcher_profile)

# ============================
# TOP ROW: PITCHER CARD + GRID
# ============================

col1, col2 = st.columns([1, 1])

with col1:
    st.markdown(card_open(pitcher_name, team), unsafe_allow_html=True)
    st.markdown(
        badge(f"HR/BBE {pitcher_profile.get('HR/BBE', 0)}", "neutral")
        + badge(f"HH% {pitcher_profile.get('HH %', 0)}", "neutral")
        + badge(f"LD% {pitcher_profile.get('LD %', 0)}", "neutral")
        + badge(f"Brl% {pitcher_profile.get('Brl %', 0)}", "neutral")
        + badge(f"ZoneContact% {pitcher_profile.get('ZoneContact %', 0)}", "neutral")
        + badge(f"Whiff% {pitcher_profile.get('Whiff %', 0)}", "neutral"),
        unsafe_allow_html=True,
    )
    st.markdown("**Pitch Arsenal**")
    arsenal = pitcher_profile.get("Pitch Arsenal", {})
    if arsenal:
        st.markdown(
            "".join(badge(f"{k} {v}%", "accent") for k, v in arsenal.items()),
            unsafe_allow_html=True,
        )
    else:
        st.caption("No arsenal data available.")
    st.markdown(card_close(), unsafe_allow_html=True)

with col2:
    st.markdown(card_open("Pitcher Danger Zone Grid", "High / Mid / Low vs Inside / Middle / Outside"), unsafe_allow_html=True)
    styled_pitcher_grid = style_stat_table(pitcher_grid, favor_high=list(pitcher_grid.columns))
    st.dataframe(styled_pitcher_grid, width="stretch")
    st.markdown(card_close(), unsafe_allow_html=True)

# ============================
# FULL LINEUP TABLE
# ============================

st.markdown(card_open("Full Lineup vs Selected Pitcher", "SLAM \u2022 Danger Zone \u2022 Matchup \u2022 BvP \u2022 Statcast \u2022 Whiff%"), unsafe_allow_html=True)

batters_roster = [p for p in roster if not p.get("is_pitcher")]

if not batters_roster:
    st.info(f"No position players found for {team} right now.")
    st.stop()

lineup_rows = []

for row in batters_roster:
    batter_name = row["name"]
    batter_id = row.get("id")
    batter_pos = row.get("position", "")

    batter_profile = get_batter_statcast(batter_id) if batter_id else {}

    required_keys = {"PullAir %", "LD %", "GB %", "Brl %", "HH %"}
    if required_keys.issubset(batter_profile.keys()):
        dz_grid = build_danger_zone(batter_profile)
        dz_score = round(float(dz_grid.values.mean()), 2)  # single-number summary of the 3x3 grid
    else:
        dz_score = 0.0

    slam_result = compute_slam_window(batter_id, "season", "bbe")
    slam_score = slam_result["slam_score"] if slam_result["slam_score"] is not None else 0.0
    matchup_mult, matchup_tag = compute_matchup_multiplier(batter_profile, pitcher_profile)
    bvp_history = get_bvp_history(pitcher_name, batter_name)

    lineup_rows.append(
        {
            "Name": batter_name,
            "Pos": batter_pos,
            "SLAM": slam_score,
            "DangerZone": dz_score,
            "Matchup": matchup_mult,
            "Brl%": batter_profile.get("Brl %", 0),
            "HH%": batter_profile.get("HH %", 0),
            "PullAir%": batter_profile.get("PullAir %", 0),
            "LD%": batter_profile.get("LD %", 0),
            "Whiff%": batter_profile.get("Whiff %", 0),
            "BvP PA": len(bvp_history) if bvp_history is not None else 0,
        }
    )

lineup_df = pd.DataFrame(lineup_rows)

styled_lineup = style_stat_table(lineup_df, favor_high=["SLAM", "DangerZone", "Matchup"])
st.dataframe(styled_lineup, width="stretch", height=400)
st.markdown(card_close(), unsafe_allow_html=True)

# ============================
# MATCHUP BARS
# ============================

st.markdown(card_open("Matchup Strength Bars", "Visual SLAM + Danger Zone comparison"), unsafe_allow_html=True)
bars_df = lineup_df[["Name", "SLAM", "DangerZone"]].set_index("Name")
st.bar_chart(bars_df, color=["#00E5FF", "#0E7C86"])
st.markdown(card_close(), unsafe_allow_html=True)

# ============================
# FOCUS BATTER DETAIL
# ============================

st.markdown(card_open("Focus Batter Detail", "SLAM \u2022 Danger Zone \u2022 Whiff% \u2022 Pitch Affinity"), unsafe_allow_html=True)
focus_batter = st.selectbox("Focus Batter", lineup_df["Name"].tolist())
st.markdown(card_close(), unsafe_allow_html=True)

focus_row = lineup_df[lineup_df["Name"] == focus_batter].iloc[0]
focus_batter_id = next((r["id"] for r in batters_roster if r["name"] == focus_batter), None)
focus_profile = get_batter_statcast(focus_batter_id) if focus_batter_id else {}

pitcher_arsenal = pitcher_profile.get("Pitch Arsenal", {})
affinity_mult = compute_pitch_affinity_multiplier(focus_profile, pitcher_arsenal)

colA, colB = st.columns([1, 1])

with colA:
    st.markdown(card_open(focus_batter, f"vs {pitcher_name}"), unsafe_allow_html=True)
    st.markdown('<div class="pf-metric-label">SLAM Score</div>', unsafe_allow_html=True)
    st.progress(min(max(focus_row["SLAM"] / 100.0, 0.0), 1.0))
    st.markdown(
        f'<div class="pf-metric-value">{focus_row["DangerZone"]}</div>'
        f'<div class="pf-metric-label">Danger Zone Score</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="pf-metric-value">{focus_profile.get("Whiff %", 0)}</div>'
        f'<div class="pf-metric-label">Whiff %</div>',
        unsafe_allow_html=True,
    )
    st.markdown(card_close(), unsafe_allow_html=True)

with colB:
    st.markdown(card_open("Pitch Affinity vs Arsenal", "Single composite multiplier \u2014 this app doesn't have a per-pitch-type affinity breakdown implemented"), unsafe_allow_html=True)
    st.markdown(badge(f"Affinity Multiplier {affinity_mult:.2f}", "accent"), unsafe_allow_html=True)
    st.markdown(card_close(), unsafe_allow_html=True)

# ============================
# DEBUG
# ============================

with st.expander("Debug Info"):
    st.write("Pitcher Profile:", pitcher_profile)
    st.write("Lineup DataFrame:", lineup_df)

footer()
