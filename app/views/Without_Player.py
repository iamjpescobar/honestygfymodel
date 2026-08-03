"""
Without Player — how a WNBA team performs when someone sits.

Reads the same slate data file the rest of the WNBA pages use.
Formula and floors in engines/without_player.py.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from styles.kc_theme import inject_kc_theme, card, footer, COLOR
from styles.table_style import style_stat_table, render_html_table
from engines.without_player import (
    without_player, team_players, MIN_WITHOUT, MIN_TEAMMATE_GP,
)
from engines.live_sync import sync_latest_button

_LOGS = Path(__file__).resolve().parent.parent / "data" / "wnba" / "player_logs.json"
_GAMES = Path(__file__).resolve().parent.parent / "data" / "wnba" / "games.json"

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-sm);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">WITHOUT</span>'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">PLAYER</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_without", include_data_package=True)


@st.cache_data(ttl=1800, max_entries=2, show_spinner=False)
def _load_logs():
    try:
        return json.loads(_LOGS.read_text())
    except Exception:
        return {}


logs = _load_logs()
if not logs:
    st.info(
        "Per-game player logs aren't in the current data build yet. This page needs "
        "them to compare games with and without a player \u2014 press \u27f3 Sync latest, "
        "and if it's still empty, the next nightly pipeline run will include them."
    )
    footer()
    st.stop()

teams = sorted({rec.get("team") for rec in logs.values() if rec.get("team")})
if not teams:
    st.info("No teams found in the current logs.")
    footer()
    st.stop()

col_a, col_b = st.columns(2)
with col_a:
    team = st.selectbox("Team", teams, key="wo_team")
with col_b:
    roster = team_players(logs, team)
    if not roster:
        st.info("No players on file for that team.")
        footer()
        st.stop()
    labels = {f"{name} ({gp} G)": pid for pid, name, gp in roster}
    pick = st.selectbox("Player out", list(labels.keys()), key="wo_player")

# labels.get(), not labels[pick].
#
# Both selectboxes persist their choice under a fixed key, but the PLAYER
# list is rebuilt from whichever TEAM is selected. Switch teams and the
# remembered player is no longer a key in `labels`, so `labels[pick]`
# raised a bare KeyError and took the page down — intermittently, because
# it only happens when the stored name doesn't exist on the new roster.
_pid = labels.get(pick)
if _pid is None:
    # Fall back to the first player on the new roster rather than
    # erroring: the widget will re-sync on the next rerun.
    _pid = next(iter(labels.values()), None)
if _pid is None:
    st.info("No players available for this team.")
    footer()
    st.stop()

rows, meta = without_player(logs, team, _pid)

with card("without"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
        f'{meta["team"]} without {meta["player"]}</div>'
        f'<div class="pf-card-subtitle" style="color:{COLOR["text_muted"]};">'
        f'Real per-game box scores split by whether he played \u00b7 '
        f'{meta["games_with"]} games with him, {meta["games_without"]} without '
        f'(of {meta["team_games"]} team games) \u00b7 minimum {MIN_WITHOUT} games missed to show '
        f'a split, and teammates need {MIN_TEAMMATE_GP}+ games of their own \u00b7 '
        f'this is what happened, not a projection \u2014 role changes usually persist, but a '
        f'small split can also just reflect who the opponents were.</div>',
        unsafe_allow_html=True,
    )

    if not meta.get("enough"):
        st.info(
            f'{meta["player"]} has only missed {meta["games_without"]} game(s) this season \u2014 '
            f'below the {MIN_WITHOUT}-game floor, so no split is shown rather than a number '
            f'built on noise.'
        )
    elif not rows:
        st.info("No teammates clear the games-played floor for this split yet.")
    else:
        if meta.get("team_pts_delta") is not None:
            _d = meta["team_pts_delta"]
            _col = COLOR["stat_high"] if _d > 0 else COLOR["error"] if _d < 0 else COLOR["text"]
            st.markdown(
                f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-body); '
                f'margin:var(--lc-space-hair) var(--lc-space-none) var(--lc-space-md) var(--lc-space-none); color:{COLOR["text"]};">Team scoring: '
                f'<b>{meta["team_pts_with"]}</b> with him \u2192 '
                f'<b style="color:{_col};">{meta["team_pts_without"]}</b> without '
                f'(<b style="color:{_col};">{_d:+.1f}</b> per game)</div>',
                unsafe_allow_html=True,
            )

        df = pd.DataFrame([
            {
                "Player": r["name"],
                "Pos": r["pos"],
                "MIN w/": f'{r["with_min"]:.1f}' if r["with_min"] is not None else "\u2014",
                "MIN w/o": f'{r["without_min"]:.1f}' if r["without_min"] is not None else "\u2014",
                "\u0394 MIN": f'{r["delta_min"]:+.1f}' if r["delta_min"] is not None else "\u2014",
                "PTS w/": f'{r["with_pts"]:.1f}' if r["with_pts"] is not None else "\u2014",
                "PTS w/o": f'{r["without_pts"]:.1f}' if r["without_pts"] is not None else "\u2014",
                "PRA w/": f'{r["with_pra"]:.1f}' if r["with_pra"] is not None else "\u2014",
                "PRA w/o": f'{r["without_pra"]:.1f}' if r["without_pra"] is not None else "\u2014",
                "\u0394 PRA": f'{r["delta_pra"]:+.1f}' if r["delta_pra"] is not None else "\u2014",
                "Games": f'{r["n_with"]}/{r["n_without"]}',
            }
            for r in rows
        ])
        render_html_table(
            style_stat_table(
                df,
                favor_high=["\u0394 PRA", "\u0394 MIN", "PRA w/o", "PTS w/o"],
                gradient=True
            )
        ,
            key="without_player_141")
        st.caption(
            "\u0394 columns are without-minus-with. Positive means he produces more when "
            "that player sits \u2014 usually a minutes and usage change, which is why "
            "\u0394 MIN is shown right next to it. Games column is with/without sample sizes; "
            "read a 4-game split gently."
        )

footer()
