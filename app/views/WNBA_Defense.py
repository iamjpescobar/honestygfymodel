"""
WNBA Defense Matchup — the board of who's facing the softest defense
tonight, by position. Formula and floors in engines/wnba_defense.py.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from styles.kc_theme import SPORT_ACCENTS, inject_kc_theme, card, footer, COLOR
from styles.table_style import style_stat_table, render_html_table, tier_legend
from engines.wnba_defense import build_board, MIN_PLAYER_GP
from engines.live_sync import sync_latest_button
from engines.calibration import log_picks, grade_pending, summary

_GAMES = Path(__file__).resolve().parent.parent / "data" / "wnba" / "games.json"

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-sm);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">DEFENSE</span>'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">MATCHUP</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_wnba_def", include_data_package=True)


# CACHED. Streamlit re-runs this whole script on every widget
# interaction, so without this the slate JSON was parsed from disk on
# each click. The file only changes when the nightly build publishes.
@st.cache_data(ttl=900, show_spinner=False)
def _load_games():
    try:
        payload = json.loads(_GAMES.read_text())
        return payload.get("games", []), payload.get("generated_at")
    except Exception:
        return [], None


games, generated_at = _load_games()
if not games:
    st.info("No WNBA slate loaded \u2014 press \u27f3 Sync latest to pull the current data build.")
    footer()
    st.stop()

_stat = st.segmented_control(
    "Stat", ["Points", "Rebounds", "Assists"], default="Points",
    key="wdef_stat", label_visibility="collapsed",
) or "Points"
_win_opts = {"L5": "l5", "L10": "l10"}
_win_label = st.segmented_control(
    "Form window", list(_win_opts.keys()), default="L10",
    key="wdef_win", label_visibility="collapsed",
) or "L10"

# generated_at comes from the data build itself — the most honest cache
# key available, since it changes precisely when the numbers do.
rows, unrated = build_board(games, _stat, _win_opts[_win_label],
                            cache_key=str(generated_at))

with card("wdef"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{SPORT_ACCENTS["WNBA"]};">Softest {_stat.lower()} matchups tonight</div>'
        f'<div class="pf-card-subtitle" style="color:{COLOR["text_muted"]};">'
        f'Basketball has no starting-pitcher analog, so this is the honest equivalent: how much '
        f'{_stat.lower()} tonight\'s opponent actually ALLOWS to this player\'s position, measured against '
        f'the slate average \u00b7 Edge = the extra production that softness implies for his own '
        f'{_win_label} form (so volume matters \u2014 a bench player in a great spot still ranks below a '
        f'starter in a good one) \u00b7 real box-score data, minimum 5 team-games of positional data and '
        f'{MIN_PLAYER_GP} player games \u2014 anything thinner is listed unrated below, never estimated.</div>',
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No rated matchups yet \u2014 positional defense needs a few more games of data.")
    else:
        df = pd.DataFrame([
            {
                "Player": r["player"],
                "Pos": r["pos"],
                "Team": r["team"],
                "Opp": r["opp"],
                f"{_win_label} {_stat[:3]}": f'{r["form"]:.1f}',
                "Opp allows": f'{r["allowed"]:.1f}',
                "Slate avg": f'{r["league"]:.1f}',
                "Softness": f'{r["soft_pct"]:+.1f}%',
                "Edge": f'{r["edge"]:+.2f}',
            }
            for r in rows[:25]
        ])
        render_html_table(
            style_stat_table(
                df,
                favor_high=["Edge", "Softness", "Opp allows", f"{_win_label} {_stat[:3]}"],
                gradient=True
            )
        ,
            key="wnba_defense_94")
        # Direction matters more here than on any other board: a HIGH
        # "Opp allows" is good for the player being targeted and bad for
        # the defence allowing it. Without a key, that column reads
        # backwards to anyone who assumes green-is-good-for-the-team.
        tier_legend(
            favor_note="Colour reads from the PLAYER\u2019s side \u2014 the brightest "
                       "cells are the softest matchups to target.",
        )
        # Calibration: the defense board's top picks are graded against
        # each player's own recent form as the line — i.e. "did the soft
        # matchup actually produce more than his usual?"
        try:
            log_picks("wnba_defense", [
                {"id": r.get("id"), "name": r["player"], "team": r["team"],
                 "stat": {"Points": "pts", "Rebounds": "reb", "Assists": "ast"}[_stat],
                 "line": r["form"]}
                for r in rows[:5] if r.get("id")
            ])
            grade_pending()
            _cal = summary().get("wnba_defense", {})
            if _cal.get("total"):
                st.caption(
                    f'Tracked record \u2014 top picks beat their own {_win_label} form '
                    f'{_cal["hits"]}/{_cal["total"]} ({_cal["rate"]}%) over the graded period'
                )
        except Exception:
            pass

        st.caption(
            "Positive Edge = the opponent gives up more than the slate average to this position, "
            "so his form projects up; negative = a tougher spot than average. This is a matchup "
            "read, not a projection \u2014 cross it with the player's own trend chart on the WNBA page."
        )

if unrated:
    with st.expander(f"\u26a0\ufe0f Not rated ({len(unrated)})"):
        for u in unrated[:40]:
            st.caption(f'{u["player"]} ({u.get("pos", "?")}, {u.get("team", "?")}): {u["reason"]}')

footer()
