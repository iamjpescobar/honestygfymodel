"""NFL — Prop Lab.

Every quarterback, back and pass-catcher on this week's slate, with the
line a prop is actually set against — season average, last three, last
game — beside what the opposing defense gives up in that phase.

Who appears is decided by the team's CURRENT roster (a traded player
keeps his box-score history but not his old team's card) and ranked by
volume: attempts, carries, targets.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from styles.kc_theme import page_header, footer, COLOR, SPORT_ACCENTS
from styles.table_style import style_stat_table
from engines.nfl_week import (EASTERN, PROP_COLUMNS, load_week,
                              staleness_note, prop_rows)

_ACCENT = SPORT_ACCENTS.get("NFL") or COLOR["stat_high"]

page_header("NFL Prop Lab", "Volume, form and the defense across the line",
            eyebrow="PLAYER RESEARCH", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load_week_for(day):
    return load_week()


_ROLES = {"Quarterbacks": "QB", "Running backs": "RB", "Pass catchers": "REC"}
_WINDOWS = {"Season": "season", "Last 3": "l3", "Last game": "last"}

_today = datetime.now(EASTERN).date()
payload, state = _load_week_for(_today.isoformat())

if state != "current":
    st.info(staleness_note(payload or {}, state, _today))
else:
    games = payload.get("games") or []
    c1, c2 = st.columns([3, 2])
    with c1:
        role_lab = st.segmented_control("Position group", list(_ROLES),
                                        default="Quarterbacks", key="nfl_pl_role",
                                        label_visibility="collapsed")
    with c2:
        win_lab = st.segmented_control("Window", list(_WINDOWS), default="Season",
                                       key="nfl_pl_win", label_visibility="collapsed")
    role = _ROLES.get(role_lab or "Quarterbacks", "QB")
    window = _WINDOWS.get(win_lab or "Season", "season")

    matchups = ["All games"] + [f'{g.get("away_abbr")} @ {g.get("home_abbr")}' for g in games]
    m = st.selectbox("Game", matchups, key="nfl_pl_game")
    scope = games if m == "All games" else [
        g for g in games if f'{g.get("away_abbr")} @ {g.get("home_abbr")}' == m]

    rows = prop_rows(scope, role, window)
    if not rows:
        st.info("No players with a sample in this group yet \u2014 it fills in "
                "after each team's first final.")
    else:
        df = pd.DataFrame(rows)
        n_teams = max([(g.get("home_profile") or {}).get("rank_of") or 0
                       for g in games] + [0]) or 32
        stat_cols = [lab for _k, lab in PROP_COLUMNS[role]]
        # INT for a passer is the one stat where more is worse for an over.
        favor_low = ["INT"] if role == "QB" else []
        favor_high = [c for c in stat_cols if c not in favor_low] + ["Opp allows", "Opp rank"]
        st.dataframe(style_stat_table(df, favor_high=favor_high,
                                      favor_low=favor_low, gradient=False),
                     hide_index=True, width="stretch")
        st.caption(
            "Per-game averages from real box scores over the games in which the "
            "player HAS a line in that category (a quarterback who didn't carry "
            "the ball has no rushing game, not a zero). GP is games with any "
            "line. \u201cOpp allows\u201d is the opposing defense's yards allowed per "
            f"game in this phase; \u201cOpp rank\u201d runs 1\u2013{n_teams}, "
            "where a HIGH number is a SOFT defense. Brighter = more.")

        names = sorted({r["Player"] for r in rows if r.get("Player")})
        who = st.selectbox("Game log", ["\u2014"] + names, key="nfl_pl_who")
        if who != "\u2014":
            plog = None
            for g in scope:
                for side in ("away", "home"):
                    for p in g.get(f"{side}_players") or []:
                        if p.get("name") == who:
                            plog = p.get("log")
            if plog:
                ldf = pd.DataFrame([{
                    "Week": x.get("week"), "Opp": x.get("opp"),
                    "Pass Yds": x.get("pass_yds"), "Rush Yds": x.get("rush_yds"),
                    "Rec": x.get("rec"), "Tgt": x.get("tgt"), "Rec Yds": x.get("rec_yds"),
                } for x in plog])
                ldf = ldf.dropna(axis=1, how="all")
                st.dataframe(style_stat_table(ldf), hide_index=True,
                             width="stretch")
            else:
                st.caption("No game log on file for that player.")

    st.caption(f'Built {payload.get("generated_at_et")} ET from '
               f'{payload.get("finals_parsed", 0)} real box scores. Research, '
               f'not a pick.')

footer()
