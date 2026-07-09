import streamlit as st
from app.engines.roster import get_live_team_roster

st.title("🛠️ Team Tools")
st.markdown("---")

team = st.text_input("Enter MLB Team Name:")

if team:
    roster = get_live_team_roster(team)
    if roster:
        st.table(roster)
    else:
        st.warning("Team not found or no roster available.")

