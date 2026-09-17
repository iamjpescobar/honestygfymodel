"""NHL — Shots Lab.

Shots on goal are the most repeatable number a skater produces, so this
is where hockey prop research starts: shots, points, goals, assists,
ice time, hits and blocks per game for every skater on the slate — for
the season, last 10 and last 5 — beside plain hit-rate counts.

The hit rates are COUNTS ("7 of his 10 games had 2+ shots"), not a
probability model, and the caption says so.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from styles.kc_theme import page_header, footer, card, COLOR, SPORT_ACCENTS
from styles.table_style import style_stat_table
from engines.slate_guard import load_slate, staleness_note, today_for
from engines.nhl_rink import (phase, countdown_text, shots_rows, HIT_RATES,
                              REGULAR_SEASON_START)

_ACCENT = SPORT_ACCENTS.get("NHL") or COLOR["stat_high"]

page_header("NHL Shots Lab", "Shots, points and ice time for every skater tonight",
            eyebrow="PLAYER RESEARCH", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load_shots_for(day):
    games, slate_date, current = load_slate("nhl")
    return games, slate_date


_WINDOWS = {"Season": "season", "Last 10": "l10", "Last 5": "l5"}

_today = today_for("nhl")
games, slate_date = _load_shots_for(_today)
_d = datetime.fromisoformat(_today).date()
has_skaters = any(g.get(f"{s}_skaters") for g in games for s in ("away", "home"))

if not has_skaters:
    note = staleness_note("nhl", _today)
    with card("nhl_shots_empty"):
        head = (countdown_text(_d) if phase(_d) != "regular"
                else "No skater samples for this slate yet.")
        st.markdown(
            f'<div style="font-weight:800; color:{_ACCENT};">{head}</div>'
            f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small); '
            f'line-height:1.7;">The Shots Lab reads regular-season box scores only. It '
            f'fills in the morning after the first regular-season final '
            f'({REGULAR_SEASON_START:%b} {REGULAR_SEASON_START.day}).</div>',
            unsafe_allow_html=True)
    if note:
        st.caption(note)
else:
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        wlab = st.segmented_control("Window", list(_WINDOWS), default="Season",
                                    key="nhl_sl_win", label_visibility="collapsed")
    with c2:
        pos = st.segmented_control("Position", ["All", "F", "D"], default="All",
                                   key="nhl_sl_pos", label_visibility="collapsed")
    with c3:
        min_gp = st.slider("Minimum GP", 1, 20, 1, key="nhl_sl_gp")
    matchups = ["All games"] + [f'{g.get("away_abbr")} @ {g.get("home_abbr")}' for g in games]
    m = st.selectbox("Game", matchups, key="nhl_sl_game")
    scope = games if m == "All games" else [
        g for g in games if f'{g.get("away_abbr")} @ {g.get("home_abbr")}' == m]

    rows = shots_rows(scope, _WINDOWS.get(wlab or "Season", "season"), min_gp)
    if pos == "D":
        rows = [r for r in rows if r["Pos"] == "D"]
    elif pos == "F":
        rows = [r for r in rows if r["Pos"] and r["Pos"] != "D"]
    if not rows:
        st.info("No skaters match those filters.")
    else:
        df = pd.DataFrame(rows)
        rate_cols = [lab for _k, lab in HIT_RATES]
        sty = style_stat_table(
            df, favor_high=["SOG/G", "P/G", "G/G", "A/G", "TOI", "HIT/G", "BLK/G",
                            "Opp SA/G"] + rate_cols, gradient=False)
        fmts = {c: "{:.2f}" for c in ("SOG/G", "P/G", "G/G", "A/G", "HIT/G", "BLK/G")}
        fmts.update({"TOI": "{:.1f}", "Opp SA/G": "{:.1f}", "GP": "{:.0f}"})
        fmts.update({c: "{:.0f}%" for c in rate_cols})
        sty = sty.format({k: v for k, v in fmts.items() if k in df.columns}, na_rep="\u2014")
        st.dataframe(sty, hide_index=True, width="stretch")
        st.caption("Per-game averages from regular-season box scores. TOI is minutes. "
                   "Hit-rate columns are always SEASON counts \u2014 the share of his "
                   "games with 2+ shots, 3+ shots, or at least a point \u2014 not a "
                   "forecast. \u201cOpp SA/G\u201d is shots the opponent allows per game "
                   "(higher = more room to shoot). Brighter = more.")

        names = sorted({r["Skater"] for r in rows if r.get("Skater")})
        who = st.selectbox("Last 10 games", ["\u2014"] + names, key="nhl_sl_who")
        if who != "\u2014":
            log = next((p.get("log") for g in scope for s in ("away", "home")
                        for p in g.get(f"{s}_skaters") or [] if p.get("name") == who), None)
            if log:
                ldf = pd.DataFrame([{"Date": x.get("date"), "Opp": x.get("opp"),
                                     "SOG": x.get("sog"), "PTS": x.get("pts"),
                                     "TOI": x.get("toi")} for x in log])
                st.dataframe(style_stat_table(ldf, favor_high=["SOG", "PTS"]).format(
                    {"SOG": "{:.0f}", "PTS": "{:.0f}", "TOI": "{:.1f}"}, na_rep="\u2014"),
                    hide_index=True, width="stretch")

footer()
