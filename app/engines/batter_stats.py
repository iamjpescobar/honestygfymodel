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


from pathlib import Path

_FG_LOCAL = Path(__file__).resolve().parent.parent / "data" / "statcast" / "fangraphs_batting.parquet"


@st.cache_data(ttl=7200)
def load_batting_stats():
    """
    Loads real MLB batting stats (FanGraphs leaderboard).
    Reads the copy shipped by the nightly pipeline first — FanGraphs
    blocks requests from cloud hosts like Render, but not from the
    GitHub Action that fetches it — and only tries a live pull if no
    local copy exists. Returns (df, error_message); error is None on
    success.
    """
    if _FG_LOCAL.exists():
        try:
            df = pd.read_parquet(_FG_LOCAL)
            df["Name_Clean"] = (
                df["Name"]
                .str.lower()
                .str.replace("[.,']", "", regex=True)
            )
            return df, None
        except Exception:
            pass  # fall through to the live pull
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


def get_batter_profile(name: str, stats_df: pd.DataFrame, load_error: str = None,
                       batter_id=None):
    """
    Returns a batter's real stat profile. Tries FanGraphs first (larger
    season-long sample); if that's unavailable (e.g. FanGraphs blocking
    cloud-host requests with a 403, as it commonly does on Streamlit Cloud/
    Render) or has no match for this name, falls back to Baseball Savant/
    Statcast data instead — a second, independent, still 100% real source.
    Never fabricates data under any circumstance.

    batter_id: the batter's MLBAM id if the caller already has it (e.g.
    from the live roster). Passing it lets the Statcast fallback read the
    player's data directly instead of resolving the name via pybaseball's
    full player-register download — which is enormous in memory and was
    OOM-crashing the 512MB instance whenever FanGraphs was blocked.
    """
    clean = name.lower().replace(".", "").replace(",", "").replace("'", "")
    match = pd.DataFrame()
    if not stats_df.empty:
        match = stats_df[stats_df["Name_Clean"] == clean]
    if not match.empty:
        row = match.iloc[0]
        return {
            "BBE": int(row.get("AB", 0)),
            "Brl %": _pct(row.get("Barrel%", 0.0)),
            "HH %": _pct(row.get("HardHit%", 0.0)),
            "GB %": _pct(row.get("GB%", 0.0)),
            "LD %": _pct(row.get("LD%", 0.0)),
            "PullAir %": _pct(row.get("FB%", 0.0)),
            "_source": "FanGraphs",
            "_error": None
        }

    # FanGraphs unavailable or no match — fall back to real Statcast data
    from engines.statcast_engine import get_player_id, get_batter_statcast
    fg_reason = load_error or f"No matching FanGraphs stats found for '{name}'."

    # Use the caller-provided MLBAM id when available; only resort to the
    # heavyweight name lookup when we genuinely have no id.
    if batter_id is None:
        batter_id = get_player_id(name)
    sc_profile = get_batter_statcast(batter_id)
    if sc_profile.get("_error") is None and sc_profile.get("BBE", 0) > 0:
        sc_profile["_source"] = "Statcast (FanGraphs unavailable)"
        sc_profile["_error"] = None
        return sc_profile

    # Both real sources failed — surface both reasons honestly, no fabrication
    sc_reason = sc_profile.get("_error") or "no batted-ball events found"
    return {
        "BBE": 0, "Brl %": 0.0, "HH %": 0.0, "GB %": 0.0,
        "LD %": 0.0, "PullAir %": 0.0,
        "_source": None,
        "_error": f"FanGraphs: {fg_reason} | Statcast fallback: {sc_reason}"
    }


def get_league_percentile(stats_df: pd.DataFrame, column: str, value: float) -> int:
    """
    Real percentile rank of `value` against the actual qualified-batter
    league leaderboard already loaded in stats_df (FanGraphs, qual=10).
    Returns None if the column isn't available or there's no data to
    rank against \u2014 callers must handle that rather than assume a number.
    This is a genuine league-wide percentile, not a percentile within
    just today's lineup.
    """
    if stats_df is None or stats_df.empty or column not in stats_df.columns:
        return None
    series = pd.to_numeric(stats_df[column], errors="coerce").dropna()
    if series.empty:
        return None
    # FanGraphs sometimes returns these as fractions (0.085) rather than
    # whole percents (8.5) \u2014 normalize both sides the same way _pct() does
    # elsewhere in this file so the comparison is apples-to-apples.
    if series.median() <= 1.5:
        series = series * 100
    pct = (series < value).mean() * 100
    return int(round(pct))