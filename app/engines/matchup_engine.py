
def compute_matchup_multiplier(batter_profile: dict, pitcher_profile: dict):
    """
    Data-driven matchup engine:
    - Compares batter strengths vs pitcher weaknesses
    - Returns:
        matchup_mult (float)
        matchup_tag (str)
    """

    # Batter strengths (defensive .get() so missing keys never crash the app)
    brl = batter_profile.get("Brl %", 0)
    hh = batter_profile.get("HH %", 0)
    pull_air = batter_profile.get("PullAir %", 0)
    ld = batter_profile.get("LD %", 0)

    # Pitcher weaknesses — sourced from statcast_engine's actual profile keys
    hr_bbe = pitcher_profile.get("HR/BBE", 0)
    hh_allowed = pitcher_profile.get("HH %", 0)
    ld_allowed = pitcher_profile.get("LD %", 0)
    zone_vuln = pitcher_profile.get("ZoneContact %", 0)  # higher zone contact allowed = more vulnerable

    # Batter damage score
    score = (
        (brl * 0.40) +
        (hh * 0.25) +
        (pull_air * 0.20) +
        (ld * 0.15)
    )

    # Pitcher vulnerability score
    vuln = (
        (hr_bbe * 0.45) +
        (hh_allowed * 0.30) +
        (ld_allowed * 0.15) +
        (zone_vuln * 0.10)
    )

    raw = score * (1.0 + (vuln / 100.0))

    # Convert to multiplier + tag
    if raw >= 80:
        matchup_mult = 1.20
        matchup_tag = "ELITE"
    elif raw >= 65:
        matchup_mult = 1.10
        matchup_tag = "GOOD"
    elif raw >= 50:
        matchup_mult = 1.00
        matchup_tag = "Neutral"
    elif raw >= 35:
        matchup_mult = 0.90
        matchup_tag = "Cold"
    else:
        matchup_mult = 0.80
        matchup_tag = "⚠️"

    return float(matchup_mult), matchup_tag
