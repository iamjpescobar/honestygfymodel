import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, footer
from auth import render_account_sidebar
from engines.roster import get_live_team_roster

inject_kc_theme()
render_account_sidebar()

page_header("Team Tools", "Look up a live roster by team")

st.markdown(card_open("Team Lookup"), unsafe_allow_html=True)
team = st.text_input("MLB team name")
st.markdown(card_close(), unsafe_allow_html=True)

if team:
    roster = get_live_team_roster(team)
    if roster:
        st.markdown(card_open(f"{team} Roster"), unsafe_allow_html=True)
        st.table(roster)
        st.markdown(card_close(), unsafe_allow_html=True)
    else:
        st.warning("Team not found or no roster available.")

footer()
