import streamlit as st
import pandas as pd
import numpy as np

# Set layout for Command Center feel
st.set_page_config(layout="wide")

st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

# --- 1. SESSION STATE FOR DRILL-DOWN ---
if 'selected_player' not in st.session_state:
    st.session_state.selected_player = None

# --- 2. DATA GENERATOR (Matches your template) ---
def get_lineup_data():
    # This generates the grid you want
    data = {
        "Batter Name": ["Jac Caglianone", "Luke Maile", "Nick Loftin", "Salvador Perez", "Michael Massey"],
        "BBE": [226, 222, 201, 175, 154],
        "💥 SLAM Index": [71.8, 23.2, 26.5, 23.2, 70.5],
        "Top 3 Matchup": ["✅ Good", "✅ Good", "Neutral", "⚠️ Cold", "✅ Good"],
        "Brl %": [14.8, 7.5, 14.9, 6.6, 10.2],
        "PullAir %": [23.7, 13.4, 13.0, 22.3, 22.0],
        "HH %": [32.2, 54.2, 44.9, 51.7, 37.1]
    }
    return pd.DataFrame(data)

# --- 3. MAIN DASHBOARD ---
matchup = st.selectbox("Select Today's Matchup:", ["Philadelphia Phillies (Cristopher Sánchez) @ Kansas City Royals (Noah Cameron)"])
pitcher = st.radio("Select Pitcher to Target:", ["Cristopher Sánchez", "Noah Cameron"])

st.markdown(f"## 📋 Pro-Report: {pitcher}")
st.markdown("---")
st.markdown("### ⚔️ Intent-To-Homer Lineup Analysis")

df = get_lineup_data()

# Create columns for the grid so we can add buttons to the names
# We use a custom display where names are buttons that trigger the drill-down
cols = st.columns([2, 8])
with cols[0]:
    st.write("**Batter Name**")
    for name in df["Batter Name"]:
        if st.button(name, key=name):
            st.session_state.selected_player = name
            st.rerun()

with cols[1]:
    st.dataframe(df.set_index("Batter Name"), use_container_width=True)

# --- 4. DRILL-DOWN VIEW (Only shows when a player is clicked) ---
if st.session_state.selected_player:
    st.markdown("---")
    st.subheader(f"📊 Detailed Scout: {st.session_state.selected_player}")
    
    # This is where we put the "Performance" metrics from your reference picture
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AVG IP", "6.4")
    c2.metric("K%", "28.5%")
    c3.metric("Whiff%", "32.2%")
    c4.metric("HR Risk", "vs LHB -1.21")
    
    st.info("Detailed performance history loaded.")
    if st.button("Close Drill-Down"):
        st.session_state.selected_player = None
        st.rerun()
