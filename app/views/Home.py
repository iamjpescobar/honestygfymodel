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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from styles.kc_theme import page_header, card, footer, data_timestamp, COLOR
from engines.calibration import BOARDS, _load, summary
from engines.slate_guard import load_slate

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

# WHICH BOARDS BELONG TO WHICH SPORT — stated once, explicitly.
#
# Every consumer of this used to re-derive it inline as
# `BOARD_PAGE if CURRENT_SPORT == "MLB" else WNBA_PAGE`, which has no
# third branch. So on KBO, NPB, NBA, NFL and NHL — five of the seven
# sports in the switcher — the "else" fired and Home presented WNBA
# Props and WNBA Defense Matchup as that sport's OWN board cards: full
# size, same weight as a live card, no jump button (correctly, since
# they aren't reachable from there) and no explanation of why. On a
# quiet night it went further and told a KBO subscriber "Not published
# yet: WNBA Props, WNBA Defense Matchup", which is a sentence about a
# league they aren't looking at.
#
# A sport that publishes no boards maps to {} and gets the honest empty
# state, which is a real answer rather than another sport's inventory.
SPORT_BOARDS = {
    "MLB": BOARD_PAGE,
    "WNBA": WNBA_PAGE,
}


# Every board the site publishes, in a stable order: each sport's own
# boards, sports in SPORT_BOARDS order.
ALL_BOARDS = [b for pages in SPORT_BOARDS.values() for b in pages]


def _boards_for(sport):
    """The boards `sport` publishes, as {board_key: page_title}."""
    return SPORT_BOARDS.get(sport, {})


def _boards_elsewhere(sport):
    """Every board the site publishes that `sport` does not, keyed by the
    sport that owns it — so the 'also published' section can name the
    right destination instead of assuming there are only two sports."""
    return {sp: pages for sp, pages in SPORT_BOARDS.items() if sp != sport}

CURRENT_SPORT = (st.session_state.get("lc_sport_seg")
                 or st.session_state.get("lc_sport", "MLB"))

# Leagues whose slate the nightly writes to disk. MLB is absent on
# purpose: its schedule is a live API call, and this page does not make
# them.
# Leagues to report, not paths to read: slate_guard owns where the file
# lives and what its date key is called. Holding a second copy of those
# paths here is how this reader drifted out from under the guard in the
# first place.
SLATE_LEAGUES = ("WNBA", "KBO", "NPB")

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

# The loaded record, set once by render(). _load() is cheap and cached,
# but reading it in a helper called inside a column loop would mean one
# call per card for a value that cannot change within a run.
_RECORD = {}


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

    ROUTED THROUGH slate_guard. This read the file directly and reported
    whatever count it found, so a nightly that stopped publishing left
    the landing page — the first screen a subscriber sees — advertising
    "WNBA - 6 games" off a slate for a night already played. That is the
    exact failure slate_guard was written for, and this was the most
    prominent reader still outside it.

    Returns {league: (n_games, slate_date_or_None)}: the date rides
    along so a lookahead slate can be labelled rather than passed off as
    tonight's. KBO and NPB publish one on purpose when Seoul or Tokyo
    has no games today.
    """
    out = {}
    for league in SLATE_LEAGUES:
        games, slate_date, is_current = load_slate(league.lower())
        if games:
            out[league] = (len(games), None if is_current else slate_date)
    return out


def _chip(text, color, live=False):
    """A small monospace status pill. live=True prefixes the breathing
    dot defined in _inject_card_css — used only on the pulse rail, where
    the statement really is about right now."""
    dot = (f'<span class="lc-live-dot" style="background:{color};"></span>'
           if live else "")
    return (f'<span style="display:inline-flex; align-items:center; '
            f'padding:var(--lc-space-hair) var(--lc-space-md); '
            f'border-radius:var(--lc-radius-sm); background:{color}22; color:{color}; '
            f'border:1px solid {color}33; '
            f'font-size:var(--lc-text-tiny); font-weight:700; letter-spacing:0.04em; '
            f'font-family:\'JetBrains Mono\',monospace;">{dot}{text}</span>')


def _section_tag(text):
    # Inline-flex with a short accent rule leading into the label. The
    # four sections on this page were previously distinguished only by
    # vertical gap, which on a phone (where the gap collapses) meant they
    # were not distinguished at all.
    return (f'<div style="display:inline-flex; align-items:center; '
            f'gap:var(--lc-space-sm); margin:var(--lc-space-xl) var(--lc-space-none) '
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
    # The figure's own colour carries down into a hairline under it, so
    # a red "0/4" and a green "3/4" read differently at a glance instead
    # of being four identically-weighted grey boxes.
    return (f'<div style="background:{COLOR["surface"]}; '
            f'border:1px solid {COLOR["border"]}; '
            f'border-top:2px solid {color}; '
            f'border-radius:var(--lc-radius-lg); height:100%; '
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


def _result_dots(picks, limit=None):
    """The night at a glance, in pick order — filled for a hit, hollow for
    a miss, faint for one that never got a result.

    Order is preserved on purpose. "Lost the first four, won the last
    seven" is a different night from "alternated all evening", and a bare
    7/11 hides which one it was.
    """
    # limit: a three-up card is far too narrow for thirteen dots. Above
    # the limit the strip is dropped entirely rather than truncated — a
    # cut-off strip would misreport the night, which is the one thing
    # this element must never do.
    if limit is not None and len(picks) > limit:
        return ""
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


# How many picks a today-card previews. Three fits a three-up column
# without the card becoming a second copy of the board's own page.
_PREVIEW_ROWS = 3


def _last_night_score(board):
    """'●○●●● 3/5' for this board's previous night, or ''.

    Read straight off the same record every other number here comes
    from, so a today-card and the Last night section can never disagree.
    Silent when the board did not publish yesterday or nothing was
    graded: an empty result is not a zero, and must not look like one.
    """
    picks = (_RECORD.get(board, {}).get(_yesterday()) or {}).get("picks", [])
    hits = sum(1 for p in picks if p.get("result") == "hit")
    total = hits + sum(1 for p in picks if p.get("result") == "miss")
    if not total:
        return ""
    color = COLOR["stat_high"] if hits * 2 >= total else COLOR["error"]
    dots = _result_dots(picks, limit=8)
    return (f'<span style="color:{COLOR["text_faint"]};">last night</span> '
            f'{dots} <span style="color:{color}; font-weight:700;">'
            f'{hits}/{total}</span>')


def _jump_target(board):
    """The page a board's button should open, or None if it isn't
    reachable from the sport currently selected. See BOARD_PAGE."""
    return _boards_for(CURRENT_SPORT).get(board)


def _goto(page_title, key, label=None, compact=False):
    """Jump button out of Home and into a page of the current sport.

    Leaves the Home view and writes that sport's nav key, which app.py
    reads at the top of the next run — the same one-click path a click on
    the radio itself takes.
    """
    # compact=True renders a tertiary (link-style) button instead of a
    # full-width bordered one. Home used to end EVERY card with a
    # full-width button repeating the card's own title — eight of them
    # down the page, each as visually heavy as the content above it.
    # That flattened the hierarchy (nothing could lead, because every
    # card weighed the same) and cost roughly a screen of height on its
    # own. The card header carries the link now; the box is gone.
    if st.button(label or f"Open {page_title}", key=key,
                 type="tertiary" if compact else "secondary",
                 use_container_width=not compact):
        st.session_state["lc_view"] = "sport"
        if CURRENT_SPORT == "WNBA":
            st.session_state["lc_sub_WNBA"] = page_title
        else:
            st.session_state["lc_nav_radio"] = page_title
            st.session_state["lc_active_page"] = page_title
        st.rerun()


def _goto_sport(sport, page_title, key, label):
    """Jump into a board that belongs to a DIFFERENT sport.

    Home cannot change sport directly — see the lc_pending_sport comment
    in app.py. It records the intent and reruns; app.py applies it at the
    top of the next pass, before the switcher widget is instantiated.

    The nav key is written here rather than there because it is
    per-sport, and this is the only place that knows which page was
    asked for.
    """
    if st.button(label, key=key, type="tertiary"):
        st.session_state["lc_pending_sport"] = sport
        if sport == "WNBA":
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
    # PER SPORT, derived. This was hardcoded to daily13 and to the word
    # "MLB", so a WNBA session with both its boards published was told
    # "MLB - board published", and an MLB night where HR Edge landed but
    # Daily 13 hadn't yet showed no chip at all.
    for _sp, _pages in SPORT_BOARDS.items():
        _n = sum(1 for _b in _pages if record.get(_b, {}).get(today))
        if _n:
            chips.append((f"{_sp} \u00b7 {_n} board{'s' if _n != 1 else ''} "
                          f"published", COLOR["accent"]))
    for league, (n, ahead) in slates.items():
        # `ahead` is set only when the slate is for a later date than
        # today in that league's own timezone. Naming the date is the
        # whole point: an unlabelled count is indistinguishable from
        # tonight's, which is how the stale-slate bug stayed invisible.
        _when = f" \u00b7 {ahead}" if ahead else ""
        chips.append((f"{league} \u00b7 {n} game{'s' if n != 1 else ''}{_when}",
                      COLOR["cold"]))
    if not chips and not published:
        return

    tail = ""
    if published:
        tail = (f'<span style="color:{COLOR["text_muted"]}; '
                f'font-size:var(--lc-text-caption);">'
                f'{published} picks published today</span>')
    # A wrapping flex rail rather than inline spans separated by spaces:
    # on a phone the chips used to break mid-pill and the trailing count
    # landed on its own orphan line.
    st.markdown(
        f'<div style="display:flex; flex-wrap:wrap; align-items:center; '
        f'gap:var(--lc-space-sm) var(--lc-space-md); '
        f'padding:var(--lc-space-sm) var(--lc-space-none);">'
        + "".join(_chip(t, c, live=True) for t, c in chips)
        + tail + '</div>',
        unsafe_allow_html=True)


def _render_today(record, today):
    """Today's published board, or an honest account of why there isn't one."""
    # SPLIT BY SPORT, don't interleave.
    #
    # This used to be one flat list — every MLB board followed by every
    # WNBA board — poured into cols[i % 3]. On an MLB session that put
    # two WNBA cards in the same grid as the baseball ones, at identical
    # weight, with no way to open either (they aren't reachable from
    # here). Whatever the day's mix happened to be decided the layout.
    _mine_boards = list(_boards_for(CURRENT_SPORT))
    # Grouped BY OWNING SPORT rather than flattened into one "the other
    # sport" bucket, because there is no such thing as one other sport —
    # see SPORT_BOARDS.
    _elsewhere = _boards_elsewhere(CURRENT_SPORT)

    mine = [(b, record[b][today]) for b in _mine_boards
            if record.get(b, {}).get(today)]
    # Boards this sport publishes that have NOT been recorded yet. They
    # used to vanish silently, so an absent HR Edge looked identical to
    # an HR Edge that doesn't exist. Named below instead.
    pending = [b for b in _mine_boards if not record.get(b, {}).get(today)]
    others = [(sp, b, record[b][today])
              for sp, pages in _elsewhere.items() for b in pages
              if record.get(b, {}).get(today)]
    live = mine + others

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
            _mine = _boards_for(CURRENT_SPORT)
            if _mine:
                cols = st.columns(len(_mine))
                for col, (board, page) in zip(cols, _mine.items()):
                    with col:
                        _goto(page, key=f"home_build_{board}")
            else:
                # Named, not assumed. This said "Switch to MLB above"
                # verbatim on every sport that isn't MLB — including
                # WNBA, which publishes two boards of its own.
                _elsewhere = " or ".join(sorted(_boards_elsewhere(CURRENT_SPORT)))
                st.caption(f"{CURRENT_SPORT} doesn't publish a graded board "
                           f"yet \u2014 switch to {_elsewhere} above to build "
                           f"one live.")
        return

    # Column count follows the card count so the last row is never a
    # single card with two empty slots beside it — same rule as the
    # Explore grid below.
    _ncols = 2 if len(mine) == 4 else max(1, min(len(mine), 3))
    cols = st.columns(_ncols)
    for i, (board, entry) in enumerate(mine):
        cfg = BOARDS.get(board, {})
        picks = entry.get("picks", [])
        with cols[i % _ncols]:
            with card(f"home_today_{board}"):
                page = _jump_target(board)
                if page:
                    _goto(page, key=f"home_open_{board}",
                          label=f"{cfg.get('label', board)}  \u2192",
                          compact=True)
                else:
                    st.markdown(
                        f'<div style="font-weight:700; color:{COLOR["text"]}; '
                        f'font-size:var(--lc-text-body);">'
                        f'{cfg.get("label", board)}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown(
                    f'<div style="font-size:var(--lc-text-tiny); '
                    f'color:{COLOR["text_muted"]}; margin-bottom:var(--lc-space-sm);">'
                    f'{len(picks)} picks \u00b7 graded on whether the player '
                    f'{cfg.get("question", "hit")}.</div>',
                    unsafe_allow_html=True,
                )
                # Three rows, not six. The full board is one click away on
                # its own page; a home screen that reprints six of every
                # board's rows is not orienting anyone, it is making them
                # read the whole site twice before they have chosen
                # anything. Three is enough to recognise a board and see
                # whether tonight looks interesting.
                # One element for the rows, not one per row. Streamlit
                # ships each st.markdown as its own entry in the delta,
                # so a three-up grid of boards was sending a dozen tiny
                # HTML fragments to draw what the browser lays out as a
                # single list.
                _rows_html = "".join(_pick_row(p)
                                     for p in picks[:_PREVIEW_ROWS])

                extra = ""
                if len(picks) > _PREVIEW_ROWS:
                    extra = (f'<span style="color:{COLOR["text_faint"]};">'
                             f'+{len(picks) - _PREVIEW_ROWS} more</span>')

                # HOW THIS BOARD DID LAST NIGHT, right beside what it likes
                # tonight. This is the one thing the site has that nobody
                # else does, and it was buried three sections down the page
                # where it read as a separate report rather than as context
                # for the picks directly above it.
                last = _last_night_score(board)
                if last or extra:
                    _rows_html += (
                        f'<div style="display:flex; align-items:center; '
                        f'justify-content:space-between; gap:var(--lc-space-md); '
                        f'padding-top:var(--lc-space-sm); '
                        f'font-size:var(--lc-text-tiny); '
                        f'font-family:\'JetBrains Mono\',monospace;">'
                        f'{extra}{last}</div>')
                st.markdown(_rows_html, unsafe_allow_html=True)

    # ---- boards this sport publishes that aren't recorded yet ----
    #
    # One line, not a card. A board with no picks used to disappear
    # entirely, so an HR Edge still waiting on lineups looked exactly
    # like an HR Edge that doesn't exist — and the grid quietly changed
    # shape depending on how far into the afternoon it was.
    if pending:
        _names = ", ".join(BOARDS.get(b, {}).get("label", b) for b in pending)
        st.markdown(
            f'<div style="color:{COLOR["text_faint"]}; '
            f'font-size:var(--lc-text-caption); '
            f'padding-top:var(--lc-space-lg);">'
            f'Not published yet: {_names} \u2014 recorded once lineups are '
            f'confirmed.</div>',
            unsafe_allow_html=True,
        )

    # ---- what the OTHER sports published, as cards you can open ----
    #
    # These were rows, not cards, for a good reason: they could not be
    # opened from here, and giving an unopenable board the same card as a
    # live one is the mistake the Explore grid used to make with its
    # "Select WNBA above" tiles. The fix was NOT to promote a dead end
    # back to a card — it was to stop it being a dead end. _goto_sport
    # carries the sport change through app.py, so one click now lands on
    # the board itself.
    #
    # They stay visually distinct all the same. A cross-sport card is
    # keyed card_home_other_* and edged in `cold` rather than `accent`,
    # so "published, elsewhere" reads differently from "published, here"
    # at a glance instead of on inspection. The colour is carrying the
    # fact, which is the same job the demotion to rows used to do.
    if others:
        _sports = sorted({sp for sp, _b, _e in others})
        _where = " and ".join(_sports)
        st.markdown(
            f'<div style="color:{COLOR["text_muted"]}; '
            f'font-size:var(--lc-text-caption); font-weight:600; '
            f'padding:var(--lc-space-2xl) var(--lc-space-none) '
            f'var(--lc-space-sm);">Also published today \u00b7 '
            f'<span style="color:{COLOR["text_faint"]}; font-weight:400;">'
            f'{_where} \u2014 opening one switches sport</span></div>',
            unsafe_allow_html=True,
        )
        _ocols = 2 if len(others) == 4 else max(1, min(len(others), 3))
        cols = st.columns(_ocols)
        for i, (sport, board, entry) in enumerate(others):
            cfg = BOARDS.get(board, {})
            picks = entry.get("picks", [])
            page = SPORT_BOARDS.get(sport, {}).get(board)
            with cols[i % _ocols]:
                with card(f"home_other_{board}"):
                    st.markdown(
                        f'<div class="lc-elsewhere">{sport}</div>',
                        unsafe_allow_html=True,
                    )
                    if page:
                        _goto_sport(sport, page, key=f"home_jump_{board}",
                                    label=f"{cfg.get('label', board)}  \u2192")
                    else:
                        st.markdown(
                            f'<div style="font-weight:700; '
                            f'color:{COLOR["text"]};">'
                            f'{cfg.get("label", board)}</div>',
                            unsafe_allow_html=True,
                        )
                    _rows_html = "".join(_pick_row(p)
                                         for p in picks[:_PREVIEW_ROWS])
                    _extra = ""
                    if len(picks) > _PREVIEW_ROWS:
                        _extra = (f'<span style="color:{COLOR["text_faint"]};">'
                                  f'+{len(picks) - _PREVIEW_ROWS} more</span>')
                    _last = _last_night_score(board)
                    if _last or _extra:
                        _rows_html += (
                            f'<div style="display:flex; align-items:center; '
                            f'justify-content:space-between; '
                            f'gap:var(--lc-space-md); '
                            f'padding-top:var(--lc-space-sm); '
                            f'font-size:var(--lc-text-tiny); '
                            f'font-family:\'JetBrains Mono\',monospace;">'
                            f'{_extra}{_last}</div>')
                    st.markdown(_rows_html, unsafe_allow_html=True)


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
    # ALL_BOARDS, not BOARD_PAGE + WNBA_PAGE. Adding a sport to
    # SPORT_BOARDS now shows up here automatically; the old form silently
    # omitted any board that wasn't baseball's or basketball's.
    rows = [(b, record.get(b, {}).get(yesterday))
            for b in ALL_BOARDS
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

    _board_rows = []
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

        _board_rows.append(
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
            f'</div>')

    st.markdown("".join(_board_rows), unsafe_allow_html=True)

    # ONE expander for the whole night, not one per board.
    #
    # Six collapsed expanders each labelled "<board> - every pick", every
    # one sitting directly under a heading that already said the board's
    # name, read as six grey bars stacked down the page. The label was
    # pure repetition and the chrome outweighed what it hid.
    with st.expander("Every pick from last night"):
        # The whole night in ONE element. This was two st.markdown calls
        # per board plus one per pick — on a six-board night with
        # thirteen Daily 13 picks that is over fifty separate fragments,
        # all of them inside a collapsed expander the reader may never
        # open.
        _detail = []
        for board, entry in rows:
            cfg = BOARDS.get(board, {})
            _detail.append(
                f'<div style="color:{COLOR["gold"]}; font-weight:700; '
                f'font-size:var(--lc-text-caption); text-transform:uppercase; '
                f'letter-spacing:0.06em; padding:var(--lc-space-lg) '
                f'var(--lc-space-none) var(--lc-space-xs);">'
                f'{cfg.get("label", board)}</div>')
            _detail.extend(_pick_row(pick, show_result=True)
                           for pick in (entry or {}).get("picks", []))
        st.markdown("".join(_detail), unsafe_allow_html=True)



def _render_explore():
    """The hook. A nav label says a page exists; this says what question it
    answers, which is the only reason anyone opens a second page."""
    # Only pages reachable from the sport currently selected get a card.
    #
    # A page from another sport used to occupy a full tile identical in
    # size and weight to a live one, its only content the sentence
    # "Select WNBA above to open this." Two dead tiles sat in the grid
    # looking exactly as important as the four working ones. They are
    # one line of text below the grid now, which is what they are worth.
    here = [(p, sp, b) for p, sp, b in EXPLORE if sp == CURRENT_SPORT]
    elsewhere = [(p, sp) for p, sp, _b in EXPLORE if sp != CURRENT_SPORT]

    st.caption("What each place actually answers.")

    # Column count picked so the last row is never a single card with
    # two empty slots beside it. Four MLB pages in a three-up grid gave
    # 3 + 1, which reads as a layout bug rather than a list that ended.
    _n = len(here) or 1
    _ncols = 2 if _n == 4 else min(_n, 3)
    cols = st.columns(_ncols)
    for i, (page, sport, blurb) in enumerate(here):
        with cols[i % _ncols]:
            with card(f"home_explore_{i}"):
                _goto(page, key=f"home_ex_{i}", label=f"{page}  \u2192",
                      compact=True)
                st.markdown(
                    f'<div style="color:{COLOR["text_muted"]}; '
                    f'font-size:var(--lc-text-caption); line-height:1.6; '
                    f'margin-top:var(--lc-space-xs);">{blurb}</div>',
                    unsafe_allow_html=True,
                )

    if elsewhere:
        by_sport = {}
        for page, sport in elsewhere:
            by_sport.setdefault(sport, []).append(page)
        # Separators are built OUTSIDE the f-strings. A backslash escape
        # inside an f-string EXPRESSION is a SyntaxError on Python 3.11,
        # which requirements.txt and both workflows pin, and it fails at
        # import time — the page does not render at all.
        _DASH = "\u2014"
        _DOT = " \u00b7 "
        parts = [f'{", ".join(pages)} {_DASH} switch to {sport} above'
                 for sport, pages in by_sport.items()]
        _joined = _DOT.join(parts)
        st.markdown(
            f'<div style="color:{COLOR["text_faint"]}; '
            f'font-size:var(--lc-text-caption); '
            f'padding-top:var(--lc-space-md);">'
            f'{_joined}</div>',
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

    # _edge_verdict answers one of five ways, and two of them mean "we
    # cannot tell yet" rather than any result. Splitting them here is
    # what lets the tile below say something true.
    def _verdict(s):
        return s.get("verdict") or ""

    measurable = [s for s in tracked
                  if "beating the league baseline" in _verdict(s)
                  or "below the league baseline" in _verdict(s)
                  or "no measurable edge" in _verdict(s)]
    beating = sum(1 for s in measurable if "beating" in _verdict(s))
    below = sum(1 for s in measurable if "below" in _verdict(s))

    cols = st.columns(4)
    with cols[0]:
        st.markdown(_tile("Graded picks", f"{graded:,}"), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_tile("Days tracked", str(days_tracked)), unsafe_allow_html=True)
    with cols[2]:
        # RED MUST MEAN LOSING, NOT "TOO EARLY".
        #
        # Colouring by verdict was the right instinct and the wrong
        # denominator. `beating / len(tracked)` counted every board that
        # had graded a single pick, so a board _edge_verdict had already
        # refused to judge — "only 22 graded picks, far too few" — landed
        # in the same bucket as one measurably below the baseline, and
        # both painted red. With 227 picks spread over six boards that
        # produced a red 0/6 on the landing page, which is the site
        # calling itself a loser on evidence it had itself decided was
        # insufficient. That is the exact failure this whole engine was
        # written to avoid, reintroduced one layer up.
        #
        # Now the denominator is the boards that CAN be judged, and the
        # colour follows the verdicts rather than their absence: green
        # when every measurable board clears the bar, red only when one
        # is genuinely below it, amber for a real mixed picture, and
        # muted when nothing has enough data yet.
        if not measurable:
            _bl_color = COLOR["text_muted"]
            _bl_value = "\u2014"
            _bl_sub = "no board has enough graded picks to judge yet"
        else:
            _bl_value = f"{beating}/{len(measurable)}"
            _plural = "" if len(measurable) == 1 else "s"
            _bl_sub = f"of {len(measurable)} board{_plural} with enough data"
            if beating == len(measurable):
                _bl_color = COLOR["accent"]
            elif below:
                _bl_color = COLOR["error"]
            elif beating:
                _bl_color = COLOR["stat_high"]
            else:
                _bl_color = COLOR["warn"]
        st.markdown(_tile("Beating baseline", _bl_value, sub=_bl_sub,
                          color=_bl_color),
                    unsafe_allow_html=True)
    with cols[3]:
        # Results is in the MLB nav and in the WNBA subpage nav. The
        # other sports have no page to open, so they get the sentence
        # without a dead button.
        if CURRENT_SPORT in ("MLB", "WNBA"):
            _goto("Results", key="home_open_results",
                  label="Open Results  \u2192", compact=True)
        st.caption("Every pick, graded, with the league rate beside it.")


def _inject_card_css():
    """Flatten the link-style buttons that act as card titles.

    kc_theme sets `.stButton > button { background-color: surface_raised;
    border: 1px solid border }` for every button on the site. That is
    right for an action and wrong for a title that happens to be
    clickable — it drew a bordered box at the top of each of the nine
    cards on this page, which is the same visual weight the full-width
    "Open X" buttons had before they were replaced.

    Scoped to this page's own container keys (home_today_*, home_explore_*)
    rather than to a Streamlit internal, and more specific than the
    global rule, so it wins without touching buttons anywhere else.
    """
    st.markdown(
        "<style>"
        "[class*='st-key-home_'] .stButton > button {"
        "  background: transparent !important; border: none !important;"
        "  padding: 0 !important; min-height: 0 !important;"
        "  text-align: left !important; justify-content: flex-start !important; }"
        "[class*='st-key-home_'] .stButton > button p {"
        f"  color: {COLOR['text']} !important; font-weight: 700 !important;"
        "  text-align: left !important; margin: 0 !important; }"
        "[class*='st-key-home_'] .stButton > button:hover p {"
        f"  color: {COLOR['accent']} !important; }}"
        # Same 1rem-gap problem as the nav: the theme's tightening rule
        # only matches DIRECT children of a vertical block, and a keyed
        # container adds a wrapper — so a card's title sat a full line
        # away from its own first row.
        "[class*='st-key-home_'] div[data-testid='stVerticalBlock'] {"
        "  gap: var(--lc-space-sm) !important; }"

        # ------------------------------------------------------------------
        # The cards are real surfaces now.
        #
        # `card()` returns a container with border=False, so every Today
        # and Explore card was an invisible box: the grid read as loose
        # text in columns, and the three-up layout was carried entirely by
        # whitespace. These give each one a surface, a border and a radius
        # — the same tokens every other panel on the site already uses, so
        # nothing new is invented, it is just applied where it was missing.
        # ------------------------------------------------------------------
        # THE EDGE CARRIES THE FACT.
        #
        # Every card declares its own --lc-edge, and that one variable
        # drives the top rule, the glow behind it and the hover border.
        # Cyan means "this sport, published today"; steel blue means
        # "published, but it lives under another sport". So the colour is
        # doing the work the old row-vs-card demotion did, without
        # stripping the content back to a line of text.
        #
        # The edge is now always visible rather than hover-only. A rule
        # that appears when you are already pointing at the card tells you
        # something you have found out; a rule that is there tells you
        # which cards are worth pointing at.
        "[class*='st-key-card_home_'] {"
        f"  --lc-edge: {COLOR['accent']};"
        f"  --lc-edge-dim: {COLOR['accent_dim']};"
        f"  --lc-edge-border: {COLOR['accent_border']};"
        f"  background: linear-gradient(158deg, {COLOR['surface_raised']} 0%,"
        f"    {COLOR['surface']} 62%);"
        f"  border: 1px solid {COLOR['border']};"
        "  border-radius: var(--lc-radius-lg);"
        "  padding: var(--lc-space-lg) var(--lc-space-xl);"
        "  position: relative; overflow: hidden;"
        "  box-shadow: 0 1px 2px rgba(0,0,0,.35);"
        "  transition: border-color .18s ease, transform .18s ease,"
        "    box-shadow .18s ease; }"

        "[class*='st-key-card_home_other_'] {"
        f"  --lc-edge: {COLOR['cold']};"
        f"  --lc-edge-dim: {COLOR['cold_dim']};"
        f"  --lc-edge-border: {COLOR['cold_border']}; }}"

        # The rule itself, plus a short wash of the same colour bleeding
        # down from it. The wash is what stops the gradient reading as a
        # flat panel with a stripe glued on top.
        "[class*='st-key-card_home_']::before {"
        "  content: ''; position: absolute; top: 0; left: 0; right: 0;"
        "  height: 2px; background: var(--lc-edge);"
        "  opacity: .55; transition: opacity .18s ease; }"
        "[class*='st-key-card_home_']::after {"
        "  content: ''; position: absolute; top: 0; left: 0; right: 0;"
        "  height: 96px; pointer-events: none;"
        "  background: linear-gradient(180deg, var(--lc-edge-dim),"
        "    transparent 78%);"
        "  opacity: .7; transition: opacity .18s ease; }"
        "[class*='st-key-card_home_']:hover::before { opacity: 1; }"
        "[class*='st-key-card_home_']:hover::after { opacity: 1; }"
        "[class*='st-key-card_home_']:hover {"
        "  border-color: var(--lc-edge-border);"
        "  box-shadow: 0 6px 18px rgba(0,0,0,.45);"
        "  transform: translateY(-2px); }"

        # Keyboard users get the same signal mouse users do.
        "[class*='st-key-card_home_']:focus-within {"
        "  border-color: var(--lc-edge-border); }"
        "[class*='st-key-card_home_']:focus-within::before { opacity: 1; }"

        # The sport badge on a cross-sport card. Small, uppercase, tracked
        # out — it names the destination the card will take you to, which
        # is the one thing a reader needs before clicking something that
        # changes sport underneath them.
        ".lc-elsewhere {"
        "  display: inline-block; font-size: var(--lc-text-micro);"
        "  font-weight: 700; letter-spacing: .14em; text-transform: uppercase;"
        f"  color: {COLOR['cold']}; background: {COLOR['cold_dim']};"
        f"  border: 1px solid {COLOR['cold_border']};"
        "  border-radius: 999px; padding: .1rem .5rem;"
        "  margin-bottom: var(--lc-space-hair); }"

        # The last row of a card (the +N more / last-night strip) sits
        # against the card's own bottom padding rather than a border.
        "[class*='st-key-card_home_'] > div > div > div:last-child > div"
        " > div:last-child { border-bottom: none; }"

        # ------------------------------------------------------------------
        # The live dot on the pulse rail. Two-second breath, and it is
        # switched off entirely under prefers-reduced-motion — an
        # animation nobody asked for is a bug for the readers who cannot
        # tolerate one.
        # ------------------------------------------------------------------
        ".lc-live-dot {"
        "  display: inline-block; width: .45rem; height: .45rem;"
        "  border-radius: 50%; margin-right: .4rem;"
        "  vertical-align: middle; animation: lc-breathe 2s ease-in-out infinite; }"
        "@keyframes lc-breathe { 0%,100% { opacity: 1; } 50% { opacity: .35; } }"
        # RAGGED ROWS. One board publishes ten picks and another
        # publishes one, so three cards in a row ended at three
        # different heights and the row read as a pile rather than a
        # row. Stretching each card to fill its column costs nothing and
        # gives the eye a line to follow. Both testids are matched
        # because Streamlit has renamed this element between versions
        # and a pinned upgrade should not silently undo the layout.
        "[data-testid='stColumn'], [data-testid='column'] {"
        "  display: flex; align-items: stretch; }"
        "[data-testid='stColumn'] > div, [data-testid='column'] > div {"
        "  width: 100%; }"
        "[class*='st-key-card_home_'] {"
        "  height: 100%; }"

        "@media (prefers-reduced-motion: reduce) {"
        "  .lc-live-dot { animation: none; }"
        "  [class*='st-key-card_home_'] { transition: none; }"
        "  [class*='st-key-card_home_']:hover { transform: none; } }"

        # The lift and the shadow are the two things that cost paint on a
        # phone, and a stacked column of cards is where that is felt.
        "@media (hover: none) {"
        "  [class*='st-key-card_home_']:hover { transform: none;"
        "    box-shadow: 0 1px 2px rgba(0,0,0,.35); } }"

        # On a phone the three-up grid is already stacked by Streamlit;
        # tighten the card padding so a stack of six doesn't become six
        # screens of scrolling.
        "@media (max-width: 640px) {"
        "  [class*='st-key-card_home_'] {"
        "    padding: var(--lc-space-md) var(--lc-space-lg); } }"
        "</style>",
        unsafe_allow_html=True,
    )


def render():
    global _RECORD
    today = _today()
    _inject_card_css()
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
    _RECORD = record
    _render_pulse(record, today)

    st.markdown(_section_tag(f"Today \u00b7 {today}"), unsafe_allow_html=True)
    _render_today(record, today)

    st.markdown(_section_tag("Last night"), unsafe_allow_html=True)
    _render_last_night(record, _yesterday())

    # Track record before Explore, on purpose. Explore is a menu; the
    # graded record is the argument. A first-time reader was scrolling
    # past four navigation cards to reach the only thing on this page
    # that distinguishes the site from every other picks account.
    st.markdown(_section_tag("Track record"), unsafe_allow_html=True)
    _render_track_record(record)

    st.markdown(_section_tag("Explore"), unsafe_allow_html=True)
    _render_explore()

    footer()


render()
