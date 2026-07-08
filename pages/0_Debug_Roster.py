import streamlit as st
from engines.roster import get_live_team_roster

team = st.text_input("Team name:", "Toronto Blue Jays")

if st.button("Test Roster"):
    roster = get_live_team_roster(team)
    st.write(roster)

