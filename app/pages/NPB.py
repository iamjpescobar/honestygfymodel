import json
from pathlib import Path

import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR
from auth import render_account_sidebar

# NOTE: no st.set_page_config here — app.py already sets it once.

inject_kc_theme()
render_account_sidebar()

_NPB_GAMES = Path(__file__).resolve().parent.parent / "data" / "npb" / "games.json"

page_header("NPB Analytics", "Nippon Professional Baseball — game-level markets", eyebrow="IN ACTIVE DEVELOPMENT")


def _load_games():
    """Reads the NPB slate produced by the nightly pipeline. Returns
    (games, generated_at) or (None, None) when the engine hasn't shipped
    data yet — the page then shows the honest in-development panel
    instead of anything fabricated."""
    try:
        payload = json.loads(_NPB_GAMES.read_text())
        return payload.get("games", []), payload.get("generated_at_jst")
    except Exception:
        return None, None


games, generated_at = _load_games()

if games is None:
    st.markdown(card_open("\u26be NPB engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["gold"]}; font-size:14px; line-height:1.7;">'
        f'NPB coverage is in active development on the same standard as the MLB engine: '
        f'every number traced to a real, verifiable source \u2014 no placeholders, no estimates. '
        f'This page lights up with the real slate the moment the data pipeline ships; '
        f'nothing appears here before that.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(card_close(), unsafe_allow_html=True)

    st.markdown(card_open("What launches first"), unsafe_allow_html=True)
    for name, desc in [
        ("Daily Slate", "Every NPB game with starters, park, and start time (JST + ET) - ties shown as ties, since NPB games can legitimately end drawn"),
        ("Team Profiles", "Real offense/pitching form for totals and run-line handicapping"),
        ("Starter Form", "Season and recent-start lines for the day\'s probables"),
    ]:
        st.markdown(
            f'<div style="margin-bottom:12px;">'
            f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:13.5px;">{name}</div>'
            f'<div style="color:{COLOR["gold"]}; font-size:12.5px;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown(card_close(), unsafe_allow_html=True)
    st.markdown(badge("MLB \u2014 live now", "good") + badge("NPB \u2014 in development", "accent"), unsafe_allow_html=True)
    footer()
    st.stop()

# ------------------------------------------------------------
# REAL SLATE (renders only when the pipeline has shipped data)
# ------------------------------------------------------------
if generated_at:
    st.caption(f"Slate data as of {generated_at} JST \u2014 refreshed by the nightly pipeline.")

if not games:
    st.info("No NPB games on today\'s schedule \u2014 likely a league off-day.")
else:
    for g in games:
        st.markdown(card_open(f'{g.get("away", "TBD")} @ {g.get("home", "TBD")}',
                              f'{g.get("stadium", "")} \u00b7 {g.get("time_jst", "TBD")} JST / {g.get("time_et", "TBD")} ET'), unsafe_allow_html=True)
        st.markdown(
            badge(f'Away SP: {g.get("away_starter", "TBD")}', "neutral")
            + badge(f'Home SP: {g.get("home_starter", "TBD")}', "neutral"),
            unsafe_allow_html=True,
        )
        st.markdown(card_close(), unsafe_allow_html=True)

footer()