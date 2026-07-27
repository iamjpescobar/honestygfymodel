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

IMPORTANT — every percentile this endpoint returns is a PERCENTILE OF
GOODNESS, including the ones built on stats where a low raw value is
the good outcome (whiff_percent, k_percent, chase_percent). Savant
orients them all so that 100 is the best in the league. For a batter,
whiff_percent = 100 means he whiffs LESS than everyone, not more.

This block previously asserted the exact opposite, citing Aaron Judge's
whiff_percent = 10.0 as proof that "low = whiffs less". The number was
right; the premise was wrong. Judge is one of the highest-whiff hitters
in baseball, so a 10 on a scale where 100 is best is precisely correct.
That mistake propagated into K Score and the xBH engine's K penalty and
inverted both — Luis Arraez, the toughest strikeout in the league, was
ranking FIRST on the Strikeout Targets board.

Anything here derived from a lower-is-better stat therefore has to be
inverted (100 - percentile) before it can feed a "higher = worse"
score. See engines/top_plays.k_score.
"""
import streamlit as st
import pandas as pd
from datetime import date
from pybaseball import statcast_batter_percentile_ranks


@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
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
