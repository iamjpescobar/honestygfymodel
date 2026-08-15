"""
Table styling: black background everywhere, plus two real signal
systems layered on top:

1. Identity colors (player names, handedness) — applied AUTOMATICALLY
   in _base_styler, not opt-in per table. Every table that calls
   plain_dark_table() or style_stat_table() gets these for free, so
   there's no risk of one card quietly being left out.

2. Heatmap fill (opt-in via gradient=True, currently used on the
   Lineup card and the Top Plays tables) — a real colored BACKGROUND
   fill, not just colored text, scaled red (bad) -> amber (mid) ->
   cyan (good). Text color is always dark (BG) against the fill,
   which stays legible across the whole red -> amber -> cyan range
   since the fill is always applied at a light-enough opacity.
"""
import json as _tbl_json
from pathlib import Path

import itertools
import re as _re
import pandas as pd


def _st_cache_1h():
    """st.cache_data if Streamlit is importable, else a no-op.

    Keeps this module importable from tests without a Streamlit runtime."""
    try:
        import streamlit as _st
        return _st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
    except Exception:
        return lambda f: f


from .kc_theme import COLOR, pitch_color_by_name
from .stat_scales import has_scale, tier_fraction

# WHY THIS OPTION IS SET, AND WHAT IT ACTUALLY FIXES
#
# pandas' Styler.format() does NOT merge with a previous format() call —
# it REPLACES the display function for every column in the subset, and
# with no subset that means every column in the frame. _base_styler runs
# .format(precision=2, na_rep="—") first; the moment a caller adds its own
# .format({...}) for two logo columns, every OTHER column loses that
# precision and falls back to `styler.format.precision`, whose pandas
# default is SIX. That is how "543.000000" reached the HR Edge board's PA
# column, and it is the same cause behind the "10.370000" note in
# Strikeout_Board.py — one symptom, fixed twice, never at the source.
#
# Setting the option to 2 makes the FALLBACK match the house style, so a
# column nobody remembered to list degrades to 543.00 instead of
# 543.000000. It is a floor, not a substitute for an explicit format:
# stat_formats() below is what gets each stat to its right precision.
#
# na_rep gets no equivalent safety net. pandas reads
# `styler.format.na_rep` only when the Styler is CONSTRUCTED, so a later
# format() call with na_rep unset still resets it to None and prints the
# literal "nan" (verified, this pandas). The only fix there is passing
# na_rep at every call site — tests/test_number_formats.py enforces it.
#
# Wrapped because a pandas upgrade could rename the option, and an
# ImportError-at-startup takes the whole site down while a wrong decimal
# only looks bad. The test asserts the option actually took effect, so a
# rename fails loudly in CI rather than silently here.
try:
    pd.set_option("styler.format.precision", 2)
except Exception:
    pass

# ONE definition of how each stat is printed, keyed by column header.
#
# The precisions are not arbitrary: they are the ones already typed by
# hand into the Game Card lineup, the Strikeout Board and the HR
# vulnerability card. Collecting them here is the same argument as
# engines/hr_floors — the same numbers written out in five places is five
# chances to disagree, and the splits tables had already drifted (BA and
# SLG rendering .25 where the lineup showed .250).
#
# Matched case- and space-insensitively so "Brl%", "Brl %" and "BRL%" —
# all three of which exist in this app — resolve to one entry.
STAT_FORMATS = {
    # Rate stats published on the .000 scale. Three decimals or they stop
    # looking like batting lines.
    "BA": "{:.3f}", "AVG": "{:.3f}", "OBP": "{:.3f}", "SLG": "{:.3f}",
    "OPS": "{:.3f}", "ISO": "{:.3f}", "WOBA": "{:.3f}", "XWOBA": "{:.3f}",
    "XBA": "{:.3f}", "XSLG": "{:.3f}",
    # Per-nine and per-inning rates.
    "WHIP": "{:.2f}", "HR/9": "{:.2f}", "K/9": "{:.2f}", "BB/9": "{:.2f}",
    # Contact that leaves ANY park. Two decimals, not one: the league
    # average is a fraction of a percent, so {:.1f} would print 0.0 for
    # most of the league and throw away the only resolution it has.
    "CLEARS%": "{:.2f}", "CLEARSANYWHERE%": "{:.2f}",
    # Percentages. One decimal everywhere, matching Brl%/HH% on the
    # lineup card.
    "BRL%": "{:.1f}", "BRL/PA": "{:.1f}", "HH%": "{:.1f}", "LD%": "{:.1f}",
    "FB%": "{:.1f}", "GB%": "{:.1f}", "PU%": "{:.1f}", "K%": "{:.1f}",
    "BB%": "{:.1f}", "WHIFF%": "{:.1f}", "SWSTR%": "{:.1f}",
    "PUTAWAY%": "{:.1f}", "MEATBALL%": "{:.1f}", "1STPS%": "{:.1f}",
    "SWEETSPOT%": "{:.1f}", "PULLAIR%": "{:.1f}", "PULLBRL%": "{:.1f}",
    "BLAST%": "{:.1f}", "HRWINDOW%": "{:.1f}", "FB95%": "{:.1f}",
    "HR/FB": "{:.1f}", "SOFTNESS": "{:+.1f}",
    # Exit velocities read as mph — one decimal is how Statcast
    # publishes them.
    "EV90": "{:.1f}", "MAXEV": "{:.1f}", "AVGEV": "{:.1f}",
    # Innings and projections.
    "IP": "{:.1f}", "IP/GS": "{:.1f}", "PROJK": "{:.1f}", "L5AVG": "{:.1f}",
    "SLAM": "{:.1f}",
    # Counting stats. A count with a decimal point on it looks like a
    # rate, and PA especially — it is the DENOMINATOR the reader is
    # checking the row's weight against.
    "PA": "{:.0f}", "AB": "{:.0f}", "HR": "{:.0f}", "H": "{:.0f}",
    "G": "{:.0f}", "GP": "{:.0f}", "BBE": "{:.0f}", "ORD": "{:.0f}",
    "PITCHES": "{:.0f}", "PITCHESSEEN": "{:.0f}", "ARMS": "{:.0f}",
    "HRINTENT": "{:.0f}", "HRTHREAT": "{:.0f}", "THREAT": "{:.0f}",
    # FORM DELTAS — SIGNED, always. These are recent-minus-season in the
    # stat's own units, so the sign is half the reading: a bare "1.8"
    # does not say which way he moved, and 0.0 is a real measured value
    # here (exactly at his own baseline) rather than a missing one.
    "ΔEV": "{:+.1f}", "ΔHH%": "{:+.1f}",
}


def _norm_stat(name) -> str:
    """Column header -> STAT_FORMATS key. Case and spaces don't count."""
    return str(name).replace(" ", "").upper()


def stat_formats(df: pd.DataFrame, extra: dict = None) -> dict:
    """Format strings for the columns of `df` that STAT_FORMATS knows.

    Pass the result straight to Styler.format(). Anything the map doesn't
    cover falls through to the precision floor set above.

    ONLY NUMERIC COLUMNS ARE INCLUDED, and that is load-bearing rather
    than tidy: many views build their frames with the numbers ALREADY
    formatted into strings (f'{r["iso"]:.3f}'), and handing "{:.3f}" a str
    raises `ValueError: Unknown format code 'f' for object of type 'str'`
    — see the note in Pitchers_To_Target.py, which hit exactly that. A
    dtype check means this helper is safe to call on any frame.

    `extra` is merged last, so a caller's own formatter for a column
    (a logo cell, a score bar) always wins over the map.
    """
    out = {}
    for col in df.columns:
        try:
            numeric = pd.api.types.is_numeric_dtype(df[col])
        except Exception:
            numeric = False
        if not numeric:
            continue
        fmt = STAT_FORMATS.get(_norm_stat(col))
        if fmt:
            out[col] = fmt
    if extra:
        out.update(extra)
    return out


BG = COLOR["bg"]
CYAN = COLOR["stat_high"]
CYAN_RGB = tuple(int(CYAN.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

_MIN_OPACITY = 0.45
_MAX_OPACITY = 1.0

# The original three-anchor palette: red (low) -> amber (mid) -> cyan
# (high). The HUES were never the problem — how they were applied was.
#
# What made the old tables look muddy: every cell got a low-opacity wash
# of an interpolated colour, and a washed-out tint of anything on a dark
# background turns grey-brown. Two thirds of the grid was sludge, so
# nothing separated.
#
# Fixed by execution, not by changing colours:
#   - fills are more saturated and less washed out, so a colour reads as
#     that colour instead of as brown
#   - the mid band is a soft TINT rather than a heavy block, so amber
#     stays amber instead of muddying into its neighbours
#   - cells are pill-shaped with a subtle vertical gradient, the same
#     treatment as the score bars, so they read as deliberate rather than
#     as a flat wash
_GRAD_LOW = tuple(int(COLOR["error"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
_GRAD_MID = tuple(int(COLOR["warn"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
_GRAD_HIGH = CYAN_RGB

# Handedness — categorical, not magnitude-based, so these are a fixed
# lookup rather than a gradient.
_BATS_COLORS = {"L": COLOR["bats_l"], "R": COLOR["bats_r"], "S": COLOR["bats_s"]}


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def _gradient_rgb(t: float):
    if t <= 0.5:
        local_t = t / 0.5
        return (
            _lerp(_GRAD_LOW[0], _GRAD_MID[0], local_t),
            _lerp(_GRAD_LOW[1], _GRAD_MID[1], local_t),
            _lerp(_GRAD_LOW[2], _GRAD_MID[2], local_t),
        )
    local_t = (t - 0.5) / 0.5
    return (
        _lerp(_GRAD_MID[0], _GRAD_HIGH[0], local_t),
        _lerp(_GRAD_MID[1], _GRAD_HIGH[1], local_t),
        _lerp(_GRAD_MID[2], _GRAD_HIGH[2], local_t),
    )


def _cyan(opacity: float, bold: bool = False) -> str:
    r, g, b = CYAN_RGB
    weight = 700 if bold else 500
    return f"color: rgba({r},{g},{b},{opacity:.2f}); background-color: {BG}; font-weight: {weight};"


_BG_RGB = tuple(int(BG.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
_TEXT_RGB = tuple(int(COLOR["text"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


# Only the ENDS of the range get a filled cell.
#
# Every cell used to be filled, which is what made the tables look muddy:
# a mid-range value got a tan/brown wash, so two thirds of the grid was
# noise competing with the values that actually matter. Nothing stood out
# because everything was shouting.
#
# Now the middle band is left plain and only the tails are painted. The
# eye lands on the genuine highs and lows immediately, and the table reads
# as data with signal in it rather than a heatmap of sludge.
# FIVE DISCRETE TIERS, not a continuous ramp.
#
# A blended gradient guarantees the problem: "below average" and
# "average" are adjacent on the scale, so they are adjacent in hue, so
# they look alike. No amount of tuning fixes that — it is what
# interpolation MEANS. Every intermediate value is a mix of its
# neighbours.
#
# Discrete bands remove the failure entirely. Five states, each with a
# hue that shares nothing with the band beside it, so a cell's tier is
# readable on its own without comparing it to the rest of the column.
#
# Cut points are percentile positions within the column, chosen to match
# how people already talk about grades: a small elite tier, a small poor
# tier, and a wide middle. The middle band is deliberately COLOURLESS —
# "average" should read as the absence of a signal, which also means it
# can never be confused with the band either side of it.
# Every tier now carries a fill — including average, which used to be
# blank. Five hues, and all TEN pairings measure at least 133 apart in
# RGB distance, so no two tiers can be mistaken for each other whether
# they sit side by side or not.
#
# Why "below" is violet: once average is teal, good is gold and elite is
# cyan, the warm end is fully occupied by poor (red) and good (gold).
# Anything warm for "below" lands between them — orange measured 56 from
# red and 50 from gold, well inside the range where colours read alike.
# Violet is the only hue left that clears every other tier, and it reads
# as "off the pace" without implying the alarm that red does.
_TIERS = [
    # (upper bound of normalised value, hex, label)
    (0.15, "#D6304A",          "poor"),      # red
    (0.40, "#9B6BC7",          "below"),     # violet
    (0.60, COLOR["stat_mid"],  "average"),   # teal
    (0.85, "#E8B33C",          "good"),      # gold
    (1.01, COLOR["stat_high"], "elite"),     # cyan
]


def _tier_for(t: float):
    """(hex_or_None, label) for a normalised value in [0, 1]."""
    for upper, hex_colour, label in _TIERS:
        if t < upper:
            return hex_colour, label
    return _TIERS[-1][1], _TIERS[-1][2]


def _gradient_fill(t: float, bold: bool = False) -> str:
    """Cell style for a normalised value in [0, 1]. See _TIERS."""
    hex_colour, label = _tier_for(t)

    if hex_colour is None:
        # No tier colour configured — plain text rather than an
        # arbitrary fill. Not reachable with the current _TIERS, but the
        # branch keeps a None entry safe if a tier is ever blanked again.
        return f"color: {COLOR['text']}; font-weight: 500;"

    r, g, b = (int(hex_colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    # One opacity per tier, not a sliding scale — a slide would
    # reintroduce the very blending this replaces. The outer tiers sit
    # stronger so elite and poor carry the most weight.
    # Strength by distance from the middle, so the extremes still carry
    # the most weight even though every tier is now filled.
    strong = label in ("elite", "poor")
    top = 0.72 if strong else (0.30 if label == "average" else 0.46)
    bottom = top - 0.12
    return (
        f"background-image: linear-gradient(180deg, "
        f"rgba({r},{g},{b},{top:.2f}) 0%, rgba({r},{g},{b},{bottom:.2f}) 100%); "
        f"color: {BG if strong else COLOR['text']}; "
        f"font-weight: {700 if strong else 600}; border-radius:var(--lc-radius-md);"
    )


def _magnitude_column(col: pd.Series, invert: bool, use_gradient: bool = False):
    """Cell fills for one column.

    ABSOLUTE FIRST. If the column's header has a fixed scale in
    styles/stat_scales.py, every cell is coloured from its OWN value
    against that scale and nothing else on screen matters. A .285 is the
    same colour in the lineup table, on the HR board, and after any
    filter change.

    That is the behaviour this used to lack. Colour came from the
    column's own min and max, so the SAME number changed tier when you
    switched Bats or Window and no value had moved. It answered "where
    does this sit among the rows on screen", which nobody reads it as —
    a colour reads as a verdict.

    RELATIVE ONLY AS A FALLBACK, for columns with no scale defined
    (counting stats, one-off composites). Better an obviously
    column-relative colour than a fixed one invented on the spot; the
    honest fix for a column that lands here is to add its cut points to
    stat_scales.SCALES, not to special-case it.
    """
    numeric = pd.to_numeric(col, errors="coerce")
    if numeric.isna().all():
        return [""] * len(col)

    if has_scale(col.name):
        out = []
        for v in numeric:
            t = tier_fraction(col.name, v, invert=invert)
            if t is None:
                out.append("")
            elif use_gradient:
                out.append(_gradient_fill(t, bold=(t >= 0.75)))
            else:
                opacity = _MIN_OPACITY + (_MAX_OPACITY - _MIN_OPACITY) * t
                out.append(_cyan(opacity, bold=(t >= 0.7)))
        return out

    vmin, vmax = numeric.min(), numeric.max()
    if vmin == vmax:
        return [_gradient_fill(0.75) if use_gradient else _cyan(0.75)] * len(col)

    norm = (numeric - vmin) / (vmax - vmin)
    if invert:
        norm = 1 - norm

    styles = []
    for v in norm:
        if pd.isna(v):
            styles.append("")
            continue
        t = float(v)
        if use_gradient:
            styles.append(_gradient_fill(t, bold=(t >= 0.75)))
        else:
            opacity = _MIN_OPACITY + (_MAX_OPACITY - _MIN_OPACITY) * t
            styles.append(_cyan(opacity, bold=(t >= 0.7)))
    return styles


def _bats_column(col: pd.Series):
    """Categorical handedness coloring — L/R/S each get a fixed,
    distinct identity color, not a magnitude scale. Switch-hitter
    labels that name a side (e.g. "S->L", "S (R)") are colored by the
    side actually being batted from, so a switch hitter's two split
    rows read in their platoon colors rather than falling back to grey."""
    styles = []
    for v in col:
        raw = str(v).strip()          # displayed AS GIVEN
        c = _BATS_COLORS.get(raw)
        if not c:
            # switch label naming a side: pick the last L/R after the S
            if raw.startswith("S") and ("L" in raw[1:] or "R" in raw[1:]):
                side = "L" if raw.rfind("L") > raw.rfind("R") else "R"
                c = _BATS_COLORS.get(side)
        if c:
            styles.append(f"color: {c}; background-color: {BG}; font-weight: 700;")
        else:
            styles.append("")
    return styles


def _player_name_column(col: pd.Series):
    """Player name identity color, applied as a real column style
    (.apply()) rather than an index style (.map_index()) — proven to
    actually render correctly in Streamlit's dataframe widget, unlike
    index-level styling which doesn't reliably show up. Covers both
    'Player' and 'Name' headers so nothing gets missed."""
    c = COLOR["player_name"]
    # Left-aligned with a touch of letter-spacing: the name column is the
    # only text column in a table of right-aligned numbers, and aligning
    # it left is what makes a lineup scannable top-to-bottom.
    return [f"color: {c}; background-color: {BG}; font-weight: 650; "
            f"text-align: left; letter-spacing: 0.01em;" for _ in col]


def _pitch_type_column(col: pd.Series):
    """Real pitch-type colors (same mapping used by the Pitch Mix bars
    elsewhere on the page) — a Sinker is the same color everywhere on
    the page, not a different color in every table."""
    styles = []
    for v in col:
        c = pitch_color_by_name(str(v).strip())
        styles.append(f"color: {c}; background-color: {BG}; font-weight: 700;")
    return styles


def _gold_column(col: pd.Series):
    """Gold text for secondary/detail columns (Detail, Confidence on
    the Matchup Edges card) — same reliable .apply() column pattern as
    everything else, not the unreliable index styling."""
    c = COLOR["gold"]
    return [f"color: {c}; background-color: {BG};" for _ in col]


def _base_styler(df: pd.DataFrame):
    """Shared foundation for every table in the app. Player names,
    handedness, and pitch type all get automatic identity colors here
    — every table that uses this gets them for free.

    Player names use .apply() on a real "Player"/"Name" column, NOT
    .map_index() on the pandas index — index-level styling doesn't
    reliably render in Streamlit's dataframe widget (confirmed: the
    generated CSS was correct, but the color didn't show up on
    screen), while column-level .apply() is proven to work (Bats
    colors render correctly using this exact method).

    The index is hidden HERE, on the Styler itself (`.hide(axis=
    "index")`), not left to st.dataframe's hide_index=True display
    param. When a Styler is passed into st.dataframe, its per-cell
    styles are positioned against the Styler's own column layout —
    if the index is only hidden at the widget level, every styled
    cell still carries the index's column slot, so colors render
    shifted one column to the left of their real header. Hiding it on
    the Styler itself removes that slot before any styling is applied,
    so colors land under the header they're actually for."""
    base = df.style.set_properties(**{
        "font-family": "'JetBrains Mono', monospace",
        "font-size": "13.5px",
        "background-color": BG,
        "color": COLOR["text"],
    # na_rep IS NOT OPTIONAL HERE.
    #
    # The engines return None (never a fabricated 0) for anything they
    # couldn't measure. Without na_rep, pandas renders that None as the
    # literal string "nan" in the cell — which looks like a bug to a
    # subscriber and, worse, invites someone to "fix" it by putting the
    # zero defaults back. An em dash says "not measured" in the same
    # visual language the rest of the app already uses.
    #
    # Callers that pass their own .format(..., na_rep=...) override this,
    # which is fine — they use "N/A" for the same purpose.
    }).format(precision=2, na_rep="\u2014").hide(axis="index")

    for name_col in ("Player", "Name"):
        if name_col in df.columns:
            base = base.apply(_player_name_column, subset=[name_col])
    if "Bats" in df.columns:
        base = base.apply(_bats_column, subset=["Bats"])
    if "Pitch Type" in df.columns:
        base = base.apply(_pitch_type_column, subset=["Pitch Type"])
    for gold_col in ("Detail", "Confidence"):
        if gold_col in df.columns:
            base = base.apply(_gold_column, subset=[gold_col])

    if df.empty or len(df.columns) == 0:
        return base

    return base.set_table_styles([
        {"selector": "th.blank", "props": f"background-color:{BG};"},
        {"selector": "th.row_heading", "props": f"background-color:{BG}; color:{COLOR['text']}; font-weight:700;"},
        {"selector": "th.col_heading", "props": f"background-color:{BG}; color:{COLOR['gold']}; font-weight:700; text-transform:uppercase; font-size:var(--lc-text-caption);"},
    ])


def plain_dark_table(df: pd.DataFrame):
    """For tables with no magnitude coloring needed (pitch arsenal
    lists, roster lookups). Still gets identity colors automatically."""
    return _base_styler(df)


def grade_text_column(styler, col, scale_key=None, gradient=True):
    """Colour a column whose cells are TEXT, by the number inside them.

    _magnitude_column coerces with pd.to_numeric and gives up on a
    column of strings — correct, because a column of words has no
    magnitude. But some cells are a number WEARING text: "86% \u2191"
    is a percentile with a direction glued on, and leaving it grey put
    the one self-relative column on the lineup table in plain type
    beside twenty graded ones, which reads as "this one doesn't matter".

    Grades on the LEADING number and ignores everything after it. The
    suffix is decoration; the number is the value.

    scale_key names an entry in stat_scales so the cut points live with
    every other scale on the site rather than being invented here. None
    falls back to the column's own spread.
    """
    import re as _r

    def _paint(column):
        nums = column.astype(str).str.extract(r"^\s*(-?\d+(?:\.\d+)?)")[0]
        nums = pd.to_numeric(nums, errors="coerce")
        nums.name = scale_key or column.name
        return _magnitude_column(nums, invert=False, use_gradient=gradient)

    if col in styler.data.columns:
        styler = styler.apply(_paint, subset=[col])
    return styler


def style_stat_table(df: pd.DataFrame, favor_high=None, favor_low=None, gradient: bool = False):
    """
    favor_high: column names where a HIGHER value is better
    favor_low:  column names where a LOWER value is better
    gradient:   False = cyan brightness only. True = real red/amber/cyan
                BACKGROUND fill with dark text.
    Player name and Bats identity colors always apply automatically,
    regardless of this table's gradient setting.
    """
    favor_high = favor_high or []
    favor_low = favor_low or []

    styler = _base_styler(df)
    for col in favor_high:
        if col in df.columns:
            styler = styler.apply(lambda c: _magnitude_column(c, invert=False, use_gradient=gradient), subset=[col])
    for col in favor_low:
        if col in df.columns:
            styler = styler.apply(lambda c: _magnitude_column(c, invert=True, use_gradient=gradient), subset=[col])

    return styler

# ----------------------------------------------------------------------
# HTML table rendering — for small reference tables on small screens.
#
# st.dataframe draws on a CANVAS (see app/.streamlit/config.toml), which
# means CSS cannot touch it: no responsive column widths, no font
# scaling, and no working sticky column. Its frozen index also smears
# during momentum scrolling in iOS Safari.
#
# For a 3-row splits table none of st.dataframe's features earn their
# keep — there is nothing to sort and nothing to resize — so these render
# as real HTML instead, where CSS does the work. The first column sticks
# while the rest scroll, so the row label stays on screen.
#
# The big lineup table deliberately does NOT use this: sorting is the
# whole point there, and that only exists in st.dataframe.
# ----------------------------------------------------------------------
_HTML_TABLE_CSS = f"""
<style>
/* min-width:0 and max-width:100% are load-bearing, not tidy-up.
   A flex/grid item defaults to min-width:auto, which means it REFUSES to
   shrink below its content width — so overflow-x:auto never engages, the
   table spills straight out of its card, and on a two-column layout it
   paints on top of the neighbouring table. That produced overlapping
   digits where the two collided. Forcing the wrapper to be allowed to
   shrink is what turns the overflow into a scroll. */
.lc-tbl-wrap {{
  /* No drag-select. Dragging across an HTML table paints the browser's
     selection highlight over the cells — the black band that appears
     when you click or swipe a row. Nobody copies text out of these, and
     on a touchscreen a scroll gesture becomes a selection, so the
     highlight fires constantly. */
  -webkit-user-select: none;
  user-select: none;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius:var(--lc-radius-md);
  min-width: 0;
  max-width: 100%;
}}
/* Streamlit's own column wrappers are flex items too, and have the same
   min-width:auto default — without this the constraint above never gets
   a chance to apply. Scoped to columns that actually contain one of
   these tables so nothing else on the page is affected. */
div[data-testid="stColumn"]:has(.lc-tbl-wrap),
div[data-testid="column"]:has(.lc-tbl-wrap) {{
  min-width: 0;
  overflow: hidden;
}}
.lc-tbl-wrap table {{
  border-collapse: separate;
  border-spacing: 0;
  /* max-content so columns keep their natural width and the wrapper
     scrolls; min-width:100% so a narrow table still fills the card
     rather than sitting in a stub at the left. */
  width: max-content;
  min-width: 100%;
  font-family: 'JetBrains Mono', monospace;
  font-size:var(--lc-text-body);
}}
.lc-tbl-wrap th, .lc-tbl-wrap td {{
  /* Roomier rows and a hairline separator instead of hard-edged blocks.
     The flat, tightly-packed grid was the other half of the dated look —
     the score bars read as modern because they have depth and breathing
     room, and the cells around them had neither. */
  padding:var(--lc-space-md) var(--lc-space-lg);
  text-align: right;
  white-space: nowrap;
  background-color: {BG};
  border-bottom: 1px solid {COLOR["border"]}55;
}}
/* Numbers in monospace so columns of digits line up; everything else
   inherits the sans face. This is the split the app always intended —
   see the note in .streamlit/config.toml. */
.lc-tbl-wrap td {{
  font-variant-numeric: tabular-nums;
}}
.lc-tbl-wrap tbody tr {{
  transition: background 0.12s ease;
}}
.lc-tbl-wrap tbody tr:hover td {{
  /* A LIFT, not a background swap.
     This used to set background-color: surface, which is DARKER than the
     gradient fills — so hovering a row blacked it out instead of
     highlighting it. box-shadow layers over whatever fill the cell has,
     so every row lifts the same way regardless of its colour. */
  box-shadow: inset 0 0 0 999px rgba(255,255,255,0.045);
}}
.lc-tbl-wrap tbody tr:last-child td {{ border-bottom: none; }}
.lc-tbl-wrap thead th {{
  color: {COLOR['text_muted']};
  font-weight: 600;
  text-transform: uppercase;
  font-size:var(--lc-text-tiny);
  letter-spacing: 0.07em;
  padding-bottom:var(--lc-space-sm);
  /* Muted grey rather than bright gold. A header row shouting in gold
     competes with the data for attention; the data should win. The
     underline does the separating instead of the colour. */
  border-bottom: 1px solid {COLOR["border"]};
  position: sticky;
  top: 0;
  z-index: 2;
}}
/* First column carries the row label (Split / Season). Sticky so it
   stays put while the stats scroll under it — this is the whole reason
   these tables are HTML and not st.dataframe. */
/* Opaque background is required: the cells that scroll UNDER this one
   carry their own gradient fills, and a transparent sticky cell would
   let them bleed through as it passes. */
.lc-tbl-wrap td:first-child, .lc-tbl-wrap th:first-child {{
  position: sticky;
  left: 0;
  z-index: 3;
  background-color: {BG} !important;
  text-align: left;
  font-weight: 700;
  color: {COLOR['text']};
  box-shadow: 1px 0 0 0 {COLOR['stat_high']}33;
}}
.lc-tbl-wrap thead th:first-child {{ z-index: 4; }}

/* ---------------- THE GRID ----------------
   Organisation only — no column gains or loses anything here.

   These tables are wide and dense, and until now the only structure in
   them was horizontal: a rule under the header and a rule under each
   row. Nothing separated one COLUMN from the next, so a run of eight
   numbers read as a stripe and your eye had to track back up to the
   header to work out which stat it was on. That is the actual
   complaint about these tables, and it is a ruling problem, not a
   content problem.

   Vertical hairlines fix it, at one twelfth the strength of the
   horizontal ones. They have to be nearly invisible: a full-strength
   grid turns the table into graph paper and competes with the cell
   fills, which are the signal. You should feel the columns, not see
   the lines.

   The label column keeps its accent edge (above) so the boundary
   between "who" and "how much" stays the strongest line in the table.  */
.lc-tbl-wrap td, .lc-tbl-wrap th {{
  border-right: 1px solid {COLOR['text']}0D;
}}
.lc-tbl-wrap td:last-child, .lc-tbl-wrap th:last-child {{
  border-right: none;
}}

/* Column hover. On a table this wide the hard part is staying on the
   right stat while reading down; the row hover already handles the
   other axis. Pure CSS, no JS: :has() lets a cell light its own column
   header when the pointer is anywhere in the table body. Browsers
   without :has() simply do not get the effect and nothing breaks. */
.lc-tbl-wrap tbody td:hover {{
  box-shadow: inset 0 0 0 999px rgba(255,255,255,0.05);
}}

/* Alignment: labels left, numbers right. Right-aligned digits put the
   ones column under the ones column, which is the only way a stack of
   numbers is comparable at a glance. Left-aligned numerics were
   ragged wherever a value lost a decimal place. */
.lc-tbl-wrap td, .lc-tbl-wrap th {{
  text-align: right;
}}
.lc-tbl-wrap td:first-child, .lc-tbl-wrap th:first-child {{
  text-align: left;
}}

/* Phones: tighter padding and smaller type so more columns fit before
   any scrolling is needed. Desktop keeps the roomier sizing above. */
@media (max-width: 900px) {{
  .lc-tbl-wrap table {{ font-size:var(--lc-text-caption); }}
  .lc-tbl-wrap th, .lc-tbl-wrap td {{ padding:var(--lc-space-xs) var(--lc-space-sm); }}
  .lc-tbl-wrap thead th {{ font-size:var(--lc-text-micro); }}
}}
/* DENSE — for tables with a lot of COLUMNS, at any screen width.
   The breakpoint above only fires below 900px, so a 25-column lineup
   table on a wide tablet got the same roomy padding as a 5-column
   reference table and ran off the edge with columns to spare. Density
   should follow the TABLE's width, not the viewport's: CSS cannot count
   columns, so render_html_table adds this class. */
.lc-tbl-wrap.lc-tbl-dense th, .lc-tbl-wrap.lc-tbl-dense td {{
  padding:var(--lc-space-xs) var(--lc-space-sm);
}}
.lc-tbl-wrap.lc-tbl-dense table {{ font-size:var(--lc-text-caption); }}
.lc-tbl-wrap.lc-tbl-dense thead th {{ font-size:var(--lc-text-micro); }}
/* A visible edge on the scroll container. Without it a table that
   continues past the viewport looks CROPPED rather than scrollable —
   the content just stops, and nothing says there is more. */
.lc-tbl-wrap {{
  background-image: linear-gradient(to left, {BG}00, {BG}ee 92%);
  background-position: right center;
  background-repeat: no-repeat;
  background-size: 28px 100%;
  background-attachment: local;
}}
</style>
"""


_TABLE_SEQ = itertools.count()


def render_html_table(styler, key: str = ""):
    """Render a pandas Styler as real HTML with a sticky first column.

    Use for SMALL reference tables where the row label matters more than
    sorting. Pass a Styler whose row label is already a real COLUMN, not
    an index — _base_styler calls .hide(axis="index"), so anything left
    in the index is dropped before it ever reaches here.

    THE UUID IS ALWAYS UNIQUE, AND THAT IS NOT A DETAIL.

    pandas builds its selectors from table_uuid: #T_{uuid}_row0_col10.
    This used to be f"lc{key}", with key defaulting to "" — so every
    caller that passed no key emitted CSS under the identical selector,
    and two such tables on one page have equal specificity. The LAST one
    rendered wins for all of them.

    That is not theoretical. The WNBA team table renders inside two
    nested loops (once per prop tab, once per side) with a hardcoded
    key="wnba_636", so a three-game slate painted dozens of tables all
    claiming the same selectors — and every team's grid wore the colours
    computed for whichever table happened to render last. It read as
    "the colours are inverted", because the numbers and their colours
    came from different tables. GameCard had nine keyless tables on one
    page with the same collision.

    So key is now a readable LABEL, not the uniqueness mechanism. A
    counter guarantees the uuid differs even when two callers pass the
    same key, or none. Uniqueness must not depend on every future caller
    remembering to invent a name — that is exactly the discipline this
    bug proves nobody sustains.
    """
    import streamlit as st

    # CSS is emitted on EVERY call, deliberately — do not "optimise" this
    # with a session_state once-only guard.
    #
    # Streamlit rebuilds the whole DOM on every rerun. A once-only flag
    # survives in session_state but the <style> tag it guarded does NOT
    # survive in the page, so from the second rerun onward these tables
    # render with no CSS at all: no overflow container, no sticky column,
    # default table layout spilling out of its card and colliding with the
    # table beside it. It looks correct on first load and breaks the
    # moment you touch any filter, which is exactly how it shipped.
    #
    # Repeating a small <style> block is cheap and idempotent; the browser
    # just applies the same rules again.
    st.markdown(_HTML_TABLE_CSS, unsafe_allow_html=True)

    # THE KEY IS SANITISED, and that is not cosmetic.
    #
    # pandas puts table_uuid straight into CSS selectors:
    #     #T_{uuid}_row0_col4 { background-image: ... }
    #
    # A key of "wnba_Pts+Reb_away" produces #T_lcwnba_Pts+Reb_away_7_...
    # and "+" is not a valid character in a CSS identifier, so the
    # browser DISCARDS THE ENTIRE RULE and the table renders with no
    # colour at all. Not a warning, not a partial failure — silence.
    #
    # This shipped: the WNBA tab labels are Points, Rebounds, Assists,
    # Threes, PRA, Pts+Reb, Pts+Ast, Reb+Ast, Stocks, Volume, and the
    # three that lost their colour were exactly the three containing a
    # "+". Every other tab was fine, which is what made it look like a
    # data problem in the combo stats rather than a naming one.
    #
    # Callers pass human labels because that is what makes selectors
    # readable in devtools. Making them CSS-safe is this function's job,
    # not every caller's.
    # A WIDE TABLE GETS TIGHTER CELLS, at any screen size. Twelve is the
    # point where roomy padding starts costing more columns than it buys
    # in legibility — a lineup table carries twenty-five and a reference
    # table five, and they should not be spaced the same.
    # `or []` on an Index raises — pandas refuses to guess the truth
    # value of one. Ask for the length directly.
    _data = getattr(styler, "data", None)
    _ncols = len(_data.columns) if _data is not None and hasattr(_data, "columns") else 0
    _dense = " lc-tbl-dense" if _ncols > 12 else ""
    safe = _re.sub(r"[^A-Za-z0-9_-]", "_", str(key))
    uid = f"lc{safe}_{next(_TABLE_SEQ)}"
    html = styler.to_html(table_uuid=uid) if hasattr(styler, "to_html") else str(styler)
    st.markdown(f'<div class="lc-tbl-wrap{_dense}">{html}</div>',
                unsafe_allow_html=True)


def score_bar(color_key: str = "gold"):
    """Formatter that renders a 0-100 score as an inline filled bar.

    Replaces st.column_config.ProgressColumn, which only exists inside
    st.dataframe — and st.dataframe brings drag-to-reorder columns with
    no way to disable it (streamlit#11222), which on a phone turns any
    scroll into a column shuffle. The bars were the only reason the
    lineup table was still on that widget.

    Returns a function suitable for Styler.format(). pandas does not
    escape formatter output, so the returned markup renders as markup.

    Missing values render as "N/A", never as a zero-width bar: an empty
    bar reads as a real score of zero, which is the worst possible
    reading of "we don't know".
    """
    # color_key is now only a FALLBACK. The bar takes its colour from the
    # value's tier, so a 92 and a 24 in the same column no longer share a
    # hue and differ only by length — the colour says the grade and the
    # length says the amount. Same five tiers as the cells, so gold means
    # "good" everywhere on the site.
    # (No assignment needed — color_key is consulted per value in _fmt.)

    def _fmt(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/A"
        try:
            pct = max(0.0, min(100.0, float(v)))
        except (TypeError, ValueError):
            return "N/A"
        fill = tier_color_for(pct)
        # A real bar, not a flat block of colour.
        #
        # Three pieces, and each one does a job:
        #   TRACK   an inset dark channel with a hairline border, so the
        #           empty portion is visible and the bar has a defined
        #           length to be read against. A floating fill with no
        #           track gives the eye nothing to measure from.
        #   FILL    a gradient along the bar rather than one flat tone.
        #           Flat fills of two similar scores look identical at a
        #           glance; a gradient gives the length itself a shape.
        #   CAP     a bright 2px leading edge. This is what makes the
        #           value readable without looking at the number — the
        #           eye lands on the cap position, and it separates a 78
        #           from an 82 far better than fill colour alone.
        return (
            f'<div style="position:relative; width:100%; min-width:62px; '
            f'height:19px; line-height:19px; border-radius:var(--lc-radius-sm); '
            f'background:{COLOR["bg"]}; '
            f'box-shadow:inset 0 0 0 1px {COLOR["stat_mid_dim"]}; '
            f'overflow:hidden;">'
            f'<div style="position:absolute; left:0; top:0; bottom:0; '
            f'width:{pct:.0f}%; border-radius:var(--lc-radius-sm); '
            f'background:linear-gradient(90deg, {fill}44 0%, {fill}8C 100%);'
            f'"></div>'
            f'<div style="position:absolute; top:1px; bottom:1px; '
            f'left:calc({pct:.0f}% - 2px); width:2px; background:{fill}; '
            f'border-radius:var(--lc-radius-sm);"></div>'
            # Number sits on the RIGHT with its own padding. Left-aligned
            # it sat underneath the fill and the leading cap sliced
            # through the digits — a 91 rendered as "9|". Right-aligned it
            # is always clear of the cap except at a full 100, where the
            # cap is at the cell edge anyway.
            f'<span style="position:relative; float:right; font-weight:700; '
            f'padding-right:var(--lc-space-sm); text-shadow:0 1px 2px {COLOR["bg"]};">'
            f'{pct:.0f}</span>'
            f'</div>'
        )
    return _fmt


def team_logo_cell():
    """Formatter: team abbreviation with its logo beside it.

    Same trick as score_bar — a Styler formatter returning markup, which
    pandas does not escape. This is why logos are possible at all now:
    st.column_config.ImageColumn only works inside st.dataframe, and
    these tables moved to HTML to escape drag-to-reorder.

    Keeps the TEXT next to the logo rather than replacing it. A logo
    alone is unreadable for anyone who doesn't know all thirty marks by
    sight, and it breaks entirely if the image fails to load.
    """
    from engines.team_logos import logo_for_any

    def _fmt(v):
        if not v or (isinstance(v, float) and pd.isna(v)):
            return "\u2014"
        url = logo_for_any(str(v))
        if not url:
            # No logo resolved — show the abbreviation alone rather than
            # a broken image icon.
            return str(v)
        # Logo ONLY when one resolves — the mark is the identifier and the
        # abbreviation beside it was pure duplication, eating width that
        # matters on a phone. title= keeps the name reachable on hover and
        # for screen readers. When no logo resolves the text is still
        # returned above, so the column never renders empty.
        return (f'<img src="{url}" title="{v}" alt="{v}" '
                f'style="height:19px; vertical-align:-4px;">')
    return _fmt


def bats_chip():
    """Formatter: L / R / S as a coloured chip.

    Handedness drives most of the platoon logic in this app, and it was
    rendering as a bare letter that reads as just another character in a
    dense row. A chip makes the split scannable down a lineup.

    Colours follow the existing palette: teal for lefties, amber for
    righties, gold for switch hitters — chosen so the two common values
    are the two most distinguishable hues in the theme, not so that
    either reads as "good".
    """
    tone = {"L": COLOR["stat_high"], "R": COLOR["warn"], "S": COLOR["gold"]}

    def _fmt(v):
        if not v or (isinstance(v, float) and pd.isna(v)):
            return "\u2014"
        raw = str(v).strip()          # displayed AS GIVEN

        # THE CHIP MUST KEEP THE SIDE. This took `[:1]` and rendered the
        # first character, which is right for "L" and "R" and silently
        # destructive for a switch hitter: "S (L)", "S (R)" and
        # "S (BOTH)" all came out as a bare "S".
        #
        # That is the bug the caller had already been fixed for. The
        # lineup table renders a switch hitter as two or three rows —
        # one per platoon side plus a combined one — with genuinely
        # different numbers, and the LABEL is the only thing telling
        # them apart. The formatter threw it away after the fact, so the
        # table showed the same player twice at the same batting order
        # with no way to tell which row was which side.
        #
        # Now the chip keeps whatever the caller sent and only uses the
        # leading letter to pick the colour.
        # Upper only to look up the colour — uppercasing the whole
        # label turned "S (both)" into a shouted "S (BOTH)".
        k = raw[:1].upper()
        c = tone.get(k)
        if not c:
            return str(v)

        # A qualified label is longer than a letter, so the chip has to
        # size to its content rather than to a fixed 17px box, and it
        # must not wrap inside a narrow Bats column.
        return (f'<span style="display:inline-block; min-width:17px; '
                f'text-align:center; white-space:nowrap; '
                f'padding:var(--lc-space-hair) var(--lc-space-xs); border-radius:var(--lc-radius-sm); '
                f'background:{c}26; color:{c}; font-weight:700; '
                f'font-size:var(--lc-text-caption);">{raw}</span>')
    return _fmt


def player_cell(locked_names=None):
    """Formatter: player name, with a HOT badge when the bat is locked in.

    The lock used to be a raw emoji prepended to the name. Emoji render
    at a different size and baseline than the monospace face around them,
    so every locked row sat a pixel or two off and the name column looked
    ragged — and an emoji carries no meaning to someone who hasn't read
    the legend.

    A text badge stays on the same baseline and says what it means.
    """
    locked = set(locked_names or ())

    def _fmt(v):
        if not v:
            return "\u2014"
        name = str(v)
        if name not in locked:
            return name
        return (
            f'{name}<span style="display:inline-block; margin-left:var(--lc-space-sm); '
            f'padding:var(--lc-space-hair) var(--lc-space-xs); border-radius:var(--lc-radius-sm); background:{COLOR["gold"]}26; '
            f'color:{COLOR["gold"]}; font-size:var(--lc-text-micro); font-weight:800; '
            f'letter-spacing:0.04em; vertical-align:1px;">HOT</span>'
        )
    return _fmt


def form_dots(hit_char="\u25cf", miss_char="\u00b7"):
    """Formatter: a run of hit/miss marks, spaced and colour-coded.

    The bare string of dots read as debris — evenly grey, no spacing, no
    indication which end was recent. Hits take the positive colour, misses
    recede into the muted one, and letter-spacing separates them so the
    pattern of gaps is legible at a glance. Newest is on the RIGHT, which
    the tooltip states rather than leaving to guesswork.
    """
    def _fmt(v):
        if not v:
            return "\u2014"
        out = []
        for ch in str(v):
            if ch == hit_char:
                out.append(f'<span style="color:{COLOR["stat_high"]};">{ch}</span>')
            elif ch == miss_char:
                out.append(f'<span style="color:{COLOR["stat_mid_text"]}; '
                           f'opacity:0.55;">{ch}</span>')
            else:
                out.append(ch)
        return (f'<span title="oldest on the left, most recent on the right" '
                f'style="letter-spacing:2.5px; font-size:var(--lc-text-body);">'
                + "".join(out) + '</span>')
    return _fmt


def sort_control(df, key: str, default: str = None, numeric_only: bool = True):
    """Dropdown that sorts a frame highest-to-lowest by a chosen column.

    Moving the tables to HTML removed st.dataframe's click-to-sort along
    with its drag-to-reorder. The drag was the thing worth losing;
    sorting was not, so this puts it back explicitly.

    Handles the awkward part: several boards build their cells as
    ALREADY-FORMATTED STRINGS ("0.214", "2.08", "—"), so a plain
    sort_values would order them as text and put "9.9" above "10.1".
    Sorting runs on a numeric coercion of the column, with unparseable
    values (the em-dash placeholders) pushed to the bottom where a
    missing value belongs rather than the top.

    Returns the sorted frame. `key` must be unique per table.
    """
    import streamlit as st

    cols = list(df.columns)
    if numeric_only:
        # A column qualifies if most of its values parse as numbers —
        # covers both real floats and pre-formatted numeric strings.
        num = []
        for c in cols:
            vals = pd.to_numeric(df[c].astype(str).str.replace("%", "", regex=False),
                                 errors="coerce")
            if vals.notna().mean() >= 0.6:
                num.append(c)
        cols = num
    if not cols:
        return df

    choice = st.selectbox(
        "Sort by", ["(board order)"] + cols,
        index=(cols.index(default) + 1) if default in cols else 0,
        key=f"sort_{key}", label_visibility="collapsed",
    )
    if not choice or choice == "(board order)":
        return df

    order = pd.to_numeric(df[choice].astype(str).str.replace("%", "", regex=False),
                          errors="coerce")
    # na_position="last": an em-dash means "no data", and a board that
    # sorts unknowns to the top is worse than one that doesn't sort.
    return df.assign(_lc_sort=order).sort_values(
        "_lc_sort", ascending=False, na_position="last").drop(columns="_lc_sort")


def tier_legend(caption: str = "", favor_note: str = "") -> None:
    """Render the five-tier colour key.

    Colour without a key is a guess. Five filled tiers look authoritative
    whether or not anyone knows what they mean, and someone betting money
    off this page should never have to infer whether gold is good.

    `favor_note` says WHICH DIRECTION is good for this table — it flips
    between boards (a high Brl% is good for a batter and bad for the
    pitcher allowing it), and that is exactly the misreading this exists
    to prevent.
    """
    import streamlit as st

    swatches = []
    for _upper, hex_colour, label in _TIERS:
        if hex_colour is None:
            continue
        swatches.append(
            f'<span style="display:inline-flex; align-items:center; gap:5px; '
            f'margin-right:var(--lc-space-lg);">'
            f'<span style="width:11px; height:11px; border-radius:var(--lc-radius-sm); '
            f'background:{hex_colour}; opacity:0.85; display:inline-block;"></span>'
            f'<span style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-tiny); '
            f'letter-spacing:0.03em;">{label}</span></span>'
        )
    note = ""
    if favor_note:
        note = (f'<div style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny); '
                f'margin-top:var(--lc-space-hair);">{favor_note}</div>')
    extra = ""
    if caption:
        extra = (f'<div style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny); '
                 f'margin-top:var(--lc-space-hair);">{caption}</div>')
    st.markdown(
        f'<div style="margin:var(--lc-space-sm) var(--lc-space-none) var(--lc-space-lg) var(--lc-space-none);">{"".join(swatches)}{note}{extra}</div>',
        unsafe_allow_html=True,
    )


def tier_color_for(value, lo=None, hi=None) -> str:
    """Tier hex for a raw 0-100 score — used to colour bars by GRADE.

    Bars used to take a fixed colour per column, so an elite score and a
    poor one in the same column were the same hue and only length
    separated them. Reading the tier colour off the value makes the bars
    speak the same language as the cells: gold means good everywhere on
    the site, not just in one table.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return COLOR["text_muted"]
    lo = 0.0 if lo is None else float(lo)
    hi = 100.0 if hi is None else float(hi)
    t = 0.0 if hi <= lo else max(0.0, min(1.0, (v - lo) / (hi - lo)))
    hex_colour, _label = _tier_for(t)
    return hex_colour or COLOR["text_muted"]


def wnba_logo_cell(id_by_name: dict, url_by_name: dict = None):
    """Formatter: WNBA team logo, keyed by ESPN team id.

    Separate from team_logo_cell because that one resolves against MLB's
    team map — pointing it at a WNBA abbreviation returns nothing and
    silently renders no logo, which is why the WNBA boards stayed
    text-only while the MLB ones got marks.

    `id_by_name` maps the team string in the column to its ESPN id, built
    by the caller from the rows it already has.

    `url_by_name` maps the team string to ESPN'S OWN logo URL, as
    captured by the nightly build. PREFERRED over the id when present,
    because the id-built CDN path does not exist for every club — the
    expansion teams 404, and a 404 renders as a broken-image "?" glyph
    in the cell, which is worse than no logo at all. Order is therefore:
    real URL -> id-built path -> plain text.
    """
    from engines.wnba_logos import logo_url_by_id

    url_by_name = url_by_name or {}

    def _fmt(v):
        if not v or (isinstance(v, float) and pd.isna(v)):
            return "\u2014"
        url = url_by_name.get(str(v)) or logo_url_by_id(id_by_name.get(str(v)))
        if not url:
            # Nothing resolved — text, never a broken image.
            return str(v)
        # onerror is the last line of defence: if the URL itself 404s at
        # render time, the image replaces ITSELF with the team name
        # rather than leaving a broken glyph in the table.
        return (f'<img src="{url}" title="{v}" alt="{v}" '
                f'onerror="this.replaceWith(document.createTextNode(this.alt))" '
                f'style="height:19px; vertical-align:-4px;">')
    return _fmt


@_st_cache_1h()
def _allowed_percentiles() -> dict:
    """League decile cut points for contact allowed, from the nightly."""
    try:
        path = (Path(__file__).resolve().parent.parent
                / "data" / "statcast" / "pitcher_allowed_pct.json")
        return _tbl_json.loads(path.read_text()) or {}
    except Exception:
        return {}


def style_vs_league(df, favor_low=None):
    """Style a ONE-ROW table by comparing each value to the whole league.

    A single row has nothing to rank within, which is why the HR
    Vulnerability card rendered one flat colour for every cell. The
    comparison that answers "is this bad?" is against OTHER PITCHERS, and
    precompute.build_pitcher_allowed_percentiles ships exactly that.

    `favor_low` lists columns where a LOW value is good for the pitcher.
    On this card the reader is a bettor looking at the BATTER's side, so
    the caller passes the direction it wants and the tiers follow.

    Falls back to plain text for any column the league file doesn't
    cover — an ungraded number beats a fabricated grade.
    """
    pct = _allowed_percentiles().get("deciles", {})
    low = set(favor_low or ())

    def _style_row(row):
        out = []
        for col, val in row.items():
            cuts = pct.get(str(col))
            if not cuts or val is None or (isinstance(val, float) and pd.isna(val)):
                out.append("")
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                out.append("")
                continue
            # Where this pitcher sits in the league, 0-1.
            above = sum(1 for c in cuts if v >= c)
            t = max(0.0, min(1.0, (above - 1) / (len(cuts) - 1)))
            if col in low:
                t = 1.0 - t
            out.append(_gradient_fill(t))
        return out

    # .hide(axis="index") — this builds its own Styler rather than going
    # through _base_styler, which is where every other table hides the
    # index. Without it a throwaway "0" rendered as a first column.
    return (df.style
              .apply(_style_row, axis=1)
              .set_properties(**{
                  "font-family": "'JetBrains Mono', monospace",
                  "font-size": "13.5px",
                  "text-align": "right",
              })
              .hide(axis="index"))
