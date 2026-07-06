import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# 🎨 PREMIUM DARK MODE THEME
st.set_page_config(page_title="Los Cappers Lab 🧪", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    h1, h2, h3 { color: #a3ffb4 !important; }
    div[data-testid="stSelectbox"] { background-color: #161b22; border: 2px solid #a3ffb4; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 Real-Time S.L.A.M. Index Hub")

@st.cache_data(ttl=3600)
def fetch_game_data():
    """Fetch schedule once, cache for 1 hour to keep it snappy."""
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        data = requests.get(url).json()
        games = data.get('dates', [{}])[0].get('games', [])
        options = []
        for g in games:
            away = g['teams']['away']['team']['name']
            home = g['teams']['home']['team']['name']
            ap = g['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
            hp = g['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
            options.append({
                "label": f"{away} ({ap}) vs {home} ({hp})",
                "away": away, "home": home, "ap": ap, "hp": hp
            })
        return options
    except: return []

# ⚡ LOAD DATA
game_list = fetch_game_data()

if game_list:
    # Use the label for the dropdown, return the full dict object
    selected = st.selectbox("Select Today's Matchup:", game_list, format_func=lambda x: x['label'])
    
    col1, col2 = st.columns(2)
    with col1:
        target_pitcher = st.radio("Select Target Pitcher:", [selected['ap'], selected['hp']])
    
    if target_pitcher != "TBD":
        st.info(f"🧪 Analyzing: {target_pitcher} vs {selected['home'] if target_pitcher == selected['ap'] else selected['away']}")
        # YOUR CALCULATION ENGINE GOES HERE
    else:
        st.warning("Pitcher TBD - Waiting for confirmed starters.")
else:
    st.error("Could not fetch MLB schedule. Please check connection.")
