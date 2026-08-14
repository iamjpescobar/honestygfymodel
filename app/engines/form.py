"""FORM — a hitter measured against HIS OWN numbers, in his own units.

WHAT THIS REPLACED, AND WHY (2026-08-14)
----------------------------------------
`engines/hr_form` returned a 0-100 index with 50 at the hitter's own
baseline. Every input to it was real. The OUTPUT was not: **63.4 is not
something a hitter did.** It was a deviation, clamped to a band and
mapped onto a hundred-point scale, and no hitter ever recorded it.

Worse, it read as the exact thing it was built to not be. HR Score, Hit
Score, HRThreat and every Savant column on these boards are
LEAGUE-relative — where a hitter sits among other hitters. Form is the
only self-relative signal on the page, and rendering it as a 0-100
number put it in the same visual class as five percentile columns three
inches away. A reader had no way to tell that one of them meant
something completely different from the other five.

So the index is gone. Form now publishes THE MEASUREMENTS THEMSELVES:

    AvgEV   91.2 mph   vs   89.4 season   ->   +1.8 mph
    HH %    48.1       vs   41.2 season   ->   +6.9 pts

Every figure there is a real stat. The deltas are subtraction and
nothing else — not scaled, not clamped, not converted to a percentile,
not compared to another hitter. That is the whole point: a number a
subscriber can check against Baseball Savant himself.


WHY THERE IS NO SINGLE "FORM NUMBER"
------------------------------------
The obvious next step is to average the two into one column. Measured
across 373 hitters at 150+ PA, L15 against season, as a percent of each
hitter's own baseline:

    input        10th    25th   median    75th    90th   |dev| 90th
    Brl/PA     -100.0  -100.0    -26.8    33.7   101.3       101.3
    PullAir %  -100.0   -39.1     -0.9    51.1   102.3       102.3
    HH %        -43.2   -26.1     -4.4    14.0    35.9        48.0
    AvgEV        -6.1    -3.4     -0.6     2.1     4.4         7.3
    Blast %     -56.0   -32.0     -5.6    18.5    42.1        67.2

AvgEV and HH% do not move on the same scale — 7.3 against 48.0. A 4%
swing in exit velocity is a near-extreme; a 4% swing in hard-hit rate is
noise. **Averaging their percent deviations would call those two equal**,
which is precisely the defect the old per-input bands existed to prevent,
reintroduced by an operation that looks more honest than it is.

There is no weighting that fixes this without becoming a choice, and a
choice is what got removed. Two real numbers, side by side, no headline
composite. If a reader wants to combine them he can see exactly what he
is combining.


WHY ONLY THESE TWO INPUTS
-------------------------
From the same table: a quarter of hitters sit at exactly -100% on
Brl/PA. That is ZERO BARRELS IN FIFTEEN GAMES — a wall, not a
measurement. Same at the 10th for pull-air. Brl/PA's median of -26.8 is
the tell: a form input on comparable footing has a median near zero,
because half a league is above its own baseline and half below.

So barrels, pull-air and blast are too SPARSE at fifteen games. AvgEV
behaves best (median -0.6, symmetric), HH% second. Adding a third input
would put a wall back on the board.
"""

# (profile key, column header, unit shown to the reader, decimals)
#
# The unit is not decoration. "+1.8" beside "+6.9" invites reading them
# on one scale, which is the mistake this module is built to prevent —
# one is miles per hour and the other is percentage points, and they are
# not comparable in either direction.
FORM_INPUTS = (
    ("AvgEV", "\u0394EV", "mph", 1),
    ("HH %", "\u0394HH%", "pts", 1),
)

# The window "recent" is measured over. Callers pass this to
# get_batter_profile_windowed; it is defined here so the window and the
# measurement that justified it live in the same file.
FORM_WINDOW = "l15"
FORM_UNIT = "bbe"

# Column headers, in display order — for any view building a table.
FORM_COLUMNS = tuple(col for _k, col, _u, _dp in FORM_INPUTS)


def form_deltas(season_profile, recent_profile):
    """{column header: real delta} for whatever can be measured.

    Recent minus season, in the stat's own units. A key is ABSENT rather
    than zero when either side is missing — this app's standing rule is
    None over a fabricated 0, and a 0.0 in a delta column is the single
    most misleading value it could hold: it reads as "measured, and he
    is exactly at his baseline".
    """
    if not season_profile or not recent_profile:
        return {}
    out = {}
    for key, col, _unit, dp in FORM_INPUTS:
        base, recent = season_profile.get(key), recent_profile.get(key)
        if base is None or recent is None:
            continue
        # ROUNDED FIRST, THEN SUBTRACTED — deliberately, and it is the
        # difference between a checkable number and one that looks like
        # an error.
        #
        # A season AvgEV of 89.44 and a recent of 91.16 display as 89.4
        # and 91.2. Subtract the raw values and the change is +1.7;
        # subtract what the reader can actually see and it is +1.8. This
        # component exists so a subscriber can verify the arithmetic
        # against Savant himself, and a card whose three numbers do not
        # add up fails at exactly that job — he has no way to tell a
        # rounding artefact from a bug.
        #
        # The precision given away is below the display resolution, so
        # nothing true is lost. What is gained is that the shown figures
        # always reconcile.
        out[col] = round(round(recent, dp) - round(base, dp), dp)
    return out


def form_lines(season_profile, recent_profile):
    """The full comparison, for the component below and for any caller
    that wants to show its working.

    Each entry carries BOTH sides of the subtraction, not just the
    answer. A delta with the numbers it came from is checkable; a delta
    on its own is one more figure to take on trust.
    """
    if not season_profile or not recent_profile:
        return []
    lines = []
    for key, col, unit, dp in FORM_INPUTS:
        base, recent = season_profile.get(key), recent_profile.get(key)
        if base is None or recent is None:
            continue
        lines.append({
            "key": key, "column": col, "unit": unit, "dp": dp,
            # Same rounding order as form_deltas above, and it must
            # stay the same: this renderer shows all three figures at
            # once, so any disagreement between them is visible on the
            # card.
            "season": round(base, dp),
            "recent": round(recent, dp),
            "delta": round(round(recent, dp) - round(base, dp), dp),
        })
    return lines


def form_note(season_profile, recent_profile):
    """One sentence, for a why-this-ranks panel or a caption."""
    lines = form_lines(season_profile, recent_profile)
    if not lines:
        return None
    return " \u00b7 ".join(
        f'{ln["key"]} {ln["recent"]:.{ln["dp"]}f} vs {ln["season"]:.{ln["dp"]}f} '
        f'season ({ln["delta"]:+.{ln["dp"]}f} {ln["unit"]})'
        for ln in lines
    )


def render_form(season_profile, recent_profile, *, window_label=None,
                title="Form", compact=False):
    """THE COMPONENT. One definition of how Form looks, everywhere.

    Imported at call time rather than module scope so this file stays
    importable in the test suite and in the nightly pipeline, neither of
    which runs Streamlit. engines/top_plays does the same for
    statcast_engine and for the same reason.

    Renders nothing and returns False when there is nothing to render —
    an empty Form card is worse than no Form card, because a heading
    with blank values under it reads as "measured, and he has none".
    """
    import streamlit as st
    from styles.kc_theme import COLOR

    lines = form_lines(season_profile, recent_profile)
    if not lines:
        return False

    _win = window_label or f"last {FORM_WINDOW.lstrip('l')} batted balls"

    if compact:
        # Inline chips, for sitting under a player name in a card.
        html = '<div style="display:flex; gap:6px; flex-wrap:wrap;">'
        for ln in lines:
            c = _delta_color(ln["delta"], COLOR)
            html += (
                f'<span style="padding:2px var(--lc-space-sm); '
                f'border-radius:var(--lc-radius-sm); background:{c}1A; '
                f'border:1px solid {c}55; color:{c}; font-weight:700; '
                f'font-size:var(--lc-text-tiny); '
                f'font-family:\'JetBrains Mono\',monospace;">'
                f'{ln["column"]} {ln["delta"]:+.{ln["dp"]}f} {ln["unit"]}</span>'
            )
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)
        return True

    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{title}</div>'
        f'<div class="pf-card-subtitle" style="color:{COLOR["text_muted"]};">'
        f'His {_win} against his OWN season \u2014 not against the league. '
        f'Every figure below is a measured stat; the arrow is subtraction.'
        f'</div>',
        unsafe_allow_html=True,
    )
    rows = ""
    for ln in lines:
        c = _delta_color(ln["delta"], COLOR)
        rows += (
            f'<tr style="font-size:var(--lc-text-caption);">'
            f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); '
            f'color:{COLOR["text"]}; font-weight:600;">{ln["key"]}</td>'
            f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); '
            f'text-align:right; color:{COLOR["text"]}; '
            f'font-family:\'JetBrains Mono\',monospace;">'
            f'{ln["recent"]:.{ln["dp"]}f}</td>'
            f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); '
            f'text-align:right; color:{COLOR["text"]}; opacity:0.55; '
            f'font-family:\'JetBrains Mono\',monospace;">'
            f'{ln["season"]:.{ln["dp"]}f}</td>'
            f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); '
            f'text-align:right; color:{c}; font-weight:800; '
            f'font-family:\'JetBrains Mono\',monospace;">'
            f'{ln["delta"]:+.{ln["dp"]}f} {ln["unit"]}</td></tr>'
        )
    head = (
        f'<tr style="font-size:var(--lc-text-tiny); color:{COLOR["text"]}; '
        f'opacity:0.55;">'
        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md);">Stat</td>'
        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); '
        f'text-align:right;">Recent</td>'
        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); '
        f'text-align:right;">Season</td>'
        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); '
        f'text-align:right;">Change</td></tr>'
    )
    st.markdown(
        f'<table style="width:100%; border-collapse:collapse;">{head}{rows}</table>',
        unsafe_allow_html=True,
    )
    return True


def _delta_color(delta, COLOR):
    """Colour by DIRECTION only.

    Deliberately not a graded scale. Grading a delta needs cut points,
    cut points need measuring, and styles/stat_scales is where that
    belongs — this component is the plain reading of the number. Up is
    up, down is down, and a delta of exactly zero is neither.
    """
    if delta > 0:
        return COLOR["stat_high"]
    if delta < 0:
        return COLOR["error"]
    return COLOR["text_muted"]
