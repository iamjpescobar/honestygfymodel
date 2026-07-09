import pandas as pd
import numpy as np

def build_danger_zone(batter_profile):
    """
    Builds a 3x3 danger grid from batter profile:
    High/Mid/Low x Inside/Middle/Outside
    """

    pull = batter_profile["PullAir %"]
    ld = batter_profile["LD %"]
    gb = batter_profile["GB %"]
    brl = batter_profile["Brl %"]
    hh = batter_profile["HH %"]

    danger_score = (
        (pull * 0.25) +
        (ld * 0.35) +
        (brl * 0.20) +
        (hh * 0.20)
    )

    grid = np.array([
        [danger_score * 0.6, danger_score * 0.8, danger_score * 1.0],
        [danger_score * 0.5, danger_score * 0.7, danger_score * 0.9],
        [danger_score * 0.3, danger_score * 0.4, danger_score * 0.6],
    ])

    df = pd.DataFrame(
        grid,
        columns=["Inside", "Middle", "Outside"],
        index=["High", "Mid", "Low"],
    )

    return df
