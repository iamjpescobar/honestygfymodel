import json
from pathlib import Path

import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR
from auth import render_account_sidebar
from engines.matchup_grades_intl import grade_kbo_matchup, render_matchup_grades_card

# NOTE: no st.set_page_config here — app.py already sets it once.

inject_kc_theme()
render_account_sidebar()

_KBO_GAMES = Path(__file__).resolve().parent.parent / "data" / "kbo" / "games.json"
_KBO_PITCHERS = Path(__file__).resolve().parent.parent / "data" / "kbo" / "pitchers.json"
_KBO_BATTERS = Path(__file__).resolve().parent.parent / "data" / "kbo" / "batters.json"
_KBO_TEAM_STATS = Path(__file__).resolve().parent.parent / "data" / "kbo" / "team_stats.json"

page_header("KBO Analytics", "Korean Baseball Organization — game-level markets", eyebrow="IN ACTIVE DEVELOPMENT")

DOT = " \u00b7 "
DASH = "\u2014"


def _load(path, key):
    """Generic loader matching the existing honest-omission pattern —
    returns (payload_list_or_dict, generated_at) or (None/[], None) if
    the pipeline hasn't shipped this file yet."""
    try:
        payload = json.loads(path.read_text())
        return payload.get(key), payload.get("generated_at_kst")
    except Exception:
        return None, None


def _load_games():
    try:
        payload = json.loads(_KBO_GAMES.read_text())
        return payload.get("games", []), payload.get("generated_at_kst")
    except Exception:
        return None, None


def _load_pitchers():
    pitchers, gen = _load(_KBO_PITCHERS, "pitchers")
    return pitchers or [], gen


def _load_batters():
    batters, gen = _load(_KBO_BATTERS, "batters")
    return batters or [], gen


def _load_team_stats():
    try:
        payload = json.loads(_KBO_TEAM_STATS.read_text())
        return payload
    except Exception:
        return None


def _stat_row(left, right, mono_right=True):
    style = f'font-family:\'JetBrains Mono\',monospace; color:{COLOR["gold"]};' if mono_right else f'color:{COLOR["gold"]};'
    return (f'<div style="display:flex; justify-content:space-between; gap:12px; '
            f'font-size:12.5px; margin-bottom:6px;">'
            f'<span style="font-weight:700; color:{COLOR["text"]}; white-space:nowrap;">{left}</span>'
            f'<span style="{style} text-align:right;">{right}</span></div>')


def _render_pitching_leaders():
    pitchers, p_generated = _load_pitchers()
    if not pitchers:
        return
    st.markdown(card_open("KBO Pitching Leaders", "Real 2026 season lines \u2014 official KBO leaderboard"),
                unsafe_allow_html=True)
    if p_generated:
        st.caption(f"Pitcher data as of {p_generated} KST.")
    for p in pitchers[:15]:
        bits = []
        if p.get("wins") is not None and p.get("losses") is not None:
            bits.append(f'{p["wins"]}-{p["losses"]}')
        if p.get("innings_pitched"):
            bits.append(f'{p["innings_pitched"]} IP')
        if p.get("strikeouts") is not None:
            bits.append(f'{p["strikeouts"]} K')
        if p.get("whip") is not None:
            bits.append(f'{p["whip"]} WHIP')
        for k, lbl in (("saves", "SV"), ("holds", "HLD")):
            v = p.get(k)
            if v and str(v) not in ("0", "-"):
                bits.append(f'{v} {lbl}')
        joined = DOT.join(bits)
        era_display = p.get("era", DASH)
        st.markdown(
            _stat_row(
                f'{p.get("name", "")} <span style="color:{COLOR["gold"]}; font-weight:400;">({p.get("team", "")})</span>',
                f'ERA {era_display}{DOT}{joined}',
            ),
            unsafe_allow_html=True,
        )
    st.markdown(card_close(), unsafe_allow_html=True)


def _render_batting_leaders():
    batters, b_generated = _load_batters()
    if not batters:
        return
    st.markdown(card_open("KBO Batting Leaders", "Real 2026 season lines \u2014 official KBO leaderboard, sorted by OPS"),
                unsafe_allow_html=True)
    if b_generated:
        st.caption(f"Batter data as of {b_generated} KST.")
    for b in batters[:15]:
        bits = []
        if b.get("avg") is not None:
            bits.append(f'{b["avg"]} AVG')
        if b.get("hr") is not None:
            bits.append(f'{b["hr"]} HR')
        if b.get("rbi") is not None:
            bits.append(f'{b["rbi"]} RBI')
        if b.get("sb") is not None:
            bits.append(f'{b["sb"]} SB')
        if b.get("obp") is not None:
            bits.append(f'{b["obp"]} OBP')
        if b.get("slg") is not None:
            bits.append(f'{b["slg"]} SLG')
        joined = DOT.join(bits)
        ops_display = b.get("ops", DASH)
        st.markdown(
            _stat_row(
                f'{b.get("name", "")} <span style="color:{COLOR["gold"]}; font-weight:400;">({b.get("team", "")})</span>',
                f'OPS {ops_display}{DOT}{joined}',
            ),
            unsafe_allow_html=True,
        )
    st.markdown(card_close(), unsafe_allow_html=True)


def _ou_badges(ou_trend, label):
    """Renders over/under hit-rate badges for a team's real finals
    against a few reference totals. Explicitly NOT tied to tonight's
    actual sportsbook line — this pipeline doesn't have access to
    betting lines, only real scored totals."""
    if not ou_trend:
        return ""
    bits = [f'Avg total {ou_trend["avg_total"]} ({ou_trend["games"]}G)']
    for line in (7.5, 8.5, 9.5):
        key = f"line_{line}"
        if key in ou_trend:
            pct = ou_trend[key]["over_pct"]
            bits.append(f'O{line}: {pct}%')
    return (f'<div style="font-size:11px; color:{COLOR["gold"]}; opacity:0.85; margin-top:2px;">'
            f'{label} O/U trend: {DOT.join(bits)}</div>')


games, generated_at = _load_games()

if games is None:
    st.markdown(card_open("\u26be KBO engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["gold"]}; font-size:14px; line-height:1.7;">'
        f'KBO coverage is in active development on the same standard as the MLB engine: '
        f'every number traced to a real, verifiable source \u2014 no placeholders, no estimates. '
        f'This page lights up with the real slate the moment the data pipeline ships; '
        f'nothing appears here before that.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(card_close(), unsafe_allow_html=True)

    st.markdown(card_open("What launches first"), unsafe_allow_html=True)
    for name, desc in [
        ("Daily Slate", "Every KBO game with starters, park, and start time (JST + ET) - start times shown in KST and ET"),
        ("Team Profiles", "Real offense/pitching form, home/away splits, and official league stats for totals and run-line handicapping"),
        ("Starter Form", "Season and recent-start lines for the day\'s probables"),
    ]:
        st.markdown(
            f'<div style="margin-bottom:12px;">'
            f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:13.5px;">{name}</div>'
            f'<div style="color:{COLOR["gold"]}; font-size:12.5px;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown(card_close(), unsafe_allow_html=True)
    st.markdown(badge("MLB \u2014 live now", "good") + badge("KBO \u2014 in development", "accent"), unsafe_allow_html=True)
    _render_pitching_leaders()
    _render_batting_leaders()
    footer()
    st.stop()

# ------------------------------------------------------------
# REAL SLATE (renders only when the pipeline has shipped data)
# ------------------------------------------------------------
if generated_at:
    st.caption(f"Slate data as of {generated_at} KST \u2014 refreshed by the nightly pipeline.")

_render_pitching_leaders()
_render_batting_leaders()

if not games:
    st.info("No KBO games on today\'s schedule \u2014 likely a league off-day.")
else:
    def _team_line(g, side):
        name = g.get(side, "TBD")
        bits = []
        if g.get(f"{side}_record"):
            bits.append(f'{g[f"{side}_record"]}')
        if g.get(f"{side}_rs_pg") is not None and g.get(f"{side}_ra_pg") is not None:
            bits.append(f'{g[f"{side}_rs_pg"]} RS / {g[f"{side}_ra_pg"]} RA per game')
        if g.get(f"{side}_last10"):
            bits.append(f'L10: {g[f"{side}_last10"]}')
        if g.get(f"{side}_streak"):
            bits.append(f'Streak: {g[f"{side}_streak"]}')
        if not bits:
            return ""
        return _stat_row(name, DOT.join(bits))

    def _home_away_split(g, side):
        """Splits are the bigger edge signal than the blended record for
        a team playing at home tonight vs. one on the road."""
        hr, ar = g.get(f"{side}_home_record"), g.get(f"{side}_away_record")
        if not hr and not ar:
            return ""
        bits = []
        if hr:
            bits.append(f'Home {hr}')
            if g.get(f"{side}_home_rs_pg") is not None:
                bits.append(f'{g[f"{side}_home_rs_pg"]}/{g[f"{side}_home_ra_pg"]} RS/RA')
        if ar:
            bits.append(f'Away {ar}')
            if g.get(f"{side}_away_rs_pg") is not None:
                bits.append(f'{g[f"{side}_away_rs_pg"]}/{g[f"{side}_away_ra_pg"]} RS/RA')
        return (f'<div style="font-size:11px; color:{COLOR["text"]}; opacity:0.85; margin-top:2px;">'
                f'{DOT.join(bits)}</div>')

    def _official_team_stats(g, side):
        """Official league-maintained batting/pitching for this team —
        independent of the scoreline scraper, so it renders even on
        days the season crawl parses zero finals."""
        tb = g.get(f"{side}_team_batting")
        tp = g.get(f"{side}_team_pitching")
        if not tb and not tp:
            return ""
        bits = []
        if tb:
            bits.append(f'{tb.get("avg", DASH)} AVG / {tb.get("ops", DASH)} OPS')
            if tb.get("runs_per_game") is not None:
                bits.append(f'{tb["runs_per_game"]} R/G')
        if tp:
            bits.append(f'{tp.get("era", DASH)} ERA / {tp.get("whip", DASH)} WHIP')
            if tp.get("runs_allowed_per_game") is not None:
                bits.append(f'{tp["runs_allowed_per_game"]} RA/G')
        return (f'<div style="font-size:11px; color:{COLOR["gold"]}; opacity:0.9; margin-top:2px;">'
                f'Official: {DOT.join(bits)}</div>')

    for g in games:
        status = g.get("status", "scheduled")
        subtitle = f'{g.get("stadium", "")} \u00b7 {g.get("time_kst", "TBD")} KST / {g.get("time_et", "TBD")} ET'
        st.markdown(card_open(f'{g.get("away", "TBD")} @ {g.get("home", "TBD")}', subtitle), unsafe_allow_html=True)

        status_style = {"postponed": "bad", "final": "good", "final (tie)": "good"}.get(status, "neutral")
        badges = badge(status.upper(), status_style)
        if g.get("final"):
            badges += badge(g["final"], "accent")
        if g.get("starters_raw"):
            badges += badge(f'Announced starters: {g["starters_raw"]}', "neutral")
        else:
            badges += (badge(f'Away SP: {g.get("away_starter", "TBD")}', "neutral")
                       + badge(f'Home SP: {g.get("home_starter", "TBD")}', "neutral"))
        st.markdown(badges, unsafe_allow_html=True)

        stats_html = ""
        for side in ("away", "home"):
            line = _team_line(g, side)
            if line:
                stats_html += line
                stats_html += _home_away_split(g, side)
                stats_html += _official_team_stats(g, side)
            elif _official_team_stats(g, side):
                # Scoreline crawl parsed nothing, but official stats still exist.
                stats_html += _stat_row(g.get(side, "TBD"), "")
                stats_html += _official_team_stats(g, side)

        if g.get("h2h_official"):
            stats_html += (f'<div style="font-size:11.5px; color:{COLOR["gold"]}; '
                           f'margin-top:6px;">Official season H2H: <b>{g["h2h_official"]}</b></div>')
        if g.get("h2h"):
            stats_html += (f'<div style="font-size:11.5px; color:{COLOR["gold"]}; '
                           f'margin-top:2px;">Scoreline H2H: {g["h2h"]}</div>')
            det = g.get("h2h_detail") or {}
            if det.get("avg_total") is not None:
                stats_html += (
                    f'<div style="font-size:11px; color:{COLOR["text"]}; margin-top:2px;">'
                    f'H2H runs: {g.get("away")} {det.get("away_avg_runs")} R/G vs '
                    f'{g.get("home")} {det.get("home_avg_runs")} R/G \u00b7 '
                    f'Avg total in series: <b>{det.get("avg_total")}</b></div>')
            if det.get("scorelines"):
                joined = " \u00b7 ".join(det["scorelines"][:6])
                stats_html += (f'<div style="font-size:10.5px; color:{COLOR["gold"]}; '
                               f'opacity:0.85; margin-top:2px;">{joined}</div>')

        for side in ("away", "home"):
            ou_html = _ou_badges(g.get(f"{side}_ou_trend"), g.get(side, ""))
            if ou_html:
                stats_html += ou_html

        if stats_html:
            st.markdown(f'<div style="margin-top:10px;">{stats_html}</div>', unsafe_allow_html=True)
        st.markdown(card_close(), unsafe_allow_html=True)

        grades = grade_kbo_matchup(g)
        render_matchup_grades_card(
            grades,
            subtitle=("This app's own signal checklist from real KBO team OPS/ERA/WHIP and "
                      "run-scoring form — formula documented in engines/matchup_grades_intl.py. "
                      "No probable-starter data in this pipeline yet, so this is graded on team "
                      "form rather than starter vs. starter. Not calibrated probabilities."),
            source_line="Source: official KBO leaderboards \u00b7 team form.",
        )

footer()