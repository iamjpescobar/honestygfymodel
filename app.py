import streamlit as st
import pandas as pd
import numpy as np

# --- 1. CONFIG & MAPPINGS ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

@st.cache_data(ttl=3600)
def get_todays_games():
    # Replace this with your full logic from your original code
    return [
        {"away": "Phillies", "home": "Royals", "away_p": "Sanchez", "home_p": "Cameron"},
        {"away": "Astros", "home": "Nationals", "away_p": "Burrows", "home_p": "Mikolas"}
    ]

# --- 2. MAIN UI & NAVIGATION ---
st.title("Los Cappers Lab 🧪")
slate = get_todays_games()
tabs = st.tabs([f"{g['away']} @ {g['home']}" for g in slate])

# This list will collect data for your bottom "Global" ranking table
all_pitcher_data = []

for i, game in enumerate(slate):
    with tabs[i]:
        st.subheader(f"Analysis: {game['away']} vs {game['home']}")
        
        # --- PASTE YOUR ANALYTICS ENGINE ---
        # 1. Calculate HR Candidates
        st.markdown("### 🏆 Top 3 HR Candidates")
        # Logic: (Example)
        st.info("Insert your HR ranking logic here")
        
        # 2. Pitcher Metrics
        st.markdown("### 🎯 Pitcher Danger Metrics")
        df_pitcher = pd.DataFrame({
            "Metric": ["Barrel% Allowed", "HardHit%", "Whiff%"],
            "Value": [10.5, 42.0, 31.0] # Replace with your dynamic calculations
        })
        
        # Fixed logic: .map() instead of .applymap()
        def color_danger(val):
            return 'background-color: #5a1e1e' if val > 10 else 'background-color: #1e3a1e'
        
        st.dataframe(df_pitcher.style.map(color_danger, subset=['Value']), use_container_width=True)
        
        # Collect data for the global table below
        all_pitcher_data.append({"Pitcher": game['away_p'], "Danger": 4.1})
        all_pitcher_data.append({"Pitcher": game['home_p'], "Danger": 9.2})

# --- 3. GLOBAL SUMMARY (BOTTOM) ---
st.divider()
st.markdown("### 📊 Daily Pitcher Danger Rankings")
if all_pitcher_data:
    df_global = pd.DataFrame(all_pitcher_data).sort_values("Danger", ascending=False)
    st.table(df_global)
