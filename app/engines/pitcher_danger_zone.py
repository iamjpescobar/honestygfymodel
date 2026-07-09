import sys
import os

# Ensure project root is in Python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

import pandas as pd
import numpy as np

def build_pitcher_danger_zone(pitcher_profile: dict) -> pd.DataFrame:
    """
    Builds a 3x3 vulnerability grid from pitcher profile:
    High/Mid/Low x Inside/Middle/Outside
    Also returns a scalar ZoneVuln Score for matchup engine.
    """

    hr_rate = pitcher_profile["HR/BBE"]
    hh = pitcher_profile["HH %"]
    ld = pitcher_profile["LD %"]
    brl = pitcher_profile["Brl %"]
    zone_contact = pitcher_profile["ZoneContact %"]

    vuln_score = (
        (hr_rate * 0.35) +
        (hh * 0.25) +
        (ld * 0.20) +
        (brl * 0.15) +
        (zone_contact * 0.05)
    )

    grid = np.array([
        [vuln_score * 1.0, vuln_score * 0.8, vuln_score * 0.6],
        [vuln_score * 0.9, vuln_score * 0.7, vuln_score * 0.5],
        [vuln_score * 0.8, vuln_score * 0.6, vuln_score * 0.4],
    ])

    df = pd.DataFrame(
        grid,
        columns=["Inside", "Middle", "Outside"],
        index=["High", "Mid", "Low"],
    )

    return df
