import streamlit as st
import pandas as pd
import numpy as np

# 1. SETUP
st.set_page_config(layout="wide")
st.title("Los Cappers Lab 🧪")

# 2. DATA MOCK (This will be replaced by your real API data)
def get_player_data(player_name):
    # This represents the data that shows the specific K% / HR Risk / etc.
    return {
        "Name": player_name,
        "Rating": 48.7,
        "AVG IP": 6.4,
        "K%": "28.5%",
        "Whiff%": "32.2%",
        "HR Risk": "vs LHB -1.21"
    }

# 3. GAME SELECTION
games = ["Phillies @ Royals", "Yankees @ Rays"]
selected_game = st.selectbox("Select Matchup:", games)

# 4. LINEUP DISPLAY (The "Drill-Down" trigger)
if selected_game:
    st.write(f"### Lineup for {selected_game}")
    players = ["Cristopher Sanchez", "Noah Cameron", "Cam Schlittler"]
    
    # Create columns for players
    cols = st.columns(len(players))
    for i, p_name in enumerate(players):
        if cols[i].button(p_name):
            st.session_state.selected_player = p_name

# 5. THE DRILL-DOWN VIEW (This matches your PropFinder reference)
if 'selected_player' in st.session_state:
    p = get_player_data(st.session_state.selected_player)
    
    st.markdown("---")
    st.header(f"📊 Detailed Scout: {p['Name']}")
    
    # Visual Metrics Row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PF Rating", p['Rating'])
    c2.metric("AVG IP", p['AVG IP'])
    c3.metric("Strikeout %", p['K%'])
    c4.metric("Whiff %", p['Whiff%'])
    
    st.write(f"**HR Risk Context:** {p['HR Risk']}")
    
    # Placeholder for your graph logic
    st.bar_chart(np.random.randn(10, 1)) # Replace this with your specific stats
    st.success("Data rendered based on PropFinder standards.")
