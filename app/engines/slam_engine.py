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

    return {
        "slam_score": slam_score,
        "xSLG": xslg,
        "xwOBA": xwoba,
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


def compute_slam_all_windows(batter_id) -> dict:
    """
    Real SLAM across all three windows at once — {"l25_pa": {...},
    "l25_bbe": {...}, "l25_games": {...}}, each with its own
    slam_score/xSLG/xwOBA/sample size. Callers should show all three,
    not just one, so a hot recent streak isn't hidden by a wider
    window that's still catching up.
    """
    return {
        key: compute_slam_window(batter_id, window, unit)
        for key, label, window, unit in SLAM_WINDOWS
    }
