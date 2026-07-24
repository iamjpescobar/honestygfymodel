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


def _gradient_fill(t: float, bold: bool = False) -> str:
    """Real colored BACKGROUND fill, not just text color. Text color is
    always dark (BG) — kept flat rather than auto-switching to white,
    per design: every number in a gradient-filled cell reads as dark
    text on the colored fill, consistently across red/amber/cyan."""
    r, g, b = _gradient_rgb(t)
    opacity = 0.35 + 0.40 * t

    weight = 700 if bold else 600
    return (
        f"background-color: rgba({r},{g},{b},{opacity:.2f}); "
        f"color: {BG}; font-weight: {weight}; border-radius: 3px;"
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
    return [f"color: {c}; background-color: {BG}; font-weight: 700;" for _ in col]


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