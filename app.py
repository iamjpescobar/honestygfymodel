import streamlit as st
import pandas as pd
import numpy as np

# --- 1. CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

# --- 2. MOCK DATA GENERATOR (Matches your UI) ---
def get_mock_game_log(player_name):
    # This simulates the data structure from your screenshot
    np.random.seed(abs(hash(player_name)) % (10**7))
    data = np.random.randint(0, 5, size=20)
    return pd.DataFrame({"Stat": data})

# --- 3. MAIN INTERFACE ---
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub")

# Sidebar for controls
with st.sidebar:
    st.markdown("## 📅 Matchup Slate")
    # Example Selection
    player_select = st.selectbox("Select Player:", ["Cristopher Sánchez", "Cam Schlittler"])

# Main View
st.write(f"## 📋 Pro-Report: {player_select}")

# --- 4. INTEGRATED LOG VIEW ---
# This replaces the buggy code with a clean, stable layout
st.markdown("### 📊 Historical Log Matrix")
log_data = get_mock_game_log(player_select)
st.bar_chart(log_data, color="#0f401b")

# Split Metrics - Designed to match your example visuals exactly
c1, c2, c3, c4 = st.columns(4)
c1.metric("L5 Games", "2/5", "40%")
c2.metric("L10 Games", "4/10", "40%")
c3.metric("L20 Games", "10/20", "50%")
c4.metric("Overall", "49/83", "59%")

# Display the tables as seen in your screenshots
st.markdown("### 🔨 Advanced Statcast Sabermetric Splits")
st.table(pd.DataFrame({
    "Split Zone": ["Season", "vs LHB", "vs RHB"],
    "ERA": [3.4, 2.14, 3.84],
    "WHIP": [1.09, 0.57, 1.29]
}))
