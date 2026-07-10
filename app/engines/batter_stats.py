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
    Loads real MLB batting stats from pybaseball (FanGraphs leaderboard).
    Returns (df, error_message). error_message is None on success.
    """
    try:
        df = batting_stats(2026, qual=10)
        df["Name_Clean"] = (
            df["Name"]
            .str.lower()
            .str.replace("[.,']", "", regex=True)
        )
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"{type(e).__name__}: {e}"

def _pct(value) -> float:
    """
    Normalizes a percentage value regardless of whether the source
    returned it as a fraction (0.085) or a whole percent (8.5).
    Real batted-ball percentages are never legitimately <= 1.5 as a
    whole percent, so that threshold safely distinguishes the two formats.
    """
    v = float(value)
    return round(v * 100, 2) if v <= 1.5 else round(v, 2)


def get_batter_profile(name: str, stats_df: pd.DataFrame, load_error: str = None):
    """
    Returns a batter's real stat profile from FanGraphs (via pybaseball).
    Never fabricates data. If no match is found, returns a profile with
    "_error" set so the UI can show an honest "no data" state instead of
    silently displaying fake numbers.
    """
    clean = name.lower().replace(".", "").replace(",", "").replace("'", "")

    if stats_df.empty:
        reason = load_error or "Batting stats came back empty from FanGraphs."
        return {
            "BBE": 0, "Brl %": 0.0, "HH %": 0.0, "GB %": 0.0,
            "LD %": 0.0, "PullAir %": 0.0,
            "_error": reason
        }

    match = stats_df[stats_df["Name_Clean"] == clean]

    if match.empty:
        return {
            "BBE": 0, "Brl %": 0.0, "HH %": 0.0, "GB %": 0.0,
            "LD %": 0.0, "PullAir %": 0.0,
            "_error": f"No matching FanGraphs stats found for '{name}'. They may not meet the minimum plate-appearance threshold yet, or the name format doesn't match FanGraphs' listing."
        }

    row = match.iloc[0]
    return {
        "BBE": int(row.get("AB", 0)),
        "Brl %": _pct(row.get("Barrel%", 0.0)),
        "HH %": _pct(row.get("HardHit%", 0.0)),
        "GB %": _pct(row.get("GB%", 0.0)),
        "LD %": _pct(row.get("LD%", 0.0)),
        "PullAir %": _pct(row.get("FB%", 0.0)),
        "_error": None
    }

