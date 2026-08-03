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
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from pybaseball import statcast_batter_percentile_ranks


_EASTERN = ZoneInfo("America/New_York")

_PCT_PATH = Path(__file__).resolve().parents[1] / "data" / "statcast" / "savant_percentiles.parquet"


@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
def load_percentile_ranks(year: int = None):
    """
    Real, live MLB-computed percentile ranks for every qualified batter
    this season, straight from baseballsavant.mlb.com. Returns
    (DataFrame indexed by player_id as a string, error_message).

    LOCAL FILE FIRST. Every score on the Game Card is built on this
    table, so the page cannot render a ranked lineup until it resolves —
    which made it a blocking network round trip on every cold start, and
    on Render's free tier the process spins down overnight, so somebody
    pays it most mornings. precompute.fetch_savant_percentiles ships the
    identical table (same endpoint, same day) in the nightly package.

    The live pull below is unchanged and still runs whenever the file
    isn't there: a deploy predating the first nightly that includes it,
    or a nightly where Savant was unreachable. This can only remove
    latency — it can't become the reason the scores go missing.
    """
    if year is None:
        # Eastern, not the server's UTC: on Dec 31 after 7pm ET the
        # server is already in January and would request a season that
        # has no leaderboard yet, blanking every score on the board.
        year = datetime.now(_EASTERN).year
    if _PCT_PATH.exists():
        try:
            df = pd.read_parquet(_PCT_PATH)
            if df is not None and not df.empty and "player_id" in df.columns:
                df = df.dropna(subset=["player_id"]).copy()
                df["player_id"] = df["player_id"].astype(int).astype(str)
                return df.set_index("player_id"), None
        except Exception:
            pass  # fall through to the live pull rather than failing
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


# ------------------------------------------------------------
# LEAGUE-WIDE HR METRICS LOOKUP
# ------------------------------------------------------------
# Reads the table precompute.build_hr_metrics ships nightly. Same access
# shape as the Savant percentile leaderboard above — one cached load,
# then O(1) lookups — so scoring a full slate costs no per-player pulls.
#
# Every *_pct column is already a 0-100 league percentile, on the same
# scale as the Savant percentiles, so callers can blend them directly.
#
# Returns None (never 0) when the table is absent or the batter didn't
# clear the sample floor. The table only appears after a nightly run
# that includes it, so hr_score MUST keep working without it.
_HR_METRICS_PATH = Path(__file__).resolve().parents[1] / "data" / "hr_metrics.parquet"


@st.cache_data(ttl=21600, max_entries=1, show_spinner=False)
def get_hr_metrics():
    """DataFrame indexed by batter id, or None when unavailable."""
    if not _HR_METRICS_PATH.exists():
        return None
    try:
        df = pd.read_parquet(_HR_METRICS_PATH)
        return df.set_index("batter")
    except Exception:
        return None


def get_hr_metric(hr_df, player_id, column):
    """One metric for one batter, or None if we can't measure him."""
    if hr_df is None or player_id is None or column not in hr_df.columns:
        return None
    try:
        val = hr_df.at[int(player_id), column]
    except (KeyError, ValueError, TypeError):
        return None
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return float(val)
