"""
Home — what the site published today, and how yesterday's picks did.

WHY THIS PAGE MAKES NO NETWORK CALLS

The landing page is the one screen where a slow first paint costs the
most: it is what a subscriber sees before they have chosen to wait for
anything. Building a board live means confirmed-lineup lookups and a
per-player Statcast pass, which is measured in tens of seconds — an
acceptable price on the Daily 13 page, where the wait is what you came
for, and an unacceptable one on a page whose only job is to orient you.

It does not have to pay that price, because the work is already done.
calibration_picks.py computes the same boards from the same engines in
CI at 1, 5 and 7 PM ET and commits them to data/calibration.json. After
the first run of the day, a live rebuild here would produce the board
that is already sitting on disk. So this page reads the record and
paints, and the ONLY case it has nothing to show is the window before
CI has run — which is a real fact about the day, stated plainly, rather
than a minute of silent spinner.

Every number here comes from engines.calibration._load(). Nothing on
this page is computed for it, which is also why it cannot disagree with
the Results page or with the boards themselves.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from styles.kc_theme import page_header, card, footer, COLOR
from engines.calibration import BOARDS, _load, summary

EASTERN = ZoneInfo("America/New_York")

# Home is a top-level view, not a page inside one sport, so it reports
# every board on the site. The jump buttons are what have to be careful.
#
# The sport switcher is instantiated by app.py ABOVE the main column, so
# its key (lc_sport_seg) cannot be written from here — Streamlit raises
# StreamlitAPIException for any widget key set after the widget exists.
# A jump therefore cannot change sport, only page WITHIN the sport that
# is currently selected. The per-sport nav radios ARE safe to write,
# because app.py renders neither of them on a Home run.
#
# So a board gets a button when its page belongs to the current sport,
# and otherwise just renders its picks. Nothing is offered that would
# land somewhere unexpected.
BOARD_PAGE = {
    "daily13": "Daily 13",
    "potd": "Player of the Day",
    "hr_edge": "HR Edge",
    "k_board": "Strikeout Board",
}

# The WNBA boards live under that sport's own subpage nav (lc_sub_WNBA).
WNBA_PAGE = {
    "wnba_props": "Props Board",
    "wnba_defense": "Defense Matchup",
}

CURRENT_SPORT = (st.session_state.get("lc_sport_seg")
                 or st.session_state.get("lc_sport", "MLB"))

# Display order: MLB boards first, then WNBA. BOARDS itself is keyed for
# grading, not for reading, so the order there is incidental.
BOARD_ORDER = ["daily13", "potd", "hr_edge", "k_board",
               "wnba_props", "wnba_defense"]

STAT_LABEL = {"strikeOuts": "K", "pts": "PTS", "reb": "REB", "ast": "AST",
              "pra": "PRA", "tpm": "3PM"}

RESULT_COLOR = {"hit": COLOR["stat_high"], "miss": COLOR["error"]}


def _today():
    return datetime.now(EASTERN).strftime("%Y-%m-%d")


def _yesterday():
    return (datetime.now(EASTERN) - timedelta(days=1)).strftime("%Y-%m-%d")


def _chip(text, color):
    return (f'<span style="display:inline-block; padding:var(--lc-space-hair) var(--lc-space-md); '
            f'border-radius:var(--lc-radius-sm); background:{color}22; color:{color}; '
            f'font-size:var(--lc-text-tiny); font-weight:700; letter-spacing:0.04em; '
            f'font-family:\'JetBrains Mono\',monospace;">{text}</span>')


def _section_tag(text):
    return (f'<div style="display:inline-block; margin:var(--lc-space-xl) var(--lc-space-none) '
            f'var(--lc-space-md) var(--lc-space-none); padding:var(--lc-space-hair) var(--lc-space-md); '
            f'border-radius:var(--lc-radius-sm); background:{COLOR["accent_dim"]}; '
            f'border:1px solid {COLOR["accent_border"]}; color:{COLOR["accent"]}; '
            f'font-size:var(--lc-text-tiny); font-weight:700; text-transform:uppercase; '
            f'letter-spacing:0.08em;">{text}</div>')


def _tile(label, value, sub="", color=None):
    color = color or COLOR["text"]
    sub_html = ""
    if sub:
        sub_html = (f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_faint"]}; '
                    f'margin-top:var(--lc-space-hair);">{sub}</div>')
    return (f'<div style="background:{COLOR["surface"]}; border-radius:var(--lc-radius-lg); '
            f'padding:var(--lc-space-lg) var(--lc-space-xl);">'
            f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]}; '
            f'letter-spacing:0.06em; text-transform:uppercase;">{label}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-stat); '
            f'font-weight:700; color:{color}; margin-top:var(--lc-space-xs);">{value}</div>'
            f'{sub_html}</div>')


def _line_text(pick):
    """'6.4 K' / '11.5 PTS', or '' for a board with no published number.

    daily13, potd and hr_edge grade against a fixed threshold rather than
    a per-pick line, so they carry no number and must not be given a
    fabricated one.
    """
    line = pick.get("line")
    if line is None:
        return ""
    label = STAT_LABEL.get(pick.get("stat"), str(pick.get("stat") or ""))
    try:
        return f"{float(line):g} {label}".strip()
    except (TypeError, ValueError):
        return f"{line} {label}".strip()


def _pick_row(pick, show_result=False):
    """One pick as a single line: name, team, published line, result."""
    name = pick.get("name") or "—"
    team = pick.get("team") or ""
    line = _line_text(pick)

    right = ""
    if show_result:
        res = pick.get("result")
        if res in RESULT_COLOR:
            right = _chip(res.upper(), RESULT_COLOR[res])
        elif res == "dnp":
            right = _chip("DNP", COLOR["text_faint"])
        else:
            right = _chip("PENDING", COLOR["text_faint"])
    elif line:
        right = (f'<span style="font-family:\'JetBrains Mono\',monospace; '
                 f'font-size:var(--lc-text-tiny); color:{COLOR["accent"]};">{line}</span>')

    return (f'<div style="display:flex; align-items:center; justify-content:space-between; '
            f'gap:var(--lc-space-md); padding:var(--lc-space-sm) var(--lc-space-none); '
            f'border-bottom:1px solid {COLOR["border_soft"]};">'
            f'<div style="min-width:0; overflow:hidden; text-overflow:ellipsis; '
            f'white-space:nowrap; color:{COLOR["player_name"]}; font-weight:600; '
            f'font-size:var(--lc-text-body);">{name}'
            f'<span style="color:{COLOR["text_faint"]}; font-weight:400; '
            f'margin-left:var(--lc-space-sm);">{team}</span></div>'
            f'<div style="flex:none;">{right}</div>'
            f'</div>')


def _jump_target(board):
    """The page a board's button should open, or None if it isn't
    reachable from the sport currently selected. See BOARD_PAGE."""
    if CURRENT_SPORT == "MLB" and board in BOARD_PAGE:
        return BOARD_PAGE[board]
    if CURRENT_SPORT == "WNBA" and board in WNBA_PAGE:
        return WNBA_PAGE[board]
    return None


def _goto(page_title, key):
    """Jump button out of Home and into a page of the current sport.

    Leaves the Home view and writes that sport's nav key, which app.py
    reads at the top of the next run — the same one-click path a click on
    the radio itself takes.
    """
    if st.button(f"Open {page_title}", key=key, use_container_width=True):
        st.session_state["lc_view"] = "sport"
        if CURRENT_SPORT == "WNBA":
            st.session_state["lc_sub_WNBA"] = page_title
        else:
            st.session_state["lc_nav_radio"] = page_title
            st.session_state["lc_active_page"] = page_title
        st.rerun()


def _render_today(record, today):
    """Today's published board, or an honest account of why there isn't one."""
    live = [(b, record.get(b, {}).get(today))
            for b in BOARD_ORDER if record.get(b, {}).get(today)]

    if not live:
        with card("home_no_board"):
            st.markdown(
                f'<div style="padding:var(--lc-space-xl); background:{COLOR["surface"]}; '
                f'border:1px solid {COLOR["border"]}; border-radius:var(--lc-radius-lg);">'
                f'<div style="color:{COLOR["text"]}; font-weight:700; '
                f'margin-bottom:var(--lc-space-sm);">Today\'s board isn\'t published yet</div>'
                f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-caption); '
                f'line-height:1.7;">Picks are locked in once lineups are confirmed — '
                f'MLB posts those one to three hours before first pitch, so the board is '
                f'recorded at 1, 5 and 7 PM ET. Nothing is shown here before then, because '
                f'a pick built off a projected lineup isn\'t the pick this site would have '
                f'made.<br><br>Any board below will build live right now if you don\'t want '
                f'to wait — it takes a moment, and it\'s the same computation.</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if CURRENT_SPORT == "MLB":
                cols = st.columns(len(BOARD_PAGE))
                for col, (board, page) in zip(cols, BOARD_PAGE.items()):
                    with col:
                        _goto(page, key=f"home_build_{board}")
            else:
                st.caption("Switch to MLB above to build one of the boards "
                           "live.")
        return

    cols = st.columns(2)
    for i, (board, entry) in enumerate(live):
        cfg = BOARDS.get(board, {})
        picks = entry.get("picks", [])
        with cols[i % 2]:
            with card(f"home_today_{board}"):
                st.markdown(
                    f'<div style="display:flex; align-items:baseline; '
                    f'justify-content:space-between; gap:var(--lc-space-md);">'
                    f'<div style="font-weight:700; color:{COLOR["text"]}; '
                    f'font-size:var(--lc-text-body);">{cfg.get("label", board)}</div>'
                    f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_faint"]}; '
                    f'font-family:\'JetBrains Mono\',monospace;">{len(picks)} picks</div>'
                    f'</div>'
                    f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]}; '
                    f'margin-bottom:var(--lc-space-sm);">Graded on whether the player '
                    f'{cfg.get("question", "hit")}.</div>',
                    unsafe_allow_html=True,
                )
                # Capped rather than scrolled. The full board is one click
                # away on its own page, and a home screen that reproduces
                # thirteen rows six times over stops being a home screen.
                for pick in picks[:6]:
                    st.markdown(_pick_row(pick), unsafe_allow_html=True)
                if len(picks) > 6:
                    st.markdown(
                        f'<div style="font-size:var(--lc-text-tiny); '
                        f'color:{COLOR["text_faint"]}; padding-top:var(--lc-space-sm);">'
                        f'+{len(picks) - 6} more</div>',
                        unsafe_allow_html=True,
                    )
                page = _jump_target(board)
                if page:
                    _goto(page, key=f"home_open_{board}")


def _render_last_night(record, yesterday):
    """Yesterday's card: what was picked, and what actually happened."""
    rows = [(b, record.get(b, {}).get(yesterday))
            for b in BOARD_ORDER if record.get(b, {}).get(yesterday)]

    if not rows:
        st.caption("No board was published yesterday, so there's nothing to grade.")
        return

    graded_any = any(p.get("result") in ("hit", "miss")
                     for _b, e in rows for p in e.get("picks", []))
    if not graded_any:
        st.caption(
            "Yesterday's picks are recorded but not graded yet — grading runs "
            "against the official box scores at 6 AM ET, once every game is final."
        )

    cols = st.columns(2)
    for i, (board, entry) in enumerate(rows):
        cfg = BOARDS.get(board, {})
        picks = entry.get("picks", [])
        hits = sum(1 for p in picks if p.get("result") == "hit")
        total = hits + sum(1 for p in picks if p.get("result") == "miss")
        with cols[i % 2]:
            with card(f"home_last_{board}"):
                # "NOT GRADED", never a bare em dash. An em dash reads
                # as "no data" when what it actually means is "we
                # published these picks and scored none of them" — the
                # measurement gap this whole record exists to expose.
                score = f"{hits}/{total}" if total else "NOT GRADED"
                if total:
                    score_color = (COLOR["stat_high"] if hits * 2 >= total
                                   else COLOR["error"])
                else:
                    score_color = COLOR["warn"]
                st.markdown(
                    f'<div style="display:flex; align-items:baseline; '
                    f'justify-content:space-between; gap:var(--lc-space-md);">'
                    f'<div style="font-weight:700; color:{COLOR["text"]}; '
                    f'font-size:var(--lc-text-body);">{cfg.get("label", board)}</div>'
                    f'<div style="font-family:\'JetBrains Mono\',monospace; font-weight:700; '
                    f'color:{score_color};">{score}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                for pick in picks[:6]:
                    st.markdown(_pick_row(pick, show_result=True),
                                unsafe_allow_html=True)
                if len(picks) > 6:
                    st.markdown(
                        f'<div style="font-size:var(--lc-text-tiny); '
                        f'color:{COLOR["text_faint"]}; padding-top:var(--lc-space-sm);">'
                        f'+{len(picks) - 6} more</div>',
                        unsafe_allow_html=True,
                    )


def _render_track_record(record):
    """The three numbers that decide whether any of the above is worth
    anything. Deliberately the same figures the Results page opens with —
    summary() is the only place they are computed."""
    sums = summary()
    graded = sum(s.get("total", 0) for s in sums.values())
    if not graded:
        st.caption(
            "No graded picks yet. Tonight's board is graded once the slate "
            "is final, so this fills in from tomorrow."
        )
        return

    days_tracked = len({d for board in record.values() for d in board})
    tracked = [s for s in sums.values() if s.get("total")]
    beating = sum(1 for s in tracked if "beating" in (s.get("verdict") or ""))

    cols = st.columns(4)
    with cols[0]:
        st.markdown(_tile("Graded picks", f"{graded:,}"), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_tile("Days tracked", str(days_tracked)), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(_tile("Beating baseline", f"{beating}/{len(tracked)}",
                          color=(COLOR["stat_high"] if beating else COLOR["text"])),
                    unsafe_allow_html=True)
    with cols[3]:
        # Results is in the MLB nav and in the WNBA subpage nav. The
        # other sports have no page to open, so they get the sentence
        # without a dead button.
        if CURRENT_SPORT in ("MLB", "WNBA"):
            _goto("Results", key="home_open_results")
        st.caption("Every pick, graded, with the league rate beside it.")


def render():
    today = _today()
    page_header(
        "Home",
        subtitle=("Everything this site published today, and how yesterday's "
                  "picks actually did."),
        align="left",
    )

    record = _load()

    st.markdown(_section_tag(f"Today · {today}"), unsafe_allow_html=True)
    _render_today(record, today)

    st.markdown(_section_tag("Last night"), unsafe_allow_html=True)
    _render_last_night(record, _yesterday())

    st.markdown(_section_tag("Track record"), unsafe_allow_html=True)
    _render_track_record(record)

    footer()


render()
