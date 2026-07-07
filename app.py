import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# --- 1. CONFIG & MAPPINGS ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

def get_hand(side_code):
    return {'L': 'LHB', 'R': 'RHB', 'S': 'SHB'}.get(side_code, 'RHB')

# --- 2. DATA FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_daily_slate():
    # Centralized game list to prevent duplicates
    return [
        {"id": 1, "away": "Phillies", "home": "Royals", "away_p": "Sanchez", "home_p": "Cameron"},
        {"id": 2, "away": "Astros", "home": "Nationals", "away_p": "Burrows", "home_p": "Mikolas"}
    ]

# --- 3. MAIN UI ---
st.title("Los Cappers Lab 🧪")
slate = get_daily_slate()

# TAB NAVIGATION
tabs = st.tabs([f"{g['away']} @ {g['home']}" for g in slate])

for i, game in enumerate(slate):
    with tabs[i]:
        st.subheader(f"Analysis: {game['away']} vs {game['home']}")
        
        # TOP 3 HR CANDIDATES (Logic)
        st.markdown("### 🏆 Top 3 HR Candidates")
        col1, col2, col3 = st.columns(3)
        # Mock logic: Replace with your BBE filtering
        candidates = [("Player A", 92.5), ("Player B", 88.2), ("Player C", 85.0)]
        for col, (name, score) in zip([col1, col2, col3], candidates):
            col.metric(name, f"{score} SLAM")
            
        # PITCHER INTEL (Styled)
        st.markdown("### 🎯 Pitcher Danger Metrics")
        df_pitcher = pd.DataFrame({
            "Metric": ["Barrel% Allowed", "HardHit%", "Whiff%"],
            "Value": [10.5, 42.0, 31.0]
        })
        
        # Color formatting for "Danger"
        def color_danger(val):
            return 'background-color: #5a1e1e' if val > 10 else 'background-color: #1e3a1e'
        
        st.dataframe(df_pitcher.style.applymap(color_danger, subset=['Value']), use_container_width=True)

# --- 4. GLOBAL DASHBOARD (Bottom) ---
st.divider()
st.markdown("### 📊 Daily Pitcher Danger Rankings")
# This is where all pitchers from all games get compared
ranking_data = pd.DataFrame({
    "Pitcher": ["Cameron", "Mikolas", "Sanchez", "Burrows"],
    "Danger Level": [9.2, 7.5, 4.1, 3.2]
}).sort_values("Danger Level", ascending=False)

st.table(ranking_data)
