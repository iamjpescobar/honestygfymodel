
def compute_pitch_affinity_multiplier(batter_profile: dict, pitcher_arsenal: dict):
    """
    Pitch affinity engine:
    - Measures how well batter handles pitcher’s pitch mix
    - Returns pitch_affinity_mult (float)
    """

    # Batter affinity vs pitch types.
    # NOTE: real per-pitch-type batter splits aren't wired up yet, so this
    # defaults every pitch type to 0.10 (the engine's own "neutral" value)
    # rather than crashing. Swap these .get() defaults out once real
    # Statcast pitch-type splits are added to batter_stats.py.
    ff_aff = batter_profile.get("FF Affinity", 0.10)
    sl_aff = batter_profile.get("SL Affinity", 0.10)
    ch_aff = batter_profile.get("CH Affinity", 0.10)
    si_aff = batter_profile.get("SI Affinity", 0.10)
    sw_aff = batter_profile.get("SW Affinity", 0.10)
    cu_aff = batter_profile.get("CU Affinity", 0.10)

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
