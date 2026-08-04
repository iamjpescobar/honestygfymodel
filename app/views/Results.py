"""
Results — this site's own track record, for subscribers.

The Calibration page has always had this data. It was admin-only,
because it was built as a diagnostic: raw records, storage paths, the
odds-entry form. But the NUMBERS in it are the single most important
thing a paying subscriber can see, and hiding them meant the only
evidence anywhere on the site was a one-line caption at the bottom of
four boards.

So this is Calibration's data with the diagnostics stripped out: what
each board picked, what actually happened, and how that compares to
the rate you would get without a model. Nothing here is generated for
this page — every figure comes from engines.calibration.summary(),
which reads the record the nightly pipeline publishes.

WHAT THIS PAGE DELIBERATELY DOES NOT DO

  - No blended "overall hit rate". HR Edge is graded on home runs
    (~14% league rate) and Daily 13 on hits (~65%). Averaging those
    into one percentage produces a number that describes nothing and
    moves whenever the slate mix changes. Boards are reported
    separately, and the only cross-board summary is a count of how
    many are beating their own baseline.

  - No grading trigger, no storage path, no raw JSON, no odds entry.
    Those are admin tools and they stay on the Calibration page. This
    page only reads, which also keeps it fast — it makes no network
    calls at all.

  - No profit figures until prices exist. summary() excludes unpriced
    picks from profit rather than assuming even money, so the profit
    block stays as an em dash while priced == 0. When odds start being
    attached it fills in on its own, with no change needed here.

The body is a function rather than top-level statements so the
empty-record case can return early. Views here are exec'd by app.py's
load_page_module inside a try/except Exception, and Streamlit's
StopException subclasses Exception — so a bare st.stop() risks being
caught and rendered as "something went wrong loading this page"
instead of ending the page cleanly.
"""
import streamlit as st

from styles.kc_theme import page_header, card, footer, data_timestamp, COLOR
from engines.calibration import summary, BOARDS, _load
from engines.calibration_trend import render_calibration_trend

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called in each view as
# well, so the same ~26KB of inline CSS was serialised, shipped and
# parsed TWICE on every rerun of every page.


# ---------------------------------------------------------------
# Verdict colour. _edge_verdict returns plain-language strings, not
# codes, so match on the phrase it actually produces. Anything
# unrecognised falls through to muted rather than being coloured as
# good or bad — a verdict we cannot classify must not be dressed up.
# ---------------------------------------------------------------
def _verdict_color(verdict: str) -> str:
    v = (verdict or "").lower()
    if "beating" in v:
        return COLOR["stat_high"]
    if "below" in v:
        return COLOR["error"]
    if "no measurable edge" in v:
        return COLOR["warn"]
    return COLOR["text_muted"]


def _chip(text: str, color: str) -> str:
    return (f'<span style="display:inline-block; padding:var(--lc-space-hair) var(--lc-space-md); '
            f'border-radius:var(--lc-radius-sm); background:{color}22; color:{color}; '
            f'font-size:var(--lc-text-tiny); font-weight:700; letter-spacing:0.04em; '
            f'font-family:\'JetBrains Mono\',monospace;">{text}</span>')


def _tile(label: str, value: str, sub: str = "", color: str = None) -> str:
    color = color or COLOR["text"]
    sub_html = ""
    if sub:
        sub_html = (f'<div style="font-size:var(--lc-text-tiny); '
                    f'color:{COLOR["text_faint"]}; '
                    f'margin-top:var(--lc-space-hair);">{sub}</div>')
    return (f'<div style="background:{COLOR["surface"]}; border-radius:var(--lc-radius-lg); '
            f'padding:var(--lc-space-lg) var(--lc-space-xl);">'
            f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]}; '
            f'letter-spacing:0.06em; text-transform:uppercase;">{label}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace; '
            f'font-size:var(--lc-text-stat); color:{color}; '
            f'margin-top:var(--lc-space-xs);">{value}</div>'
            f'{sub_html}</div>')


def _section_tag(text: str) -> str:
    return (f'<div style="display:inline-block; '
            f'padding:var(--lc-space-hair) var(--lc-space-md); '
            f'border-radius:var(--lc-radius-sm); background:{COLOR["gold"]}22; '
            f'border:1px solid {COLOR["gold"]}55; color:{COLOR["gold"]}; '
            f'font-size:var(--lc-text-tiny); font-weight:700; '
            f'text-transform:uppercase; letter-spacing:0.05em; '
            f'margin:var(--lc-space-2xl) var(--lc-space-none) '
            f'var(--lc-space-lg) var(--lc-space-none);">{text}</div>')


def _render_board(board, cfg, s, days):
    """One board's card. `s` is that board's summary() entry."""
    label = cfg.get("label", board)
    question = cfg.get("question", "")

    if not s.get("total"):
        # A published board with no record yet is information a
        # subscriber is entitled to, so it is listed rather than hidden.
        st.markdown(
            f'<div style="display:flex; align-items:baseline; '
            f'gap:var(--lc-space-md); flex-wrap:wrap;">'
            f'<span style="font-size:var(--lc-text-subhead); font-weight:700; '
            f'color:{COLOR["player_name"]};">{label}</span>'
            f'<span style="font-size:var(--lc-text-small); '
            f'color:{COLOR["text_muted"]};">{question}</span></div>'
            f'<div style="font-size:var(--lc-text-caption); '
            f'color:{COLOR["text_faint"]}; margin-top:var(--lc-space-sm);">'
            f'No graded picks yet \u2014 {len(days)} day(s) logged, '
            f'awaiting results.</div>',
            unsafe_allow_html=True,
        )
        return

    rate = s.get("rate")
    base = s.get("baseline")
    edge = s.get("edge")
    profit = s.get("profit", {}) or {}

    # Bar colour follows the honest read, not the raw rate: a board
    # under its baseline is red even at 67%, and one above it is blue
    # even at 22%. The percentage on its own is exactly the thing this
    # page exists to stop people misreading.
    if edge is not None and edge > 0:
        bar = COLOR["stat_high"]
    elif edge is not None and edge < 0:
        bar = COLOR["error"]
    else:
        bar = COLOR["text_faint"]

    if edge is not None:
        edge_html = (f'<span style="font-size:var(--lc-text-body); color:{bar};">'
                     f'{edge:+.1f} vs {base:.1f}</span>')
    else:
        edge_html = (f'<span style="font-size:var(--lc-text-body); '
                     f'color:{COLOR["text_muted"]};">no baseline</span>')

    units_html = ""
    if profit.get("priced"):
        u = profit["units"]
        uc = (COLOR["accent"] if u > 0
              else COLOR["error"] if u < 0
              else COLOR["text_muted"])
        units_html = (f'<span style="font-size:var(--lc-text-body); color:{uc};">'
                      f'{u:+.2f}u</span>')

    st.markdown(
        f'<div style="display:flex; align-items:baseline; '
        f'justify-content:space-between; gap:var(--lc-space-lg); flex-wrap:wrap;">'
        f'<div><span style="font-size:var(--lc-text-subhead); font-weight:700; '
        f'color:{COLOR["player_name"]};">{label}</span>'
        f'<span style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]}; '
        f'margin-left:var(--lc-space-md);">{question}</span></div>'
        f'<div style="display:flex; align-items:baseline; gap:var(--lc-space-xl); '
        f'font-family:\'JetBrains Mono\',monospace;">'
        f'<span style="font-size:var(--lc-text-stat); color:{COLOR["text"]};">'
        f'{rate:.1f}%</span>{edge_html}{units_html}</div></div>',
        unsafe_allow_html=True,
    )

    # Bar with the baseline tick. Fixed 0-100 scale so boards stay
    # visually comparable, and so a 22% home-run rate LOOKS like 22%
    # rather than being stretched to fill the track.
    tick = ""
    if base is not None:
        tick = (f'<div style="position:absolute; left:{min(max(base, 0), 100):.1f}%; '
                f'top:-3px; width:2px; height:12px; '
                f'background:{COLOR["text_muted"]};"></div>')
    st.markdown(
        f'<div style="position:relative; height:6px; background:{COLOR["bg"]}; '
        f'border-radius:var(--lc-radius-sm); margin-top:var(--lc-space-lg);">'
        f'<div style="position:absolute; left:0; top:0; height:6px; '
        f'width:{min(max(rate, 0), 100):.1f}%; background:{bar}; '
        f'border-radius:var(--lc-radius-sm);"></div>{tick}</div>',
        unsafe_allow_html=True,
    )

    # Which markets this board's record actually covers, read off the
    # logged picks rather than hardcoded. A board that can publish five
    # stat types but has only ever logged one says so, instead of
    # implying full coverage.
    stats = sorted({p.get("stat") for d in days.values()
                    for p in d.get("picks", []) if p.get("stat")})
    market_chip = _chip(f"{stats[0]} only", COLOR["warn"]) if len(stats) == 1 else ""

    detail = f'{s["hits"]}/{s["total"]} graded'
    if s.get("dnp"):
        detail += f' \u00b7 {s["dnp"]} DNP'
    detail += f' \u00b7 {len(days)} days'
    if profit.get("priced"):
        detail += (f' \u00b7 {profit["priced"]} priced'
                   f' \u00b7 breakeven {profit["breakeven"]:.1f}%'
                   f' \u00b7 {profit["roi"]:+.1f}% ROI')
    else:
        detail += " \u00b7 no prices attached, so no ROI shown"

    verdict = s.get("verdict") or "\u2014"
    st.markdown(
        f'<div style="display:flex; gap:var(--lc-space-md); flex-wrap:wrap; '
        f'align-items:center; margin-top:var(--lc-space-lg);">'
        f'{_chip(verdict, _verdict_color(verdict))}{market_chip}'
        f'<span style="font-family:\'JetBrains Mono\',monospace; '
        f'font-size:var(--lc-text-tiny); color:{COLOR["text_faint"]};">'
        f'{detail}</span></div>',
        unsafe_allow_html=True,
    )

    # Direction, not just the cumulative total. Reuses the existing
    # trend renderer, which draws nothing below three graded days
    # rather than implying a direction from two points.
    with st.expander("Trend"):
        render_calibration_trend(days, base, label)


def render():
    page_header(
        "Results",
        subtitle=("Every pick this site published, graded against the "
                  "official box score. Picks are locked before first pitch."),
        align="left",
    )
    data_timestamp("Record updated")

    data = _load()
    sums = summary()

    graded = sum(s.get("total", 0) for s in sums.values())
    if not graded:
        st.info(
            "No graded picks yet. Tonight's picks are logged before first "
            "pitch and graded once the slate is final, so this fills in "
            "from tomorrow."
        )
        footer()
        return

    dnp = sum(s.get("dnp", 0) for s in sums.values())
    days_tracked = len({d for board in data.values() for d in board})
    tracked = [s for s in sums.values() if s.get("total")]
    beating = sum(1 for s in tracked if "beating" in (s.get("verdict") or ""))
    units = sum(s["profit"]["units"] for s in sums.values()
                if s.get("profit", {}).get("priced"))
    priced = sum(s.get("profit", {}).get("priced", 0) for s in sums.values())

    cols = st.columns(4)
    with cols[0]:
        st.markdown(_tile("Graded picks", f"{graded:,}",
                          f"{dnp} DNP excluded" if dnp else ""),
                    unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_tile("Days tracked", str(days_tracked)),
                    unsafe_allow_html=True)
    with cols[2]:
        st.markdown(_tile("Boards beating baseline",
                          f"{beating}/{len(tracked)}",
                          color=(COLOR["stat_high"] if beating
                                 else COLOR["text"])),
                    unsafe_allow_html=True)
    with cols[3]:
        # Shown as an em dash rather than omitted, so the ABSENCE of a
        # profit figure is visible instead of silently missing.
        st.markdown(_tile("Units",
                          f"{units:+.2f}" if priced else "\u2014",
                          f"{priced} priced" if priced
                          else "no prices attached",
                          color=(COLOR["accent"] if priced and units > 0
                                 else COLOR["error"] if priced and units < 0
                                 else COLOR["text_muted"])),
                    unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-family:\'JetBrains Mono\',monospace; '
        f'font-size:var(--lc-text-tiny); color:{COLOR["text_faint"]}; '
        f'margin-top:var(--lc-space-lg); line-height:1.7;">'
        f'Each board is graded on the outcome it is trying to produce, '
        f'against the measured league rate for that same outcome. A board '
        f'sitting AT its baseline added nothing, however high the '
        f'percentage looks. Read these over weeks, not nights.</div>',
        unsafe_allow_html=True,
    )

    st.markdown(_section_tag("By board"), unsafe_allow_html=True)

    # Boards with the most graded picks first; empty ones fall to the
    # bottom rather than being dropped.
    for board in sorted(BOARDS, key=lambda b: -(sums.get(b, {}).get("total") or 0)):
        with card(f"results_{board}"):
            _render_board(board, BOARDS[board],
                          sums.get(board, {}), data.get(board, {}))

    footer()


render()
