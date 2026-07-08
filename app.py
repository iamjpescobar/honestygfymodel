import streamlit as st
import pandas as pd
from pybaseball import batting_stats

# Use caching to bypass 403 errors and speed up your app
@st.cache_data(ttl=3600)
def load_batting_stats():
    try:
        # Fetch data
        df = batting_stats(2026, qual=10)
        
        # Ensure 'Name_Clean' exists to prevent Engine Errors
        if 'Name' in df.columns:
            df['Name_Clean'] = df['Name'].str.lower().str.replace('[.,\']', '', regex=True)
        else:
            # Fallback if structure changes
            df['Name_Clean'] = "unknown"
            
        return df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame() # Return empty to prevent crashes
