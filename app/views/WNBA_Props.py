"""
WNBA Props Board — the best prop bets on tonight's slate.
Formula, weights, and floors in engines/wnba_props.py.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from styles.kc_theme import inject_kc_theme, card, footer, COLOR
from styles.table_style import style_stat_table, render_html_table, score_bar
from engines.wnba_props import (
    build_props, STATS, MIN_GP, MIN_MPG, MIN_LOG,
    W_CONSISTENCY, W_FORM, W_MATCHUP, W_PACE,
)
from engines.live_sync import sync_latest_button
from engines.calibration import log_picks, grade_pending, summary

_GAMES = Path(__file__).resolve().parent.parent / "data" / "wnba" / "games.json"

inject_kc_theme()

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">PROPS</span>'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">BOARD</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_wnba_props", include_data_package=True)


# CACHED. Streamlit re-runs this whole script on every widget
# interaction, so without this the slate JSON was parsed from disk on
# each click. The file only changes when the nightly build publishes.
@st.cache_data(ttl=900, show_spinner=False)
def _load_games():
    try:
        return json.loads(_GAMES.read_text()).get("games", [])
    except Exception:
        return []


games = _load_games()
if not games:
    st.info("No WNBA slate loaded \u2014 press \u27f3 Sync latest to pull the current data build.")
    footer()
    st.stop()

_stat = st.segmented_control(
    "Stat", list(STATS.keys()), default="Points",
    key="wprops_stat", label_visibility="collapsed",
) or "Points"
_win_opts = {"L5": "l5", "L10": "l10"}
_win_label = st.segmented_control(
    "Form window", list(_win_opts.keys()), default="L10",
    key="wprops_win", label_visibility="collapsed",
) or "L10"

# Cache key = the slate file's mtime. Changes exactly when the nightly
# build publishes new data, and never otherwise — so switching stat or
# window is instant while a fresh build still invalidates correctly.
_build_key = str(_GAMES.stat().st_mtime) if _GAMES.exists() else "none"
rows, unrated = build_props(games, _stat, _win_opts[_win_label],
                            cache_key=_build_key)

with card("wprops"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Best {_stat.lower()} props tonight</div>'
        f'<div class="pf-card-subtitle" style="color:{COLOR["magenta_purple"]};">'
        f'Ranked by consistency ({W_CONSISTENCY:.0%}), form ({W_FORM:.0%}), positional matchup '
        f'({W_MATCHUP:.0%}), and game pace ({W_PACE:.0%}) \u00b7 the Line is each player\'s own recent '
        f'average rounded to the nearest .5 (this app carries no odds) \u00b7 Clears = how often he beat '
        f'that number in his last 15; Floor = how often he stayed within 20% of it even when he missed '
        f'\u2014 that second number is what separates a safe prop from a coin flip \u00b7 '
        f'floors: {MIN_GP} games, {MIN_MPG:.0f} min/game, {MIN_LOG} games of log history.</div>',
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No rated props yet \u2014 the board needs a few more games of log data.")
    else:
        top = rows[:20]
        df = pd.DataFrame([
            {
                "Player": r["player"],
                "Pos": r["pos"],
                "Team": r["team"],
                "Opp": r["opp"],
                "Line": f'{r["line"]:.1f}',
                "Score": f'{r["score"]:.1f}',
                "Clears (L15)": r["l15_txt"],
                "Floor (L15)": r.get("floor_txt", "\u2014"),
                "Form": f'{r["form"]:.0f}' if r.get("form") is not None else "\u2014",
                "Matchup": f'{r["matchup"]:.0f}' if r.get("matchup") is not None else "\u2014",
                "Pace": f'{r["pace"]:.0f}' if r.get("pace") is not None else "\u2014",
            }
            for r in top
        ])
        render_html_table(
            style_stat_table(
                df,
                favor_high=["Score", "Form", "Matchup", "Pace"],
                gradient=True
            ).format({"Score": score_bar("stat_high")})
        ,
            key="wnba_props_101")

        # Calibration: log tonight's top picks and show the record.
        try:
            log_picks("wnba_props", [
                {"id": r.get("id"), "name": r["player"], "team": r["team"],
                 "stat": STATS[_stat]["key"], "line": r["line"]}
                for r in top[:10] if r.get("id")
            ])
            grade_pending()
            _cal = summary().get("wnba_props", {})
            if _cal.get("total"):
                st.caption(
                    f'Tracked record \u2014 this board\'s picks {_cal["question"]} '
                    f'{_cal["hits"]}/{_cal["total"]} ({_cal["rate"]}%) over the graded period'
                    + (f' \u00b7 {_cal["dnp"]} did not play (excluded)' if _cal.get("dnp") else "")
                )
            else:
                st.caption("Tracked record \u2014 tonight's picks are logged; results appear "
                           "here once the games are final.")
        except Exception:
            pass

        with st.expander("\U0001F50D Why each prop \u2014 the components behind the score"):
            for r in top:
                st.caption(
                    f'**{r["player"]}** ({r["team"]} vs {r["opp"]}) \u2014 '
                    f'{_stat} {r["line"]:.1f} \u00b7 score {r["score"]:.1f} \u00b7 '
                    f'cleared {r["l15_txt"]}, stayed near it {r.get("floor_txt", "?")} \u00b7 '
                    f'{r.get("why", "")}'
                )

if unrated:
    with st.expander(f"\u26a0\ufe0f Not rated ({len(unrated)})"):
        # No [:40] slice. The whole point of this list is that a player
        # who isn't ranked still gets NAMED with a reason — truncating it
        # recreated the exact problem it exists to solve, silently hiding
        # players on a busy slate. The expander is collapsed by default,
        # so length costs nothing.
        for u in unrated:
            st.caption(f'{u["player"]} ({u.get("pos", "?")}, {u.get("team", "?")}): {u["reason"]}')

footer()
