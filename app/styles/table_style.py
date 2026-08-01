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
import pandas as pd

from .kc_theme import COLOR, pitch_color_by_name

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
_TIERS = [
    # (upper bound of normalised value, hex, label)
    (0.15, COLOR["error"],     "poor"),
    (0.40, COLOR["warn"],      "below"),
    (0.60, None,               "average"),   # None = no fill
    (0.85, COLOR["stat_mid"],  "good"),
    (1.01, COLOR["stat_high"], "elite"),
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
        # Average: no fill, plain readable text. The absence IS the
        # signal, and it makes the four coloured tiers unmistakable.
        return f"color: {COLOR['text']}; font-weight: 500;"

    r, g, b = (int(hex_colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    # One opacity per tier, not a sliding scale — a slide would
    # reintroduce the very blending this replaces. The outer tiers sit
    # stronger so elite and poor carry the most weight.
    strong = label in ("elite", "poor")
    top = 0.72 if strong else 0.42
    bottom = top - 0.12
    return (
        f"background-image: linear-gradient(180deg, "
        f"rgba({r},{g},{b},{top:.2f}) 0%, rgba({r},{g},{b},{bottom:.2f}) 100%); "
        f"color: {BG if strong else COLOR['text']}; "
        f"font-weight: {700 if strong else 600}; border-radius: 5px;"
    )


def _magnitude_column(col: pd.Series, invert: bool, use_gradient: bool = False):
    numeric = pd.to_numeric(col, errors="coerce")
    if numeric.isna().all():
        return [""] * len(col)

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
        raw = str(v).strip().upper()
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
    }).format(precision=2).hide(axis="index")

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
        {"selector": "th.col_heading", "props": f"background-color:{BG}; color:{COLOR['gold']}; font-weight:700; text-transform:uppercase; font-size:11px;"},
    ])


def plain_dark_table(df: pd.DataFrame):
    """For tables with no magnitude coloring needed (pitch arsenal
    lists, roster lookups). Still gets identity colors automatically."""
    return _base_styler(df)


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
  border-radius: 6px;
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
  font-size: 13px;
}}
.lc-tbl-wrap th, .lc-tbl-wrap td {{
  /* Roomier rows and a hairline separator instead of hard-edged blocks.
     The flat, tightly-packed grid was the other half of the dated look —
     the score bars read as modern because they have depth and breathing
     room, and the cells around them had neither. */
  padding: 9px 12px;
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
  font-size: 10px;
  letter-spacing: 0.07em;
  padding-bottom: 7px;
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

/* Phones: tighter padding and smaller type so more columns fit before
   any scrolling is needed. Desktop keeps the roomier sizing above. */
@media (max-width: 900px) {{
  .lc-tbl-wrap table {{ font-size: 11.5px; }}
  .lc-tbl-wrap th, .lc-tbl-wrap td {{ padding: 4px 6px; }}
  .lc-tbl-wrap thead th {{ font-size: 9.5px; }}
}}
</style>
"""


def render_html_table(styler, key: str = ""):
    """Render a pandas Styler as real HTML with a sticky first column.

    Use for SMALL reference tables where the row label matters more than
    sorting. Pass a Styler whose row label is already a real COLUMN, not
    an index — _base_styler calls .hide(axis="index"), so anything left
    in the index is dropped before it ever reaches here.
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

    html = styler.to_html(table_uuid=f"lc{key}") if hasattr(styler, "to_html") else str(styler)
    st.markdown(f'<div class="lc-tbl-wrap">{html}</div>', unsafe_allow_html=True)


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
    fill = COLOR.get(color_key, COLOR["gold"])

    def _fmt(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/A"
        try:
            pct = max(0.0, min(100.0, float(v)))
        except (TypeError, ValueError):
            return "N/A"
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
            f'height:19px; line-height:19px; border-radius:4px; '
            f'background:{COLOR["bg"]}; '
            f'box-shadow:inset 0 0 0 1px {COLOR["stat_mid_dim"]}; '
            f'overflow:hidden;">'
            f'<div style="position:absolute; left:0; top:0; bottom:0; '
            f'width:{pct:.0f}%; border-radius:3px; '
            f'background:linear-gradient(90deg, {fill}44 0%, {fill}8C 100%);'
            f'"></div>'
            f'<div style="position:absolute; top:1px; bottom:1px; '
            f'left:calc({pct:.0f}% - 2px); width:2px; background:{fill}; '
            f'border-radius:1px;"></div>'
            # Number sits on the RIGHT with its own padding. Left-aligned
            # it sat underneath the fill and the leading cap sliced
            # through the digits — a 91 rendered as "9|". Right-aligned it
            # is always clear of the cap except at a full 100, where the
            # cap is at the cell edge anyway.
            f'<span style="position:relative; float:right; font-weight:700; '
            f'padding-right:7px; text-shadow:0 1px 2px {COLOR["bg"]};">'
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
        k = str(v).strip().upper()[:1]
        c = tone.get(k)
        if not c:
            return str(v)
        return (f'<span style="display:inline-block; min-width:17px; '
                f'text-align:center; padding:1px 5px; border-radius:3px; '
                f'background:{c}26; color:{c}; font-weight:700; '
                f'font-size:11px;">{k}</span>')
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
            f'{name}<span style="display:inline-block; margin-left:6px; '
            f'padding:1px 5px; border-radius:3px; background:{COLOR["gold"]}26; '
            f'color:{COLOR["gold"]}; font-size:9.5px; font-weight:800; '
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
                f'style="letter-spacing:2.5px; font-size:13px;">'
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
