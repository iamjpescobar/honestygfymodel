"""
Shared trend chart — the one bar chart used by every game-by-game
trend on the site (MLB batter trends, WNBA player trends).

Design goals, straight from use:
- The NUMBER is printed on every bar — no squinting at axis lines.
- Bars are teal when the game cleared the line (v > line, so a 0.5
  line means "got at least 1"), muted red when it didn't — read the
  colors, not the heights.
- A dashed rule marks the line itself.
- A chip row above the chart answers "how many times did he clear it"
  per window (e.g. L25: 18/25 · 72%) so nobody ever counts bars again.

Pure rendering + arithmetic on values handed in — no data fetching
here; the callers own their sources and their honesty labels.
"""
import pandas as pd

# Pulled from the table tiers so chart and table never drift apart. If
# the tier palette changes, these follow automatically.
try:
    from styles.table_style import _TIERS as _TBL_TIERS
    _TIER_MISSED = _TBL_TIERS[0][1]    # poor
    _TIER_CLEARED = _TBL_TIERS[-1][1]  # elite
except Exception:      # styling import failing must never break a chart
    # LITERALS ON PURPOSE - do not "fix" these into COLOR lookups.
    #
    # This branch runs precisely when importing from styles/ has failed.
    # Reaching back into styles.kc_theme for COLOR here would be the one
    # thing guaranteed not to work, and would turn a chart that renders
    # in fallback colours into a NameError. They mirror COLOR["error"]
    # and COLOR["stat_high"]; if the palette moves, update them by hand.
    _TIER_MISSED, _TIER_CLEARED = "#D6304A", "#3BB8FF"

import streamlit as st

from styles.kc_theme import COLOR

WINDOW_N = {"Season": None, "L25": 25, "L15": 15, "L10": 10, "L5": 5}


def window_hit_chips(values, line: float, active_label: str,
                     windows=("Season", "L25", "L10", "L5")) -> None:
    """Chip per window: cleared/total and percent, computed over the
    FULL chronological value list handed in. Color: teal >= 60%, gold
    45-59%, red below — same scale everywhere so chips read instantly.
    The active window gets a teal outline."""
    cells = []
    for lbl in windows:
        n = WINDOW_N.get(lbl)
        sub = values if n is None else values[-n:]
        if not sub:
            continue
        hit = sum(1 for v in sub if v is not None and v > line)
        total = len(sub)
        pct = hit / total * 100
        col = COLOR["stat_high"] if pct >= 60 else (COLOR["warn"] if pct >= 45 else COLOR["error"])
        border = (f'border:1px solid {COLOR["stat_high"]};' if lbl == active_label
                  else "border:1px solid transparent;")
        cells.append(
            f'<div style="flex:1; text-align:center; padding:var(--lc-space-md) var(--lc-space-sm); border-radius:var(--lc-radius-lg); '
            f'background:{col}18; {border}">'
            f'<div style="font-size:var(--lc-text-tiny); letter-spacing:0.06em; color:{COLOR["text"]}; '
            f'opacity:0.65; text-transform:uppercase;">{lbl}</div>'
            f'<div style="font-size:var(--lc-text-body-lg); font-weight:800; color:{col};">{hit}/{total}</div>'
            f'<div style="font-size:var(--lc-text-tiny); color:{col};">{pct:.0f}%</div>'
            f'</div>'
        )
    if cells:
        st.markdown(
            f'<div style="display:flex; gap:8px; margin:var(--lc-space-sm) var(--lc-space-none) var(--lc-space-md) var(--lc-space-none);">{"".join(cells)}</div>',
            unsafe_allow_html=True,
        )


def render_trend_bars(labels, values, stat_label: str, line: float,
                      logos=None) -> None:
    """Labeled bar chart for one window's games, oldest to newest.
    logos: optional list of image URLs (or None per game), same length
    as labels — rendered as a row of opponent logos under the bars so
    the x-axis stays short (dates only)."""
    import altair as alt

    df = pd.DataFrame({"Game": labels, "v": [0 if v is None else v for v in values]})
    df["cleared"] = df["v"] > line
    order = list(df["Game"])
    has_logos = bool(logos) and len(logos) == len(labels) and any(logos)
    ymax = max([v for v in df["v"]] + [line]) * 1.18 or 1
    ypad = ymax * 0.11 if has_logos else 0

    base = alt.Chart(df).encode(
        x=alt.X("Game:N", sort=order, axis=alt.Axis(labelAngle=-45, title=None)),
    )
    _yscale = alt.Scale(domain=[-ypad, ymax]) if has_logos else alt.Undefined
    _yaxis = alt.Axis(tickMinStep=1, values=list(range(0, int(ymax) + 1))) if has_logos else alt.Axis(tickMinStep=1)
    # Same treatment as the score bars in the tables: a gradient along the
    # bar and a bright cap at its end, rather than a flat block of colour.
    #
    # Built as TWO LAYERS because a gradient is a mark-level property in
    # Vega-Lite while cleared/missed is per-datum — one alt.condition
    # cannot carry two different gradients. Each layer filters to its own
    # outcome and paints its own fill.
    def _grad(hex_colour):
        """Vertical gradient, faint at the base to solid at the top —
        matching the score bars, where the fill deepens toward the value."""
        return alt.Gradient(
            gradient="linear", x1=0, x2=0, y1=1, y2=0,
            # Two DIFFERENT stops. Both were the same colour on the first
            # pass, which is a flat fill wearing a gradient's name. Faint
            # at the base, solid at the top, so the bar deepens toward its
            # value exactly like the score bars do.
            stops=[alt.GradientStop(color=COLOR["bg"], offset=0),
                   alt.GradientStop(color=hex_colour, offset=1)],
        )

    def _bar_layer(cleared: bool, hex_colour: str, opacity: float):
        return (
            # Explicit == comparison rather than `~alt.datum.cleared`.
            # Negating a datum reference with ~ is easy to get subtly
            # wrong, and a filter that silently matches nothing renders an
            # empty layer with no error to explain it.
            base.transform_filter(
                alt.datum.cleared == (True if cleared else False))
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                      color=_grad(hex_colour), opacity=opacity,
                      # The bright cap: a stroke on the top edge only,
                      # which is the cue that makes a value readable
                      # without reading the number.
                      stroke=hex_colour, strokeWidth=2)
            .encode(
                y=alt.Y("v:Q", title=stat_label, axis=_yaxis, scale=_yscale),
                tooltip=[alt.Tooltip("Game:N"),
                         alt.Tooltip("v:Q", title=stat_label)],
            )
        )

    # Tier colours, so the chart speaks the same language as the tables:
    # cleared the line -> "elite" cyan, missed it -> "poor" red. The old
    # miss colour was a one-off maroon appearing nowhere else on the site.
    bars = alt.layer(
        _bar_layer(True, _TIER_CLEARED, 0.85),
        _bar_layer(False, _TIER_MISSED, 0.75),
    )
    text = base.mark_text(dy=-8, fontWeight="bold", fontSize=12,
                          color=COLOR["text"]).encode(
        y=alt.Y("v:Q"),
        text=alt.Text("v:Q", format=".0f"),
    )
    rule = alt.Chart(pd.DataFrame({"y": [line]})).mark_rule(
        strokeDash=[5, 4], color=COLOR["text"], opacity=0.6
    ).encode(y="y:Q")

    layers = [bars, text, rule]
    if has_logos:
        ldf = pd.DataFrame({"Game": labels,
                            "url": [u or "" for u in logos],
                            "ly": [-ypad * 0.55] * len(labels)})
        ldf = ldf[ldf["url"] != ""]
        if not ldf.empty:
            layers.append(
                alt.Chart(ldf).mark_image(width=16, height=16).encode(
                    x=alt.X("Game:N", sort=order),
                    y=alt.Y("ly:Q"),
                    url="url:N",
                )
            )
    st.altair_chart(
        alt.layer(*layers).properties(height=250).configure_view(strokeOpacity=0),
        use_container_width=True,
    )
