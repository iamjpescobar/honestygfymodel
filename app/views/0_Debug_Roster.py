import streamlit as st

from styles.kc_theme import page_header, card_open, card_close
from auth import require_admin
from engines.roster import get_live_team_roster

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

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
