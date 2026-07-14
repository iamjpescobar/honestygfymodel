import json
from pathlib import Path

import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR
from auth import render_account_sidebar

# NOTE: no st.set_page_config here — app.py already sets it once.

inject_kc_theme()
render_account_sidebar()

_WNBA_GAMES = Path(__file__).resolve().parent.parent / "data" / "wnba" / "games.json"

page_header("WNBA Analytics", "Live season coverage — game-level markets", eyebrow="IN ACTIVE DEVELOPMENT")


def _load_games():
    """Reads the WNBA slate produced by the nightly pipeline. Returns
    (games, generated_at) or (None, None) when the engine hasn't shipped
    data yet — the page then shows the honest in-development panel
    instead of anything fabricated."""
    try:
        payload = json.loads(_WNBA_GAMES.read_text())
        return payload.get("games", []), payload.get("generated_at_et")
    except Exception:
        return None, None


games, generated_at = _load_games()

if games is None:
    st.markdown(card_open("\U0001F3C0 WNBA engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["gold"]}; font-size:14px; line-height:1.7;">'
        f'WNBA coverage is in active development on the same standard as the MLB engine: '
        f'every number traced to a real, verifiable source \u2014 no placeholders, no estimates. '
        f'The league is mid-season right now, so this page lights up with the real slate the '
        f'moment the data pipeline ships; nothing appears here before that.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(card_close(), unsafe_allow_html=True)
    st.markdown(badge("MLB / KBO / NPB \u2014 live now", "good") + badge("WNBA \u2014 in development", "accent"), unsafe_allow_html=True)
    footer()
    st.stop()

# ------------------------------------------------------------
# REAL SLATE (renders only when the pipeline has shipped data)
# ------------------------------------------------------------
if generated_at:
    st.caption(f"Slate data as of {generated_at} ET \u2014 refreshed by the nightly pipeline.")

if not games:
    st.info("No WNBA games on today's schedule \u2014 likely a league off-day or break.")
else:
    for g in games:
        status = g.get("status", "scheduled")
        subtitle = f'{g.get("arena", "")} \u00b7 {g.get("time_et", "TBD")} ET'
        st.markdown(card_open(f'{g.get("away", "TBD")} @ {g.get("home", "TBD")}', subtitle), unsafe_allow_html=True)

        status_style = {"postponed": "bad", "final": "good", "in progress": "accent"}.get(status, "neutral")
        badges = badge(status.upper(), status_style)
        if g.get("final"):
            badges += badge(g["final"], "accent")
        st.markdown(badges, unsafe_allow_html=True)

        if g.get("score"):
            st.markdown(badge(g["score"], "accent"), unsafe_allow_html=True)
        if g.get("line"):
            st.markdown(badge(f'Line: {g["line"]}', "neutral"), unsafe_allow_html=True)

        dot = " \u00b7 "
        lines = ""
        for side in ("away", "home"):
            name = g.get(side, "TBD")
            rec = g.get(f"{side}_record")
            leaders = g.get(f"{side}_leaders") or []
            right_bits = []
            if rec:
                right_bits.append(rec)
            for ld in leaders:
                right_bits.append(f'{ld["name"]} {ld["value"]} {ld["cat"]}')
            if not right_bits:
                continue
            joined = dot.join(right_bits)
            lines += (f'<div style="display:flex; justify-content:space-between; gap:12px; '
                      f'font-size:12.5px; margin-bottom:6px;">'
                      f'<span style="font-weight:700; color:{COLOR["text"]}; white-space:nowrap;">{name}</span>'
                      f'<span style="font-family:\'JetBrains Mono\',monospace; '
                      f'color:{COLOR["gold"]}; text-align:right;">{joined}</span></div>')
        if lines:
            kind = g.get("leaders_kind", "season")
            caption = ("Leaders shown are season averages \u2014 the players carrying each side tonight."
                       if kind == "season"
                       else "Leaders shown are this game\'s actual totals.")
            st.markdown(f'<div style="margin-top:10px;">{lines}'
                        f'<div style="font-size:10.5px; color:{COLOR["gold"]}; opacity:0.8; '
                        f'margin-top:2px;">{caption}</div></div>', unsafe_allow_html=True)
        st.markdown(card_close(), unsafe_allow_html=True)

footer()