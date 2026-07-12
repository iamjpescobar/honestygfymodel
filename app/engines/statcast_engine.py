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

    from styles.kc_theme import pitch_name
    df = pd.DataFrame(
        [(pitch_name(k), v) for k, v in arsenal.items()],
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
    """Derives Barrel %, Hard Hit %, LD/GB/FB %, Sweet Spot %, PullAir %,
    Pull Barrel %, and Blast % from batted-ball rows / real bat-tracking data."""
    empty = {
        "Brl %": 0.0, "HH %": 0.0, "LD %": 0.0, "GB %": 0.0, "FB %": 0.0,
        "SweetSpot %": 0.0, "PullAir %": 0.0, "PullBrl %": 0.0, "Blast %": 0.0, "BBE": 0,
    }
    if df.empty or "type" not in df.columns:
        return empty

    bbe_df = df[df["type"] == "X"].copy()
    bbe_count = len(bbe_df)
    if bbe_count == 0:
        return empty

    ls = pd.to_numeric(bbe_df.get("launch_speed"), errors="coerce")
    la = pd.to_numeric(bbe_df.get("launch_angle"), errors="coerce")

    hh = (ls >= 95).sum()

    if "launch_speed_angle" in bbe_df.columns:
        is_barrel = bbe_df["launch_speed_angle"] == 6
    else:
        # Approximation if Statcast's own barrel bucket isn't present
        is_barrel = (ls >= 98) & (la >= 26) & (la <= 30)
    barrels = is_barrel.sum()

    # Sweet Spot % — MLB's own definition: launch angle 8-32 degrees
    sweet_spot = la.between(8, 32).sum()

    bb_type = bbe_df.get("bb_type", pd.Series(dtype=str))
    ld = (bb_type == "line_drive").sum()
    gb = (bb_type == "ground_ball").sum()
    fb = (bb_type == "fly_ball").sum()

    pull_air = 0
    pull_barrel = 0
    if {"hc_x", "hc_y", "stand"}.issubset(bbe_df.columns):
        angle = _spray_angle(pd.to_numeric(bbe_df["hc_x"], errors="coerce"),
                              pd.to_numeric(bbe_df["hc_y"], errors="coerce"))
        is_fb = bb_type == "fly_ball"
        pulled_rhh = (bbe_df["stand"] == "R") & (angle < 0)
        pulled_lhh = (bbe_df["stand"] == "L") & (angle > 0)
        is_pulled = pulled_rhh | pulled_lhh
        pull_air = (is_fb & is_pulled).sum()
        pull_barrel = (is_barrel & is_pulled).sum()

    # Blast % — real MLB formula: squared-up% = EV / ((bat_speed*1.23) + (pitch_speed*0.2116));
    # a swing is a "blast" when (squared_up% * 100) + bat_speed >= 164.
    # Scoped to balls in play AND fouls (both are real contact with a
    # real measurable exit velocity) — NOT balls-in-play only. A ball
    # that gets fouled off weakly is still a real swing that should
    # count toward the denominator; excluding it meant only shots that
    # "worked out" into fair territory were ever measured, which
    # quietly inflates the rate. A true swing-and-miss has no exit
    # velocity to measure at all (bat never touched the ball), so it
    # can't enter this specific formula — that's a real physical limit
    # of the stat, not an oversight.
    blast_pct = 0.0
    if "description" in df.columns and {"bat_speed", "release_speed"}.issubset(df.columns):
        contact_df = df[(df["type"] == "X") | (df["description"] == "foul")]
        c_ls = pd.to_numeric(contact_df.get("launch_speed"), errors="coerce")
        c_bs = pd.to_numeric(contact_df.get("bat_speed"), errors="coerce")
        c_pitch_speed = pd.to_numeric(contact_df.get("release_speed"), errors="coerce")
        tracked = c_bs.notna() & c_pitch_speed.notna() & c_ls.notna()
        if tracked.sum() > 0:
            max_ev = (c_bs[tracked] * 1.23) + (c_pitch_speed[tracked] * 0.2116)
            squared_up_pct = (c_ls[tracked] / max_ev) * 100
            is_blast = (squared_up_pct + c_bs[tracked]) >= 164
            blast_pct = round(is_blast.sum() / tracked.sum() * 100, 2)

    return {
        "Brl %": round(barrels / bbe_count * 100, 2),
        "HH %": round(hh / bbe_count * 100, 2),
        "LD %": round(ld / bbe_count * 100, 2),
        "GB %": round(gb / bbe_count * 100, 2),
        "FB %": round(fb / bbe_count * 100, 2),
        "SweetSpot %": round(sweet_spot / bbe_count * 100, 2),
        "PullAir %": round(pull_air / bbe_count * 100, 2),
        "PullBrl %": round(pull_barrel / bbe_count * 100, 2),
        "Blast %": blast_pct,
        "BBE": bbe_count,
    }


def _compute_swstr_pct(df: pd.DataFrame) -> float:
    """SwStr % = swinging strikes / ALL PITCHES SEEN. Different
    denominator than Whiff % (below) — don't conflate the two, they
    answer different questions."""
    if df.empty or "description" not in df.columns:
        return 0.0
    return round((df["description"] == "swinging_strike").mean() * 100, 2)


def _compute_whiff_pct(df: pd.DataFrame) -> float:
    """Whiff % = swinging strikes / SWINGS ONLY (swings = contact +
    swinging strikes). This was previously computed with the wrong
    denominator (all pitches, which is actually SwStr%) — fixed to use
    the real definition."""
    if df.empty or "description" not in df.columns:
        return 0.0
    swing_desc = ["hit_into_play", "foul", "foul_tip", "swinging_strike", "swinging_strike_blocked"]
    swings = df["description"].isin(swing_desc)
    total_swings = swings.sum()
    if total_swings == 0:
        return 0.0
    whiffs = df["description"].isin(["swinging_strike", "swinging_strike_blocked"]).sum()
    return round(whiffs / total_swings * 100, 2)


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
    metrics["SwStr %"] = _compute_swstr_pct(df)
    metrics["_error"] = error
    metrics["_raw_df"] = df  # kept for real recency-window slicing downstream
    return metrics


def get_batter_vs_pitch_types(batter_id, pitch_types: list, window: str = "season", unit: str = "bbe"):
    """
    Real batter performance specifically against a given set of pitch
    types (meant to be a pitcher's top 3 most-used pitches) — same real
    windowing and the exact same proven stat formulas as
    get_batter_profile_windowed, just filtered down to pitches of
    those specific types first.

    Kept as its OWN separate stat rather than folded into SLAM: SLAM
    already asks a lot of a small recent-window sample, and narrowing
    it further by pitch type on top would leave a real, honest "not
    enough data" far more often than it would a usable number.
    """
    from engines.recency_windows import apply_window
    df, error = _safe_statcast_pull(statcast_batter, batter_id)
    windowed_df = apply_window(df, window, unit)

    if windowed_df.empty or "pitch_type" not in windowed_df.columns or not pitch_types:
        matchup_df = windowed_df.iloc[0:0]
    else:
        matchup_df = windowed_df[windowed_df["pitch_type"].isin(pitch_types)]

    metrics = _compute_batted_ball_metrics(matchup_df)
    metrics["Whiff %"] = _compute_whiff_pct(matchup_df)
    metrics["SwStr %"] = _compute_swstr_pct(matchup_df)
    metrics["_error"] = error
    metrics["_pitches_seen"] = len(matchup_df)
    metrics["_window_rows"] = len(windowed_df)
    return metrics


def get_batter_profile_windowed(batter_id, window: str = "season", unit: str = "bbe"):
    """
    Real recency-windowed batter profile — same metrics as
    get_batter_statcast, but sliced to a specific window ("season" /
    "l60" / "l25" / "l15" / "l5") and unit ("games" / "pa" / "bbe")
    using engines/recency_windows.py. This is what SLAM, the Lineup
    table's window filter, and the pitch-matchup stat all call.
    """
    from engines.recency_windows import apply_window
    df, error = _safe_statcast_pull(statcast_batter, batter_id)
    windowed_df = apply_window(df, window, unit)
    metrics = _compute_batted_ball_metrics(windowed_df)
    metrics["Whiff %"] = _compute_whiff_pct(windowed_df)
    metrics["SwStr %"] = _compute_swstr_pct(windowed_df)
    if not windowed_df.empty and {"estimated_slg_using_speedangle", "estimated_woba_using_speedangle"}.issubset(windowed_df.columns):
        bbe_only = windowed_df[windowed_df["type"] == "X"] if "type" in windowed_df.columns else windowed_df
        metrics["xSLG"] = round(pd.to_numeric(bbe_only["estimated_slg_using_speedangle"], errors="coerce").mean(), 3) if not bbe_only.empty else None
        metrics["xwOBA"] = round(pd.to_numeric(bbe_only["estimated_woba_using_speedangle"], errors="coerce").mean(), 3) if not bbe_only.empty else None
    else:
        metrics["xSLG"] = None
        metrics["xwOBA"] = None
    metrics["_error"] = error
    metrics["_window_rows"] = len(windowed_df)
    return metrics


# ============================================================
# PITCHER STATCAST PROFILE
# ============================================================

def _compute_pitch_type_breakdown(df: pd.DataFrame) -> dict:
    """
    Real per-pitch-type breakdown: usage%, Whiff% (of swings against
    THAT pitch specifically), and Hard Hit% allowed (of batted balls
    against that pitch). This is what actually makes an arsenal list
    useful — "usage 23%" alone doesn't tell you if that pitch is any
    good, whiff/hard-hit rates do.
    """
    if df.empty or "pitch_type" not in df.columns:
        return {}

    total = len(df)
    breakdown = {}
    for pt, group in df.groupby("pitch_type"):
        if pd.isna(pt):
            continue
        usage = round(len(group) / total * 100, 2)
        whiff = _compute_whiff_pct(group)
        bbe = group[group["type"] == "X"] if "type" in group.columns else pd.DataFrame()
        if not bbe.empty and "launch_speed" in bbe.columns:
            ls = pd.to_numeric(bbe["launch_speed"], errors="coerce")
            hh_allowed = round((ls >= 95).mean() * 100, 2) if ls.notna().any() else None
        else:
            hh_allowed = None
        breakdown[pt] = {"usage": usage, "whiff": whiff, "hh_allowed": hh_allowed, "n": len(group)}
    return breakdown


def get_pitcher_statcast(pitcher_id):
    df, error = _safe_statcast_pull(statcast_pitcher, pitcher_id)

    metrics = _compute_batted_ball_metrics(df)
    metrics["Whiff %"] = _compute_whiff_pct(df)
    metrics["SwStr %"] = _compute_swstr_pct(df)
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
        metrics["Pitch Arsenal Detail"] = _compute_pitch_type_breakdown(df)
    else:
        metrics["Pitch Arsenal"] = {}
        metrics["Pitch Arsenal Detail"] = {}

    metrics["_error"] = error
    return metrics


# ============================================================
# ADVANCED PITCHER SPLITS
# (for the Game Card Splits table — BA/SLG/ISO/WHIP/K%/BB%/etc.)
#
# Every derived stat below uses a specific, documented definition so
# nothing here claims more precision than it has. These are standard
# sabermetric formulas computed from raw Statcast pitch-level rows —
# NOT pulled from a third-party stats provider, so treat them as this
# app's own calculation rather than an official league stat.
# ============================================================

_HIT_EVENTS = {"single", "double", "triple", "home_run"}
_OUT_EVENTS = {
    "field_out", "strikeout", "strikeout_double_play", "double_play",
    "grounded_into_double_play", "force_out", "fielders_choice_out",
    "sac_fly", "sac_bunt", "triple_play", "field_error",
}
# Note: field_error does NOT record an out in real scoring (reached on
# error), but we count it toward outs here as a pragmatic IP estimate
# since we don't have an official box-score outs feed — flagged so it's
# not mistaken for a certified stat.
_WALK_EVENTS = {"walk", "hit_by_pitch"}
_STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}


def get_pitcher_advanced_splits(pitcher_id, side: str = None) -> dict:
    """
    Computes BA/SLG/ISO/WHIP/HR/HR9/BB%/K%/Whiff%/SwStr%/K9/Putaway%/
    1stPitchStrike%/Meatball% against a pitcher from raw Statcast rows.

    side: None for overall, "R" for vs RHB, "L" for vs LHB (filters on
    the batter's stand).

    Definitions used:
      BA        = hits / at-bats (at-bats = PAs with a batted-ball or
                  strikeout result; walks/HBP/sac excluded per standard rule)
      SLG       = total bases / at-bats
      ISO       = SLG - BA
      WHIP      = (walks + hits) / estimated innings pitched
      IP        = estimated from out-producing events / 3 (approximation —
                  this app has no official box-score innings feed)
      BB%, K%   = walks / PA, strikeouts / PA
      Whiff%    = swinging strikes / total swings
      SwStr%    = swinging strikes / total pitches
      Putaway%  = strikeouts / pitches thrown with a 2-strike count
      1stPS%    = first pitch of the PA was a strike, as % of PAs
      Meatball% = pitches landing in the heart of the zone (Statcast
                  attack-zone approximation: |plate_x| < 0.83 ft and
                  1.5-3.5 ft plate_z), as % of all pitches
    """
    empty = {
        "BA": 0.0, "SLG": 0.0, "ISO": 0.0, "WHIP": 0.0, "HR": 0, "HR/9": 0.0,
        "BB%": 0.0, "K%": 0.0, "Whiff%": 0.0, "SwStr%": 0.0, "K/9": 0.0,
        "Putaway%": 0.0, "1stPS%": 0.0, "Meatball%": 0.0, "_error": None,
    }

    df, error = _safe_statcast_pull(statcast_pitcher, pitcher_id)
    if df.empty:
        empty["_error"] = error
        return empty

    if side and "stand" in df.columns:
        df = df[df["stand"] == side].copy()
    if df.empty:
        empty["_error"] = "No pitches found for this split."
        return empty

    total_pitches = len(df)
    swings_desc = {"hit_into_play", "foul", "foul_tip", "swinging_strike",
                    "swinging_strike_blocked"}
    swinging_strike_desc = {"swinging_strike", "swinging_strike_blocked"}

    swings = df["description"].isin(swings_desc).sum() if "description" in df.columns else 0
    whiffs = df["description"].isin(swinging_strike_desc).sum() if "description" in df.columns else 0
    whiff_pct = round(whiffs / swings * 100, 1) if swings > 0 else 0.0
    swstr_pct = round(whiffs / total_pitches * 100, 1) if total_pitches > 0 else 0.0

    # Per-plate-appearance aggregation (last pitch of each PA carries the event)
    pa_events = pd.Series(dtype=object)
    if "events" in df.columns:
        pa_events = df["events"].dropna()

    pa_count = len(pa_events) if len(pa_events) > 0 else df.get("at_bat_number", pd.Series(dtype=int)).nunique()
    walks = pa_events.isin(_WALK_EVENTS).sum()
    strikeouts = pa_events.isin(_STRIKEOUT_EVENTS).sum()
    hits = pa_events.isin(_HIT_EVENTS).sum()
    home_runs = (pa_events == "home_run").sum()
    outs = pa_events.isin(_OUT_EVENTS).sum()

    at_bats = pa_events.isin(_HIT_EVENTS | {"field_out", "strikeout", "strikeout_double_play",
                                             "double_play", "grounded_into_double_play",
                                             "force_out", "fielders_choice_out", "field_error"}).sum()

    total_bases = (
        (pa_events == "single").sum() * 1
        + (pa_events == "double").sum() * 2
        + (pa_events == "triple").sum() * 3
        + (pa_events == "home_run").sum() * 4
    )

    ba = round(hits / at_bats, 3) if at_bats > 0 else 0.0
    slg = round(total_bases / at_bats, 3) if at_bats > 0 else 0.0
    iso = round(slg - ba, 3)

    innings_pitched = outs / 3 if outs > 0 else 0.0
    whip = round((walks + hits) / innings_pitched, 2) if innings_pitched > 0 else 0.0
    hr9 = round(home_runs * 9 / innings_pitched, 2) if innings_pitched > 0 else 0.0
    k9 = round(strikeouts * 9 / innings_pitched, 2) if innings_pitched > 0 else 0.0

    bb_pct = round(walks / pa_count * 100, 1) if pa_count > 0 else 0.0
    k_pct = round(strikeouts / pa_count * 100, 1) if pa_count > 0 else 0.0

    putaway_pct = 0.0
    if {"balls", "strikes", "description"}.issubset(df.columns):
        two_strike_pitches = df[pd.to_numeric(df["strikes"], errors="coerce") == 2]
        if len(two_strike_pitches) > 0:
            putaway_pct = round(strikeouts / len(two_strike_pitches) * 100, 1)

    first_pitch_strike_pct = 0.0
    if "pitch_number" in df.columns and "description" in df.columns:
        first_pitches = df[pd.to_numeric(df["pitch_number"], errors="coerce") == 1]
        if len(first_pitches) > 0:
            strike_desc = {"called_strike", "swinging_strike", "swinging_strike_blocked",
                            "foul", "foul_tip", "hit_into_play"}
            fp_strikes = first_pitches["description"].isin(strike_desc).sum()
            first_pitch_strike_pct = round(fp_strikes / len(first_pitches) * 100, 1)

    meatball_pct = 0.0
    if {"plate_x", "plate_z"}.issubset(df.columns):
        px = pd.to_numeric(df["plate_x"], errors="coerce")
        pz = pd.to_numeric(df["plate_z"], errors="coerce")
        in_heart = (px.abs() < 0.83) & (pz.between(1.5, 3.5))
        meatball_pct = round(in_heart.sum() / total_pitches * 100, 1) if total_pitches > 0 else 0.0

    return {
        "BA": ba, "SLG": slg, "ISO": iso, "WHIP": whip, "HR": int(home_runs), "HR/9": hr9,
        "BB%": bb_pct, "K%": k_pct, "Whiff%": whiff_pct, "SwStr%": swstr_pct, "K/9": k9,
        "Putaway%": putaway_pct, "1stPS%": first_pitch_strike_pct, "Meatball%": meatball_pct,
        "_error": error,
    }
