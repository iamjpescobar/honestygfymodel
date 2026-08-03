"""Bullpen Board — who finishes the game, and what they allow.

Every other page on this site reads the starter. This one reads the arms
that take over after he's gone, which is where a third of a hitter's
plate appearances actually happen. Built for the live-betting question:
the starter is out, a reliever is warming, is this a spot to take the
batter or leave it alone?

Splits by batter hand are the point. A pooled team bullpen rate cannot
tell you that the only lefty in the pen has been hit hard by right-handed
bats, and that is frequently the whole story of a late-inning spot.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import inject_kc_theme, footer, card, COLOR
from styles.table_style import style_stat_table, render_html_table
from engines.weather_engine import get_todays_games_with_weather
from engines.team_logos import logo_for
from engines.live_sync import sync_latest_button
from engines.bullpen_board import (
    get_bullpen, pen_totals, worst_matchup, PEN_STATS, MIN_SPLIT_IP,
)

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-sm);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; '
    f'color:{COLOR["text"]};">BULLPEN BOARD</span></div>',
    unsafe_allow_html=True,
)
st.caption(
    "What each available reliever actually allows, split by batter hand. "
    "Blue favours the batter. Every figure is computed from that pitcher's "
    "own Statcast rows — a split with fewer than "
    f"{MIN_SPLIT_IP:.0f} IP is shown as N/A rather than a number, because a "
    "handful of innings is noise, not a read."
)

sync_latest_button(key="sync_bullpen", include_data_package=True)

# (games, error) TUPLE, not a bare list — every other caller in the app
# unpacks it the same way. Binding the tuple to `games` made `g` the list
# itself on the first loop pass, hence "'list' object has no attribute
# 'get'".
games, games_error = get_todays_games_with_weather()
if games_error and not games:
    st.warning(f"Couldn't load today's slate: {games_error}")
    footer()
    st.stop()
games = games or []
if not games:
    st.info("No games on the board yet — press ⟳ Sync latest to pull today's slate.")
    footer()
    st.stop()

# One row per TEAM, since a bullpen belongs to a team rather than a game.
_opts = []
for g in games:
    for side in ("away", "home"):
        name = g.get(side)
        if not name:
            continue
        opp = g.get("home" if side == "away" else "away")
        starter = g.get(f"{side}_pitcher_id")
        _opts.append((f"{name}  (vs {opp})", name, starter))

if not _opts:
    st.info("Today's slate is loaded but has no teams resolved yet.")
    footer()
    st.stop()

_labels = [o[0] for o in _opts]
_pick = st.selectbox("Bullpen", _labels, key="pen_board_team",
                     label_visibility="collapsed")
# .get-style fallback, not _labels.index(_pick): the slate rebuilds as
# games go final, so a remembered team can vanish from the list between
# reruns and indexing it would be a hard crash.
_sel = next((o for o in _opts if o[0] == _pick), _opts[0])
_label, team, starter_pid = _sel

_win_opts = {"Season": "season", "L25": "l25", "L15": "l15"}
_win_label = st.segmented_control(
    "Window", list(_win_opts), default="Season", key="pen_board_window",
    label_visibility="collapsed",
) or "Season"
window = _win_opts[_win_label]

with st.spinner(f"Reading {team}'s bullpen…"):
    pen = get_bullpen(team, starter_pid, window)

if not pen:
    st.warning(
        f"No reliever data resolved for {team}. This is usually a roster "
        f"that hasn't refreshed yet rather than an empty bullpen — try ⟳ "
        f"Sync latest."
    )
    footer()
    st.stop()

# ---------------------------------------------------------------- totals
_tot = pen_totals(pen)
# logo_for returns a URL STRING, not markup. Interpolating it bare printed
# the raw https://... next to the team name instead of showing the logo.
_logo_url = logo_for(team)
_logo_img = (f'<img src="{_logo_url}" style="height:22px; '
             f'vertical-align:-4px; margin-right:var(--lc-space-md);">') if _logo_url else ""
with card("pen_totals"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
        f'{_logo_img}{team} bullpen — {_tot.get("arms", 0)} available arms'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f'{_tot.get("IP", 0)} IP · {_tot.get("lhp_arms", 0)} left-handed '
        f'({_tot.get("lhp_ip_share", 0) * 100:.0f}% of innings) · '
        f'innings-weighted, so a mop-up arm with four innings does not move '
        f'these the way the setup man does.'
    )
    _trow = {lbl: _tot.get(key) for key, lbl, _hi in PEN_STATS if key in _tot}
    if _trow:
        render_html_table(
            style_stat_table(
                pd.DataFrame([{"Line": "Pen total", **_trow}]),
                favor_high=[l for k, l, hi in PEN_STATS if hi is True and k in _tot],
                favor_low=[l for k, l, hi in PEN_STATS if hi is False and k in _tot],
                gradient=True,
            ),
            key="pen_totals_tbl",
        )

# ------------------------------------------------------- per-reliever
_side_label = st.segmented_control(
    "Split", ["Overall", "vs RHB", "vs LHB"], default="Overall",
    key="pen_board_split", label_visibility="collapsed",
) or "Overall"
_side_key = {"Overall": "overall", "vs RHB": "vs_rhb", "vs LHB": "vs_lhb"}[_side_label]

rows = []
for r in pen:
    split = r.get(_side_key) or {}
    row = {"Reliever": r["name"], "T": r.get("throws") or "?"}
    for key, label, _hi in PEN_STATS:
        # None, not 0 — a reliever with no qualifying sample against this
        # hand has an UNKNOWN rate, and 0.000 SLG allowed would read as
        # the most dominant arm in the pen.
        row[label] = split.get(key)
    rows.append(row)

with card("pen_relievers"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
        f'Relievers — {_side_label}</div>',
        unsafe_allow_html=True,
    )
    _empty = sum(1 for r in rows if r.get("IP") is None)
    if _empty and _side_key != "overall":
        st.caption(
            f"{_empty} of {len(rows)} arms have fewer than {MIN_SPLIT_IP:.0f} IP "
            f"against this hand, so their rows read N/A. That absence is the "
            f"honest answer — not a zero."
        )
    render_html_table(
        style_stat_table(
            pd.DataFrame(rows),
            favor_high=[l for _k, l, hi in PEN_STATS if hi is True],
            favor_low=[l for _k, l, hi in PEN_STATS if hi is False],
            gradient=True,
        ),
        key=f"pen_rel_{_side_key}",
    )

# ------------------------------------------------------ live-bet read
with card("pen_read"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
        f'Live read</div>',
        unsafe_allow_html=True,
    )
    for hand, word in (("L", "left-handed"), ("R", "right-handed")):
        w = worst_matchup(pen, hand)
        if w is None:
            st.caption(
                f"No reliever has {MIN_SPLIT_IP:.0f}+ IP against {word} bats "
                f"yet — nothing to report rather than a guess."
            )
            continue
        split = w["vs_lhb"] if hand == "L" else w["vs_rhb"]
        st.caption(
            f"**{word.capitalize()} bats** have done the most damage to "
            f"**{w['name']}** ({w.get('throws') or '?'}HP): "
            f"{split.get('SLG')} SLG, {split.get('ISO')} ISO, "
            f"{split.get('HR/9')} HR/9 over {split.get('IP')} IP."
        )
    st.caption(
        "Ranked on slugging allowed, not batting average — a high average "
        "with no power is a different bet than a high slug."
    )

footer()
