import pandas as pd
import numpy as np
from datetime import date
from pybaseball import statcast_batter, statcast_pitcher, playerid_lookup

DEFAULT_START_DATE = "2026-03-01"


def _today_str():
    return date.today().strftime("%Y-%m-%d")


# ============================================================
# SAFE STATCAST PULL — surfaces real errors instead of hiding them
# ============================================================

def _safe_statcast_pull(func, player_id, start_date=DEFAULT_START_DATE, end_date=None):
    """
    Pulls real Statcast data for a player.
    Returns (df, error_message). error_message is None on success —
    including when a player legitimately has zero rows (e.g. hasn't
    played yet this season) — so callers can tell "no data available"
    apart from "the pull actually failed."
    """
    if end_date is None:
        end_date = _today_str()

    if player_id is None:
        return pd.DataFrame(), "No player ID could be resolved for this name — check spelling or that pybaseball's lookup table has them."

    try:
        df = func(start_date, end_date, player_id)
        if df is None:
            return pd.DataFrame(), "Statcast returned no response for this player/date range."
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"Statcast pull failed: {e}"


def get_player_id(full_name: str):
    """
    Resolves a player's full name (e.g. "Gerrit Cole") to an MLBAM id
    using pybaseball's player lookup. Works for batters and pitchers alike.
    Returns None if no match is found so callers can fail safely instead
    of crashing.
    """
    if not full_name or not isinstance(full_name, str):
        return None

    parts = full_name.strip().split(" ")
    if len(parts) < 2:
        return None

    first_name = parts[0]
    last_name = " ".join(parts[1:])

    try:
        matches = playerid_lookup(last_name, first_name)
        if matches is None or matches.empty:
            return None
        matches = matches.sort_values("mlb_played_last", ascending=False)
        return int(matches.iloc[0]["key_mlbam"])
    except Exception:
        return None


# Kept as an alias — existing code calls get_pitcher_id(), and the lookup
# itself isn't pitcher-specific.
get_pitcher_id = get_player_id


def build_pitch_arsenal(pitcher_data: dict) -> pd.DataFrame:
    """
    Converts the 'Pitch Arsenal' usage dict inside a pitcher profile
    (as returned by get_pitcher_statcast) into a clean DataFrame for display.
    """
    arsenal = {}
    if isinstance(pitcher_data, dict):
        arsenal = pitcher_data.get("Pitch Arsenal", {}) or {}

    if not arsenal:
        return pd.DataFrame(columns=["Pitch Type", "Usage %"])

    df = pd.DataFrame(
        list(arsenal.items()),
        columns=["Pitch Type", "Usage %"]
    ).sort_values("Usage %", ascending=False).reset_index(drop=True)

    return df


# ============================================================
# REAL STATCAST COLUMN DERIVATIONS
# (raw pybaseball/Statcast output has NO "barrel"/"hard_hit"/"ld"/"gb"
#  boolean columns — these must be derived from launch_speed,
#  launch_angle, bb_type, hc_x/hc_y, zone, description, events)
# ============================================================

def _spray_angle(hc_x, hc_y):
    """Standard horizontal spray-angle formula (degrees) from Statcast hit coordinates."""
    return np.degrees(np.arctan2((hc_x - 125.42), (198.27 - hc_y)))


def _compute_batted_ball_metrics(df: pd.DataFrame):
    """Derives Barrel %, Hard Hit %, LD/GB/FB %, and PullAir % from batted-ball rows only."""
    if df.empty or "type" not in df.columns:
        return {"Brl %": 0.0, "HH %": 0.0, "LD %": 0.0, "GB %": 0.0, "PullAir %": 0.0, "BBE": 0}

    bbe_df = df[df["type"] == "X"].copy()
    bbe_count = len(bbe_df)
    if bbe_count == 0:
        return {"Brl %": 0.0, "HH %": 0.0, "LD %": 0.0, "GB %": 0.0, "PullAir %": 0.0, "BBE": 0}

    ls = pd.to_numeric(bbe_df.get("launch_speed"), errors="coerce")
    la = pd.to_numeric(bbe_df.get("launch_angle"), errors="coerce")

    hh = (ls >= 95).sum()

    if "launch_speed_angle" in bbe_df.columns:
        barrels = (bbe_df["launch_speed_angle"] == 6).sum()
    else:
        # Approximation if Statcast's own barrel bucket isn't present
        barrels = ((ls >= 98) & (la >= 26) & (la <= 30)).sum()

    bb_type = bbe_df.get("bb_type", pd.Series(dtype=str))
    ld = (bb_type == "line_drive").sum()
    gb = (bb_type == "ground_ball").sum()
    fb = (bb_type == "fly_ball").sum()

    pull_air = 0
    if {"hc_x", "hc_y", "stand"}.issubset(bbe_df.columns):
        angle = _spray_angle(pd.to_numeric(bbe_df["hc_x"], errors="coerce"),
                              pd.to_numeric(bbe_df["hc_y"], errors="coerce"))
        is_fb = bb_type == "fly_ball"
        pulled_rhh = (bbe_df["stand"] == "R") & (angle < 0)
        pulled_lhh = (bbe_df["stand"] == "L") & (angle > 0)
        pull_air = (is_fb & (pulled_rhh | pulled_lhh)).sum()

    return {
        "Brl %": round(barrels / bbe_count * 100, 2),
        "HH %": round(hh / bbe_count * 100, 2),
        "LD %": round(ld / bbe_count * 100, 2),
        "GB %": round(gb / bbe_count * 100, 2),
        "PullAir %": round(pull_air / bbe_count * 100, 2),
        "BBE": bbe_count
    }


def _compute_whiff_pct(df: pd.DataFrame) -> float:
    if df.empty or "description" not in df.columns:
        return 0.0
    return round((df["description"] == "swinging_strike").mean() * 100, 2)


def _compute_zone_contact_pct(df: pd.DataFrame) -> float:
    if df.empty or "zone" not in df.columns or "description" not in df.columns:
        return 0.0
    in_zone = pd.to_numeric(df["zone"], errors="coerce").between(1, 9)
    contact_desc = ["hit_into_play", "foul", "foul_tip"]
    swing_desc = contact_desc + ["swinging_strike"]
    swings_in_zone = df["description"].isin(swing_desc) & in_zone
    contact_in_zone = df["description"].isin(contact_desc) & in_zone
    total_swings = swings_in_zone.sum()
    if total_swings == 0:
        return 0.0
    return round(contact_in_zone.sum() / total_swings * 100, 2)


# ============================================================
# BATTER STATCAST PROFILE
# ============================================================

def get_batter_statcast(batter_id):
    df, error = _safe_statcast_pull(statcast_batter, batter_id)
    metrics = _compute_batted_ball_metrics(df)
    metrics["Whiff %"] = _compute_whiff_pct(df)
    metrics["_error"] = error
    return metrics


# ============================================================
# PITCHER STATCAST PROFILE
# ============================================================

def get_pitcher_statcast(pitcher_id):
    df, error = _safe_statcast_pull(statcast_pitcher, pitcher_id)

    metrics = _compute_batted_ball_metrics(df)
    metrics["Whiff %"] = _compute_whiff_pct(df)
    metrics["ZoneContact %"] = _compute_zone_contact_pct(df)

    bbe = metrics["BBE"]
    if not df.empty and "events" in df.columns:
        hr_count = (df["events"] == "home_run").sum()
        metrics["HR/BBE"] = round(hr_count / bbe, 3) if bbe > 0 else 0.0
    else:
        metrics["HR/BBE"] = 0.0

    if not df.empty and "pitch_type" in df.columns:
        arsenal = df["pitch_type"].dropna().value_counts(normalize=True) * 100
        metrics["Pitch Arsenal"] = {k: round(v, 2) for k, v in arsenal.items()}
    else:
        metrics["Pitch Arsenal"] = {}

    metrics["_error"] = error
    return metrics
