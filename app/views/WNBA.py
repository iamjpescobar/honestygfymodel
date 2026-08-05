import pandas as pd
import streamlit as st

from styles.kc_theme import (page_header, card_open, card_close,
                             badge, footer, COLOR, SPORT_ACCENTS)
from styles.table_style import style_stat_table, render_html_table, tier_legend
from engines.matchup_grades_intl import grade_wnba_matchup, render_matchup_grades_card

# NOTE: no st.set_page_config here — app.py already sets it once.

from engines.live_sync import sync_latest_button
from engines.trend_chart import window_hit_chips, render_trend_bars
from engines.wnba_logos import logo_url_by_id
from engines.slate_guard import (load_slate, staleness_note,
                                 generated_at as slate_guard_generated_at)

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

# WNBA orange, resolved once. Every accented element on this page reads
# from here so the page carries ONE identity colour instead of the six
# it used to (orange header, teal tabs, blue leans, magenta labels, gold
# body text, per-team blues) — none of which meant anything.
_ACCENT = SPORT_ACCENTS.get("WNBA", COLOR["stat_high"])

# Prop-tab styling. Idle tabs are muted grey and the active tab is the
# page accent — previously idle was gold and active was MLB teal, which
# put two more colours on screen for no informational gain.
st.markdown(
    "<style>"
    ".stTabs [data-baseweb='tab-list'] { gap: 2px; }"
    ".stTabs [data-baseweb='tab'] { font-family: 'JetBrains Mono', monospace; }"
    f".stTabs [data-baseweb='tab'] p {{ font-size:var(--lc-text-small); color: {COLOR['text_muted']}; }}"
    f".stTabs [aria-selected='true'] p {{ color: {_ACCENT} !important; font-weight: 700; }}"
    f".stTabs [data-baseweb='tab-highlight'] {{ background-color: {_ACCENT}; }}"
    # Segmented controls (form window / grade window) follow the same rule.
    f'div[data-testid="stSegmentedControl"] button[aria-checked="true"] {{ color: {_ACCENT} !important; }}'
    "</style>",
    unsafe_allow_html=True,
)

def _ordinal(n):
    """1 -> st, 2 -> nd, 3 -> rd, 11-13 -> th. Used for percentile ranks.

    Defined UP HERE, not down with the other helpers: the Player of the
    Day block runs at module level (this view is a script, not a
    function), so a definition further down the file would not exist yet
    when that block calls it.
    """
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# _SB_URL used to live here: one hardcoded scoreboard host, which was
# the exact path wnba_precompute documents as 403 from cloud IP
# ranges. It was already blocked when it was written. The page never
# said so, because _live_overrides swallows failures by design, so
# live scores and the 75s auto-refresh were both dead in silence.
#
# The mirror chain lives in engines/espn_wnba.py and the pipeline
# reads the same one. Do not put a URL back in this file.
from engines.espn_wnba import live_scores as _live_scores

# HEADER FIRST, TOOLBAR SECOND.
#
# sync_latest_button() used to run up at import time, before this line,
# so Streamlit painted the sync control and the tab strip at the very top
# and pushed the page title down behind them — roughly 150px of empty
# black above the only element that tells you what page you're on, and on
# a phone the title landed below the fold entirely.
#
# Nothing about the button changed; it just renders after the header now.
page_header("WNBA Analytics", "Live season coverage — game & prop research",
            eyebrow="LIVE", align="left")
sync_latest_button(key="sync_wnba", include_data_package=True)


# Shared availability rule — the same one the Props, Defense and Player
# of the Day boards use, so one page can't disagree with another about
# who is playing.
from engines.wnba_props import (availability as _availability,
                                likely_starters as _likely_starters,
                                league_reference_date as _ref_date)


# CACHED. This is the biggest page on the site and its slate JSON was
# being re-read and re-parsed from disk on EVERY widget interaction —
# Streamlit re-runs the whole script each time you touch a control. The
# other views were cached in an earlier pass and this one was missed.
# The file only changes when the nightly build publishes.
#
# ROUTED THROUGH slate_guard. WNBA_Props and WNBA_Defense were moved
# behind the guard when the stale-slate bug was found; this page — the
# main WNBA board, the one those two hang off — was left reading the
# file raw, so the headline board could still present a night already
# played as tonight's while its two sub-pages correctly refused to.
#
# The _REF machinery below is NOT a substitute and is not being replaced:
# it anchors "has she played recently" to the newest game in the data,
# which is a different question from "is this slate tonight's". Both are
# needed. A slate from three nights ago produces internally consistent
# availability and a completely wrong board.
@st.cache_data(ttl=900, show_spinner=False)
def _load_games():
    games, slate_date, is_current = load_slate("wnba")
    if not games:
        # Distinguishes "guard rejected it" from "file is gone" for the
        # caller: None means no board at all, and the note says why.
        return None, None, slate_date
    return games, slate_guard_generated_at("wnba"), slate_date


@st.cache_data(ttl=60, max_entries=4, show_spinner=False)
def _live_overrides():
    """Live scores for tonight, or {} — shared across sessions and
    refreshed at most once a minute.

    All the work is in engines/espn_wnba.live_scores(), which tries every
    known mirror and returns {} rather than raising. Keeping the fetch
    there rather than here is the whole point of the change: this file
    used to hold its own copy pointed at a blocked host.

    The mirrors are proven from GitHub Actions, not from Render — a
    different cloud range, and ESPN blocks by range. Worst case every
    mirror is blocked here too and this returns {}, which is exactly what
    the old single-host version returned on every single call.
    """
    return _live_scores()


games, generated_at, slate_date = _load_games()

# Reference point for "has she played recently". Anchored to the newest
# game in the data rather than the wall clock, because the nightly WNBA
# fetch is allowed to fail without failing the build — so a stale slate
# would otherwise flag every player in the league as absent. See
# engines.wnba_props.league_reference_date.
_REF = _ref_date(games)
if _REF:
    from datetime import date as _date
    _stale_days = (_date.today() - _REF).days
    # 10 days, not 3, and the wording no longer blames the fetch.
    #
    # The first version fired at 3 days and said "the nightly fetch may be
    # failing" — which it announced during the All-Star break (Jul 23-27,
    # last game Jul 22), when the fetch was working perfectly and the
    # league simply wasn't playing. A confident wrong diagnosis is worse
    # than no message.
    #
    # The league schedules real gaps: All-Star in late July, and the FIBA
    # World Cup break Aug 31 - Sep 16, which is roughly SIXTEEN days. Any
    # threshold below that will cry wolf every September. 10 days clears
    # All-Star, and during FIBA this states the gap as a fact without
    # asserting a cause.
    if _stale_days > 10:
        st.info(
            f"No WNBA games in this data since {_REF} ({_stale_days} days). "
            f"That's expected during a scheduled league break \u2014 All-Star in "
            f"late July, the FIBA World Cup break Aug 31 \u2013 Sep 16 \u2014 and can "
            f"also mean the nightly fetch hasn't run. Availability below is "
            f"judged against {_REF} rather than today, so nobody is falsely "
            f"marked out either way."
        )

if games is None:
    # A rejected slate is a different fact from an unbuilt engine, and
    # reads completely differently to a subscriber: one is "not ready
    # yet", the other is "tonight's data never arrived". Saying the
    # first when the second is true is what hid this for days.
    _note = staleness_note("wnba")
    if slate_date or _note:
        st.warning(_note)
        footer()
        st.stop()
    st.markdown(card_open("\U0001F3C0 WNBA engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-body-lg); line-height:1.7;">'
        f'WNBA coverage is in active development on the same standard as the MLB engine: '
        f'every number traced to a real, verifiable source \u2014 no placeholders, no estimates.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(card_close(), unsafe_allow_html=True)
    footer()
    st.stop()

if not games:
    st.info("No WNBA games on today's schedule \u2014 likely a league off-day or break.")

if games:
    from engines.player_of_the_day import get_wnba_player_of_the_day
    _fw_opts = {"L5": "l5", "L10": "l10", "L15": "l15", "L25": "l25"}
    _fw_choice = st.segmented_control(
        "Form window", list(_fw_opts.keys()), default="L15",
        key="wnba_potd_window", label_visibility="collapsed",
    )
    _fw_label = _fw_choice or "L5"
    wnba_pick, _wnba_candidates, wnba_potd_error = get_wnba_player_of_the_day(
        form_window=_fw_opts.get(_fw_label, "l5")
    )
    if wnba_pick:
        # NO STAR. It was the only emoji on any board on the site, and
        # it sat on a real model output — a ranked recent-form pick with
        # published percentiles behind it — making it read like a social
        # post rather than a result. MLB's Player of the Day carries no
        # decoration; this one now matches.
        st.markdown(card_open(f'Player of the Day \u2014 {wnba_pick["name"]} ({wnba_pick["team"]})'),
                    unsafe_allow_html=True)
        st.caption("This app's best real recent-form pick, by the numbers \u2014 not a prediction, not a lock.")
        potd_badges = (
            badge(f'{wnba_pick["pos"] or "?"}', "neutral")
            + badge(f'vs {wnba_pick["opponent"]}', "neutral")
            + badge(f'{_fw_label} PRA {wnba_pick["form_pra"]}', "accent")
        )
        st.markdown(f'<div>{potd_badges}</div>', unsafe_allow_html=True)
        # TILE HIERARCHY.
        #
        # Four numbers used to sit at one size in one colour, so nothing
        # told you which to read — and the stat the pick is actually
        # RANKED on (form PRA) was the smallest thing on the row, tucked
        # into a badge. It leads now, in the page accent, with season PRA
        # and the delta as its supporting line.
        #
        # The three component averages carry real league percentiles
        # (engines/wnba_props.percentile_of) computed from every
        # qualified player's season in the same nightly file. Where a
        # percentile can't be computed honestly — stat missing, or too
        # few qualified players — the rank is simply absent. There is no
        # fallback 50th.
        from engines.wnba_props import league_percentiles as _lp, percentile_of as _pct
        _dist = _lp()
        _season_pra = wnba_pick.get("season_pra")
        _form_pra = wnba_pick.get("form_pra")
        _pra_delta = (round(_form_pra - _season_pra, 1)
                      if _form_pra is not None and _season_pra is not None else None)
        _delta_txt = ""
        if _season_pra is not None:
            _delta_txt = f'SEASON {_season_pra}'
            if _pra_delta:
                _delta_txt += f' · {_pra_delta:+.1f}'
        st.markdown(
            f'<div style="margin-top:var(--lc-space-md);">'
            f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-tiny); '
            f'letter-spacing:0.16em; color:{_ACCENT}; font-weight:700;">{_fw_label} PRA</div>'
            # THE VALUE IS NOT THE PAGE ACCENT.
            #
            # kc_theme's own rule is "labels are text_muted, values are
            # text, headings are gold" — colour on a number has to mean
            # something. A hero figure painted in the sport's identity
            # colour reads as a rating, when 30.5 is just a number. It
            # still leads: it is the largest, heaviest thing in the card.
            # The eyebrow above it keeps the accent, because marking
            # WHOSE page this is what the sport colour is for.
            f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-hero); '
            f'font-weight:800; color:{COLOR["text"]}; line-height:1.1;">'
            f'{_form_pra if _form_pra is not None else "N/A"}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-caption); '
            f'color:{COLOR["text_muted"]};">{_delta_txt}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        _rows = ""
        for _lbl, _val, _key in (("PPG", wnba_pick.get("form_ppg"), "ppg"),
                                 ("RPG", wnba_pick.get("form_rpg"), "rpg"),
                                 ("APG", wnba_pick.get("form_apg"), "apg")):
            _p = _pct(_key, _val, _dist)
            # Bar width IS the percentile — no bar at all when there
            # isn't one, rather than an empty rail implying zero.
            if _p is not None:
                _rank = (f'<span style="font-family:\'JetBrains Mono\',monospace; '
                         f'font-size:var(--lc-text-caption); color:{COLOR["stat_high"]};">'
                         f'{_p}{_ordinal(_p)}</span>')
                _bar = (f'<div style="height:3px; background:{COLOR["surface_raised"]}; '
                        f'border-radius:2px; margin-top:3px;">'
                        f'<div style="height:3px; width:{_p}%; background:{COLOR["stat_high"]}; '
                        f'border-radius:2px;"></div></div>')
            else:
                _rank, _bar = "", ""
            _rows += (
                f'<div style="margin-top:var(--lc-space-sm);">'
                f'<div style="display:flex; justify-content:space-between; align-items:baseline;">'
                f'<span style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-tiny); '
                f'letter-spacing:0.12em; color:{COLOR["text_muted"]};">{_lbl}</span>'
                f'<span><span style="font-family:\'JetBrains Mono\',monospace; '
                f'font-size:var(--lc-text-body-lg); font-weight:700; color:{COLOR["text"]};">'
                f'{_val if _val is not None else "N/A"}</span> {_rank}</span>'
                f'</div>{_bar}</div>')
        st.markdown(f'<div style="max-width:420px;">{_rows}</div>', unsafe_allow_html=True)
        if _dist:
            st.caption(
                "Percentile = this player's real season average ranked against every "
                "WNBA player with 5+ real games in the same nightly file. Measured, not modelled."
            )

        # PROJECTED LINE FOR TONIGHT, shown beside the recent averages
        # it's built from so the adjustment is visible rather than
        # implied. The delta on each metric IS the opponent-defense
        # factor made legible: a positive delta means this matchup helps
        # her, negative means it doesn't.
        _pp, _pr, _pa = (wnba_pick.get("proj_pts"), wnba_pick.get("proj_reb"),
                         wnba_pick.get("proj_ast"))
        # PROJECTION ALWAYS SHOWS ITS NUMBERS.
        #
        # An earlier pass hid this whole block when the opponent-defense
        # factor rounded to 1.00, on the reasoning that the projection is
        # then arithmetically identical to the form averages above and
        # the tiles read as a duplicate render. That was the wrong call:
        # it removed the tonight-facing numbers — PTS, REB, AST and the
        # adjusted PRA — which are the reason anyone opens this card. A
        # neutral matchup is INFORMATION ("this defense doesn't move
        # her"), not a reason to show nothing.
        #
        # So the numbers always render, and the factor is stated on the
        # label instead: x0.998 reads as neutral, x1.07 reads as a boost,
        # and the row underneath says which. Nothing is hidden and
        # nothing is duplicated without explanation.
        _fac = wnba_pick.get("def_factor")
        _fac_txt = f'\u00d7{_fac:.3f}'.rstrip("0").rstrip(".") if _fac is not None else ""
        _neutral = _fac is not None and round(float(_fac), 2) == 1.00
        if any(v is not None for v in (_pp, _pr, _pa)):
            _tag = (f'<span style="color:{COLOR["text_faint"]};">{_fac_txt}'
                    + (" \u00b7 neutral matchup" if _neutral else "") + '</span>')
            st.markdown(
                f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-tiny); '
                f'letter-spacing:0.16em; color:{_ACCENT}; font-weight:700; '
                f'margin-top:var(--lc-space-lg);">PROJECTED TONIGHT &nbsp;{_tag}</div>',
                unsafe_allow_html=True)

            _proj_rows = ""
            for _lbl, _proj, _base in (
                    ("PTS", _pp, wnba_pick.get("form_ppg")),
                    ("REB", _pr, wnba_pick.get("form_rpg")),
                    ("AST", _pa, wnba_pick.get("form_apg")),
                    ("PRA", wnba_pick.get("adj_pra"), wnba_pick.get("form_pra"))):
                if _proj is None:
                    _shown, _delta = "N/A", ""
                else:
                    _shown = f"{_proj}"
                    _d = round(_proj - _base, 1) if _base is not None else None
                    if _d:
                        _dc = COLOR["accent"] if _d > 0 else COLOR["warn"]
                        _delta = (f'<span style="font-family:\'JetBrains Mono\',monospace; '
                                  f'font-size:var(--lc-text-caption); color:{_dc};"> {_d:+.1f}</span>')
                    else:
                        # Explicitly "same as her form" rather than a
                        # blank, so a zero delta doesn't look like a
                        # missing one.
                        _delta = (f'<span style="font-family:\'JetBrains Mono\',monospace; '
                                  f'font-size:var(--lc-text-caption); '
                                  f'color:{COLOR["text_faint"]};"> \u2014</span>')
                _proj_rows += (
                    f'<div style="display:flex; justify-content:space-between; '
                    f'align-items:baseline; margin-top:var(--lc-space-sm);">'
                    f'<span style="font-family:\'JetBrains Mono\',monospace; '
                    f'font-size:var(--lc-text-tiny); letter-spacing:0.12em; '
                    f'color:{COLOR["text_muted"]};">{_lbl}</span>'
                    f'<span><span style="font-family:\'JetBrains Mono\',monospace; '
                    f'font-size:var(--lc-text-body-lg); font-weight:700; '
                    f'color:{COLOR["text"]};">{_shown}</span>{_delta}</span></div>')
            st.markdown(f'<div style="max-width:420px;">{_proj_rows}</div>',
                        unsafe_allow_html=True)
            st.caption(
                f'Projection = her real last-{_fw_label[1:]}-game averages \u00d7 the same '
                f'{_fac}\u00d7 opponent-defense factor used to rank her'
                + (" — this opponent allows almost exactly the slate average, so "
                   "tonight's line is her recent form essentially unchanged. "
                   if _neutral else ". ")
                + 'Both inputs are measured, not modelled \u2014 but this is an '
                  'estimate, not a forecast with a track record: the Calibration '
                  'page grades whether she records an extra-base-equivalent, not '
                  'whether she hits these numbers.'
            )

        st.caption(
            f'Real games played this season: {wnba_pick["gp"]} \u2014 ranked by real last-{_fw_label[1:]}-game PRA '
            f'(points+rebounds+assists) \u00d7 opponent-defense factor '
            f'({wnba_pick.get("def_factor", 1.0)}\u00d7: opponent allows {wnba_pick.get("opp_pa_pg") or "?"} PPG '
            f'vs a slate average of {wnba_pick.get("slate_pa_avg") or "?"}, capped \u00b110%), '
            f'season PRA as tiebreaker.'
        )
        st.markdown(card_close(), unsafe_allow_html=True)
    elif wnba_potd_error:
        st.caption(f"Player of the Day: {wnba_potd_error}")


def _hex(c, fallback):
    if c and isinstance(c, str) and len(c) in (3, 6):
        return f"#{c}"
    return fallback


def _fmt(v):
    return "\u2014" if v is None else v



# (label, key, direction) — direction says which side of the row is the
# BETTER number, and it's the whole basis of the new colouring:
#   "high" larger wins   "low" smaller wins   None neither (context row)
#
# Colour used to encode team identity: orange meant Connecticut, blue
# meant Dallas. You already know that from which column the number is
# in, so the colour carried no information and you had to read all
# eleven rows to work out who was better at anything. Now brightness
# means advantage and the team colour survives as a small edge marker,
# so a sweep is visible at a glance — and "points against", where lower
# wins and the winner flips sides, is handled by the same rule instead
# of asking you to remember that it's inverted.
TAPE_ROWS = [
    ("Record", "record", "record"), ("Home / Road", None, None),
    ("Last 10", "l10", "record"),
    ("Points For / G", "pf_pg", "high"), ("Points Against / G", "pa_pg", "low"),
    # Neither team "wins" the shared total of their own game — it's a
    # totals-market context row, so it stays neutral rather than being
    # forced into a winner.
    ("Avg Game Total", "avg_total", None),
    ("FG %", "fg_pct", "high"), ("3P %", "tp_pct", "high"),
    ("Rebounds / G", "reb_g", "high"), ("Assists / G", "ast_g", "high"),
    ("Turnovers / G", "to_g", "low"),
]


def _win_pct(rec):
    """Win rate from a 'W-L' record string, or None if it isn't one.

    Used only to decide which side of a Record / Last 10 row is ahead.
    Returns None for anything unparseable so the row simply renders
    neutral rather than guessing a winner.
    """
    try:
        w, l = str(rec).replace("\u2013", "-").split("-")[:2]
        w, l = int(w), int(l)
        return w / (w + l) if (w + l) else None
    except Exception:
        return None


def _num(v):
    try:
        return float(str(v).replace("%", ""))
    except Exception:
        return None


def _advantage(av, hv, direction):
    """Returns (away_is_better, home_is_better).

    Both False on a tie, on a neutral row, or whenever either value is
    missing or unparseable — an unknown is never shown as a win. This is
    the same rule the rest of the app follows: no data means no claim.
    """
    if not direction:
        return False, False
    a = _win_pct(av) if direction == "record" else _num(av)
    h = _win_pct(hv) if direction == "record" else _num(hv)
    if a is None or h is None or a == h:
        return False, False
    better_is_larger = direction in ("high", "record")
    a_wins = (a > h) if better_is_larger else (a < h)
    return a_wins, not a_wins

PROP_TABS = [
    ("Points", "ppg", "l5_ppg", "l10_ppg", "h2h_ppg"),
    ("Rebounds", "rpg", "l5_rpg", "l10_rpg", "h2h_rpg"),
    ("Assists", "apg", "l5_apg", "l10_apg", "h2h_apg"),
    ("Threes", "tpm", "l5_tpm", "l10_tpm", "h2h_tpm"),
    ("PRA", "pra", "l5_pra", "l10_pra", "h2h_pra"),
    ("Pts+Reb", "pr", "l5_pr", "l10_pr", "h2h_pr"),
    ("Pts+Ast", "pa", "l5_pa", "l10_pa", "h2h_pa"),
    ("Reb+Ast", "ra", "l5_ra", "l10_ra", "h2h_ra"),
    ("Stocks", "stocks", "l5_stocks", "l10_stocks", "h2h_stocks"),
    ("Volume", "fga", "l5_fga", "l10_fga", "h2h_fga"),
]
TAB_NOTES = {
    "Pts+Reb": "Points + rebounds combined \u2014 a standard sportsbook combo market (PR).",
    "Pts+Ast": "Points + assists combined \u2014 a standard sportsbook combo market (PA).",
    "Reb+Ast": "Rebounds + assists combined \u2014 a standard sportsbook combo market (RA).",
    "Stocks": "Stocks = steals + blocks combined \u2014 the STL/BLK columns show the season split.",
    "Volume": "FGA per game \u2014 shot volume drives points props; FTA and TO shown for context.",
}


def _render_slate():
    live = _live_overrides()
    any_live = False

    # Grade window — Season is the checklist that's been running;
    # L25/L15/L10/L5 re-grade every game on that many recent REAL
    # finals (scoring form, differential, totals, record). FG% and
    # TO/G stay season-based — ESPN has no per-game shooting logs and
    # this page won't fake them.
    _gw_opts = {"Season": "season", "L25": "l25", "L15": "l15", "L10": "l10", "L5": "l5"}
    _gw_choice = st.segmented_control(
        "Grade window", list(_gw_opts.keys()), default="Season",
        key="wnba_grade_window", label_visibility="collapsed",
    )
    _gw_label = _gw_choice or "Season"
    _gw = _gw_opts.get(_gw_label, "season")

    for gi, g in enumerate(games):
        away, home = g.get("away", "TBD"), g.get("home", "TBD")
        a_col = _hex(g.get("away_color"), COLOR["stat_high"])
        h_col = _hex(g.get("home_color"), COLOR["stat_high"])

        status = g.get("status", "scheduled")
        scoreline = g.get("final") or g.get("score")
        detail = None
        lv = live.get((away, home))
        if lv:
            status = lv.get("status", status)
            scoreline = lv.get("scoreline", scoreline)
            detail = lv.get("detail")
        if status == "in progress":
            any_live = True

        st.markdown(card_open("", ""), unsafe_allow_html=True)
        st.markdown(
            f'<div style="display:flex; justify-content:center; align-items:baseline; gap:14px; '
            f'margin:var(--lc-space-hair) var(--lc-space-none) var(--lc-space-hair) var(--lc-space-none); flex-wrap:wrap;">'
            f'<span style="font-size:var(--lc-text-title); font-weight:800; color:{a_col};">{away}</span>'
            f'<span style="font-size:var(--lc-text-small); color:{COLOR["text_faint"]};">@</span>'
            f'<span style="font-size:var(--lc-text-title); font-weight:800; color:{h_col};">{home}</span>'
            f'</div>'
            f'<div style="text-align:center; font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; margin-bottom:var(--lc-space-md);">'
            f'{g.get("arena", "")} \u00b7 {g.get("time_et", "TBD")} ET</div>',
            unsafe_allow_html=True,
        )

        status_style = {"postponed": "bad", "final": "good", "in progress": "accent"}.get(status, "neutral")
        center = badge(status.upper(), status_style)
        if detail and status == "in progress":
            center += badge(detail, "accent")
        if scoreline:
            center += badge(scoreline, "accent")
        if g.get("line"):
            center += badge(f'Line: {g["line"]}', "neutral")
        st.markdown(f'<div style="text-align:center;">{center}</div>', unsafe_allow_html=True)

        rows_html = ""
        for label, key, direction in TAPE_ROWS:
            if key is None:  # Home / Road split row
                av = f'{_fmt(g.get("away_home_record"))} / {_fmt(g.get("away_road_record"))}'
                hv = f'{_fmt(g.get("home_home_record"))} / {_fmt(g.get("home_road_record"))}'
                if "\u2014 / \u2014" in (av, hv):
                    continue
            else:
                av, hv = _fmt(g.get(f"away_{key}")), _fmt(g.get(f"home_{key}"))
                if av == "\u2014" and hv == "\u2014":
                    continue
            # BRIGHT = BETTER. The winning side gets full-strength text
            # and a 2px team-coloured edge marker; the losing side is
            # dimmed. On a tie, a context row, or a missing value both
            # sides render neutral — an unknown must never look like a
            # win.
            a_win, h_win = _advantage(av, hv, direction)
            a_style = (f'color:{COLOR["text"]}; font-weight:700;' if a_win
                       else f'color:{COLOR["text_muted"]}; font-weight:400;')
            h_style = (f'color:{COLOR["text"]}; font-weight:700;' if h_win
                       else f'color:{COLOR["text_muted"]}; font-weight:400;')
            a_mark = (f'border-right:2px solid {a_col}; padding-right:8px;' if a_win
                      else 'border-right:2px solid transparent; padding-right:8px;')
            h_mark = (f'border-left:2px solid {h_col}; padding-left:8px;' if h_win
                      else 'border-left:2px solid transparent; padding-left:8px;')
            rows_html += (
                f'<div style="display:grid; grid-template-columns:1fr auto 1fr; gap:10px; '
                f'padding:var(--lc-space-xs) var(--lc-space-none); border-bottom:1px solid {COLOR["surface_raised"]};">'
                f'<div style="text-align:right; font-family:\'JetBrains Mono\',monospace; '
                f'font-size:var(--lc-text-body); {a_style} {a_mark}">{av}</div>'
                f'<div style="text-align:center; font-size:var(--lc-text-tiny); color:{COLOR["text_faint"]}; '
                f'text-transform:uppercase; letter-spacing:0.06em; min-width:120px; '
                f'align-self:center;">{label}</div>'
                f'<div style="text-align:left; font-family:\'JetBrains Mono\',monospace; '
                f'font-size:var(--lc-text-body); {h_style} {h_mark}">{hv}</div>'
                f'</div>')
        if rows_html:
            st.markdown(f'<div style="max-width:560px; margin:var(--lc-space-md) auto var(--lc-space-none) auto;">{rows_html}</div>',
                        unsafe_allow_html=True)

        hh = g.get("h2h")
        # .get(), not [] — this block used to index hh["summary"] and
        # hh["meetings"] directly, so a games.json written by any build
        # whose team_h2h shape differed by one key raised a KeyError that
        # escaped the whole view. Not a degraded H2H strip: the entire
        # WNBA page fell to app.py's generic "something went wrong"
        # error, taking the slate, the props and the Player of the Day
        # with it. A supplementary line must never be able to do that.
        if hh and hh.get("summary"):
            scorelines = " \u00b7 ".join(hh.get("scorelines") or [])
            _meetings = hh.get("meetings")
            _meet_txt = (f' ({_meetings} meetings)'
                         if _meetings is not None else "")
            st.markdown(
                f'<div style="text-align:center; margin-top:var(--lc-space-md);">'
                f'<span style="display:inline-block; padding:var(--lc-space-sm) var(--lc-space-lg); border-radius:var(--lc-radius-md); '
                f'background:{COLOR["surface_raised"]}; font-size:var(--lc-text-small); color:{COLOR["text"]};">'
                f'<b>Season Series:</b> {hh["summary"]} \u00b7 '
                f'Avg total in H2H: <b>{_fmt(hh.get("avg_total"))}</b>'
                f'{_meet_txt}</span>'
                f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]}; margin-top:var(--lc-space-xs);">{scorelines}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="text-align:center; margin-top:var(--lc-space-md);">'
                f'<span style="display:inline-block; padding:var(--lc-space-sm) var(--lc-space-lg); border-radius:var(--lc-radius-md); '
                f'background:{COLOR["surface_raised"]}; font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                f'First meeting of the season \u2014 no head-to-head data exists yet, '
                f'and this page will not invent any.</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown(card_close(), unsafe_allow_html=True)

        grades = grade_wnba_matchup(g, window=_gw)
        _gw_note = "" if _gw == "season" else (
            f" Graded on the {_gw_label} window \u2014 scoring form, differential, totals, and "
            f"record from that many recent real finals; FG%/TO remain season stats."
        )
        if _gw != "season" and not g.get("away_form"):
            _gw_note = (" Windowed form isn't in the current data file yet \u2014 showing season "
                        "values until the next nightly build.")
        render_matchup_grades_card(
            grades,
            subtitle=("This app's own signal checklist from real team scoring, shooting, and "
                      "turnover rates \u2014 there's no starting-pitcher analog in basketball, so this "
                      "is graded on team form. Formula documented in "
                      "engines/matchup_grades_intl.py. Not calibrated probabilities." + _gw_note),
            source_line="Source: real WNBA box-score-derived team stats.",
            key=f'wnba_{gi}_{away}_{home}',
            accent=_ACCENT,
        )

        if g.get("away_players") or g.get("home_players"):
            # Streamlit runs everything inside a collapsed expander — it
            # only hides the OUTPUT. With 10 prop tabs x 2 styled tables
            # per game, a 6-game slate was building ~120 tables on every
            # single interaction, including games nobody opened. This
            # checkbox gates the work itself: nothing below runs until
            # you ask for that game, which is the single biggest speed
            # win on the page.
            _open_key = f"wnba_props_open_{gi}"
            _show_props = st.checkbox(
                f'\U0001F3C0 Prop research \u2014 {away} @ {home}',
                key=_open_key, value=False,
            )
            if _show_props:
                st.markdown(
                    f'<div class="pf-card-subtitle" style="color:{COLOR["text_muted"]}; margin-bottom:var(--lc-space-xs);">'
                    f'Real box-score data \u00b7 Season / L5 / L10 = averages over all, last 5, and last 10 '
                    f'games played \u00b7 vs OPP = this player\'s real averages in this season\'s meetings '
                    f'with tonight\'s opponent (H2H GP = how many) \u00b7 small samples are shown as small '
                    f'samples \u2014 judge accordingly</div>',
                    unsafe_allow_html=True,
                )
                tabs = st.tabs([t[0] for t in PROP_TABS])

                # ---- Player Trend: game-by-game bars + hit-rate chips ----
                st.markdown(
                    f'<div style="font-size:var(--lc-text-small); font-weight:700; color:{COLOR["text"]}; '
                    f'margin:var(--lc-space-md) var(--lc-space-none) var(--lc-space-hair) var(--lc-space-none);">Player Trend</div>'
                    f'<div class="pf-card-subtitle">Game-by-game results with the line drawn in \u2014 '
                    f'chips show how many games cleared it per window. Real box scores; the log carries '
                    f'the last 25 games.</div>',
                    unsafe_allow_html=True,
                )
                _pt_pool = {}
                for _side in ("away", "home"):
                    for _pp in g.get(f"{_side}_players") or []:
                        if _pp.get("name"):
                            _pt_pool[f'{_pp["name"]} \u2014 {g.get(_side, "")}'] = _pp
                _pt_pick = st.selectbox(
                    "Player trend", ["Select a player\u2026"] + list(_pt_pool.keys()),
                    key=f"wnba_trend_pick_{gi}", label_visibility="collapsed",
                )
                if _pt_pick in _pt_pool:
                    _pl = _pt_pool[_pt_pick]
                    _plog = _pl.get("log") or []
                    if not _plog:
                        st.caption("Per-game logs arrive with the next data build \u2014 "
                                   "press \u27f3 Sync latest up top to pull it.")
                    else:
                        _pt_stat = st.segmented_control(
                            "Stat", ["Points", "Rebounds", "Assists", "PRA", "3PM",
                                     "Stocks", "Minutes"],
                            default="Points", key=f"wnba_trend_stat_{gi}",
                            label_visibility="collapsed",
                        ) or "Points"
                        _pt_win = st.segmented_control(
                            "Window", ["L25", "L15", "L10", "L5"],
                            default="L10", key=f"wnba_trend_win_{gi}",
                            label_visibility="collapsed",
                        ) or "L10"
                        # Line options follow the STAT. A fixed list meant
                        # switching Points -> 3PM kept a 14.5 line, which is
                        # meaningless for threes; and because the widget key
                        # didn't change with the stat, Streamlit held onto
                        # the stale value. Keying by stat gives each one its
                        # own remembered choice.
                        _LINE_SETS = {
                            "Points": (["9.5", "14.5", "19.5", "24.5"], "14.5"),
                            "Rebounds": (["3.5", "5.5", "7.5", "9.5"], "5.5"),
                            "Assists": (["1.5", "2.5", "3.5", "5.5"], "2.5"),
                            "PRA": (["14.5", "19.5", "24.5", "29.5"], "19.5"),
                            "3PM": (["0.5", "1.5", "2.5", "3.5"], "1.5"),
                            "Stocks": (["0.5", "1.5", "2.5", "3.5"], "1.5"),
                            "Minutes": (["19.5", "24.5", "29.5", "33.5"], "29.5"),
                        }
                        _opts, _dflt = _LINE_SETS.get(_pt_stat, (["9.5", "14.5"], "14.5"))
                        _pt_line = float(st.segmented_control(
                            "Line", _opts, default=_dflt,
                            key=f"wnba_trend_line_{gi}_{_pt_stat}",
                            label_visibility="collapsed",
                        ) or _dflt)
                        _pt_key = {"Points": "pts", "Rebounds": "reb",
                                   "Assists": "ast", "PRA": "pra", "3PM": "tpm",
                                   "Stocks": "stocks", "Minutes": "min"}[_pt_stat]
                        # Stocks (steals + blocks) is derived per game
                        # rather than stored, so it works on any log.
                        def _stat_of(gl):
                            if _pt_key == "stocks":
                                return (gl.get("stl") or 0) + (gl.get("blk") or 0)
                            return gl.get(_pt_key) or 0
                        _pt_all = [_stat_of(gl) for gl in _plog]
                        window_hit_chips(_pt_all, _pt_line, _pt_win,
                                         windows=("L25", "L15", "L10", "L5"))
                        _n = {"L25": 25, "L15": 15, "L10": 10, "L5": 5}[_pt_win]
                        _sub = _plog[-_n:]
                        # Short date labels — the opponent shows as a
                        # LOGO under each bar, same as the MLB charts,
                        # so long team names never crowd the axis.
                        _lbls, _seen, _logos = [], {}, []
                        for gl in _sub:
                            _b = str(gl.get("date") or "")[5:]
                            _seen[_b] = _seen.get(_b, 0) + 1
                            _lbls.append(_b if _seen[_b] == 1 else f"{_b} ({_seen[_b]})")
                            # Prefer ESPN's own URL; the id-built path
                            # 404s for some teams and rendered a "?".
                            _logos.append(gl.get("opp_logo")
                                          or logo_url_by_id(gl.get("opp_id")))
                        _vals = [_stat_of(gl) for gl in _sub]
                        render_trend_bars(_lbls, _vals, _pt_stat, _pt_line,
                                          logos=_logos)
                        _avg = sum(_vals) / len(_vals)
                        st.caption(
                            f"{_pl.get('name')} \u00b7 {_pt_win}: {len(_vals)} games \u00b7 "
                            f"avg {_avg:.1f} {_pt_stat}/game \u00b7 line {_pt_line} \u00b7 "
                            f"teal bars cleared it, red didn't \u00b7 real box scores."
                        )
                for tab, (label, season_k, l5_k, l10_k, h2h_k) in zip(tabs, PROP_TABS):
                    with tab:
                        # SORT CONTROL.
                        #
                        # These tables are rendered as HTML (render_html_table)
                        # rather than st.dataframe, deliberately — st.dataframe
                        # brings drag-to-reorder columns that can't be disabled,
                        # which on a phone turns any scroll into a column
                        # shuffle. The trade was losing click-to-sort headers,
                        # and this control gives that back without giving the
                        # scrolling problem back with it.
                        #
                        # One control per tab, governing BOTH team tables under
                        # it: sorting one team by L10 and leaving the other in
                        # role order would make the two halves of the same
                        # matchup incomparable.
                        _sort_opts = ["Role", "Season", "L5", "L10", "vs OPP", "MIN"]
                        _sort_by = st.segmented_control(
                            "Sort", _sort_opts, default="Role",
                            key=f"wnba_sort_{gi}_{label}",
                            label_visibility="collapsed",
                        ) or "Role"
                        for side, col in (("away", a_col), ("home", h_col)):
                            plist = g.get(f"{side}_players")
                            if not plist:
                                continue
                            st.markdown(
                                f'<div style="display:inline-block; padding:var(--lc-space-hair) var(--lc-space-md); border-radius:var(--lc-radius-sm); '
                                f'background:{col}22; border:1px solid {col}55; color:{col}; '
                                f'font-weight:700; font-size:var(--lc-text-caption); text-transform:uppercase; '
                                f'letter-spacing:0.05em; margin:var(--lc-space-lg) var(--lc-space-none) var(--lc-space-xs) var(--lc-space-none);">{g.get(side, "")}</div>',
                                unsafe_allow_html=True,
                            )
                            rows = []
                            # Derived from RECENT minutes among available
                            # players — the WNBA feed publishes no starter
                            # flag. See likely_starters for why recent and
                            # not season minutes.
                            _starters = _likely_starters(plist, today=_REF)
                            for p in plist:
                                pos = p.get("pos") or ""
                                # Flag, don't hide. This is the full slate
                                # roster rather than a pick list, so a
                                # player who hasn't appeared recently is
                                # still worth seeing — but her Season/L5/L10
                                # numbers describe a month ago, and without
                                # a marker they read as current form.
                                # Boards that actually PICK players
                                # (Props, Defense, Player of the Day) drop
                                # her outright; this one labels her.
                                _ok, _why, _days = _availability(p, today=_REF)
                                pname = f'{p.get("name")} \u00b7 {pos}' if pos else p.get("name")
                                if not _ok:
                                    pname = f'\u26a0 {pname}'
                                _pid = p.get("pid") or p.get("id")
                                _is_starter = _pid in _starters if _starters else False
                                row = {
                                    "Player": pname,
                                    # Blank rather than "BENCH" when the
                                    # inference couldn't run at all —
                                    # unknown shouldn't read as demoted.
                                    # ESPN's own wording when it has one
                                    # ("Out", "Day-To-Day"), otherwise the
                                    # inferred label. A real status beats a
                                    # guess, and saying which is which
                                    # keeps the two distinguishable.
                                    "Status": (p.get("today_status")
                                               or p.get("injury_status")
                                               or (f'OUT {_days}d' if (not _ok and _days)
                                                   else ("OUT" if not _ok else ""))),
                                    "Role": ("OUT" if not _ok
                                             else "START" if _is_starter
                                             else ("BENCH" if _starters else "")),
                                    "GP": p.get("gp"), "MIN": p.get("min"),
                                    "Season": p.get(season_k),
                                    "L5": p.get(l5_k), "L10": p.get(l10_k),
                                    "vs OPP": p.get(h2h_k), "H2H GP": p.get("h2h_gp"),
                                }
                                if label == "Stocks":
                                    row["STL"] = p.get("stl")
                                    row["BLK"] = p.get("blk")
                                if label == "Volume":
                                    row["FTA"] = p.get("fta")
                                    row["TO"] = p.get("to")
                                    row["FG%"] = p.get("fg_pct")
                                if label == "Points":
                                    row["FG%"] = p.get("fg_pct")
                                    row["3P%"] = p.get("tp_pct")
                                if label == "Threes":
                                    row["3P%"] = p.get("tp_pct")
                                rows.append(row)
                            # Starters first, then bench, then unavailable —
                            # and within each group by minutes. The table was
                            # in roster order, which put tonight's best bets
                            # anywhere on the list.
                            _order = {"START": 0, "": 1, "BENCH": 1, "OUT": 2}
                            if _sort_by == "Role":
                                rows.sort(key=lambda r: (_order.get(r.get("Role"), 1),
                                                         -(r.get("MIN") or 0)))
                            else:
                                # Sorted by the chosen stat, high to low.
                                #
                                # Two rules that survive every sort mode:
                                # players who are OUT stay at the bottom (a
                                # board must never lead with someone who
                                # isn't playing, however good her numbers
                                # look), and a MISSING value sorts last
                                # rather than as a zero — an unmeasured stat
                                # is not a bad one.
                                def _sort_key(r, _c=_sort_by):
                                    v = r.get(_c)
                                    missing = not isinstance(v, (int, float))
                                    return (1 if r.get("Role") == "OUT" else 0,
                                            1 if missing else 0,
                                            -(v if not missing else 0))
                                rows.sort(key=_sort_key)
                            df = pd.DataFrame(rows)
                            # "Status" is TEXT ("OUT 30d"). It was in this
                            # list, so pd.to_numeric turned it into NaN and
                            # the em-dash pass below printed it as "—" —
                            # the availability flag was computed correctly
                            # and then destroyed one line later. The warning
                            # glyph on the name survived only because it
                            # rides in the Player column.
                            _TEXT_COLS = ("Player", "Status", "Role")
                            num_cols = [c for c in df.columns if c not in _TEXT_COLS]
                            for c in num_cols:
                                df[c] = pd.to_numeric(df[c], errors="coerce")
                            # Render every stat as fixed-format TEXT so
                            # values sit flush under their left-aligned
                            # headers — the grid right-aligns real numbers,
                            # floating them across stretched columns. Safe
                            # for the color gradients: _magnitude_column in
                            # table_style.py coerces each column back to
                            # numeric internally, so color math still runs
                            # on the real values. NaN becomes an em dash in
                            # the DATA rather than relying on Styler na_rep.
                            int_like = ("GP", "H2H GP")
                            for c in num_cols:
                                if c in int_like:
                                    df[c] = df[c].map(lambda v: "\u2014" if pd.isna(v) else str(int(v)))
                                else:
                                    df[c] = df[c].map(lambda v: "\u2014" if pd.isna(v) else f"{v:.1f}")
                            # The Styler already hides its own index (see
                            # table_style._base_styler) — passing hide_index or
                            # column_config on TOP of a Styler makes Streamlit
                            # lay columns out against a different grid than the
                            # styles were computed for, which is exactly the
                            # floating/misaligned column bug. So: hand the
                            # widget the Styler and NOTHING else that touches
                            # column layout.
                            styled = style_stat_table(
                                df, favor_high=["MIN", "Season", "L5", "L10",
                                                "vs OPP", "FG%", "3P%"],
                                gradient=True,
                            )
                            # hide_index: this df is built from a plain
                            # list (line 587), so its index is a throwaway
                            # 0,1,2 RangeIndex — but st.dataframe PINS the
                            # index column, and a frozen column smears
                            # against momentum scrolling in iOS Safari
                            # while the stats scroll under it. The MLB
                            # tables were fixed for this; the WNBA lineup
                            # table was missed. Player name already
                            # identifies the row, so the number adds
                            # nothing but the scrolling artifact.
                            render_html_table(styled,
                                key="wnba_636")
                            # Every other gradient table on the site says
                            # what its colours mean; this one didn't, and
                            # it is the densest table we render. Five
                            # filled tiers look authoritative whether or
                            # not anyone knows what they stand for, so a
                            # table without a key is a table that invites
                            # a confident misread.
                            tier_legend(
                                favor_note="Higher is better \u2014 colour is the "
                                           "player\u2019s grade in that column, "
                                           "against the rest of this table.",
                                caption="vs OPP is this player\u2019s real average in "
                                        "this season\u2019s meetings with tonight\u2019s "
                                        "opponent \u2014 check H2H GP before trusting it.",
                            )
                            note = TAB_NOTES.get(label)
                            if note:
                                st.caption(note)

    return any_live


any_live_now = bool(_live_overrides()) and any(
    (_live_overrides().get((g.get("away", ""), g.get("home", ""))) or {}).get("status") == "in progress"
    for g in games
)

slate = st.fragment(run_every="75s" if any_live_now else None)(_render_slate)
slate()

if generated_at:
    live_note = (" \u00b7 Live scores refresh about every minute while games are in progress."
                 if any_live_now else "")
    st.caption(f"Research data as of {generated_at} ET (nightly pipeline). "
               f"All stats computed from real box scores.{live_note}")

footer()
