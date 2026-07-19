"""
The Daily 13 — personal consistency board: the 13 most consistent
hitters on today's slate for at least one hit, minimum 60% of games
with a hit across their full season log, minimum 25 games.

Runs inside app.py's loader. Formula + bars documented in
engines/daily_13.py.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import inject_kc_theme, card, footer, COLOR
from styles.table_style import style_stat_table
from engines.daily_13 import get_daily_13, MIN_HIT_RATE, MIN_GAMES, BOARD_SIZE
from engines.live_sync import sync_latest_button

inject_kc_theme()

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">THE DAILY</span>'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">13</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_daily13", include_data_package=True)

with st.spinner("Scanning every hitter on today's slate\u2026 (first load of the day does the real work; it's cached after)"):
    rows, meta = get_daily_13()

if meta.get("warning"):
    st.warning(meta["warning"])

with card("daily13"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Most consistent hitters on today\'s slate</div>'
        f'<div class="pf-card-subtitle" style="color:{COLOR["magenta_purple"]};">'
        f'Hit% = share of games with \u2265 1 hit across every game in this app\'s Statcast files '
        f'(full current season \u00b7 the deepest real history the pipeline carries) \u00b7 '
        f'bar to make the board: \u2265 {MIN_HIT_RATE:.0f}% and \u2265 {MIN_GAMES} games \u00b7 '
        f'this is historical consistency, not tonight\'s probability \u2014 it ignores tonight\'s pitcher '
        f'by design; cross it with the Game Card before acting on it.</div>',
        unsafe_allow_html=True,
    )

    if not rows:
        st.info(
            f"No hitter on today's slate clears the {MIN_HIT_RATE:.0f}% / "
            f"{MIN_GAMES}-game bar right now \u2014 the board doesn't pad with "
            f"players below the minimum."
        )
    else:
        df = pd.DataFrame([
            {
                "Player": r["name"],
                "Team": r["team"],
                "GP": str(r["gp"]),
                "Games w/ Hit": str(r["hit_gp"]),
                "Hit%": f'{r["rate"]:.1f}',
                "Active streak": str(r["streak"]),
            }
            for r in rows
        ])
        st.dataframe(
            style_stat_table(
                df,
                favor_high=["Hit%", "Active streak"],
                gradient=True,
            ),
            width="stretch",
            height=min(56 + 35 * len(df), 560),
        )
        if len(rows) < BOARD_SIZE:
            st.caption(
                f"Only {len(rows)} hitter(s) clear the bar today \u2014 shown as-is, "
                f"no padding below the minimum."
            )

    st.caption(
        f"Game logs through {meta.get('data_through') or 'unknown'} "
        f"(build {meta.get('built') or '?'} \u00b7 press \u27f3 Sync latest to pull a newer one) \u00b7 "
        f"Scanned {meta.get('scanned', 0)} hitters across today's rosters \u00b7 "
        f"{meta.get('qualified', 0)} met the bar \u00b7 "
        f"{meta.get('no_file', 0)} had no local game log (called up recently or no Statcast file yet). "
        f"Refreshes every 30 minutes."
    )

footer()
