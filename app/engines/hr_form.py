"""FORM — how far a hitter is from his OWN recent baseline.

Not "last season vs this season" — that is career trajectory, and it
breaks for rookies, for anyone whose role changed, and it is stale by
August. Form is RECENT vs the player's own baseline, which is the same
definition wnba_props already uses.

WHY ONLY TWO INPUTS, AND WHY THESE TWO

The obvious build measures form in the things HR Score is made of:
barrels, pull-air, blast rate. Measured over L15 against season, across
373 hitters at 150+ PA:

    input        10th    25th   median    75th    90th   |dev| 90th
    Brl/PA     -100.0  -100.0    -26.8    33.7   101.3       101.3
    PullAir %  -100.0   -39.1     -0.9    51.1   102.3       102.3
    HH %        -43.2   -26.1     -4.4    14.0    35.9        48.0
    AvgEV        -6.1    -3.4     -0.6     2.1     4.4         7.3
    Blast %     -56.0   -32.0     -5.6    18.5    42.1        67.2

A QUARTER OF HITTERS SIT AT EXACTLY -100% ON Brl/PA. That is not cold
form, it is ZERO BARRELS IN FIFTEEN GAMES — a wall, not a measurement.
Same at the 10th for pull-air. And Brl/PA's median is -26.8, nowhere
near zero, which is the sanity check that catches it: a form metric
computed on comparable footing has a median at zero, because half a
league is above its own baseline and half below.

So barrels, pull-air and blast are too SPARSE at fifteen games. Only
AvgEV behaves (median -0.6, symmetric) with HH% second.

BANDS ARE PER INPUT, from the |dev| 90th column. At that width about one
hitter in ten reaches an extreme, which is what an extreme should mean.
One shared band would flatten the stable input and saturate the volatile
one — exactly how the WNBA 3PM form column ended up with a quarter of
the league pinned at 100.
"""

# (profile key, band as a percent of the player's own baseline, weight)
#
# AvgEV carries more because it is the better-behaved measurement, not
# because exit velocity matters more than contact quality. A metric
# whose distribution is symmetric and unsaturated can be read; one that
# piles up against a wall cannot, whatever it represents.
FORM_INPUTS = (("AvgEV", 7.3, 0.60),
               ("HH %", 48.0, 0.40))

FORM_WINDOW = "l15"


def form_score(season_profile, recent_profile):
    """0-100, 50 = exactly at his own baseline. None if unmeasurable.

    Returns None rather than 50 when nothing can be measured. A neutral
    50 and "we could not tell" look identical on a board and mean
    opposite things.
    """
    if not season_profile or not recent_profile:
        return None
    parts = []
    for key, band, weight in FORM_INPUTS:
        base, recent = season_profile.get(key), recent_profile.get(key)
        if not base or recent is None:
            continue
        dev = (recent - base) / base * 100.0
        # Clamped to the band, then mapped onto 0-100 with 50 at zero.
        t = max(-1.0, min(1.0, dev / band))
        parts.append(((t + 1.0) / 2.0 * 100.0, weight))
    if not parts:
        return None
    return round(sum(v * w for v, w in parts) / sum(w for _, w in parts), 1)


def form_note(season_profile, recent_profile):
    """A sentence naming what moved, for the why-this-ranks panel."""
    if not season_profile or not recent_profile:
        return None
    bits = []
    for key, _band, _w in FORM_INPUTS:
        base, recent = season_profile.get(key), recent_profile.get(key)
        if not base or recent is None:
            continue
        bits.append(f"{key} {recent:.1f} vs {base:.1f} season")
    return " · ".join(bits) or None
