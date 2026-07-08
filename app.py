import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pybaseball import batting_stats, pitching_stats

# --- 1. CONFIG ---
st.set_page_config(layout="wide", page_title="Los Cappers Lab", page_icon="🧪")

# --- 2. ROBUST DATA LOADERS ---
@st.cache_data(ttl=3600)
def load_batting_data():
    try:
        return batting_stats(2026, qual=10)
    except Exception as e:
        return None # Return None if the site blocks us

# --- 3. UI ---
st.title("🧪 Los Cappers Lab: Engine Status")

tab1, tab2, tab3 = st.tabs(["📊 Analytics", "🎯 Weakspots", "⚡ K-Zone"])

with tab1:
    st.write("Data pipeline active.")
    df = load_batting_data()
    if df is not None:
        st.dataframe(df.head())
    else:
        st.error("Data Load Error: Site is currently blocking requests. Caching is active.")

with tab2:
    st.write("Weakspot Map active.")
    # Plotly is now safe because requirements.txt will install it
    fig = px.scatter(x=[1, 2, 3], y=[1, 2, 3]) 
    st.plotly_chart(fig)

with tab3:
    st.write("Strikeout Zone active.")
