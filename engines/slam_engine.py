import numpy as np

def compute_slam_index(
    brl: float,
    hh: float,
    pull_air: float,
    gb: float,
    bbe: int,
    matchup_tag: str = "Neutral",
    affinity_mult: float = 1.0,
):
    """
    Core SLAM Index calculation.
    Combines power indicators, matchup boosts, sample-size adjustments,
    and optional pitcher affinity multipliers.
    """

    # Base power score
    base = (brl * 3.5) + (hh * 0.5) + (pull_air * 0.3) - (gb * 0.2)

    # Matchup boosts
    if matchup_tag == "🔥 ELITE":
        base *= 1.25
    elif matchup_tag == "✅ Good":
        base *= 1.15
    elif matchup_tag == "⚠️ Cold":
        base *= 0.85

    # Sample size adjustments
    if bbe > 120:
        base += 8
    elif bbe < 40:
        base *= 0.85

    # Pitcher affinity multiplier
    base *= affinity_mult

    # Clamp to range 5–100
    return float(min(100.0, max(5.0, base)))


def random_match_tag(seed_key: str):
    """
    Generates a consistent matchup tag for each batter.
    Seeded randomness ensures the same batter gets the same tag each session.
    """
    np.random.seed(abs(hash(seed_key)) % (10**8))
    return np.random.choice(
        ["🔥 ELITE", "✅ Good", "Neutral", "⚠️ Cold"],
        p=[0.15, 0.45, 0.30, 0.10],
    )

