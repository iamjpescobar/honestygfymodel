"""
Weather icons — inline SVG for the weather strip and Weather Board.

Drawn rather than emoji for two reasons: emoji glyphs render very
differently across operating systems (and several look dated on
desktop), and drawn icons can encode the actual DATA — the wind arrow
points where the ball will be pushed, the thermometer fills to the
real temperature, the park gauge fills toward hitter- or
pitcher-friendly.

Shared by the Game Card and the Weather Board so both pages stay
identical; changing an icon here changes it everywhere.

All functions take display strings (the same ones already rendered on
the page) and degrade to a neutral grey icon when a value is missing
or unparseable, rather than inventing a reading.
"""
import math
import re

from styles.kc_theme import COLOR

# Icon strokes read from the palette like everything else, so a
# theme change moves them too instead of leaving them behind.
_GREY = COLOR["text_muted"]
_COLD = COLOR["cold"]

# Compass bearing -> map angle (0 = up/North, clockwise). Used only for the
# forecast-pending state: when MLB hasn't posted official field-relative wind
# yet, the NWS forecast gives a compass direction (marked with *). We show it
# as a dashed COMPASS rose (map-style, N=up) rather than a field arrow, because
# a bearing can't honestly be mapped to "out to CF / in from LF" without the
# park's orientation.
_COMPASS = {
    "n": 0, "nne": 22.5, "ne": 45, "ene": 67.5, "e": 90, "ese": 112.5,
    "se": 135, "sse": 157.5, "s": 180, "ssw": 202.5, "sw": 225, "wsw": 247.5,
    "w": 270, "wnw": 292.5, "nw": 315, "nnw": 337.5,
}


def weather_icon(condition: str) -> str:
    """Inline SVG for the sky condition — drawn rather than emoji so
    it matches the app's palette and renders identically on every
    platform (emoji glyphs differ wildly between OSes)."""
    c = (condition or "").lower()
    gold, blue, grey = COLOR["gold"], COLOR["stat_high"], _GREY
    if "dome" in c or "roof" in c:
        return (
            '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
            f'<path d="M3 13a9 9 0 0 1 18 0" stroke="{blue}" stroke-width="1.8" '
            'stroke-linecap="round"/>'
            f'<rect x="3" y="13" width="18" height="7" rx="1.5" stroke="{grey}" '
            'stroke-width="1.5"/>'
            f'<path d="M7 20v-4M12 20v-5M17 20v-4" stroke="{grey}" stroke-width="1.2"/>'
            '</svg>'
        )
    if "storm" in c or "thunder" in c:
        return (
            '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
            f'<path d="M7 15a4 4 0 0 1 .6-8 5.5 5.5 0 0 1 10.3 1.6A3.5 3.5 0 0 1 17.5 15z" '
            f'fill="{grey}" opacity="0.35" stroke="{grey}" stroke-width="1.3"/>'
            f'<path d="M13 14l-3 4.5h2.6L11.4 22 15 17h-2.4z" fill="{gold}">'
            '<animate attributeName="opacity" values="1;0.25;1" dur="1.4s" '
            'repeatCount="indefinite"/></path></svg>'
        )
    if "rain" in c or "shower" in c:
        drops = "".join(
            f'<line x1="{x}" y1="16.5" x2="{x - 1.5}" y2="21" stroke="{blue}" '
            f'stroke-width="1.6" stroke-linecap="round">'
            f'<animate attributeName="opacity" values="0;1;0" dur="1.3s" '
            f'begin="{i * 0.28}s" repeatCount="indefinite"/></line>'
            for i, x in enumerate((9.5, 13, 16.5))
        )
        return (
            '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
            f'<path d="M7 15a4 4 0 0 1 .6-8 5.5 5.5 0 0 1 10.3 1.6A3.5 3.5 0 0 1 17.5 15z" '
            f'fill="{grey}" opacity="0.3" stroke="{grey}" stroke-width="1.3"/>'
            f'{drops}</svg>'
        )
    if "cloud" in c or "overcast" in c:
        return (
            '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
            f'<path d="M7 17a4 4 0 0 1 .6-8 5.5 5.5 0 0 1 10.3 1.6A3.5 3.5 0 0 1 17.5 17z" '
            f'fill="{grey}" opacity="0.3" stroke="{grey}" stroke-width="1.4"/></svg>'
        )
    if "clear" in c or "sunny" in c or "fair" in c:
        rays = "".join(
            f'<line x1="12" y1="2.5" x2="12" y2="5" stroke="{gold}" stroke-width="1.6" '
            f'stroke-linecap="round" transform="rotate({a} 12 12)"/>'
            for a in range(0, 360, 45)
        )
        return (
            '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
            f'<circle cx="12" cy="12" r="4.6" fill="{gold}" opacity="0.9">'
            '<animate attributeName="opacity" values="0.75;1;0.75" dur="3s" '
            'repeatCount="indefinite"/></circle>'
            f'{rays}</svg>'
        )
    # partly cloudy / unknown
    return (
        '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
        f'<circle cx="9" cy="9" r="3.4" fill="{gold}" opacity="0.85"/>'
        f'<path d="M9 18a3.4 3.4 0 0 1 .5-6.8 4.7 4.7 0 0 1 8.8 1.4A3 3 0 0 1 17.8 18z" '
        f'fill="{grey}" opacity="0.32" stroke="{grey}" stroke-width="1.3"/></svg>'
    )

def wind_arrow(wind_str: str) -> str:
    """An arrow that actually points where the ball will be pushed.

    MLB's field-relative wind string ("12 mph, Out To CF") is the
    only source that can say where the ball will be pushed — a compass
    forecast like "SW 12 mph" cannot be mapped to the field without
    knowing the park's orientation. So there are three states:

      - FIELD ARROW  — official field-relative wind posted: a solid,
        colored arrow pointing where the ball goes (gold = out/helps,
        red = in/kills, blue = crosswind).
      - COMPASS ROSE — only a forecast bearing so far (string ends in
        *): a faint DASHED arrow pointing in the real-world compass
        direction (map-style, N = up), so you can see the wind exists
        and roughly where it's from without implying a field impact
        we can't know yet.
      - SWIRL        — dome, calm (0 mph), or nothing posted: a neutral
        grey swirl.

    Angles for the field arrow are from the batter's point of view:
    up = out to center, down = blowing in, left/right = crosswind.
    Speed drives the animation, so a 20 mph wind pulses faster than a
    6 mph breeze.
    """
    w = (wind_str or "").lower()
    is_forecast = "*" in (wind_str or "")

    m = re.search(r"(\d+)\s*mph", w)
    mph = int(m.group(1)) if m else 0

    angle = None
    if "out to cf" in w or "out to center" in w:
        angle = 0
    elif "out to lf" in w or "out to left" in w:
        angle = -38
    elif "out to rf" in w or "out to right" in w:
        angle = 38
    elif "in from cf" in w or "in from center" in w:
        angle = 180
    elif "in from lf" in w or "in from left" in w:
        angle = 142
    elif "in from rf" in w or "in from right" in w:
        angle = -142
    elif "l to r" in w:
        angle = 90
    elif "r to l" in w:
        angle = -90

    # ---- FORECAST-PENDING: compass bearing, no field mapping yet ----
    # Only when we have a real speed and a parseable bearing, and MLB
    # hasn't given us a field-relative string (angle is None). A dashed
    # compass rose, deliberately NOT rotated to the field.
    if angle is None and is_forecast and mph > 0:
        cm = re.match(r"\s*([nsew]{1,3})\b", w)
        cangle = _COMPASS.get(cm.group(1)) if cm else None
        if cangle is not None:
            dur = max(1.1, 2.8 - min(mph, 22) * 0.06)
            return (
                f'<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
                f'<circle cx="12" cy="12" r="9.2" stroke="{_GREY}" '
                f'stroke-width="0.8" opacity="0.28" stroke-dasharray="1.5 2"/>'
                f'<g transform="rotate({cangle} 12 12)">'
                f'<line x1="12" y1="18.5" x2="12" y2="6.5" stroke="{_GREY}" '
                f'stroke-width="1.8" stroke-linecap="round" '
                f'stroke-dasharray="2.2 2" opacity="0.8">'
                f'<animate attributeName="opacity" values="0.4;0.85;0.4" '
                f'dur="{dur}s" repeatCount="indefinite"/></line>'
                f'<path d="M12 4l3.4 4H8.6z" fill="{_GREY}" opacity="0.8"/>'
                f'</g></svg>'
            )

    if angle is None or mph <= 0:
        # honest neutral state: dome, calm, or nothing posted
        return (
            '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
            f'<path d="M4 9h11a2.5 2.5 0 1 0-2.5-2.5" stroke="{_GREY}" '
            'stroke-width="1.6" stroke-linecap="round"/>'
            f'<path d="M4 14h8a2 2 0 1 1-2 2" stroke="{_GREY}" '
            'stroke-width="1.6" stroke-linecap="round" opacity="0.75"/></svg>'
        )

    # out = helps the ball (gold), in = kills it (red), cross = neutral
    if abs(angle) <= 45:
        col = COLOR["gold"]
    elif abs(angle) >= 135:
        col = COLOR["error"]
    else:
        col = COLOR["stat_high"]
    dur = max(0.9, 2.6 - min(mph, 22) * 0.075)

    return (
        f'<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
        f'<g transform="rotate({angle} 12 12)">'
        f'<line x1="12" y1="19" x2="12" y2="7" stroke="{col}" stroke-width="2.2" '
        f'stroke-linecap="round">'
        f'<animate attributeName="opacity" values="0.55;1;0.55" dur="{dur}s" '
        f'repeatCount="indefinite"/></line>'
        f'<path d="M12 4.5l4.2 5H7.8z" fill="{col}">'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0 1.6; 0 -1.2; 0 1.6" dur="{dur}s" repeatCount="indefinite"/></path>'
        f'</g></svg>'
    )

def temp_icon(temp_text: str) -> str:
    """A thermometer whose mercury level and colour track the real
    temperature — cold blue through hot red. Reads at a glance,
    which a static emoji never did."""
    try:
        t = float(str(temp_text).replace("*", "").replace("\u00b0", "").strip())
    except (TypeError, ValueError):
        t = None
    if t is None:
        fill_h, col = 0.0, _GREY
    else:
        # 40F..100F mapped onto the tube
        frac = max(0.0, min(1.0, (t - 40.0) / 60.0))
        fill_h = 8.5 * frac
        col = (COLOR["error"] if t >= 85 else
               COLOR["gold"] if t >= 70 else
               COLOR["stat_high"] if t >= 55 else _COLD)
    return (
        '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
        f'<rect x="10" y="3.5" width="4" height="12" rx="2" stroke="{_GREY}" '
        'stroke-width="1.4"/>'
        f'<circle cx="12" cy="18" r="3.4" fill="{col}"/>'
        f'<rect x="11.2" y="{15.5 - fill_h:.1f}" width="1.6" height="{fill_h:.1f}" '
        f'rx="0.8" fill="{col}"/>'
        '</svg>'
    )

def park_icon(pf_text: str) -> str:
    """A gauge for park factor: the arc fills toward gold above 100
    (hitter-friendly) and blue below (pitcher-friendly), so the
    number has visual meaning instead of sitting next to a generic
    stadium glyph."""
    try:
        pf = float(str(pf_text).strip())
    except (TypeError, ValueError):
        pf = None
    if pf is None:
        col, frac = _GREY, 0.5
    else:
        frac = max(0.0, min(1.0, (pf - 88.0) / 24.0))   # 88..112
        col = (COLOR["gold"] if pf >= 104 else
               COLOR["error"] if pf <= 96 else COLOR["stat_high"])
    # semicircle arc, r=8, from 180deg to 0deg
    
    ang = math.pi * (1 - frac)
    x = 12 + 8 * math.cos(ang)
    y = 16 - 8 * math.sin(ang)
    return (
        '<svg width="30" height="30" viewBox="0 0 24 24" fill="none">'
        f'<path d="M4 16a8 8 0 0 1 16 0" stroke="{_GREY}" stroke-width="1.6" '
        'stroke-linecap="round" opacity="0.35"/>'
        f'<path d="M4 16a8 8 0 0 1 {x - 4:.2f} {y - 16:.2f}" stroke="{col}" '
        f'stroke-width="2.2" stroke-linecap="round" fill="none"/>'
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2" fill="{col}"/>'
        '</svg>'
    )
