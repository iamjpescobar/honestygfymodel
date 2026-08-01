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
from styles.table_style import (style_stat_table, render_html_table,
                                team_logo_cell)
from engines.daily_13 import (
    get_daily_13, MIN_HIT_RATE, MIN_GAMES, BOARD_SIZE,
    W_FORM, W_MATCHUP, W_CONTEXT, L15_GATE_HITS, L15_GATE_GAMES,
)
from engines.live_sync import sync_latest_button
from engines.calibration import log_picks, grade_pending, summary

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
        f'The 13 best bets to get a hit TONIGHT \u2014 a slate read, not a season leaderboard \u00b7 '
        f'floor to qualify: \u2265 {MIN_HIT_RATE:.0f}% of games with a hit and \u2265 {MIN_GAMES} games \u00b7 '
        f'ranked by recent form ({W_FORM:.0%}), tonight\'s pitcher matchup ({W_MATCHUP:.0%}), and '
        f'bullpen + lineup-slot context ({W_CONTEXT:.0%}) \u00b7 '
        f'\U0001F512 = hit in {L15_GATE_HITS}+ of his last {L15_GATE_GAMES} \u00b7 '
        f'every component is real and shown per row \u2014 cross it with the Game Card before acting.</div>',
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
                "Player": ("\U0001F512 " if r.get("locked") else "") + r["name"],
                "Team": r["team"],
                "Opp": r.get("opp", "\u2014"),
                "Tonight": f'{r["tonight"]:.1f}',
                # Oldest -> newest, full block = hit. Placed before the
                # L15/L5 counts so the shape reads first and the numbers
                # confirm it.
                # Header says what the dots mean, so no legend is needed.
                "Last 10": r.get("spark", ""),
                "L15": r.get("l15", "\u2014"),
                "L5": r.get("l5", "\u2014"),
                "Season": f'{r["rate"]:.1f}',
                "Form": f'{r.get("form", 0):.0f}',
                "Matchup": f'{r.get("matchup", 0):.0f}',
                "Context": f'{r.get("context", 0):.0f}',
                "Streak": str(r["streak"]),
                "Today": r.get("today", "roster"),
            }
            for r in rows
        ])
        render_html_table(
            style_stat_table(
                df,
                favor_high=["Tonight", "Form", "Matchup", "Context", "Season", "Streak"],
                gradient=True
            # Logos beside the abbreviations. Only possible since this
            # table moved to HTML — st.column_config.ImageColumn works
            # only inside st.dataframe. Text stays next to the mark so
            # the column still reads if an image fails to load.
            ).format({"Team": team_logo_cell(), "Opp": team_logo_cell()})
        ,
            key="daily_13_80")
        # Calibration: record tonight's board, grade past days, and
        # show the running record. This is what turns "the board looks
        # right" into a measured hit rate.
        log_picks("daily13", rows)
        grade_pending()
        _cal = summary().get("daily13", {})
        if _cal.get("total"):
            # The baseline and verdict ride along with the rate ON PURPOSE.
            # A bare "65%" reads as a strong result when the league-average
            # starter does about the same, and people size real bets off
            # this line.
            _base = _cal.get("baseline")
            _cap = (f'Tracked record \u2014 this board\'s picks {_cal["question"]} '
                    f'{_cal["hits"]}/{_cal["total"]} ({_cal["rate"]}%) over the graded period')
            if _base is not None:
                _cap += (f' \u00b7 league baseline {_base:.1f}% '
                         f'({_cal["edge"]:+.1f}) \u00b7 {_cal["verdict"]}')
            if _cal.get("dnp"):
                _cap += f' \u00b7 {_cal["dnp"]} did not play (excluded)'
            st.caption(_cap)
        else:
            st.caption("Tracked record \u2014 tonight's picks are logged; results appear "
                       "here once the games are final.")

        with st.expander("\U0001F50D Why each bat \u2014 the components behind tonight's score"):
            for r in rows:
                _lock = " \u00b7 \U0001F512 locked in" if r.get("locked") else ""
                st.caption(
                    f'**{r["name"]}** ({r["team"]} vs {r.get("opp", "?")}) \u2014 '
                    f'tonight {r["tonight"]:.1f}{_lock} \u00b7 '
                    f'form {r.get("form", 0):.0f} (L15 {r.get("l15", "?")}, L5 {r.get("l5", "?")}) \u00b7 '
                    f'matchup {r.get("matchup", 0):.0f} \u00b7 context {r.get("context", 0):.0f}'
                    + (f' \u00b7 {r["why"]}' if r.get("why") else "")
                )

        if len(rows) < BOARD_SIZE:
            st.caption(
                f"Only {len(rows)} hitter(s) clear the bar today \u2014 shown as-is, "
                f"no padding below the minimum."
            )

    st.caption(
        f"Game logs through {meta.get('data_through') or 'unknown'} "
        f"(build {meta.get('built') or '?'} \u00b7 press \u27f3 Sync latest to pull a newer one) \u00b7 "
        f"Playing-today guard: {meta.get('confirmed_teams', 0)} team(s) pooled from their CONFIRMED "
        f"lineup; the rest from rosters with a recent-activity filter (last game within 6 days of the "
        f"data build \u2014 {meta.get('inactive', 0)} inactive/IL name(s) filtered out). "
        f"Scanned {meta.get('scanned', 0)} hitters \u00b7 "
        f"{meta.get('qualified', 0)} met the bar \u00b7 "
        f"{meta.get('no_file', 0)} had no local game log (called up recently or no Statcast file yet). "
        f"Refreshes every 30 minutes."
    )

footer()
