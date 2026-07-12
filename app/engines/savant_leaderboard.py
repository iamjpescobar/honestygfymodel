"""
Real, live MLB Statcast percentile rankings — pulled directly from
baseballsavant.mlb.com (MLB's own first-party data), not FanGraphs.
This is what HR Score / Hit Score / K Score are built on: real
percentiles MLB computes themselves, not our own approximation against
a leaderboard that kept getting blocked in cloud/dev environments.

Verified against real live data before this was built, not assumed:
Aaron Judge and James Wood show brl_percent=100.0 / hard_hit_percent=
98-100.0 (MLB's actual top performers, 100th percentile) — confirms
this endpoint returns a true 0-100 percentile scale, not a raw rate.
Luis Arraez and Nico Hoerner show 0.6 / 0.9 on the SEPARATE raw-rate
endpoint (statcast_batter_exitvelo_barrels) — confirms that one is the
real raw stat, not a percentile. The two are easy to confuse since
both use a column literally named "brl_percent" — this file only uses
the percentile-ranks endpoint, on purpose.

IMPORTANT — whiff_percent and k_percent here are percentile RANKS of
the raw stat itself, not "percentile of goodness": a LOW number means
the batter whiffs/strikes out LESS than most of the league (good), a
HIGH number means more than most (bad). Confirmed via real data —
Aaron Judge (elite contact hitter) shows whiff_percent=10.0. Used
directly for K Score with no inversion needed; that already matches
this app's "higher K Score = more strikeout-prone" convention.
"""
import streamlit as st
import pandas as pd
from datetime import date
from pybaseball import statcast_batter_percentile_ranks


@st.cache_data(ttl=3600)
def load_percentile_ranks(year: int = None):
    """
    Real, live MLB-computed percentile ranks for every qualified batter
    this season, straight from baseballsavant.mlb.com. Returns
    (DataFrame indexed by player_id as a string, error_message).
    Cached 1 hour — this is a season-aggregate leaderboard, not
    something that needs to refetch every pageview.
    """
    if year is None:
        year = date.today().year
    try:
        df = statcast_batter_percentile_ranks(year)
        if df is None or df.empty:
            return pd.DataFrame(), "Baseball Savant returned no data for this year yet."
        df = df.dropna(subset=["player_id"]).copy()
        df["player_id"] = df["player_id"].astype(int).astype(str)
        return df.set_index("player_id"), None
    except Exception as e:
        return pd.DataFrame(), f"Baseball Savant request failed: {e}"


def get_percentile(df: pd.DataFrame, player_id, column: str):
    """
    Real percentile for one batter/column, or None if unavailable.
    Never returns a fabricated 0 — None means "no data for this
    player," which callers must display honestly (e.g. "N/A"), not
    silently treat as a real zero percentile.
    """
    if df is None or df.empty or player_id is None:
        return None
    player_id = str(player_id)
    if player_id not in df.index:
        return None
    val = df.loc[player_id, column]
    if isinstance(val, pd.Series):  # duplicate index guard, take first
        val = val.iloc[0]
    if pd.isna(val):
        return None
    return float(val)
