import sys
import os

# Ensure project root is in Python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

import numpy as np

def compute_pitch_affinity_multiplier(batter_profile: dict, pitcher_arsenal: dict):
    """
    Pitch affinity engine:
    - Measures how well batter handles pitcher’s pitch mix
    - Returns pitch_affinity_mult (float)
    """

    # Batter affinity vs pitch types
    ff_aff = batter_profile["FF Affinity"]
    sl_aff = batter_profile["SL Affinity"]
    ch_aff = batter_profile["CH Affinity"]
    si_aff = batter_profile["SI Affinity"]
    sw_aff = batter_profile["SW Affinity"]
    cu_aff = batter_profile["CU Affinity"]

    # Pitcher usage %
    ff_use = pitcher_arsenal.get("FF %", 0.0)
    sl_use = pitcher_arsenal.get("SL %", 0.0)
    ch_use = pitcher_arsenal.get("CH %", 0.0)
    si_use = pitcher_arsenal.get("SI %", 0.0)
    sw_use = pitcher_arsenal.get("SW %", 0.0)
    cu_use = pitcher_arsenal.get("CU %", 0.0)

    weighted_affinity = (
        ff_aff * ff_use +
        sl_aff * sl_use +
        ch_aff * ch_use +
        si_aff * si_use +
        sw_aff * sw_use +
        cu_aff * cu_use
    )

    total_use = ff_use + sl_use + ch_use + si_use + sw_use + cu_use
    if total_use == 0:
        return 1.0  # neutral if no arsenal data

    avg_affinity = weighted_affinity / total_use

    if avg_affinity >= 0.18:
        pitch_mult = 1.15
    elif avg_affinity >= 0.12:
        pitch_mult = 1.08
    elif avg_affinity >= 0.08:
        pitch_mult = 1.00
    elif avg_affinity >= 0.04:
        pitch_mult = 0.93
    else:
        pitch_mult = 0.85

    return float(pitch_mult)
