import streamlit as st

from styles.kc_theme import (
    inject_kc_theme, page_header, card_open, card_close, badge,
    edge_tag, status_banner, footer, data_timestamp,
)
from auth import render_account_sidebar
from engines.player_of_the_day import get_mlb_player_of_the_day
from engines.live_sync import sync_latest_button

inject_kc_theme()
render_account_sidebar()

page_header(
    "MLB Player of the Day",
    "This app's best real matchup edge, by the numbers — not a prediction, not a lock.",
    eyebrow="LIVE",
)

# Signal window — Season is the default formula; L25/L15/L10/L5 re-run
# the same pick logic with the opposing starters' splits sliced to
# their last N games. HR/Hit/K Scores are Baseball Savant SEASON
# percentiles in every window (Savant doesn't publish windowed
# percentiles, and this app doesn't fake them) — the window changes
# the starter-weakness evidence, labeled below.
sync_latest_button(key="sync_potd")

_win_opts = {"Season": "season", "L25": "l25", "L15": "l15", "L10": "l10", "L5": "l5"}
_win_choice = st.segmented_control(
    "Starter-signal window", list(_win_opts.keys()), default="Season",
    key="potd_window", label_visibility="collapsed",
)
_win_label = _win_choice or "Season"

pick, candidates, error = get_mlb_player_of_the_day(window=_win_opts.get(_win_label, "season"))

if error and not candidates:
    status_banner("info", error)
    footer()
    st.stop()

# -----------------------------------------------------
# THE PICK
# -----------------------------------------------------
st.markdown(card_open(f'\u2b50 {pick["name"]} \u2014 {pick["team"]}'), unsafe_allow_html=True)

top_line = (
    badge(f'Bats {pick["bats"]}', "neutral")
    + badge(f'vs {pick["opponent"]}', "neutral")
    + badge(f'Score {pick["score"]}', "accent")
)
st.markdown(f'<div>{top_line}</div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
c1.metric("HR Score", pick["hr_score"] if pick["hr_score"] is not None else "N/A",
          help="Real Baseball Savant percentile average of Barrel% and Hard-Hit%.")
c2.metric("Hit Score", pick["hit_score"] if pick["hit_score"] is not None else "N/A",
          help="Real Baseball Savant percentile average of xBA and Hard-Hit%.")
c3.metric("K Score (caution)", pick["k_score"] if pick["k_score"] is not None else "N/A",
          help="Real Savant Whiff% percentile. HIGHER = whiffs more than league average. "
               "Shown as a risk flag, not counted toward the score.")

st.caption(f'Lineup source: {pick["lineup_note"]}')

st.markdown("**Why this pick — real signals, not a vibe:**")
st.markdown(
    f"- Batter quality (avg HR/Hit Score): **{pick['batter_quality']}** / 100 "
    f"(real Baseball Savant percentiles this season)"
)
if pick["pitcher_signals"]:
    for s in pick["pitcher_signals"]:
        st.markdown(f"- Opposing starter real weakness ({_win_label}): **{s}**")
elif pick["pitcher_note"]:
    st.markdown(f"- Opposing starter matchup: _{pick['pitcher_note']}_ (batter quality alone drove this pick)")
else:
    st.markdown("- No real starter-weakness signals fired for this matchup \u2014 picked on batter quality alone.")

if pick["k_score"] is not None and pick["k_score"] >= 70:
    st.markdown(edge_tag(f'Elevated real strikeout risk \u2014 K Score {pick["k_score"]}', "risk"),
                unsafe_allow_html=True)

st.markdown(card_close(), unsafe_allow_html=True)

# -----------------------------------------------------
# FULL BOARD
# -----------------------------------------------------
with st.expander(f"See the full ranked board ({len(candidates)} real candidates today)"):
    st.caption(
        "Every player here is in a real today's/last real lineup with a real Baseball Savant "
        "sample. Score = avg(HR Score, Hit Score) + 10 per real pitcher-weakness signal. "
        "Sorted highest to lowest."
    )
    rows = []
    for c in candidates[:25]:
        rows.append({
            "Player": c["name"], "Team": c["team"], "Bats": c["bats"], "Opp": c["opponent"],
            "HR Score": c["hr_score"], "Hit Score": c["hit_score"], "K Score": c["k_score"],
            "Pitcher signals": len(c["pitcher_signals"]), "Score": c["score"],
        })
    st.dataframe(rows, width="stretch", hide_index=True)

data_timestamp("Rankings computed")
footer()
