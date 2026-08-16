"""The weak-spot panel, drawn spatially instead of as a stack of bars.

WHY THE BARS WENT
-----------------
"Where does this pitcher get hurt" is a SPATIAL and RELATIONAL question,
and nineteen horizontal bars flatten both. Up/middle/down is a strike
zone rendered sideways. Pitch types are usage AND damage — two numbers
per pitch, and a bar can only carry one, so the bar carried damage and
threw usage into a subtitle where it stopped being comparable. Times
through the order is a trend across three points, drawn as three
unconnected bars.

Three panels replace all of it:

  ARSENAL QUADRANT   usage on x, damage on y. Position answers the
                     question: top-right is "he throws it a lot AND it
                     gets hit", which is the only quadrant worth acting
                     on. Bubble area is batted balls, so a confident
                     bucket and a thin one look different before you
                     read a number.

  ZONE MAP           up / middle / down, stacked the way a strike zone
                     actually is, shaded by damage.

  ORDER SLOPE        three passes as a line. The SHAPE — usually a
                     decline, sometimes a jump — is the whole story and
                     three separate bars hide it.

THESE ARE SVG STRINGS, not Streamlit widgets, so the panel is one
markdown call instead of ~19 nested column layouts. It also means the
whole thing can be unit-tested without a Streamlit runtime — the old
version could not be.

COLOURS ARE PASSED IN, never hardcoded here. The view owns the theme;
this module owns the geometry. Every threshold comes from
pitcher_weakspots so there is exactly one definition of "damage".
"""
from engines.pitcher_weakspots import XSLG_HOT, XSLG_COLD

# The plot's y-range. Deliberately wider than the thresholds so a bucket
# at either extreme still lands inside the axes rather than on them —
# measured 10th is 0.394 and 90th is 0.675, so this holds the real
# distribution with room to spare.
Y_LO, Y_HI = 0.35, 0.75

_DANGER = "#E24B4A"
_MID = "#BA7517"
_GOOD = "#378ADD"
_DIM = "#6b6a66"


def tone(xslg):
    """One colour rule, shared by every panel. None stays neutral."""
    if xslg is None:
        return _DIM
    if xslg >= XSLG_HOT:
        return _DANGER
    if xslg <= XSLG_COLD:
        return _GOOD
    return _MID


def _y(v):
    v = max(Y_LO, min(Y_HI, v))
    return 250 - (v - Y_LO) / (Y_HI - Y_LO) * 190


def arsenal_svg(pitches, min_usage=3.0):
    """Usage against damage. The panel that replaces six bars.

    A pitch below its sample floor has no damage number, so it cannot be
    plotted — it is listed underneath by name rather than dropped, since
    "he throws a curveball 16% of the time and we cannot rate it" is
    itself worth knowing.
    """
    shown = [p for p in pitches if (p.get("usage") or 0) >= min_usage]
    rated = [p for p in shown if p.get("xslg") is not None]
    unrated = [p for p in shown if p.get("xslg") is None]
    if not rated:
        return ""

    max_u = max(max((p["usage"] for p in rated), default=10), 12)
    max_b = max(max((p.get("bbe") or 1 for p in rated), default=1), 1)

    def _x(u):
        return 92 + (u / max_u) * 300

    out = [
        '<svg width="100%" viewBox="0 0 680 300" role="img">',
        '<title>Pitch usage against damage allowed</title>',
        '<desc>Each bubble is a pitch type: further right is thrown more '
        'often, higher is more damage allowed on contact.</desc>',
        f'<rect x="242" y="60" width="152" height="{_y(XSLG_HOT) - 60:.0f}" '
        f'fill="{_DANGER}" opacity="0.07"/>',
        f'<text x="388" y="76" text-anchor="end" font-size="12" '
        f'fill="{_DANGER}" font-family="inherit">thrown often, gets hit</text>',
        f'<line x1="92" y1="250" x2="410" y2="250" stroke="{_DIM}" stroke-width="0.5"/>',
        f'<line x1="92" y1="55" x2="92" y2="250" stroke="{_DIM}" stroke-width="0.5"/>',
        f'<line x1="92" y1="{_y(XSLG_HOT):.0f}" x2="410" y2="{_y(XSLG_HOT):.0f}" '
        f'stroke="{_DANGER}" stroke-width="0.5" stroke-dasharray="4 4"/>',
        f'<text x="416" y="{_y(XSLG_HOT) + 4:.0f}" font-size="12" '
        f'fill="{_DANGER}" font-family="inherit">{XSLG_HOT:.3f}</text>',
        f'<line x1="92" y1="{_y(XSLG_COLD):.0f}" x2="410" y2="{_y(XSLG_COLD):.0f}" '
        f'stroke="{_GOOD}" stroke-width="0.5" stroke-dasharray="4 4"/>',
        f'<text x="416" y="{_y(XSLG_COLD) + 4:.0f}" font-size="12" '
        f'fill="{_GOOD}" font-family="inherit">{XSLG_COLD:.3f}</text>',
    ]

    for p in sorted(rated, key=lambda q: -(q.get("bbe") or 0)):
        # PLOTTED ON RECENT USAGE, RATED ON SEASON DAMAGE.
        #
        # The x-axis is what he is throwing NOW — a pitch he has dropped
        # since June belongs at the left edge no matter how much he threw
        # it in March. The y-axis stays season, because a damage rate
        # needs 35 batted balls and thirty days will not clear that.
        _u = p.get("usage_recent")
        _u = p["usage"] if _u is None else _u
        cx, cy = _x(_u), _y(p["xslg"])
        r = 7 + ((p.get("bbe") or 1) / max_b) ** 0.5 * 9
        # TOP THREE READ AS THE FOCUS, THE REST STAY VISIBLE. A hollow
        # ring rather than a hidden bubble: a fourth pitch thrown 9% of
        # the time still leaves the yard, and a pitch a pitcher has just
        # ADDED shows up here before it shows up anywhere else on the
        # site.
        _pri = p.get("primary", True)
        out.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" '
                   f'fill="{tone(p["xslg"])}" '
                   f'opacity="{0.78 if _pri else 0.20}" '
                   f'stroke="{tone(p["xslg"])}" stroke-width="1.5" '
                   f'stroke-opacity="{0 if _pri else 0.9}"/>')
        # The drift note only appears when a pitch has actually moved.
        # No threshold is invented here — the number itself is shown and
        # the reader judges it, which is what the site does everywhere a
        # cut point has not been measured.
        _d = p.get("usage_drift")
        _drift = (f'  {_d:+.0f} pts' if _d is not None and abs(_d) >= 1 else '')
        out.append(f'<text x="{cx:.0f}" y="{cy - r - 7:.0f}" text-anchor="middle" '
                   f'font-size="12" fill="currentColor" font-family="inherit" '
                   f'opacity="{1.0 if _pri else 0.65}">'
                   f'{p["name"]} {p["xslg"]:.3f}{_drift}</text>')

    for i, u in enumerate((0, max_u / 2, max_u)):
        out.append(f'<text x="{_x(u):.0f}" y="268" text-anchor="middle" font-size="12" '
                   f'fill="{_DIM}" font-family="inherit">{u:.0f}%</text>')
    out.append(f'<text x="92" y="288" font-size="12" fill="{_DIM}" '
               f'font-family="inherit">usage over the last 30 days '
               f'\u00b7 bubble size = batted balls \u00b7 solid = top 3, '
               f'hollow = the rest \u00b7 \u00b1pts = usage change vs '
               f'his season</text>')
    if unrated:
        names = ", ".join(f'{p["name"].lower()} {p["usage"]:.0f}%' for p in unrated)
        out.append(f'<text x="92" y="{306 if False else 300}" font-size="12" '
                   f'fill="{_DIM}" font-family="inherit">'
                   f'{names} \u2014 below the sample floor</text>')
    out.append("</svg>")
    return "".join(out)


def zone_svg(bands):
    """Up / middle / down, stacked as a strike zone rather than sideways."""
    order = {"Up": 0, "Middle": 1, "Down": 2}
    rows = sorted((b for b in bands if b.get("xslg") is not None),
                  key=lambda b: order.get(b.get("band"), 9))
    if not rows:
        return ""
    out = ['<svg width="100%" viewBox="0 0 680 250" role="img">',
           '<title>Damage allowed by zone band</title>',
           '<desc>The strike zone in three horizontal bands, each shaded by '
           'how much damage the pitcher allows there.</desc>']
    for i, b in enumerate(rows):
        y = 20 + i * 74
        c = tone(b["xslg"])
        out.append(f'<rect x="200" y="{y}" width="280" height="66" rx="6" '
                   f'fill="{c}" opacity="0.55"/>')
        out.append(f'<text x="340" y="{y + 30}" text-anchor="middle" font-size="14" '
                   f'font-weight="500" fill="#0d0d0c" font-family="inherit">'
                   f'{b["band"].lower()}</text>')
        out.append(f'<text x="340" y="{y + 50}" text-anchor="middle" font-size="12" '
                   f'fill="#0d0d0c" font-family="inherit">'
                   f'{b["xslg"]:.3f} \u00b7 {b.get("bbe", 0)} bbe</text>')
    out.append("</svg>")
    return "".join(out)


def tto_svg(tto):
    """Three passes as a line, because the SHAPE is the finding."""
    rows = [t for t in tto if t.get("xslg") is not None]
    if len(rows) < 2:
        return ""
    lo = min(t["xslg"] for t in rows) - 0.03
    hi = max(t["xslg"] for t in rows) + 0.03
    span = max(hi - lo, 0.01)

    def py(v):
        return 130 - (v - lo) / span * 80

    xs = [120 + i * 130 for i in range(len(rows))]
    pts = " ".join(f'{x},{py(t["xslg"]):.0f}' for x, t in zip(xs, rows))
    out = ['<svg width="100%" viewBox="0 0 680 190" role="img">',
           '<title>Damage allowed by times through the order</title>',
           '<desc>A line across the first, second and third time through '
           'a lineup showing whether the pitcher declines.</desc>',
           f'<line x1="100" y1="150" x2="{xs[-1] + 40}" y2="150" '
           f'stroke="{_DIM}" stroke-width="0.5"/>',
           f'<polyline points="{pts}" fill="none" stroke="{_DANGER}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>']
    for x, t in zip(xs, rows):
        out.append(f'<circle cx="{x}" cy="{py(t["xslg"]):.0f}" r="5" '
                   f'fill="{tone(t["xslg"])}"/>')
        out.append(f'<text x="{x}" y="{py(t["xslg"]) - 14:.0f}" text-anchor="middle" '
                   f'font-size="12" fill="currentColor" font-family="inherit">'
                   f'{t["xslg"]:.3f}</text>')
        _p = t["pass"]
        _suf = "st" if _p == 1 else "nd" if _p == 2 else "rd"
        out.append(f'<text x="{x}" y="170" text-anchor="middle" font-size="12" '
                   f'fill="{_DIM}" font-family="inherit">{_p}{_suf}</text>')
    out.append("</svg>")
    return "".join(out)


def slot_rows(slots, lineup=None, top_n=None):
    """Slots SORTED BY LEAK, joined to tonight's hitters where known.

    THIS IS THE ORDERING THAT MAKES THE PANEL WORTH READING. Nine slots
    listed 1 through 9 is a roster printout — the reader has to scan all
    nine and hold them in their head. Sorted by damage, the top rows ARE
    the answer.

    A slot line partly reflects WHICH HITTERS batted there across his
    starts, not the pitcher's own skill, and that caveat is real. But it
    stops mattering the moment the slot is joined to tonight's lineup:
    the claim is no longer "he is bad at slot 4", it is "the soft spots
    in this order line up with these bats tonight", which is true
    whatever causes the softness.

    `lineup` is a list in batting order; index + 1 is the slot.
    Returns [(slot, xslg, bbe, hitter_or_None)] with unmeasured slots
    dropped entirely rather than rendered as empty tracks.
    """
    by_slot = {}
    if lineup:
        for i, b in enumerate(lineup[:9], start=1):
            by_slot[i] = b
    rows = [(s["slot"], s["xslg"], s.get("bbe"), by_slot.get(s["slot"]))
            for s in slots if s.get("xslg") is not None]
    rows.sort(key=lambda r: -r[1])
    return rows[:top_n] if top_n else rows
