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
from engines.statcast_engine import get_pitcher_k_game_log_json
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
                f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Season K trend \u2014 game by game</div>'
                f'<div class="pf-card-subtitle">Pick a starter from today\'s board \u00b7 real strikeouts '
                f'per appearance from his own Statcast rows, in schedule order.</div>',
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
                try:
                    _trend = json.loads(get_pitcher_k_game_log_json(_r["pid"]))
                except Exception:
                    _trend = []
                if not _trend:
                    st.caption("No Statcast appearances on file for this pitcher yet.")
                else:
                    _tdf = pd.DataFrame(_trend)
                    # MM-DD labels; doubleheader same-day starts get a
                    # suffix so the chart doesn't merge two appearances
                    _lbls, _seen = [], {}
                    for _d in _tdf["date"].str[5:]:
                        _seen[_d] = _seen.get(_d, 0) + 1
                        _lbls.append(_d if _seen[_d] == 1 else f"{_d} ({_seen[_d]})")
                    _tdf["Game"] = _lbls
                    st.bar_chart(
                        _tdf.set_index("Game")["k"],
                        color=COLOR["stat_high"],
                        height=240,
                    )
                    _ks = [t["k"] for t in _trend]
                    _avg = sum(_ks) / len(_ks)
                    st.caption(
                        f"{len(_ks)} appearances \u00b7 season avg {_avg:.1f} K \u00b7 "
                        f"last 5: {', '.join(str(x) for x in _ks[-5:])} \u00b7 "
                        f"tonight's projection: {_r['proj']} vs {_r['opp']}"
                        + (f" \u00b7 vs {_r['opp']} history: {_r['vs_opp_avg']} K avg over "
                           f"{_r['vs_opp_n']} meeting(s)"
                           if _r.get('vs_opp_avg') is not None else
                           f" \u00b7 no starts vs {_r['opp']} since last season")
                    )

    if unprojected:
        with st.expander(f"\u26a0\ufe0f Not projected ({len(unprojected)})"):
            for r in unprojected:
                st.caption(f"{r['matchup']} \u2014 {r['pitcher']} ({r['team']}): {r.get('status', 'no data')}")

footer()
