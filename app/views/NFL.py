"""NFL — The Week.

Football is the one league on the site that is read days ahead, so this
page is a WEEK, not a night: every game Tuesday to Monday, grouped by
TV window, each with its tale of the tape built from real box scores,
the single biggest unit mismatch on each side, and who is hurt.

Data: nfl_precompute.py -> data/nfl/games.json, week-guarded by
engines/nfl_week.load_week (a stale week shows NOTHING, never last
week's games as this week's).
"""
import html
from datetime import datetime

import streamlit as st

from styles.kc_theme import (page_header, badge, footer, card, COLOR,
                             SPORT_ACCENTS)
from engines.live_sync import sync_latest_button
from engines.nfl_week import (EASTERN, WINDOW_ORDER, load_week,
                              staleness_note, mismatches, edge_tier)
from engines.espn_feed import live_scores

_ACCENT = SPORT_ACCENTS.get("NFL") or COLOR["stat_high"]

page_header("NFL Analytics", "The whole week on one board \u2014 unit matchups, "
            "weather, injuries and lines", eyebrow="LIVE", align="left")
sync_latest_button(key="sync_nfl", include_data_package=True)


@st.cache_data(ttl=900, show_spinner=False)
def _load_week_for(day):
    """Keyed on the Eastern date (a real argument, not _day — Streamlit
    leaves underscore args OUT of the key) so the week rolls over at
    midnight without waiting out the TTL."""
    return load_week()


@st.cache_data(ttl=60, max_entries=4, show_spinner=False)
def _live(day):
    return live_scores("nfl", day.replace("-", ""))


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _fmt(v, nd=1, suffix=""):
    if v is None:
        return "\u2014"
    if isinstance(v, (int, float)):
        return f"{v:.{nd}f}{suffix}"
    return _esc(v)


def _team_col(g, side):
    c = g.get(f"{side}_color")
    return f"#{c}" if c else COLOR["text"]


def _rank_chip(rank, of):
    """A rank, coloured by which third of the league it sits in."""
    if rank is None:
        return ""
    of = of or 32
    if rank <= of / 3:
        col = COLOR["stat_high"]
    elif rank > 2 * of / 3:
        col = COLOR["error"]
    else:
        col = COLOR["text_muted"]
    return (f'<span style="color:{col}; font-size:var(--lc-text-tiny); '
            f'font-weight:700; margin-left:4px;">#{rank}</span>')


_TAPE = [
    ("Points / G", "pf_pg", 1, ""),
    ("Allowed / G", "pa_pg", 1, ""),
    ("Yards / G", "ypg", 1, ""),
    ("Pass yds / G", "pass_ypg", 1, ""),
    ("Rush yds / G", "rush_ypg", 1, ""),
    ("Yds allowed / G", "ypg_allowed", 1, ""),
    ("Pass yds allowed", "pass_allowed", 1, ""),
    ("Rush yds allowed", "rush_allowed", 1, ""),
    ("3rd down %", "third_pct", 1, "%"),
    ("Red zone TD %", "rz_td_pct", 1, "%"),
    ("Sacks / G", "sacks_pg", 1, ""),
    ("Sacked / G", "sacked_pg", 1, ""),
    ("TO margin / G", "to_margin_pg", 1, ""),
    ("Avg game total", "avg_total", 1, ""),
]


def _render_tape(g):
    a = g.get("away_profile") or {}
    h = g.get("home_profile") or {}
    if not a and not h:
        st.caption("No finals yet for these two teams \u2014 the tape fills in "
                   "after their first game.")
        return
    rows = []
    for label, key, nd, sfx in _TAPE:
        av, hv = a.get(key), h.get(key)
        if av is None and hv is None:
            continue
        rows.append(
            f'<tr><td style="text-align:right;">{_fmt(av, nd, sfx)}'
            f'{_rank_chip((a.get("ranks") or {}).get(key), a.get("rank_of"))}</td>'
            f'<td style="text-align:center; color:{COLOR["text_muted"]}; '
            f'font-size:var(--lc-text-tiny); text-transform:uppercase; '
            f'letter-spacing:0.04em; padding:4px 10px;">{label}</td>'
            f'<td style="text-align:left;">{_fmt(hv, nd, sfx)}'
            f'{_rank_chip((h.get("ranks") or {}).get(key), h.get("rank_of"))}</td></tr>')
    st.markdown(
        '<div class="lc-tbl-wrap"><table style="width:100%; '
        "font-family:'JetBrains Mono',monospace; font-size:var(--lc-text-small);\">"
        f'<tr><th style="text-align:right; color:{_team_col(g, "away")};">'
        f'{_esc(g.get("away_abbr"))} \u00b7 {a.get("gp", 0)} GP</th><th></th>'
        f'<th style="text-align:left; color:{_team_col(g, "home")};">'
        f'{_esc(g.get("home_abbr"))} \u00b7 {h.get("gp", 0)} GP</th></tr>'
        + "".join(rows) + "</table></div>",
        unsafe_allow_html=True)
    st.caption("Every figure is an average of real box scores this season. "
               "#N is the league rank for THAT team \u2014 #1 is best at it "
               "(most yards gained, fewest allowed). Early-season ranks rest on "
               "one or two games; the GP count is shown for that reason.")


def _render_edges(g):
    rows = [r for r in mismatches([g]) if r["edge"] > 0]
    if not rows:
        return
    best = {}
    for r in rows:
        best.setdefault(r["team"], r)
    of = (g.get("home_profile") or {}).get("rank_of")
    chips = []
    for r in best.values():
        tier = edge_tier(r["edge"], of)
        chips.append(badge(f'{_esc(r["abbr"])} {r["unit"].lower()} #{r["att_rank"]} '
                           f'vs #{r["def_rank"]} \u00b7 {tier}',
                           "good" if tier in ("Glaring", "Strong") else "neutral"))
    st.markdown("Biggest edge each side: " + " ".join(chips), unsafe_allow_html=True)


def _render_injuries(g):
    inj = g.get("injuries") or {}
    if not inj:
        return
    with st.expander("Injury report"):
        for side in ("away", "home"):
            rows = inj.get(g.get(side)) or []
            if not rows:
                continue
            parts = []
            for r in rows[:14]:
                out = str(r.get("status", "")).lower() in ("out", "injured reserve", "ir")
                parts.append(
                    f'{_esc(r["name"])} <span style="color:{COLOR["text_faint"]};">'
                    f'{_esc(r.get("pos"))}</span> <span style="color:'
                    f'{COLOR["error"] if out else COLOR["warn"]};">{_esc(r["status"])}</span>')
            st.markdown(f'<b style="color:{_team_col(g, side)};">{_esc(g.get(side))}</b><br>'
                        + " \u00b7 ".join(parts), unsafe_allow_html=True)


def _render_key_players(g):
    lines = []
    for side in ("away", "home"):
        ps = g.get(f"{side}_players") or []
        bits = []
        for role, key, lab in (("QB", "pass_yds", "pass yds"),
                               ("RB", "rush_yds", "rush yds"),
                               ("REC", "rece_yds", "rec yds")):
            p = next((x for x in ps if x.get("role") == role), None)
            if p and p.get(key) is not None:
                tag = f' <i>({_esc(p["status"])})</i>' if p.get("status") else ""
                bits.append(f'{_esc(p.get("name"))}{tag} {p[key]:.0f} {lab}/G')
        if bits:
            lines.append(f'<b style="color:{_team_col(g, side)};">'
                         f'{_esc(g.get(f"{side}_abbr"))}</b> ' + " \u00b7 ".join(bits))
    if lines:
        st.markdown(
            f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]}; '
            f'line-height:1.8;">' + "<br>".join(lines) + "</div>",
            unsafe_allow_html=True)


def _team_line(g, side):
    logo = g.get(f"{side}_logo")
    img = (f'<img src="{_esc(logo)}" style="height:28px; vertical-align:middle; '
           f'margin-right:6px;">' if logo else "")
    rec = g.get(f"{side}_record") or (g.get(f"{side}_profile") or {}).get("record") or ""
    return (f'{img}<span style="color:{_team_col(g, side)}; font-weight:800;">'
            f'{_esc(g.get(side))}</span> <span style="color:{COLOR["text_faint"]}; '
            f'font-size:var(--lc-text-tiny);">{_esc(rec)}</span>')


def _chips(g):
    chips = []
    if g.get("kickoff_et"):
        try:
            d = datetime.fromisoformat(g["kickoff_et"])
            chips.append(badge(f'{d:%a %b} {d.day} \u00b7 {g.get("kick_time_et")} ET', "neutral"))
        except ValueError:
            pass
    if g.get("network"):
        chips.append(badge(_esc(g["network"]), "neutral"))
    odds = g.get("odds") or {}
    if odds.get("details"):
        chips.append(badge(f'Line {_esc(odds["details"])}', "accent"))
    if odds.get("total") is not None:
        chips.append(badge(f'O/U {odds["total"]:g}', "accent"))
    if g.get("indoor") is True:
        chips.append(badge("Indoors", "neutral"))
    elif g.get("temp_f") is not None or g.get("weather"):
        bits = []
        if g.get("temp_f") is not None:
            bits.append(f'{g["temp_f"]:.0f}\u00b0F')
        if g.get("weather"):
            bits.append(_esc(g["weather"]))
        if g.get("gust_mph"):
            bits.append(f'gusts {g["gust_mph"]:.0f} mph')
        chips.append(badge(" ".join(bits), "bad" if (g.get("gust_mph") or 0) >= 20 else "neutral"))
    if g.get("venue"):
        chips.append(badge(_esc(g["venue"]), "neutral"))
    return " ".join(chips)


def _render_game(g, live):
    lv = live.get((g.get("away"), g.get("home"))) or {}
    status = lv.get("status") or g.get("status") or "scheduled"
    a_s = lv.get("away_score", g.get("away_score"))
    h_s = lv.get("home_score", g.get("home_score"))
    with card(f'nfl_{g.get("event_id")}'):
        score = ""
        if status in ("in progress", "final") and a_s is not None and h_s is not None:
            tag = "FINAL" if status == "final" else _esc(lv.get("detail") or "LIVE")
            score = ("<div style=\"font-family:'JetBrains Mono',monospace; font-size:1.4rem; "
                     f'font-weight:800; color:{_ACCENT};">{a_s} \u2013 {h_s} '
                     f'<span style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]};">'
                     f'{tag}</span></div>')
        elif status == "postponed":
            score = badge("Postponed", "bad")
        st.markdown(
            '<div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">'
            f'<div style="line-height:2;">{_team_line(g, "away")}<br>'
            f'<span style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny);">at</span> '
            f'{_team_line(g, "home")}</div>{score}</div>',
            unsafe_allow_html=True)
        st.markdown(_chips(g), unsafe_allow_html=True)
        _render_edges(g)
        _render_key_players(g)
        with st.expander("Tale of the tape"):
            _render_tape(g)
        _render_injuries(g)


_today = datetime.now(EASTERN).date()
payload, state = _load_week_for(_today.isoformat())

if state != "current":
    st.info(staleness_note(payload or {}, state, _today))
else:
    games = payload.get("games") or []
    st.markdown(
        badge(f'Week {payload.get("week")}', "accent")
        + badge(f'{payload.get("week_start_et")} \u2192 {payload.get("week_end_et")}', "neutral")
        + badge(f'{len(games)} games', "neutral")
        + badge(f'{payload.get("finals_parsed", 0)} box scores behind the numbers', "good"),
        unsafe_allow_html=True)

    present = [w for w in WINDOW_ORDER if any(g.get("window") == w for g in games)]
    pick = st.segmented_control("Window", ["All"] + present, default="All",
                                key="nfl_window", label_visibility="collapsed")
    shown = games if pick in (None, "All") else [g for g in games if g.get("window") == pick]

    today_s = _today.isoformat()
    live = _live(today_s) if any(g.get("kick_date_et") == today_s for g in games) else {}

    if not shown:
        st.info("No games in that window this week.")
    for w in WINDOW_ORDER:
        grp = [g for g in shown if g.get("window") == w]
        if not grp:
            continue
        st.markdown(
            f'<div style="margin:var(--lc-space-xl) 0 var(--lc-space-sm); color:{_ACCENT}; '
            f'font-weight:800; letter-spacing:0.12em; text-transform:uppercase; '
            f'font-size:var(--lc-text-caption);">{w} \u00b7 {len(grp)}</div>',
            unsafe_allow_html=True)
        for g in grp:
            _render_game(g, live)
    for g in (x for x in shown if x.get("window") not in WINDOW_ORDER):
        _render_game(g, live)

    st.caption(f'Week built {payload.get("generated_at_et")} ET from '
               f'{payload.get("source")}. Lines are shown as ESPN lists them, '
               f'not as a recommendation.')

footer()
