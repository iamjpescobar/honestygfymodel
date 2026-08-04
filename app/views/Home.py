"""
Home — what the site published today, how last night went, and where to
look next.

WHY THIS PAGE MAKES NO NETWORK CALLS

The landing page is the one screen where a slow first paint costs the
most: it is what a subscriber sees before they have chosen to wait for
anything. Building a board live means confirmed-lineup lookups and a
per-player Statcast pass, measured in tens of seconds — a fair price on
the Daily 13 page, where the wait is what you came for, and an unfair
one on a page whose only job is to orient you.

It does not have to pay that price, because the work is already done.
calibration_picks.py computes the same boards from the same engines in
CI at 1, 5 and 7 PM ET and commits them to data/calibration.json, and
the nightly writes each league's slate to data/<league>/games.json. So
every number on this page comes off disk, and the ONLY thing it cannot
show is a board CI has not built yet — a real fact about the time of
day, stated plainly, rather than a minute of silent spinner.

Nothing here is computed for this page. The picks come from
engines.calibration._load(), the rates from summary(). That is also why
it cannot disagree with the Results page or with the boards themselves.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from styles.kc_theme import page_header, card, footer, data_timestamp, COLOR
from engines.calibration import BOARDS, _load, summary

EASTERN = ZoneInfo("America/New_York")
_DATA = Path(__file__).resolve().parent.parent / "data"

# Home is a top-level view, not a page inside one sport, so it reports
# every board on the site. The jump buttons are what have to be careful.
#
# The sport switcher is instantiated by app.py ABOVE the main column, so
# its key (lc_sport_seg) cannot be written from here — Streamlit raises
# StreamlitAPIException for any widget key set after the widget exists.
# A jump therefore cannot change sport, only page WITHIN the sport that
# is currently selected. The per-sport nav radios ARE safe to write,
# because app.py renders neither of them on a Home run.
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

# Leagues whose slate the nightly writes to disk. MLB is absent on
# purpose: its schedule is a live API call, and this page does not make
# them.
SLATE_FILES = {"WNBA": _DATA / "wnba" / "games.json",
               "KBO": _DATA / "kbo" / "games.json",
               "NPB": _DATA / "npb" / "games.json"}

# What each part of the site actually answers. One honest sentence each —
# a nav label tells you a page exists; this tells you why you would open
# it, which is the only reason anyone opens a second page.
EXPLORE = [
    ("Game Card", "MLB",
     "One matchup end to end: both starters' arsenals, the lineup they "
     "face, park and weather, and a graded read on the moneyline and total."),
    ("Bullpen Board", "MLB",
     "What happens after the starter leaves \u2014 roughly a third of a "
     "hitter's plate appearances, and the part most models ignore."),
    ("Weather Board", "MLB",
     "Wind, temperature and park orientation across the whole slate, "
     "because a ball carries differently in Wrigley with a north wind."),
    ("Pitchers to Target", "MLB",
     "Which starters are giving up the kind of contact you want to be "
     "betting on tonight."),
    ("Props Board", "WNBA",
     "Every qualifying player ranked against the line the board derives "
     "from their own last fifteen games."),
    ("Defense Matchup", "WNBA",
     "Which defences are soft to a position, and who draws them tonight."),
]

STAT_LABEL = {"strikeOuts": "K", "pts": "PTS", "reb": "REB", "ast": "AST",
              "pra": "PRA", "tpm": "3PM"}

RESULT_COLOR = {"hit": COLOR["stat_high"], "miss": COLOR["error"]}


def _today():
    return datetime.now(EASTERN).strftime("%Y-%m-%d")


def _yesterday():
    return (datetime.now(EASTERN) - timedelta(days=1)).strftime("%Y-%m-%d")


def _greeting():
    hour = datetime.now(EASTERN).hour
    if hour < 12:
        part = "Good morning"
    elif hour < 18:
        part = "Good afternoon"
    else:
        part = "Good evening"
    name = (st.session_state.get("name") or "").strip()
    return f"{part}, {name}" if name else part


def _slate_counts():
    """{league: n games} for every league whose slate is on disk.

    Silently omits a league rather than showing a zero: a missing file
    means the nightly hasn't shipped that slate, which is NOT the same
    fact as "no games tonight" and must not be displayed as if it were.
    """
    out = {}
    for league, path in SLATE_FILES.items():
        try:
            games = (json.loads(path.read_text()) or {}).get("games") or []
        except Exception:
            continue
        if games:
            out[league] = len(games)
    return out


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
    name = pick.get("name") or "\u2014"
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


def _result_dots(picks):
    """The night at a glance, in pick order — filled for a hit, hollow for
    a miss, faint for one that never got a result.

    Order is preserved on purpose. "Lost the first four, won the last
    seven" is a different night from "alternated all evening", and a bare
    7/11 hides which one it was.
    """
    out = []
    for p in picks:
        res = p.get("result")
        if res == "hit":
            out.append(f'<span style="color:{COLOR["stat_high"]};">\u25cf</span>')
        elif res == "miss":
            out.append(f'<span style="color:{COLOR["error"]};">\u25cb</span>')
        else:
            out.append(f'<span style="color:{COLOR["text_faint"]};">\u00b7</span>')
    return (f'<span style="font-size:var(--lc-text-body); letter-spacing:0.16em; '
            f'font-family:\'JetBrains Mono\',monospace;">{"".join(out)}</span>')


def _jump_target(board):
    """The page a board's button should open, or None if it isn't
    reachable from the sport currently selected. See BOARD_PAGE."""
    if CURRENT_SPORT == "MLB" and board in BOARD_PAGE:
        return BOARD_PAGE[board]
    if CURRENT_SPORT == "WNBA" and board in WNBA_PAGE:
        return WNBA_PAGE[board]
    return None


def _goto(page_title, key, label=None):
    """Jump button out of Home and into a page of the current sport.

    Leaves the Home view and writes that sport's nav key, which app.py
    reads at the top of the next run — the same one-click path a click on
    the radio itself takes.
    """
    if st.button(label or f"Open {page_title}", key=key,
                 use_container_width=True):
        st.session_state["lc_view"] = "sport"
        if CURRENT_SPORT == "WNBA":
            st.session_state["lc_sub_WNBA"] = page_title
        else:
            st.session_state["lc_nav_radio"] = page_title
            st.session_state["lc_active_page"] = page_title
        st.rerun()


# ----------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------
def _render_pulse(record, today):
    """One line of true things about right now: which leagues are on, and
    how much has actually been published."""
    slates = _slate_counts()
    published = sum(len((record.get(b, {}).get(today) or {}).get("picks", []))
                    for b in BOARDS)

    chips = []
    if record.get("daily13", {}).get(today):
        chips.append(("MLB \u00b7 board published", COLOR["accent"]))
    for league, n in slates.items():
        chips.append((f"{league} \u00b7 {n} game{'s' if n != 1 else ''}",
                      COLOR["cold"]))
    if not chips and not published:
        return

    tail = ""
    if published:
        tail = (f'<span style="margin-left:var(--lc-space-lg); '
                f'color:{COLOR["text_muted"]}; font-size:var(--lc-text-caption);">'
                f'{published} picks published today</span>')
    st.markdown(" ".join(_chip(t, c) for t, c in chips) + tail,
                unsafe_allow_html=True)


def _render_today(record, today):
    """Today's published board, or an honest account of why there isn't one."""
    live = [(b, record.get(b, {}).get(today))
            for b in list(BOARD_PAGE) + list(WNBA_PAGE)
            if record.get(b, {}).get(today)]

    if not live:
        with card("home_no_board"):
            st.markdown(
                f'<div style="padding:var(--lc-space-xl); background:{COLOR["surface"]}; '
                f'border:1px solid {COLOR["border"]}; border-radius:var(--lc-radius-lg);">'
                f'<div style="color:{COLOR["text"]}; font-weight:700; '
                f'margin-bottom:var(--lc-space-sm);">Today\'s board isn\'t published yet</div>'
                f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-caption); '
                f'line-height:1.7;">Picks are locked in once lineups are confirmed \u2014 '
                f'MLB posts those one to three hours before first pitch, so the board is '
                f'recorded at 1, 5 and 7 PM ET. Nothing is shown here before then, because '
                f'a pick built off a projected lineup isn\'t the pick this site would have '
                f'made.<br><br>Any board below will build live right now if you don\'t want '
                f'to wait \u2014 it takes a moment, and it\'s the same computation.</div>'
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


def _best_call(rows, sums):
    """Last night's most improbable hit — the one on the board with the
    LOWEST league baseline, since clearing a 14% bar is a different
    achievement from clearing a 65% one.

    Returns None when nothing hit, or when no board involved carries a
    measured baseline. Deliberately silent rather than falling back to
    "any hit at all": calling an ordinary result the night's best is the
    small dishonesty that turns a record into marketing.
    """
    best = None
    for board, entry in rows:
        base = (sums.get(board) or {}).get("baseline")
        if base is None:
            continue
        for p in (entry or {}).get("picks", []):
            if p.get("result") != "hit":
                continue
            if best is None or base < best[0]:
                best = (base, board, p)
    return best


def _render_last_night(record, yesterday):
    """The night as a scoreboard: one row per board, in pick order, with
    the detail folded away rather than stacked six cards deep."""
    rows = [(b, record.get(b, {}).get(yesterday))
            for b in list(BOARD_PAGE) + list(WNBA_PAGE)
            if record.get(b, {}).get(yesterday)]

    if not rows:
        st.caption("No board was published yesterday, so there's nothing to "
                   "grade.")
        return

    sums = summary()

    best = _best_call(rows, sums)
    if best:
        base, board, pick = best
        cfg = BOARDS.get(board, {})
        st.markdown(
            f'<div style="background:{COLOR["accent_dim"]}; border:1px solid '
            f'{COLOR["accent_border"]}; border-radius:var(--lc-radius-lg); '
            f'padding:var(--lc-space-lg) var(--lc-space-xl); '
            f'margin-bottom:var(--lc-space-lg);">'
            f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["accent"]}; '
            f'text-transform:uppercase; letter-spacing:0.08em; font-weight:700;">'
            f'Call of the night</div>'
            f'<div style="color:{COLOR["text"]}; font-size:var(--lc-text-body_lg); '
            f'font-weight:700; margin-top:var(--lc-space-hair);">'
            f'{pick.get("name", "")} \u2014 {cfg.get("question", "hit")}</div>'
            f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-caption); '
            f'margin-top:var(--lc-space-hair);">{cfg.get("label", board)} \u00b7 '
            f'the league average for that outcome is {base:.0f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    for board, entry in rows:
        cfg = BOARDS.get(board, {})
        picks = (entry or {}).get("picks", [])
        hits = sum(1 for p in picks if p.get("result") == "hit")
        total = hits + sum(1 for p in picks if p.get("result") == "miss")

        # "NOT GRADED", never a bare em dash. An em dash reads as "no
        # data" when what it means is "we published these and scored none
        # of them" — the measurement gap this record exists to expose.
        if total:
            score = f"{hits}/{total}"
            score_color = (COLOR["stat_high"] if hits * 2 >= total
                           else COLOR["error"])
        else:
            score = "NOT GRADED"
            score_color = COLOR["warn"]

        base = (sums.get(board) or {}).get("baseline")
        rate = round(hits / total * 100) if total else None
        if rate is not None and base is not None:
            note = (f"{rate}% against a {base:.0f}% league average "
                    f"\u00b7 one night, not a trend")
        elif total:
            note = "graded against this board's own published number"
        else:
            note = "published, not yet scored"

        st.markdown(
            f'<div style="display:flex; align-items:center; gap:var(--lc-space-lg); '
            f'padding:var(--lc-space-md) var(--lc-space-none); '
            f'border-bottom:1px solid {COLOR["border_soft"]};">'
            f'<div style="flex:1 1 auto; min-width:0;">'
            f'<div style="color:{COLOR["text"]}; font-weight:700; '
            f'font-size:var(--lc-text-body);">{cfg.get("label", board)}</div>'
            f'<div style="color:{COLOR["text_faint"]}; '
            f'font-size:var(--lc-text-tiny);">{note}</div></div>'
            f'<div style="flex:none;">{_result_dots(picks)}</div>'
            f'<div style="flex:none; min-width:5.5rem; text-align:right; '
            f'font-family:\'JetBrains Mono\',monospace; font-weight:700; '
            f'color:{score_color};">{score}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"{cfg.get('label', board)} \u2014 every pick"):
            for pick in picks:
                st.markdown(_pick_row(pick, show_result=True),
                            unsafe_allow_html=True)


def _render_explore():
    """The hook. A nav label says a page exists; this says what question it
    answers, which is the only reason anyone opens a second page."""
    st.caption("Six places worth your time, and what each one actually "
               "answers.")
    cols = st.columns(2)
    for i, (page, sport, blurb) in enumerate(EXPLORE):
        with cols[i % 2]:
            with card(f"home_explore_{i}"):
                st.markdown(
                    f'<div style="display:flex; align-items:baseline; '
                    f'gap:var(--lc-space-md);">'
                    f'<div style="font-weight:700; color:{COLOR["text"]}; '
                    f'font-size:var(--lc-text-body);">{page}</div>'
                    f'<div style="font-size:var(--lc-text-tiny); '
                    f'color:{COLOR["text_faint"]}; letter-spacing:0.06em;">'
                    f'{sport}</div></div>'
                    f'<div style="color:{COLOR["text_muted"]}; '
                    f'font-size:var(--lc-text-caption); line-height:1.6; '
                    f'margin:var(--lc-space-sm) var(--lc-space-none);">{blurb}</div>',
                    unsafe_allow_html=True,
                )
                if sport == CURRENT_SPORT:
                    _goto(page, key=f"home_ex_{i}")
                else:
                    st.caption(f"Select {sport} above to open this.")


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
        _greeting(),
        subtitle=("Everything this site published today, how last night's "
                  "picks actually did, and where to look next."),
        eyebrow="LOS CAPPERS",
        accent=COLOR["accent"],
        align="left",
    )
    data_timestamp("Data refreshed", align="left")

    record = _load()
    _render_pulse(record, today)

    st.markdown(_section_tag(f"Today \u00b7 {today}"), unsafe_allow_html=True)
    _render_today(record, today)

    st.markdown(_section_tag("Last night"), unsafe_allow_html=True)
    _render_last_night(record, _yesterday())

    st.markdown(_section_tag("Explore"), unsafe_allow_html=True)
    _render_explore()

    st.markdown(_section_tag("Track record"), unsafe_allow_html=True)
    _render_track_record(record)

    footer()


render()
