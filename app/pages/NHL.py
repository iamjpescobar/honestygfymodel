import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR
from auth import render_account_sidebar

# NOTE: no st.set_page_config here — app.py already sets it once for the
# whole app, and these pages render inside that same run.

inject_kc_theme()
render_account_sidebar()

page_header("NHL Analytics", "In development — built on real data or not at all", eyebrow="COMING SOON")

st.markdown(card_open("🏒 NHL is on the roadmap"), unsafe_allow_html=True)
st.markdown(
    f'<div style="color:{COLOR["gold"]}; font-size:14px; line-height:1.7;">'
    f'NHL tools are being built on the same standard as the MLB engine: every number '
    f'traced to a real, verifiable source — no placeholders, no estimates, no filler. '
    f'Nothing ships on this page until its data engine is real.'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(card_close(), unsafe_allow_html=True)

st.markdown(card_open("What\'s planned"), unsafe_allow_html=True)
st.markdown(
    f'<div style="margin-bottom:12px;">'
    f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:13.5px;">Game Cards</div>'
    f'<div style="color:{COLOR["gold"]}; font-size:12.5px;">Nightly matchup pages — team shot quality and special teams</div>'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div style="margin-bottom:12px;">'
    f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:13.5px;">Goalie Matchups</div>'
    f'<div style="color:{COLOR["gold"]}; font-size:12.5px;">Starter confirmations and save-quality profiles</div>'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div style="margin-bottom:12px;">'
    f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:13.5px;">Totals Models</div>'
    f'<div style="color:{COLOR["gold"]}; font-size:12.5px;">Game-level leans built on real shot data</div>'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(card_close(), unsafe_allow_html=True)

st.markdown(
    badge("MLB — live now", "good") + badge("NHL — in development", "neutral"),
    unsafe_allow_html=True,
)

footer()