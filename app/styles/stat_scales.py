"""Fixed cut points per stat, so a number is the same colour everywhere.

WHAT CHANGED AND WHY

Cell colour used to be computed from the column you were looking at:
`_magnitude_column` normalised each column against its own min and max,
so .285 came out gold in one table and violet in another, and changing
a filter recoloured every cell without a single number moving. The
colour told you where a value sat *among the rows currently on screen* —
which is a real thing to know, but it is not what anyone reads it as.
People read a colour as a verdict.

Now the tier comes from the VALUE, against a fixed scale that never
moves. .285 is the same colour in the lineup table, on the HR board, and
after any filter change, because the scale does not know what else is on
screen. That is the whole point: no working out what a colour means in
this particular table.

WHAT A COLOUR MEANS

The same five tiers the app already uses — poor, below, average, good,
elite — with the same hues and the same reasoning (see _TIERS in
table_style.py). What has changed is only where the boundaries sit:
percentile-of-the-column before, fixed values now.

DIRECTION IS STILL THE CALLER'S CALL, DELIBERATELY

A 26% whiff rate is excellent for a pitcher and awful for a hitter. The
number does not carry its own verdict, so the scale cannot either.
`style_stat_table` already takes favor_high / favor_low per table, and
that is what decides which end of the scale is "elite". So the rule is:
the same value, in the same column, on tables that agree about
direction, is always the same colour. A stat that appears in both a
pitcher and a batter table flips — correctly, and only because the
caller said so.

THESE NUMBERS ARE CALIBRATION CONSTANTS, NOT MEASUREMENTS

Every cut point below is a judgement about where a stat stops being
average, anchored on ordinary league-wide ranges. They are not derived
from this season's data and nothing recomputes them. They live in one
table so they can be argued with and changed in one place. If a scale
looks wrong on a real board, fix the number HERE and say why in the
comment — do not special-case it at a call site, which is how five
different definitions of "good" get into one app.

Anything NOT listed here has no fixed scale and falls back to the old
relative colouring, which is honest: better an obviously column-relative
colour than a fixed one invented on the spot.
"""

# Four cut points per stat, ascending, in the stat's own raw units.
# They divide the number line into the five tiers. Read as:
#   value <  c0            -> tier 0
#   c0 <= value <  c1      -> tier 1
#   c1 <= value <  c2      -> tier 2   (average)
#   c2 <= value <  c3      -> tier 3
#   value >= c3            -> tier 4
# Tier 0 is the LOW end of the number, always. Which end is "elite" is
# decided by direction at the call site, not here.
SCALES = {
    # ---- rate stats, batting -------------------------------------
    # Anchored on the ordinary league picture: a .240 average is
    # unremarkable, .300 is a good year, .200 is a problem.
    "BA":        (0.200, 0.240, 0.270, 0.300),
    "AVG":       (0.200, 0.240, 0.270, 0.300),
    "OBP":       (0.280, 0.310, 0.340, 0.380),
    "SLG":       (0.350, 0.400, 0.450, 0.520),
    "xSLG":      (0.350, 0.400, 0.450, 0.520),
    "ISO":       (0.100, 0.140, 0.180, 0.230),
    "wOBA":      (0.290, 0.310, 0.340, 0.380),
    "xwOBA":     (0.290, 0.310, 0.340, 0.380),

    # ---- contact quality -----------------------------------------
    # Barrel rate is the one that separates power hitters fastest:
    # single digits are ordinary, low teens is genuine thump.
    "Brl %":     (3.0, 6.0, 9.0, 13.0),
    "Brl/PA":    (2.0, 4.0, 6.0, 9.0),
    "HH %":      (32.0, 37.0, 42.0, 48.0),
    # MEASURED 2026-08-12, 373 hitters at 150+ PA:
    #   median 88.60 · 75th 90.10 · 90th 91.80
    # AVERAGE exit velocity, not the 90th percentile. The two are
    # different questions — "how hard is his contact" against "how hard
    # is his BEST contact" — and a scale written for one grades nothing
    # when applied to the other. A "91 EV" floor aimed at this column
    # was applied to EV90 (median 104.2) and cleared 373 of 373.
    "AvgEV":     (87.0, 88.6, 90.1, 91.8),
    # FORM DELTAS — signed, and the cut points STRADDLE ZERO, because
    # zero is the meaningful anchor: a hitter doing exactly what he
    # always does is neither hot nor cold. A scale spanning a range,
    # like every other entry in this file, would grade "unchanged" as
    # bad.
    #
    # DERIVED, NOT MEASURED — say so plainly. hr_floors_probe measured
    # these as PERCENTAGES of each hitter's own baseline across 373
    # hitters at 150+ PA (AvgEV: 25th -3.4, median -0.6, 75th +2.1,
    # 90th +4.4; HH%: 25th -26.1, median -4.4, 75th +14.0, 90th +35.9).
    # Converting to units needs a baseline, and these use the league
    # averages — about 89 mph and about 40% — so they are right for a
    # typical hitter and progressively wrong for the tails.
    #
    # form_scale_probe.py measures them directly. Run it and replace
    # these with the real figures; do not quietly tune them by eye.
    "ΔEV":     (-3.0, -0.5, 1.9, 3.9),
    "ΔHH%":    (-10.4, -1.8, 5.6, 14.4),
    "EV90":      (100.0, 103.0, 106.0, 109.0),
    # MEASURED 2026-08-12, 373 hitters at 150+ PA:
    #   median 11.49 · 65th 13.45 · 75th 15.07 · 90th 18.66 · MAX 30.89
    #
    # These were (15, 25, 35, 45) and the top TWO tiers were unreachable:
    # nobody in the league hit 35, and the 90th percentile (18.66) did
    # not clear the SECOND cut. Three quarters of hitters sat in the
    # bottom tier. Same defect as Clears%, found the same way — by
    # measuring instead of assuming a per-batted-ball rate spans 15-45.
    "FB95%":     (11.5, 13.4, 15.1, 18.7),
    # CLEARS ANYWHERE IS A RATE IN TENTHS OF A PERCENT, not tens.
    #
    # These cut points were (10, 20, 30, 40) — reasonable-looking numbers
    # for a percentage, and wrong by a factor of about twenty. The
    # nightly measures the league mean at 0.32%; across 373 hitters at
    # 150+ PA the median is 0.00, the 75th is 0.63 and the 90th is 0.93.
    # NOBODY IN BASEBALL reaches the first cut, so every cell in the
    # column rendered in the bottom tier — including a bat at 1.01,
    # above the 90th percentile of the league.
    #
    # A colour reads as a verdict (see _magnitude_column). The board was
    # telling the reader that the best trajectory-clearing hitter on the
    # slate was bad at it, in the same red as one at 0.13.
    #
    # Set from the measured distribution: median, ~65th, 75th, 90th. The
    # median is 0.00 because over half of qualified hitters have never
    # once put a ball on a trajectory that leaves every park — so the
    # first cut sits just above zero, and "has done it at all" is
    # genuinely what separates the bottom tier here.
    "Clears%":   (0.15, 0.40, 0.65, 0.95),
    "HR/FB":     (6.0, 9.0, 12.0, 16.0),

    # ---- plate discipline ----------------------------------------
    # Listed low-to-high like everything else. On a BATTER table the
    # caller passes K%/Whiff%/SwStr% as favor_low, so low lands elite;
    # on a PITCHER table it passes them as favor_high. Same numbers,
    # opposite ends, one definition.
    "K %":       (16.0, 20.0, 25.0, 30.0),
    "K%":        (16.0, 20.0, 25.0, 30.0),
    "BB %":      (5.0, 7.0, 9.0, 12.0),
    "BB%":       (5.0, 7.0, 9.0, 12.0),
    "Whiff %":   (20.0, 24.0, 28.0, 33.0),
    "WHIFF%":    (20.0, 24.0, 28.0, 33.0),
    "SwStr %":   (8.0, 10.0, 12.0, 14.0),

    # ---- pitching ------------------------------------------------
    "ERA":       (2.75, 3.50, 4.25, 5.00),
    "WHIP":      (1.05, 1.20, 1.32, 1.45),
    "HR/9":      (0.80, 1.10, 1.40, 1.75),
    "OAVG":      (0.200, 0.240, 0.270, 0.300),

    # ---- this app's own 0-100 composites -------------------------
    # These are OURS, computed to a 0-100 scale, so the cut points are
    # simply where we decided the grades sit. No league anchor exists
    # or is needed.
    "SLAM":      (35.0, 50.0, 65.0, 80.0),
    "HR Score":  (15.0, 30.0, 45.0, 60.0),
    "Hit Score": (30.0, 45.0, 55.0, 65.0),
    "HRWindow%": (25.1, 26.6, 27.7, 30.1),
    "HRIntent":  (35.0, 50.0, 65.0, 80.0),
    "HRThreat":  (35.0, 50.0, 65.0, 80.0),
}

# Stats where a bigger number is worse for the subject of MOST tables
# that show them. Only used to sanity-check a caller that declares no
# direction at all; it never overrides an explicit favor_high/favor_low.
_USUALLY_LOWER_IS_BETTER = {"ERA", "WHIP", "HR/9", "OAVG"}

N_TIERS = 5


def has_scale(stat: str) -> bool:
    return stat in SCALES


def tier_index(stat: str, value, invert: bool = False):
    """0-4 for a raw value on this stat's fixed scale, or None.

    invert=True flips the ladder, for a column where LOW is the good
    end (a batter's strikeout rate, a pitcher's ERA). Returns None when
    the stat has no fixed scale or the value is not a number, and the
    caller falls back to relative colouring.
    """
    cuts = SCALES.get(stat)
    if cuts is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:                      # NaN
        return None

    idx = 0
    for c in cuts:
        if v >= c:
            idx += 1
        else:
            break
    return (N_TIERS - 1 - idx) if invert else idx


def tier_fraction(stat: str, value, invert: bool = False):
    """The tier as a 0-1 position, for code that already speaks in
    normalised values (_gradient_fill and friends).

    Returns the MIDDLE of the tier's band rather than its edge, so a
    value cannot land exactly on a boundary and tip into the neighbour
    depending on floating-point noise.
    """
    idx = tier_index(stat, value, invert=invert)
    if idx is None:
        return None
    return (idx + 0.5) / N_TIERS


def describe(stat: str):
    """Human-readable band edges, for a legend or a tooltip."""
    cuts = SCALES.get(stat)
    if cuts is None:
        return None
    return cuts
