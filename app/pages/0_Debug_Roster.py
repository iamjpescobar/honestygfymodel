import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close
from auth import render_account_sidebar, require_admin
from engines.roster import get_live_team_roster

inject_kc_theme()
render_account_sidebar()

# Belt-and-suspenders: app.py only adds this page to the nav for admins,
# but gate it here too in case that ever changes.
require_admin()

page_header("Debug Roster", "Internal tool \u2014 not part of the subscriber product", eyebrow="ADMIN ONLY")

st.markdown(card_open("Roster Lookup"), unsafe_allow_html=True)
team = st.text_input("Team name", "Toronto Blue Jays")
st.markdown(card_close(), unsafe_allow_html=True)

if st.button("Test Roster", type="primary"):
    roster = get_live_team_roster(team)
    st.write(roster)
