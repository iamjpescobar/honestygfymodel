import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR

# NOTE: no st.set_page_config here — app.py already sets it once for the
# whole app, and these pages render inside that same run.

inject_kc_theme()

page_header("NHL Analytics", "In development — built on real data or not at all", eyebrow="COMING SOON")

st.markdown(card_open("🏒 NHL is on the roadmap"), unsafe_allow_html=True)
st.markdown(
    f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-body-lg); line-height:1.7;">'
    f'NHL tools are being built on the same standard as the MLB engine: every number '
    f'traced to a real, verifiable source — no placeholders, no estimates, no filler. '
    f'Nothing ships on this page until its data engine is real.'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(card_close(), unsafe_allow_html=True)

st.markdown(card_open("What\'s planned"), unsafe_allow_html=True)
st.markdown(
    f'<div style="margin-bottom:var(--lc-space-lg);">'
    f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:var(--lc-text-body);">Game Cards</div>'
    f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">Nightly matchup pages — team shot quality and special teams</div>'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div style="margin-bottom:var(--lc-space-lg);">'
    f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:var(--lc-text-body);">Goalie Matchups</div>'
    f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">Starter confirmations and save-quality profiles</div>'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div style="margin-bottom:var(--lc-space-lg);">'
    f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:var(--lc-text-body);">Totals Models</div>'
    f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">Game-level leans built on real shot data</div>'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(card_close(), unsafe_allow_html=True)

st.markdown(
    badge("MLB — live now", "good") + badge("NHL — in development", "neutral"),
    unsafe_allow_html=True,
)

footer()
