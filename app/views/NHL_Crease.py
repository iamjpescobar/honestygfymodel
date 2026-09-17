"""NHL — Crease Report.

Every goalie in the league on one sheet: starts, how many of his team's
last ten he started, save percentage, goals against, form over his last
five starts, and how much rubber he faces per sixty.

Crease share is a COUNT of recent starts, not a starter confirmation —
the page says so every time it shows one.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from styles.kc_theme import page_header, footer, card, COLOR, SPORT_ACCENTS
from styles.table_style import style_stat_table
from engines.slate_guard import load_slate, today_for, payload_field, staleness_note
from engines.nhl_rink import (phase, countdown_text, crease_rows,
                              REGULAR_SEASON_START)

_ACCENT = SPORT_ACCENTS.get("NHL") or COLOR["stat_high"]

page_header("NHL Crease Report", "Every goalie \u2014 workload, save quality, form",
            eyebrow="GOALIES", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load_crease_for(day):
    games, slate_date, _current = load_slate("nhl")
    # A slate the guard rejected (dated in the past) means the nightly has
    # not published since — its goalie sheet is just as old, so it is not
    # shown as current either.
    if slate_date is None or slate_date < day:
        return games, {}, None, slate_date
    return (games, payload_field("nhl", "goalies", {}),
            payload_field("nhl", "generated_at_et"), slate_date)


_today = today_for("nhl")
games, goalies, built, _slate_date = _load_crease_for(_today)
_d = datetime.fromisoformat(_today).date()

if not goalies:
    _note = staleness_note("nhl", _today)
    if _note and phase(_d) == "regular":
        st.info(_note)
    with card("nhl_crease_empty"):
        msg = (countdown_text(_d) if phase(_d) != "regular"
               else "No regular-season starts on file yet.")
        st.markdown(
            f'<div style="font-weight:800; color:{_ACCENT};">{msg}</div>'
            f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small); '
            f'line-height:1.7;">The Crease Report is built only from regular-season box '
            f'scores, so it fills in the morning after opening night '
            f'({REGULAR_SEASON_START:%b} {REGULAR_SEASON_START.day}). Exhibition '
            f'starts are deliberately left out.</div>', unsafe_allow_html=True)
else:
    tonight = {g.get(s) for g in games for s in ("away", "home")
               if g.get("game_type") != "preseason"}
    only = st.toggle("Only teams playing on the current slate", value=bool(tonight),
                     key="nhl_crease_tonight", disabled=not tonight)
    min_gs = st.slider("Minimum starts", 0, 20, 1, key="nhl_crease_min")
    rows = [r for r in crease_rows(goalies, tonight if (only and tonight) else None)
            if (r["Starts"] or 0) >= min_gs]
    if not rows:
        st.info("No goalies match those filters.")
    else:
        df = pd.DataFrame(rows)
        sty = style_stat_table(df, favor_high=["SV%", "L5 SV%", "Starts"],
                               favor_low=["GAA", "SA/60"], gradient=False)
        sty = sty.format({"SV%": "{:.3f}", "L5 SV%": "{:.3f}", "GAA": "{:.2f}",
                          "SA/60": "{:.1f}", "GP": "{:.0f}", "Starts": "{:.0f}"},
                         na_rep="\u2014")
        st.dataframe(sty, hide_index=True, width="stretch")
    st.caption("SV% and GAA are pooled over every regular-season appearance "
               "(saves \u00f7 shots; goals \u00d7 60 \u00f7 minutes). L5 SV% is his last "
               "five STARTS. Crease share = starts in his team's last 10 games \u2014 "
               "a workload count, not a confirmed starter. Brighter = better for the "
               "goalie (higher SV%, lower GAA and shot volume).")
    if built:
        st.caption(f"Built {built} ET.")

footer()
