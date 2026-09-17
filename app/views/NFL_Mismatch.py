"""NFL — Mismatch Finder.

The question a football week is really asked: WHERE is one unit much
better than the unit it's lined up against? Every offense-vs-defense
pairing on the slate, ranked by the gap between the two league ranks.

Transparent by construction: both ranks and both raw numbers are on the
row, and the tier is nothing but a rank gap as a fraction of the league.
Nothing here is fitted to outcomes.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from styles.kc_theme import page_header, badge, footer, card, COLOR, SPORT_ACCENTS
from styles.table_style import style_stat_table
from engines.nfl_week import (EASTERN, UNIT_PAIRS, load_week, staleness_note,
                              mismatches, edge_tier)

_ACCENT = SPORT_ACCENTS.get("NFL") or COLOR["stat_high"]

page_header("NFL Mismatch Finder", "Unit vs unit, every game this week, "
            "biggest gap first", eyebrow="WEEK EDGES", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load_week_for(day):
    return load_week()


_today = datetime.now(EASTERN).date()
payload, state = _load_week_for(_today.isoformat())

if state != "current":
    st.info(staleness_note(payload or {}, state, _today))
else:
    games = payload.get("games") or []
    rows = mismatches(games)
    n_teams = max([(g.get("home_profile") or {}).get("rank_of") or 0 for g in games] + [0]) or 32
    if not rows:
        st.info("No ranked units yet \u2014 the finder fills in once teams have "
                "a final on the books.")
    else:
        units = [u for u, _a, _d in UNIT_PAIRS]
        c1, c2 = st.columns([3, 2])
        with c1:
            pick = st.multiselect("Units", units, default=units, key="nfl_mm_units")
        with c2:
            hide_played = st.toggle("Hide games already final", value=True,
                                    key="nfl_mm_hide_final")
        view = [r for r in rows if r["unit"] in (pick or units)
                and not (hide_played and r["status"] == "final")]

        top = [r for r in view if edge_tier(r["edge"], n_teams) == "Glaring"][:6]
        if top:
            st.markdown(
                f'<div style="color:{_ACCENT}; font-weight:800; letter-spacing:0.12em; '
                f'text-transform:uppercase; font-size:var(--lc-text-caption); '
                f'margin:var(--lc-space-lg) 0 var(--lc-space-sm);">Glaring this week</div>',
                unsafe_allow_html=True)
            cols = st.columns(min(3, len(top)))
            for i, r in enumerate(top):
                with cols[i % len(cols)]:
                    with card(f'nfl_mm_{i}'):
                        st.markdown(
                            f'<div style="font-weight:800; font-size:var(--lc-text-body-lg);">'
                            f'{r["abbr"]} {r["unit"].lower()}</div>'
                            f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">'
                            f'#{r["att_rank"]} ({r["att_value"]}) into {r["vs_abbr"]}\'s '
                            f'#{r["def_rank"]} ({r["def_value"]})</div>'
                            f'<div style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny); '
                            f'margin-top:4px;">{r["game"]} \u00b7 {r["window"]} \u00b7 '
                            f'{r["gp"]} GP sample</div>',
                            unsafe_allow_html=True)
                        st.markdown(badge(f'Edge +{r["edge"]}', "good"), unsafe_allow_html=True)

        df = pd.DataFrame([{
            "Game": r["game"], "Window": r["window"],
            "Team": r["abbr"], "Unit": r["unit"],
            "Team value": r["att_value"], "Team rank": r["att_rank"],
            "Vs": r["vs_abbr"], "Vs value": r["def_value"], "Vs rank": r["def_rank"],
            "Edge": r["edge"], "Read": edge_tier(r["edge"], n_teams), "GP": r["gp"],
        } for r in view])
        if df.empty:
            st.info("Nothing matches those filters.")
        else:
            st.dataframe(style_stat_table(df, favor_high=["Edge", "Vs rank"],
                                          favor_low=["Team rank"], gradient=True),
                         hide_index=True, width="stretch")
        st.caption(
            f"Ranks run 1\u2013{n_teams}; #1 is best at that thing for the team that "
            "owns it. Edge = the defending unit's rank minus the attacking unit's "
            "rank, so a #3 pass offense into the #30 pass defense is +27. "
            "\u201cPass rush\u201d pairs a defense's sacks per game with the other "
            "offensive line's sacks allowed. Reads are rank gaps as a share of the "
            "league (Glaring \u2265 60%, Strong \u2265 35%, Lean \u2265 15%) \u2014 "
            "a description of distance, not a probability. Colour: brighter = "
            "bigger edge / softer opposing unit.")
        st.caption(f'Built {payload.get("generated_at_et")} ET from '
                   f'{payload.get("finals_parsed", 0)} real box scores.')

footer()
