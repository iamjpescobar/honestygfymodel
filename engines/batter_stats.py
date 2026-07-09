import sys
import os

# Ensure project root is in Python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

import streamlit as st
import pandas as pd
import numpy as np
from pybaseball import batting_stats

@st.cache_data(ttl=7200)
def load_batting_stats():
    """
    Loads real MLB batting stats from pybaseball.
    Adds a cleaned name column for matching.
    """
    try:
        df = batting_stats(2026, qual=10)
        df["Name_Clean"] = (
            df["Name"]
            .str.lower()
            .str.replace("[.,']", "", regex=True)
        )
        return df
    except Exception:
        return pd.DataFrame()

def get_batter_profile(name: str, stats_df: pd.DataFrame):
    """
    Returns a batter's stat profile.
    If no real stats exist, generates a realistic fallback profile.
    """
    clean = name.lower().replace(".", "").replace(",", "").replace("'", "")

    # Try to match real stats
    if not stats_df.empty:
        match = stats_df[stats_df["Name_Clean"] == clean]
    else:
        match = pd.DataFrame()

    if not match.empty:
        row = match.iloc[0]
        bbe = int(row.get("AB", 80))
        brl = float(row.get("Barrel%", 8.5))
        hh = float(row.get("HardHit%", 40.0))
        gb = float(row.get("GB%", 42.0))
        ld = float(row.get("LD%", 20.0))
        pull_air = float(row.get("FB%", 35.0))
    else:
        # Fallback random profile (seeded for consistency)
        np.random.seed(abs(hash(name)) % (10**8))
        bbe = int(np.random.uniform(30, 240))
        brl = round(np.random.uniform(4.0, 14.0), 1)
        hh = round(np.random.uniform(25.0, 50.0), 1)
        gb = round(np.random.uniform(35.0, 48.0), 1)
        ld = round(np.random.uniform(15.0, 25.0), 1)
        pull_air = round(np.random.uniform(10.0, 25.0), 1)

    return {
        "BBE": bbe,
        "Brl %": brl,
        "HH %": hh,
        "GB %": gb,
        "LD %": ld,
        "PullAir %": pull_air,
    }

