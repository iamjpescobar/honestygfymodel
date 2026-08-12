"""ONE definition of the HR qualification floors.

Imported by the board, by hr_floors_probe.py and by the research log, so
there is exactly one answer to "what counts as clearing Brl%". Three
copies of nine numbers is nine chances to disagree, and this repo has
already paid for that with anchors typed separately into precompute and
statcast_engine.

WHY THEY ARE PERCENTILES AND NOT THE NUMBERS AS TYPED
-----------------------------------------------------
The floors arrived as literals: Brl% 11, Brl/PA 8, HH% 40, FB% 26,
EV 91, Blast% 18, PullAir% 10, ISO .200. hr_floors_probe measured all
nine against 373 hitters at 150+ PA and three of them were not doing
what they were meant to:

  EV 91    cleared 373 of 373 and removed nothing. The intent was a
           floor on AVERAGE exit velocity, where 91 sits above a league
           average near 89 — but the only EV column was EV90, the 90th
           PERCENTILE of a hitter's batted balls, whose median is 104.2.
           Right number, wrong stat. avg_ev now exists (see
           statcast_engine) so 91 means what it was meant to mean.

  HH% 40   is the league median to two decimals (39.95), and after the
           two barrel floors above it removed exactly ONE more hitter.
           Described as firm; behaved as average.

  PullAir% is below the median too (median 11.89, floor 10).
  10

A literal is a photograph of one season. Set at the 75th percentile in
2026 and left alone, it is the median by 2028 and nobody notices,
because nothing about a hardcoded 40 announces that the league moved.
So the floors are stored as the PERCENTILE they were meant to express,
resolved nightly against the qualified pool — the same pattern
hr_anchors already uses for HRIntent and HRThreat.

FALLBACK, not default. The literals below are what the numbers resolve
to when baselines.json has no measured floors yet — an archive published
before this shipped. They are the values measured on 2026-08-12, not the
values as originally typed, except where the two agree.
"""

# (key, profile key, percentile of the qualified pool, fallback literal)
#
# `pct` is the share of the qualified pool the floor should sit ABOVE.
# 0.75 means "top quarter clears this". Chosen to preserve what each
# floor was reaching for, checked against the 2026-08-12 measurement:
# Brl/PA 8.0 was already the 90th, ISO .200 the ~78th, Brl% 11 the ~77th.
# HH%, FB%, PullAir% and avg EV are RAISED to the 75th, which is where
# "firm" was meant to be and where the typed literals were not.
FLOOR_SPECS = (
    ("brl_pct",   "Brl %",            0.75, 10.65),
    ("brl_pa",    "Brl/PA",           0.90,  8.00),
    ("hard_hit",  "HH %",             0.75, 44.59),
    ("fb_pct",    "FB %",             0.75, 30.59),
    ("avg_ev",    "AvgEV",            0.75, 90.20),
    ("blast",     "Blast %",          0.75, 19.57),
    ("pull_air",  "PullAir %",        0.75, 15.21),
    ("iso",       "ISO",              0.78,  0.200),
    # NOT a percentile. Its median is 0.00 — more than half of qualified
    # hitters have never once put a ball on a trajectory that leaves
    # every park — so a percentile floor here would resolve to zero and
    # pass everybody. "Has done it at all" is the real threshold, and it
    # is the only floor in the set that is not a power proxy.
    ("clears",    "ClearsAnywhere %", None,  0.001),
)

# Where the nightly writes the measured values.
BASELINE_KEY = "hr_floors"


def resolve(baselines=None):
    """{key: threshold} — measured where available, fallback otherwise.

    `baselines` is the parsed baselines.json dict. Passing None returns
    the fallbacks, which is what a caller with no archive gets.
    """
    measured = {}
    if isinstance(baselines, dict):
        raw = baselines.get(BASELINE_KEY) or {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                # A floor of 0 or a negative is not a measurement, it is
                # an empty pool that produced a number anyway.
                if isinstance(v, (int, float)) and v > 0:
                    measured[k] = float(v)
    return {key: measured.get(key, fallback)
            for key, _pkey, _pct, fallback in FLOOR_SPECS}


def evaluate(profile, thresholds):
    """(met, total, missed) for one batter's profile.

    An UNMEASURED metric fails its floor and is named in `missed`. It is
    not a pass and it is not silently dropped from the denominator: a bat
    with no bat-tracking data has not cleared the Blast floor, and a
    9/9 that quietly became 8/8 would be the same number meaning two
    different things.
    """
    missed, met = [], 0
    for key, pkey, _pct, _fb in FLOOR_SPECS:
        val = profile.get(pkey) if isinstance(profile, dict) else None
        try:
            ok = val is not None and float(val) >= thresholds[key]
        except (TypeError, ValueError):
            ok = False
        if ok:
            met += 1
        else:
            missed.append(pkey)
    return met, len(FLOOR_SPECS), missed
