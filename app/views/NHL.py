"""NHL — Tonight's Ice.

Hockey is decided in the crease and on the shot clock, so every game
card here leads with those: the goalie duel (starts, crease share,
SV%, GAA, form), shot share, special teams, and the tape.

Through the preseason gap the tab is still live: it shows the real
exhibition slate (labelled as such), counts down to opening night, and
says plainly that research starts with the first regular-season final.

Data: nhl_precompute.py -> data/nhl/games.json via slate_guard("nhl").
"""
import html
from datetime import datetime

import streamlit as st

from styles.kc_theme import page_header, badge, footer, card, COLOR, SPORT_ACCENTS
from engines.live_sync import sync_latest_button
from engines.slate_guard import load_slate, staleness_note, today_for, generated_at
from engines.espn_feed import live_scores
from engines.nhl_rink import (phase, countdown_text, fmt_svp, tape_rows,
                              REGULAR_SEASON_START)

_ACCENT = SPORT_ACCENTS.get("NHL") or COLOR["stat_high"]

page_header("NHL Analytics", "The crease, the shot clock and special teams "
            "\u2014 every game tonight", eyebrow="LIVE", align="left")
sync_latest_button(key="sync_nhl", include_data_package=True)


@st.cache_data(ttl=900, show_spinner=False)
def _load_slate_for(day):
    games, slate_date, current = load_slate("nhl")
    return games, slate_date, current, generated_at("nhl")


@st.cache_data(ttl=60, max_entries=4, show_spinner=False)
def _live(day):
    return live_scores("nhl", day.replace("-", ""))


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _col(g, side):
    c = g.get(f"{side}_color")
    return f"#{c}" if c else COLOR["text"]


def _num(v, nd=1, sfx=""):
    return "\u2014" if v is None else (f"{v:.{nd}f}{sfx}" if isinstance(v, (int, float)) else _esc(v))


def _render_tape(g):
    a, h = g.get("away_profile"), g.get("home_profile")
    if not a and not h:
        st.caption("No regular-season games yet for these teams \u2014 the tape "
                   "starts with their first final.")
        return
    rows = []
    for label, av, hv, hb in tape_rows(a, h):
        if av is None and hv is None:
            continue
        aw = hw = ""
        if hb is not None and isinstance(av, (int, float)) and isinstance(hv, (int, float)) and av != hv:
            better_away = (av > hv) == hb
            aw = f'color:{COLOR["stat_high"]}; font-weight:700;' if better_away else ""
            hw = "" if better_away else f'color:{COLOR["stat_high"]}; font-weight:700;'
        nd = 2 if label.startswith("Goals") or label == "Avg game total" else 1
        fmt = (lambda v: _num(v, nd)) if isinstance(av, (int, float)) or isinstance(hv, (int, float)) else _esc
        rows.append(f'<tr><td style="text-align:right;{aw}">{fmt(av)}</td>'
                    f'<td style="text-align:center; color:{COLOR["text_muted"]}; '
                    f'font-size:var(--lc-text-tiny); text-transform:uppercase; '
                    f'padding:4px 10px;">{label}</td>'
                    f'<td style="text-align:left;{hw}">{fmt(hv)}</td></tr>')
    st.markdown(
        '<div class="lc-tbl-wrap"><table style="width:100%; '
        "font-family:'JetBrains Mono',monospace; font-size:var(--lc-text-small);\">"
        f'<tr><th style="text-align:right; color:{_col(g, "away")};">{_esc(g.get("away_abbr"))} '
        f'\u00b7 {(a or {}).get("gp", 0)} GP</th><th></th>'
        f'<th style="text-align:left; color:{_col(g, "home")};">{_esc(g.get("home_abbr"))} '
        f'\u00b7 {(h or {}).get("gp", 0)} GP</th></tr>' + "".join(rows) + "</table></div>",
        unsafe_allow_html=True)
    notes = [f'{_esc(g.get(s))}: {p["otl_unverified"]} loss(es) could not be checked '
             f'for OT, counted as regulation'
             for s, p in (("away", a or {}), ("home", h or {})) if p.get("otl_unverified")]
    if notes:
        st.caption(" \u00b7 ".join(notes))
    st.caption("Brighter side = better at that line. Shot share = the team's shots "
               "as a share of all shots in its games.")


def _render_goalie_duel(g):
    cols = st.columns(2)
    for col, side in zip(cols, ("away", "home")):
        with col:
            gs = g.get(f"{side}_goalies") or []
            st.markdown(f'<div style="color:{_col(g, side)}; font-weight:800; '
                        f'font-size:var(--lc-text-small);">{_esc(g.get(f"{side}_abbr"))} crease</div>',
                        unsafe_allow_html=True)
            if not gs:
                st.caption("No regular-season starts yet.")
                continue
            for x in gs[:2]:
                share = (" \u00b7 " + _esc(x["crease_share"]) + " recent"
                         if x.get("crease_share") else "")
                st.markdown(
                    f'<div style="font-size:var(--lc-text-small); line-height:1.7;">'
                    f'<b>{_esc(x.get("name"))}</b> '
                    f'<span style="color:{COLOR["text_faint"]};">{x.get("starts", 0)} GS'
                    f'{share}</span><br>SV% <b>{fmt_svp(x.get("sv_pct"))}</b> \u00b7 GAA '
                    f'<b>{_num(x.get("gaa"), 2)}</b> \u00b7 L5 {fmt_svp(x.get("l5_sv_pct"))}</div>',
                    unsafe_allow_html=True)
    st.caption("Crease share is how many of the team's last 10 games each goalie "
               "started. It is NOT a confirmed starter for tonight.")


def _render_shooters(g):
    lines = []
    for side in ("away", "home"):
        sk = sorted((p for p in g.get(f"{side}_skaters") or [] if p.get("sog") is not None),
                    key=lambda p: -p["sog"])[:3]
        if sk:
            lines.append(f'<b style="color:{_col(g, side)};">{_esc(g.get(f"{side}_abbr"))}</b> '
                         + " \u00b7 ".join(f'{_esc(p["name"])} {p["sog"]:.1f} SOG/G'
                                           for p in sk))
    if lines:
        st.markdown(f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]}; '
                    f'line-height:1.8;">Top shooters \u2014 ' + "<br>".join(lines) + "</div>",
                    unsafe_allow_html=True)


def _render_game(g, live):
    lv = live.get((g.get("away"), g.get("home"))) or {}
    status = lv.get("status") or g.get("status") or "scheduled"
    a_s = lv.get("away_score", g.get("away_score"))
    h_s = lv.get("home_score", g.get("home_score"))
    with card(f'nhl_{g.get("event_id")}'):
        def _team(side):
            logo = g.get(f"{side}_logo")
            img = (f'<img src="{_esc(logo)}" style="height:26px; vertical-align:middle; '
                   f'margin-right:6px;">' if logo else "")
            rec = (g.get(f"{side}_profile") or {}).get("record") or ""
            return (f'{img}<span style="color:{_col(g, side)}; font-weight:800;">'
                    f'{_esc(g.get(side))}</span> <span style="color:{COLOR["text_faint"]}; '
                    f'font-size:var(--lc-text-tiny);">{_esc(rec)}</span>')
        score = ""
        if status in ("in progress", "final") and a_s is not None and h_s is not None:
            tag = _esc(lv.get("detail") or g.get("detail") or status.upper())
            score = ("<div style=\"font-family:'JetBrains Mono',monospace; font-size:1.4rem; "
                     f'font-weight:800; color:{_ACCENT};">{a_s} \u2013 {h_s} '
                     f'<span style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]};">'
                     f'{tag}</span></div>')
        st.markdown(
            '<div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">'
            f'<div style="line-height:2;">{_team("away")}<br>'
            f'<span style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny);">at</span> '
            f'{_team("home")}</div>{score}</div>', unsafe_allow_html=True)
        chips = []
        if g.get("game_type") == "preseason":
            chips.append(badge("Exhibition", "bad"))
        if g.get("time_et"):
            chips.append(badge(f'{g["time_et"]} ET', "neutral"))
        odds = g.get("odds") or {}
        if odds.get("details"):
            chips.append(badge(f'Line {_esc(odds["details"])}', "accent"))
        if odds.get("total") is not None:
            chips.append(badge(f'O/U {odds["total"]:g}', "accent"))
        if g.get("venue"):
            chips.append(badge(_esc(g["venue"]), "neutral"))
        st.markdown(" ".join(chips), unsafe_allow_html=True)
        if g.get("game_type") == "preseason":
            st.caption("Exhibition game \u2014 split squads and prospects. Nothing from "
                       "it is counted in any number on this site.")
            return
        _render_goalie_duel(g)
        _render_shooters(g)
        with st.expander("Tale of the tape"):
            _render_tape(g)


_today = today_for("nhl")
games, slate_date, current, built = _load_slate_for(_today)
_ph = phase(datetime.fromisoformat(_today).date())

if _ph != "regular":
    with card("nhl_countdown"):
        st.markdown(
            f'<div style="font-size:var(--lc-text-body-lg); font-weight:800; color:{_ACCENT};">'
            f'\U0001F3D2 {countdown_text(datetime.fromisoformat(_today).date())}</div>'
            f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small); '
            f'line-height:1.7; margin-top:4px;">The 2026\u201327 season is 84 games. '
            f'Team profiles, the Crease Report and the Shots Lab switch on the '
            f'morning after the first regular-season final ({REGULAR_SEASON_START:%b} '
            f'{REGULAR_SEASON_START.day}). Until then, exhibition games are shown '
            f'as a schedule only.</div>', unsafe_allow_html=True)

note = staleness_note("nhl", _today)
if note:
    st.info(note)

if games:
    live = _live(_today) if current else {}
    st.markdown(badge(f"{slate_date}", "accent") + badge(f"{len(games)} games", "neutral"),
                unsafe_allow_html=True)
    for g in sorted(games, key=lambda x: x.get("start_et") or ""):
        _render_game(g, live)
    if built:
        st.caption(f"Built {built} ET from ESPN's public NHL feed. Lines as listed, "
                   f"not a recommendation.")

footer()
