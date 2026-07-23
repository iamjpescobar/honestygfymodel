import streamlit as st

from styles.kc_theme import (
    inject_kc_theme, page_header, card_open, card_close, badge,
    edge_tag, status_banner, footer, data_timestamp,
)
from auth import render_account_sidebar
from engines.player_of_the_day import get_mlb_player_of_the_day
from engines.live_sync import sync_latest_button
from engines.calibration import log_picks, grade_pending, summary

inject_kc_theme()
render_account_sidebar()

page_header(
    "MLB Player of the Day",
    "Tonight's best EXTRA-BASE HIT play — double, triple, or home run.",
    eyebrow="XBH PLAY",
)

status_banner(
    "info",
    "This pick is an EXTRA-BASE HIT play: it wins on a double, triple, or home run. "
    "It ranks on xSLG, Barrel%, Hard-Hit% and Exit Velocity, with a real strikeout "
    "penalty (a K is a plate appearance with zero chance of an extra-base hit), then "
    "tonight's matchup Edge, what the starter actually allows in extra bases, an "
    "XBH-tuned park factor, and wind. League-wide a hitter records an extra-base hit "
    "in roughly one game in three \u2014 the tracked record below grades this pick on "
    "exactly that, so judge it over weeks, not nights."
)

sync_latest_button(key="sync_potd")

_win_opts = {"Season": "season", "L25": "l25", "L15": "l15", "L10": "l10", "L5": "l5"}
_win_choice = st.segmented_control(
    "Starter-signal window", list(_win_opts.keys()), default="L15",
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
c1.metric("XBH Score", pick.get("xbh_score") if pick.get("xbh_score") is not None else "N/A",
          help="Extra-base-hit skill from real Savant percentiles: xSLG (35%), Barrel% "
               "(25%), Hard-Hit% (20%), Exit Velocity (10%), with a K% penalty (10%).")
c2.metric("With matchup", pick.get("hr_edge") if pick.get("hr_edge") is not None else "N/A",
          help="XBH Score plus the Edge layer: career BvP vs this starter, zone fit, "
               "and the bullpen behind him.")
c3.metric("K Score (caution)", pick["k_score"] if pick["k_score"] is not None else "N/A",
          help="Real Savant Whiff% percentile. HIGHER = whiffs more than league average. "
               "Shown as a risk flag, not counted toward the score.")

st.caption(f'Lineup source: {pick["lineup_note"]}')

st.markdown("**Why this pick — real signals, not a vibe:**")
st.markdown(
    f"- Batter quality (avg HR/Hit Score): **{pick['batter_quality']}** / 100 "
    f"(real Baseball Savant percentiles this season)"
)
_why = []
if pick.get("bvp_adj"):
    _why.append(f'BvP {pick["bvp_adj"]:+d} ({pick.get("bvp_line") or "career line"})')
if pick.get("zone_adj"):
    _why.append(f'Zone fit {pick["zone_adj"]:+d} ({pick.get("zone_note") or "zone overlap"})')
if pick.get("pen_adj"):
    _why.append(f'Bullpen {pick["pen_adj"]:+d} ({pick.get("pen_note") or "pen profile"})')
if pick.get("pxbh_adj"):
    _why.append(f'Starter {pick["pxbh_adj"]:+d} ({pick.get("pxbh_note") or "extra bases allowed"})')
if pick.get("park_adj"):
    _why.append(f'Park {pick["park_adj"]:+d} ({pick.get("park_note") or pick.get("park_factor")})')
if pick.get("wind_adj"):
    _why.append(f'Wind {pick["wind_adj"]:+d} ({pick.get("wind_note") or "field-relative"})')
_kp = (pick.get("xbh_parts") or {}).get("_k_adj")
if _kp:
    _why.append(f'Strikeout rate {_kp:+.1f} '
                f'({"low-K bat, more balls in play" if _kp > 0 else "high-K bat, fewer chances"})')

if _why:
    st.markdown("**Why this bat tonight:**")
    for _w in _why:
        st.markdown(f"- {_w}")
else:
    st.caption("No matchup, park, or wind adjustments cleared their thresholds tonight — "
               "this pick is ranking on power skill alone.")

# Calibration — graded on HOME RUNS, matching what this pick is for.
try:
    log_picks("potd", [{"id": pick.get("id"), "name": pick.get("name"),
                        "team": pick.get("team")}])
    grade_pending()
    _cal = summary().get("potd", {})
    if _cal.get("total"):
        st.caption(
            f'Tracked record \u2014 this pick {_cal["question"]} '
            f'{_cal["hits"]}/{_cal["total"]} ({_cal["rate"]}%) over the graded period'
            + (f' \u00b7 {_cal["dnp"]} did not play (excluded)' if _cal.get("dnp") else "")
            + ". League-wide, a given hitter homers in roughly 1 game in 8, so a "
              "sustained rate above that is the bar this pick is trying to clear."
        )
    else:
        st.caption("Tracked record \u2014 tonight's pick is logged; home-run results "
                   "appear here once the games are final.")
except Exception:
    pass

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
