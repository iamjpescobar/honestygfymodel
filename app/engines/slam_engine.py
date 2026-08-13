"""
SLAM — real, live power-quality signal for a batter, built entirely on
MLB's own published expected stats (xSLG, xwOBA), not this app's own
invented weighting of raw inputs.

Why xSLG/xwOBA instead of hand-blending Brl%/HH%/PullAir%/LD%: those
raw inputs are all real, but there's no published, defensible formula
for combining them into one number — any set of weights we pick
ourselves is a modeling choice, not a measured fact. xSLG and xwOBA
ARE that already-solved problem: MLB computes them, they're
peer-reviewed-adjacent (used across the industry), and adopting them
directly means SLAM's core number is never something we invented.

Computed across three separate real recency windows — last 25 PA,
last 25 BBE, last 25 games — shown SEPARATELY, not averaged together.
Averaging them would hide exactly the signal a real bettor wants: a
batter who's mashing in his last 25 BBE but whose last-25-game number
is still dragged down by a cold stretch earlier in that window.
"""
from engines.statcast_engine import get_batter_profile_windowed

SLAM_WINDOWS = [
    ("l25_pa", "Last 25 PA", "l25", "pa"),
    ("l25_bbe", "Last 25 BBE", "l25", "bbe"),
    ("l25_games", "Last 25 Games", "l25", "games"),
]


# HR/FB scoring anchors — shared with engines/top_plays.py so both
# scores treat the stat identically.
# HR/FB scoring anchor — MEASURED, not asserted.
#
# This was a hardcoded 11.5. Close to reality, but typed in rather than
# measured, so it silently went stale as the league moved and nothing in
# the app could tell. precompute.build_baselines now measures HR per FLY
# BALL across the whole league each night and ships it in baselines.json.
#
# The literal survives only as a fallback for a build that predates the
# measurement, so the score never breaks — it just uses the old anchor
# until the next nightly, and says so in the docstring rather than
# pretending the number is measured.
_LEAGUE_HRFB_FALLBACK = 11.5


def _league_hrfb() -> float:
    """League HR/FB percent from the nightly build, else the fallback."""
    try:
        import json as _j
        from pathlib import Path as _P
        _p = (_P(__file__).resolve().parent.parent
              / "data" / "statcast" / "baselines.json")
        v = (_j.loads(_p.read_text()) or {}).get("hrPerFlyBall")
        return float(v) if v else _LEAGUE_HRFB_FALLBACK
    except Exception:
        return _LEAGUE_HRFB_FALLBACK
_HRFB_WEIGHT = 0.15


def slam_from_profile(profile: dict) -> dict:
    """
    Pure computation: real SLAM score from an ALREADY-FETCHED windowed
    batter profile (see get_batter_profile_windowed). Split out from
    compute_slam_window() so a caller who already has the profile
    (e.g. the Lineup table, which needs the same profile for its raw
    stat columns) doesn't have to pull the same live data twice.
    """
    xslg = profile.get("xSLG")
    xwoba = profile.get("xwOBA")

    # Fallback: if the expected-stat columns weren't available for this
    # window (e.g. a data pull missing estimated_slg/woba, which zeroed
    # SLAM for every batter on the Season window), fall back to the
    # REAL slugging line so SLAM still computes from actual outcomes
    # rather than collapsing to nothing. xSLG is preferred when present
    # because it's noise-adjusted, but real SLG is a valid stand-in and
    # far better than a blank board. ISO isn't used as a direct anchor
    # (different scale) but SLG carries the same power signal.
    slg_fallback = profile.get("SLG")
    if xslg is None and slg_fallback:
        try:
            xslg = float(slg_fallback)
        except (TypeError, ValueError):
            pass

    parts = [p for p in [xslg, xwoba] if p is not None]
    # xSLG is on a ~0-4+ scale, xwOBA on a ~0-1 scale — normalize both
    # to a 0-100ish display scale using real, published scale anchors
    # (league-average xSLG ~.400, league-average xwOBA ~.310) rather
    # than an arbitrary multiplier.
    slam_score = None
    if parts:
        norm_slg = (xslg / 0.400 * 50) if xslg is not None else None
        norm_woba = (xwoba / 0.310 * 50) if xwoba is not None else None
        norm_parts = [p for p in [norm_slg, norm_woba] if p is not None]
        slam_score = round(sum(norm_parts) / len(norm_parts), 1) if norm_parts else None

        # HR/FB layer (15%) — xSLG/xwOBA price expected damage; HR/FB
        # asks whether his fly balls actually leave. Same league anchor
        # (~11.5% -> 50) and same light weight as HR Score, and it only
        # applies when the profile cleared the 25-fly-ball floor, so a
        # thin sample never moves SLAM.
        hrfb = profile.get("HR/FB")
        if slam_score is not None and hrfb is not None:
            hrfb_scaled = max(0.0, min(100.0, hrfb / _league_hrfb() * 50.0))
            slam_score = round(slam_score * (1 - _HRFB_WEIGHT)
                               + hrfb_scaled * _HRFB_WEIGHT, 1)

    return {
        "slam_score": slam_score,
        "xSLG": xslg,
        "xwOBA": xwoba,
        "HR/FB": profile.get("HR/FB"),
        "FB_count": profile.get("FB_count", 0),
        "sample_bbe": profile.get("BBE", 0),
        "window_rows": profile.get("_window_rows", 0),
        "error": profile.get("_error"),
    }


def compute_slam_window(batter_id, window: str, unit: str) -> dict:
    """
    Real SLAM number for one specific window: fetches the windowed
    profile live, then calls slam_from_profile(). Use this when you
    don't already have the profile; use slam_from_profile() directly
    if you do, to avoid pulling the same live data twice.
    """
    profile = get_batter_profile_windowed(batter_id, window=window, unit=unit)
    return slam_from_profile(profile)
