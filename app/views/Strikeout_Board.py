"""
Strikeout Board — projected K line for every posted probable starter
on today's MLB slate, sorted highest projection first.

Runs inside app.py's loader (no st.set_page_config here). The formula
and all inputs are shown on the page — see engines/k_projection.py.
"""
import json

import pandas as pd
import streamlit as st

from styles.kc_theme import inject_kc_theme, card, footer, COLOR
from styles.table_style import style_stat_table
from engines.k_projection import get_slate_k_projections
from engines.pitcher_trends import render_pitcher_trend
from engines.live_sync import sync_latest_button

inject_kc_theme()

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">STRIKEOUT</span>'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">BOARD</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_kboard")

# Projection basis — Season is the original formula (stable, but by
# midseason it can lag a starter's current pace: it still averages in
# April ramp-ups and short hooks). L10 form runs the SAME formula on
# each starter's last 10 appearances: tonight's actual leash. Compare
# both against your book's line; the L5 avg column shows what each
# starter has ACTUALLY done lately.
_basis_opts = {"Season": "season", "L10 form": "l10"}
_basis_choice = st.segmented_control(
    "Projection basis", list(_basis_opts.keys()), default="Season",
    key="kb_basis", label_visibility="collapsed",
)
_basis_label = _basis_choice or "Season"

rows, warning = get_slate_k_projections(basis=_basis_opts.get(_basis_label, "season"))

if warning:
    st.warning(warning)

projected = [r for r in rows if r.get("proj") is not None]
unprojected = [r for r in rows if r.get("proj") is None]

if not rows:
    st.info("No games on today's slate.")
else:
    with card("k_board"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Projected K \u2014 today\'s probable starters</div>'
            f'<div class="pf-card-subtitle">proj K = (K/9 \u00f7 9) \u00d7 innings per start \u00d7 opponent K factor \u2014 '
            f'every input is in the table. This app\'s own projection from real Statcast + MLB team stats, '
            f'not a sportsbook line and not a certified prediction. '
            f'Basis: <b>{_basis_label}</b> \u2014 pitcher inputs from '
            f'{"the full season" if _basis_label == "Season" else "his last 10 appearances"}. '
            f"vs Opp = his real K average against tonight's opponent, this season + last "
            f"(meetings in parentheses; \u2014 means they haven't met).</div>",
            unsafe_allow_html=True,
        )
        if projected:
            df = pd.DataFrame([
                {
                    "Pitcher": r["pitcher"],
                    "Game": r["matchup"],
                    "Team": r["team"],
                    "Opp": r["opp"],
                    "IP/GS": r["ip_gs"],
                    "K/9": r["k9"],
                    "Opp K%": r["opp_k_pct"],
                    "L5 avg": r.get("l5_avg"),
                    "vs Opp": (f'{r["vs_opp_avg"]} ({r["vs_opp_n"]})'
                               if r.get("vs_opp_avg") is not None else "\u2014"),
                    "Proj K": r["proj"],
                }
                for r in projected
            ]).sort_values("Proj K", ascending=False).set_index("Pitcher")
            st.dataframe(
                style_stat_table(
                    df,
                    favor_high=["Proj K", "K/9", "Opp K%", "L5 avg"],
                    gradient=True,
                ),
                width="stretch",
                height=min(56 + 35 * len(df), 900),
            )
            st.caption(
                "IP/GS is estimated from Statcast out events (same basis as the Splits table \u2014 "
                "no official box-score innings feed). Opp K% is that lineup's real season strikeout "
                "rate from MLB's team stats; its effect is capped at \u00b115%. Compare Proj K against "
                "your book's line \u2014 the gap is the read, not the raw number."
            )
        else:
            st.info("No projectable starters yet \u2014 probables usually fill in through the morning.")

    # ---- Game-by-game K trend for any starter on the board ----
    if projected:
        with card("k_trend"):
            st.markdown(
                f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Pitcher trend \u2014 game by game</div>'
                f'<div class="pf-card-subtitle">Pick a starter from today\'s board \u00b7 real per-start '
                f'results from MLB official box-score game logs \u00b7 chips show how many starts cleared '
                f'the line in each window.</div>',
                unsafe_allow_html=True,
            )
            _by_name = {r["pitcher"]: r for r in projected if r.get("pid")}
            _pick = st.selectbox(
                "Pitcher",
                ["Select a pitcher\u2026"] + list(_by_name.keys()),
                key="kb_trend_pick",
                label_visibility="collapsed",
            )
            if _pick in _by_name:
                _r = _by_name[_pick]
                _t_stat = st.segmented_control(
                    "Stat", ["Strikeouts", "Earned Runs", "Hits Allowed", "Walks", "Innings"],
                    default="Strikeouts", key="kb_trend_stat", label_visibility="collapsed",
                ) or "Strikeouts"
                _t_win = st.segmented_control(
                    "Window", ["Season", "L25", "L10", "L5"],
                    default="L10", key="kb_trend_win", label_visibility="collapsed",
                ) or "L10"
                _t_line = float(st.segmented_control(
                    "Line", ["3.5", "4.5", "5.5", "6.5", "7.5"],
                    default="5.5", key="kb_trend_line", label_visibility="collapsed",
                ) or "5.5")
                render_pitcher_trend(_r["pid"], _pick, _t_stat, _t_win, line=_t_line)
                _vs_bit = (
                    f" \u00b7 vs {_r['opp']} history: {_r['vs_opp_avg']} K avg over "
                    f"{_r['vs_opp_n']} meeting(s)"
                    if _r.get("vs_opp_avg") is not None
                    else f" \u00b7 no starts vs {_r['opp']} since last season"
                )
                st.caption(f"Tonight's projection: {_r['proj']} K vs {_r['opp']}" + _vs_bit)

    if unprojected:
        with st.expander(f"\u26a0\ufe0f Not projected ({len(unprojected)})"):
            for r in unprojected:
                st.caption(f"{r['matchup']} \u2014 {r['pitcher']} ({r['team']}): {r.get('status', 'no data')}")

footer()
