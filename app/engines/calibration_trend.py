"""Calibration over time — is a board's edge real, or drifting?

The Calibration page reports a single cumulative rate: "36/58 = 62.1%".
That one number hides everything that matters about direction. A board
that opened at 70% and has been sliding for a week reads identically to
one that has sat flat at 62% the whole time, and those are completely
different situations for someone deciding what to bet tonight.

This draws the running rate against the measured league baseline, so the
question "is this board actually beating chance" becomes something you
can see rather than infer from a table.

Deliberately plots the CUMULATIVE rate, not each day's rate in
isolation. A single day is 5 or 13 picks — far too few to mean anything,
and a day-by-day line would swing wildly and invite exactly the
over-reading this whole calibration system exists to prevent.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR


def render_calibration_trend(days: dict, baseline=None, label: str = ""):
    """Cumulative hit rate over time for one board, vs its baseline.

    `days` is the per-date record: {date: {"picks": [...]}}. Draws
    nothing at all when there are fewer than three graded days, because a
    two-point line implies a trend that isn't there.
    """
    import altair as alt

    rows = []
    hits = total = 0
    for date in sorted(days.keys()):
        picks = days[date].get("picks", []) or []
        d_hit = sum(1 for p in picks if p.get("result") == "hit")
        d_miss = sum(1 for p in picks if p.get("result") == "miss")
        if d_hit + d_miss == 0:
            continue          # ungraded or all-DNP day: nothing to plot
        hits += d_hit
        total += d_hit + d_miss
        rows.append({
            "Date": date,
            "Rate": round(hits / total * 100, 1),
            "Picks": total,
            "Day": f"{d_hit}/{d_hit + d_miss}",
        })

    if len(rows) < 3:
        st.caption(
            f"Trend needs at least three graded days — {len(rows)} so far. "
            f"A two-point line would imply a direction the data doesn't "
            f"support."
        )
        return

    df = pd.DataFrame(rows)

    line = alt.Chart(df).mark_line(
        point=alt.OverlayMarkDef(size=45, filled=True),
        strokeWidth=2.5, color=COLOR["stat_high"],
    ).encode(
        x=alt.X("Date:N", axis=alt.Axis(labelAngle=-45, title=None)),
        y=alt.Y("Rate:Q",
                axis=alt.Axis(title="cumulative hit rate %"),
                scale=alt.Scale(zero=False, nice=True)),
        tooltip=["Date", "Rate", "Picks", "Day"],
    )

    layers = [line]
    if baseline is not None:
        # The baseline is the whole point of the chart. Without it the
        # line is just a number moving around; with it, every point above
        # the rule is the board adding something and every point below is
        # it subtracting.
        rule = alt.Chart(pd.DataFrame({"b": [float(baseline)]})).mark_rule(
            strokeDash=[6, 4], strokeWidth=1.5, color=COLOR["warn"],
        ).encode(y="b:Q")
        layers.append(rule)

    st.altair_chart(
        alt.layer(*layers).properties(height=220).configure_view(strokeWidth=0),
        use_container_width=True,
    )
    if baseline is not None:
        st.caption(
            f"Solid line: this board's cumulative hit rate. Dashed line: the "
            f"measured league baseline ({float(baseline):.1f}%). Above the "
            f"dash is the board adding something; below it, it isn't. "
            f"Cumulative on purpose — a single day is too few picks to read."
        )
