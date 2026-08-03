import json
from pathlib import Path

import streamlit as st

from styles.kc_theme import (inject_kc_theme, page_header, card_open, card_close,
                             badge, footer, COLOR, SPORT_ACCENTS)
from engines.matchup_grades_intl import grade_kbo_matchup, render_matchup_grades_card
from engines.kbo_k_projection import project_kbo_slate
from styles.table_style import style_stat_table, render_html_table

# NOTE: no st.set_page_config here — app.py already sets it once.

from engines.live_sync import sync_latest_button

inject_kc_theme()
sync_latest_button(key="sync_kbo", include_data_package=True)

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


# CACHED. Streamlit re-runs this whole script on every widget
# interaction, so without this the slate JSON was parsed from disk on
# each click. The file only changes when the nightly build publishes.
@st.cache_data(ttl=900, show_spinner=False)
def _load_games():
    try:
        payload = json.loads(_KBO_GAMES.read_text())
        return (payload.get("games", []), payload.get("generated_at_kst"),
                payload.get("slate_date_kst"))
    except Exception:
        # THREE values, not two. The success path returns a 3-tuple and
        # this returned 2, so any failure to read the slate file — missing,
        # truncated, mid-write — crashed the caller with "not enough
        # values to unpack" instead of degrading into the empty-slate
        # message the page already has.
        return None, None, None


# CACHED. Streamlit re-runs this whole script on every widget
# interaction, so without this the slate JSON was parsed from disk on
# each click. The file only changes when the nightly build publishes.
@st.cache_data(ttl=900, show_spinner=False)
def _load_pitchers():
    pitchers, gen = _load(_KBO_PITCHERS, "pitchers")
    return pitchers or [], gen


# CACHED — see _load_games above.
@st.cache_data(ttl=900, show_spinner=False)
def _load_batters():
    batters, gen = _load(_KBO_BATTERS, "batters")
    return batters or [], gen


# CACHED — see _load_games above.
@st.cache_data(ttl=900, show_spinner=False)
def _load_team_stats():
    try:
        payload = json.loads(_KBO_TEAM_STATS.read_text())
        return payload
    except Exception:
        return None


def _stat_row(left, right, mono_right=True):
    style = f'font-family:\'JetBrains Mono\',monospace; color:{COLOR["text"]};' if mono_right else f'color:{COLOR["text"]};'
    return (f'<div style="display:flex; justify-content:space-between; gap:12px; '
            f'font-size:var(--lc-text-small); margin-bottom:var(--lc-space-sm);">'
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
                f'{p.get("name", "")} <span style="color:{COLOR["text_muted"]}; font-weight:400;">({p.get("team", "")})</span>',
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
                f'{b.get("name", "")} <span style="color:{COLOR["text_muted"]}; font-weight:400;">({b.get("team", "")})</span>',
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
    return (f'<div style="font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; opacity:0.85; margin-top:var(--lc-space-hair);">'
            f'{label} O/U trend: {DOT.join(bits)}</div>')


def _render_k_projections():
    """Strikeout projections for the day's KBO starters — same formula
    as the MLB Strikeout Board, fed by the official leaderboard + team
    batting data. Renders nothing if there's no slate."""
    _games, _gen, _slate = _load_games()
    if not _games:
        return
    _pitchers_list, _ = _load_pitchers()
    _pitchers = {p.get("name"): p for p in (_pitchers_list or []) if p.get("name")}
    _team = _load_team_stats()
    rows, warning = project_kbo_slate(_games, _pitchers, _team)
    if not rows:
        return
    st.markdown(card_open(
        "\u26be Strikeout Projections",
        "proj K = (K/9 \u00f7 9) \u00d7 IP per start \u00d7 opponent K factor \u2014 "
        "same model as the MLB board, off the official season leaderboard. "
        "Opponent factor clamped \u00b115%. Not a sportsbook line."
    ), unsafe_allow_html=True)

    import pandas as _pd
    projected = [r for r in rows if r.get("proj") is not None]
    if projected:
        df = _pd.DataFrame([{
            "Pitcher": r["pitcher"],
            "Team": r["team"],
            "Opponent": r["opponent"],
            "Proj K": r["proj"],
            "K/9": r["k9"],
            "IP/GS": r["ip_gs"],
            "Opp K factor": r["factor"],
        } for r in projected])
        render_html_table(
            style_stat_table(
                df, favor_high=["Proj K", "K/9", "Opp K factor"], gradient=True
            ).format({"Proj K": "{:.1f}", "K/9": "{:.2f}", "IP/GS": "{:.1f}",
                      "Opp K factor": "{:.3f}"}, na_rep="\u2014")
        ,
            key="kbo_208")
    if warning:
        st.caption(warning)
    # Honest listing of starters we couldn't project and why.
    unprojected = [r for r in rows if r.get("proj") is None]
    if unprojected:
        _bits = ", ".join(f'{r["pitcher"]} ({r["status"]})' for r in unprojected)
        st.caption(f"Not projected yet \u2014 {_bits}")
    st.markdown(card_close(), unsafe_allow_html=True)


games, generated_at, slate_date = _load_games()

# Date-boundary guard: KBO plays on Korea time (UTC+9). The file holds
# the slate for whatever "today" was in Korea when the pipeline last
# ran; by the time a US user looks, Korea may have rolled to the next
# day, leaving the file a day behind. Compare the file's slate date to
# TODAY in Korea and, if it's stale, say so plainly instead of showing
# yesterday's games as if they're tonight's.
from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _ZI
_today_kst = _dt.now(_ZI("Asia/Seoul")).strftime("%Y-%m-%d")
_stale = bool(slate_date and slate_date != _today_kst)
if _stale:
    if slate_date > _today_kst:
        # Intended: no games today in Korea, so the pipeline advanced
        # to the next date that has them.
        st.info(
            f"No KBO games today in Korea ({_today_kst}) \u2014 "
            f"showing the next slate: {slate_date}."
        )
    else:
        # File is behind today: the build hasn't run since the date
        # rolled. Prompt a sync.
        st.warning(
            f"Showing the {slate_date} KST slate \u2014 today in Korea is "
            f"{_today_kst}. The nightly build hasn't refreshed yet; press "
            f"\u27f3 Sync latest above to pull the current slate."
        )

if games is None:
    st.markdown(card_open("\u26be KBO engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-body-lg); line-height:1.7;">'
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
            f'<div style="margin-bottom:var(--lc-space-lg);">'
            f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:var(--lc-text-body);">{name}</div>'
            f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown(card_close(), unsafe_allow_html=True)
    st.markdown(badge("MLB \u2014 live now", "good") + badge("KBO \u2014 in development", "accent"), unsafe_allow_html=True)
    _render_pitching_leaders()
    footer()
    st.stop()

# ------------------------------------------------------------
# REAL SLATE (renders only when the pipeline has shipped data)
# ------------------------------------------------------------
if generated_at:
    st.caption(f"Slate data as of {generated_at} KST \u2014 refreshed by the nightly pipeline.")

_render_pitching_leaders()
_render_k_projections()
if not games and not _stale:
    st.info("No KBO games on today\'s schedule \u2014 likely a league off-day.")
else:
    from engines.run_total import (project_total as _project_total,
                                   league_run_average as _league_avg)

    def _kbo_starter_era(gm, side, pitchers):
        """Announced starter's ERA from the real pitcher leaderboard.

        Matched by name against the same list the Strikeout board uses.
        Returns None when the starter isn't posted or isn't on the
        leaderboard — the projection then leaves the starter term out
        rather than inventing an ERA.
        """
        nm = (gm.get(f"{side}_starter") or "").strip()
        if not nm or nm.upper() == "TBD":
            return None
        # Same normalisation the strikeout board uses. Exact comparison
        # failed on every KBO starter — the schedule writes "James Naile"
        # while the leaderboard writes "NAILE James", and Korean names
        # arrive hyphenated on one page and spaced on the other. Without
        # this the run total silently never applied a starter.
        from engines.kbo_k_projection import _name_key
        want = _name_key(nm)
        hits = [sp for sp in (pitchers or []) if _name_key(sp.get("name")) == want]
        if len(hits) != 1:
            return None          # ambiguous or absent -> no adjustment
        try:
            return float(hits[0].get("era"))
        except (TypeError, ValueError):
            return None

    # Measured from the teams on this slate, not assumed. None means the
    # projection sits out rather than resting on a guessed baseline.
    _LEAGUE_RS = _league_avg({
        g.get(sd): {"rs_pg": g.get(f"{sd}_rs_pg")}
        for g in (games or []) for sd in ("home", "away")
        if g.get(f"{sd}_rs_pg") is not None
    })
    # _load_pitchers() rather than `pitchers`: that name is a LOCAL
    # inside the pitcher-tab function further up, not a module-level
    # binding, so referencing it here was a NameError on every page load.
    # The loader is cached, so calling it again costs nothing.
    _kbo_pitchers, _ = _load_pitchers()
    _eras = []
    for _sp in (_kbo_pitchers or []):
        try:
            _eras.append(float(_sp.get("era")))
        except (TypeError, ValueError):
            pass
    _LEAGUE_ERA = round(sum(_eras) / len(_eras), 2) if _eras else None

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
        return (f'<div style="font-size:var(--lc-text-caption); color:{COLOR["text"]}; opacity:0.85; margin-top:var(--lc-space-hair);">'
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
        return (f'<div style="font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; opacity:0.9; margin-top:var(--lc-space-hair);">'
                f'Official: {DOT.join(bits)}</div>')

    for gi, g in enumerate(games):
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

        # PROJECTED RUN TOTAL. Arithmetic on measured run rates, with the
        # announced starters applied where their ERA is published. NOT a
        # moneyline — see engines/run_total for why a win probability
        # needs fitted history that doesn't exist yet.
        _tot, _det = _project_total(
            {"rs_pg": g.get("home_rs_pg"), "ra_pg": g.get("home_ra_pg")},
            {"rs_pg": g.get("away_rs_pg"), "ra_pg": g.get("away_ra_pg")},
            _LEAGUE_RS,
            league_era=_LEAGUE_ERA,
            home_starter_era=_kbo_starter_era(g, "home", _kbo_pitchers),
            away_starter_era=_kbo_starter_era(g, "away", _kbo_pitchers),
        )
        if _tot is not None:
            _sp_note = (" \u00b7 starters applied"
                        if (_det.get("home_starter_adj") or _det.get("away_starter_adj"))
                        else "")
            stats_html += (
                f'<div style="font-size:var(--lc-text-small); margin-top:var(--lc-space-sm); '
                f'display:flex; justify-content:space-between; gap:12px;">'
                f'<span style="font-weight:700; color:{COLOR["text"]};">PROJECTED TOTAL</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["text"]};">'
                f'{_tot} runs \u00b7 {g.get("away","")} {_det["away_exp"]} / '
                f'{g.get("home","")} {_det["home_exp"]}{_sp_note}</span></div>')

        if g.get("h2h_official"):
            stats_html += (f'<div style="font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; '
                           f'margin-top:var(--lc-space-sm);">Official season H2H: <b>{g["h2h_official"]}</b></div>')
        if g.get("h2h"):
            stats_html += (f'<div style="font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; '
                           f'margin-top:var(--lc-space-hair);">Scoreline H2H: {g["h2h"]}</div>')
            det = g.get("h2h_detail") or {}
            if det.get("avg_total") is not None:
                stats_html += (
                    f'<div style="font-size:var(--lc-text-caption); color:{COLOR["text"]}; margin-top:var(--lc-space-hair);">'
                    f'H2H runs: {g.get("away")} {det.get("away_avg_runs")} R/G vs '
                    f'{g.get("home")} {det.get("home_avg_runs")} R/G \u00b7 '
                    f'Avg total in series: <b>{det.get("avg_total")}</b></div>')
            if det.get("scorelines"):
                joined = " \u00b7 ".join(det["scorelines"][:6])
                stats_html += (f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]}; '
                               f'opacity:0.85; margin-top:var(--lc-space-hair);">{joined}</div>')

        for side in ("away", "home"):
            ou_html = _ou_badges(g.get(f"{side}_ou_trend"), g.get(side, ""))
            if ou_html:
                stats_html += ou_html

        if stats_html:
            st.markdown(f'<div style="margin-top:var(--lc-space-md);">{stats_html}</div>', unsafe_allow_html=True)
        st.markdown(card_close(), unsafe_allow_html=True)

        grades = grade_kbo_matchup(g)
        render_matchup_grades_card(
            grades,
            subtitle=("This app's own signal checklist from real KBO team OPS/ERA/WHIP and "
                      "run-scoring form — formula documented in engines/matchup_grades_intl.py. "
                      "No probable-starter data in this pipeline yet, so this is graded on team "
                      "form rather than starter vs. starter. Not calibrated probabilities."),
            source_line="Source: official KBO leaderboards \u00b7 team form.",
            key=f'kbo_{gi}_{g.get("away","")}_{g.get("home","")}',
            # Card carries this page's own identity colour, the same way
            # the WNBA page does. Grade badge colours are grade-driven,
            # so they are identical everywhere — only the title follows
            # the sport.
            accent=SPORT_ACCENTS.get("KBO"),
        )

footer()
