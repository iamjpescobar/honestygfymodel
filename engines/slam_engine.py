import numpy as np

def compute_slam_index(
    brl: float,              # Barrel %
    hh: float,               # Hard Hit %
    pull_air: float,         # Pull-side Air %
    ld: float,               # Line Drive %
    gb: float,               # Groundball %
    bbe: int,                # Batted Ball Events (sample size)
    matchup_mult: float,     # From matchup_engine
    pitch_affinity_mult: float  # From pitch_affinity_engine
) -> float:
    """
    Legit SLAM Index:
    - 100% real Statcast-style inputs
    - No randomness, no gimmicks
    - Weighted by predictive strength
    """

    # Core weights (you can tune, but these are sane starting points)
    w_brl = 3.8    # Barrel % — strongest HR predictor
    w_hh = 0.55    # Hard Hit %
    w_pull_air = 0.32  # Pull-side Air %
    w_ld = 0.28   # Line Drive %
    w_gb = -0.22  # Groundball % — negative for HR

    base = (
        (brl * w_brl) +
        (hh * w_hh) +
        (pull_air * w_pull_air) +
        (ld * w_ld) +
        (gb * w_gb)
    )

    # Sample size trust adjustment
    if bbe >= 150:
        base *= 1.10
    elif bbe <= 40:
        base *= 0.85

    # Data-driven multipliers
    base *= matchup_mult
    base *= pitch_affinity_mult

    # Clamp to [1, 100]
    return float(min(100.0, max(1.0, base)))
