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
   cyan (good). Text color auto-switches to dark when a fill gets
   bright enough to need it, same as any real dashboard would do —
   this is the "polished and professional" version, not colored text
   on black.
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


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG relative luminance, with proper sRGB gamma correction —
    not a rough weighted average, which gets bright cyan specifically
    wrong (its zero red channel drags the simple formula way down even
    though cyan reads as very bright to the eye)."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast_ratio(rgb1, rgb2) -> float:
    l1, l2 = _relative_luminance(*rgb1), _relative_luminance(*rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


_BG_RGB = tuple(int(BG.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
_TEXT_RGB = tuple(int(COLOR["text"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def _gradient_fill(t: float, bold: bool = False) -> str:
    """Real colored BACKGROUND fill, not just text color. Text color
    picks whichever of off-white/dark gives the higher real WCAG
    contrast ratio against the ACTUAL blended background (fill color
    mixed with the table's black at this opacity) — verified against
    real measured contrast ratios, not a rough brightness guess (a
    simple weighted-average heuristic gets saturated cyan specifically
    wrong, since its zero red channel drags the average down even
    though it reads as very bright)."""
    r, g, b = _gradient_rgb(t)
    opacity = 0.35 + 0.40 * t

    blended = tuple(round(c * opacity + bg_c * (1 - opacity)) for c, bg_c in zip((r, g, b), _BG_RGB))
    contrast_light = _contrast_ratio(blended, _TEXT_RGB)
    contrast_dark = _contrast_ratio(blended, _BG_RGB)
    text_color = COLOR["text"] if contrast_light >= contrast_dark else BG

    weight = 700 if bold else 600
    return (
        f"background-color: rgba({r},{g},{b},{opacity:.2f}); "
        f"color: {text_color}; font-weight: {weight}; border-radius: 3px;"
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
    distinct identity color, not a magnitude scale."""
    styles = []
    for v in col:
        c = _BATS_COLORS.get(str(v).strip().upper())
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
    colors render correctly using this exact method)."""
    base = df.style.set_properties(**{
        "font-family": "'JetBrains Mono', monospace",
        "font-size": "13.5px",
        "background-color": BG,
        "color": COLOR["text"],
    }).format(precision=2)

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
                BACKGROUND fill with auto-contrast text.
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
