import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR
from styles.table_style import style_stat_table
from auth import render_account_sidebar
from engines.matchup_grades_intl import grade_wnba_matchup, render_matchup_grades_card

# NOTE: no st.set_page_config here — app.py already sets it once.

from engines.live_sync import sync_latest_button
from engines.trend_chart import window_hit_chips, render_trend_bars

inject_kc_theme()
sync_latest_button(key="sync_wnba", include_data_package=True)

# Prop-tab styling — match the MLB page's language: JetBrains Mono,
# gold idle tabs, teal active tab + underline.
st.markdown(
    "<style>"
    ".stTabs [data-baseweb='tab-list'] { gap: 2px; }"
    ".stTabs [data-baseweb='tab'] { font-family: 'JetBrains Mono', monospace; }"
    f".stTabs [data-baseweb='tab'] p {{ font-size: 12px; color: {COLOR['gold']}; }}"
    f".stTabs [aria-selected='true'] p {{ color: {COLOR['stat_high']} !important; font-weight: 700; }}"
    f".stTabs [data-baseweb='tab-highlight'] {{ background-color: {COLOR['stat_high']}; }}"
    "</style>",
    unsafe_allow_html=True,
)
render_account_sidebar()

_WNBA_GAMES = Path(__file__).resolve().parent.parent / "data" / "wnba" / "games.json"
_SB_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"

page_header("WNBA Analytics", "Live season coverage — game & prop research", eyebrow="LIVE")


def _load_games():
    try:
        payload = json.loads(_WNBA_GAMES.read_text())
        return payload.get("games", []), payload.get("generated_at_et")
    except Exception:
        return None, None


@st.cache_data(ttl=60, show_spinner=False)
def _live_overrides():
    """Best-effort live score check straight from the same verified feed
    the pipeline uses, shared across all sessions and refreshed at most
    once a minute. Returns {} on ANY failure — the page then simply
    shows the pipeline snapshot, never anything invented."""
    try:
        r = requests.get(_SB_URL, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return {}
        out = {}
        for event in r.json().get("events", []) or []:
            comp = (event.get("competitions") or [{}])[0]
            competitors = comp.get("competitors") or []
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            key = ((away.get("team") or {}).get("displayName", ""),
                   (home.get("team") or {}).get("displayName", ""))
            stype = ((event.get("status") or {}).get("type")) or {}
            name = stype.get("name", "")
            status = {"STATUS_FINAL": "final", "STATUS_IN_PROGRESS": "in progress",
                      "STATUS_HALFTIME": "in progress", "STATUS_END_PERIOD": "in progress",
                      "STATUS_POSTPONED": "postponed"}.get(name)
            entry = {"detail": stype.get("shortDetail") or stype.get("detail")}
            if status:
                entry["status"] = status
            try:
                a_s, h_s = int(float(away.get("score", 0))), int(float(home.get("score", 0)))
                if status in ("in progress", "final"):
                    entry["scoreline"] = f"{key[0]} {a_s} - {h_s} {key[1]}"
            except (TypeError, ValueError):
                pass
            out[key] = entry
        return out
    except Exception:
        return {}


games, generated_at = _load_games()

if games is None:
    st.markdown(card_open("\U0001F3C0 WNBA engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["gold"]}; font-size:14px; line-height:1.7;">'
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
        "Form window", list(_fw_opts.keys()), default="L5",
        key="wnba_potd_window", label_visibility="collapsed",
    )
    _fw_label = _fw_choice or "L5"
    wnba_pick, _wnba_candidates, wnba_potd_error = get_wnba_player_of_the_day(
        form_window=_fw_opts.get(_fw_label, "l5")
    )
    if wnba_pick:
        st.markdown(card_open(f'\u2b50 Player of the Day \u2014 {wnba_pick["name"]} ({wnba_pick["team"]})'),
                    unsafe_allow_html=True)
        st.caption("This app's best real recent-form pick, by the numbers \u2014 not a prediction, not a lock.")
        potd_badges = (
            badge(f'{wnba_pick["pos"] or "?"}', "neutral")
            + badge(f'vs {wnba_pick["opponent"]}', "neutral")
            + badge(f'{_fw_label} PRA {wnba_pick["form_pra"]}', "accent")
        )
        st.markdown(f'<div>{potd_badges}</div>', unsafe_allow_html=True)
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric(f"{_fw_label} PPG", wnba_pick["form_ppg"] if wnba_pick["form_ppg"] is not None else "N/A")
        pc2.metric(f"{_fw_label} RPG", wnba_pick["form_rpg"] if wnba_pick["form_rpg"] is not None else "N/A")
        pc3.metric(f"{_fw_label} APG", wnba_pick["form_apg"] if wnba_pick["form_apg"] is not None else "N/A")
        pc4.metric("Season PRA", wnba_pick["season_pra"])
        st.caption(
            f'Real games played this season: {wnba_pick["gp"]} \u2014 ranked by real last-{_fw_label[1:]}-game PRA '
            f'(points+rebounds+assists), season PRA as tiebreaker.'
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


TAPE_ROWS = [
    ("Record", "record"), ("Home / Road", None),
    ("Last 10", "l10"),
    ("Points For / G", "pf_pg"), ("Points Against / G", "pa_pg"),
    ("Avg Game Total", "avg_total"),
    ("FG %", "fg_pct"), ("3P %", "tp_pct"),
    ("Rebounds / G", "reb_g"), ("Assists / G", "ast_g"),
    ("Turnovers / G", "to_g"),
]

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
            f'margin:2px 0 2px 0; flex-wrap:wrap;">'
            f'<span style="font-size:19px; font-weight:800; color:{a_col};">{away}</span>'
            f'<span style="font-size:12px; color:{COLOR["gold"]};">@</span>'
            f'<span style="font-size:19px; font-weight:800; color:{h_col};">{home}</span>'
            f'</div>'
            f'<div style="text-align:center; font-size:11.5px; color:{COLOR["gold"]}; margin-bottom:8px;">'
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
        for label, key in TAPE_ROWS:
            if key is None:  # Home / Road split row
                av = f'{_fmt(g.get("away_home_record"))} / {_fmt(g.get("away_road_record"))}'
                hv = f'{_fmt(g.get("home_home_record"))} / {_fmt(g.get("home_road_record"))}'
                if "\u2014 / \u2014" in (av, hv):
                    continue
            else:
                av, hv = _fmt(g.get(f"away_{key}")), _fmt(g.get(f"home_{key}"))
                if av == "\u2014" and hv == "\u2014":
                    continue
            rows_html += (
                f'<div style="display:grid; grid-template-columns:1fr auto 1fr; gap:10px; '
                f'padding:4px 0; border-bottom:1px solid {COLOR["surface_raised"]};">'
                f'<div style="text-align:right; font-family:\'JetBrains Mono\',monospace; '
                f'color:{a_col}; font-size:13px; font-weight:700;">{av}</div>'
                f'<div style="text-align:center; font-size:10px; color:{COLOR["gold"]}; '
                f'text-transform:uppercase; letter-spacing:0.06em; min-width:120px; '
                f'align-self:center;">{label}</div>'
                f'<div style="text-align:left; font-family:\'JetBrains Mono\',monospace; '
                f'color:{h_col}; font-size:13px; font-weight:700;">{hv}</div>'
                f'</div>')
        if rows_html:
            st.markdown(f'<div style="max-width:560px; margin:10px auto 0 auto;">{rows_html}</div>',
                        unsafe_allow_html=True)

        hh = g.get("h2h")
        if hh:
            scorelines = " \u00b7 ".join(hh.get("scorelines", [])[:4])
            st.markdown(
                f'<div style="text-align:center; margin-top:10px;">'
                f'<span style="display:inline-block; padding:6px 14px; border-radius:6px; '
                f'background:{COLOR["surface_raised"]}; font-size:12px; color:{COLOR["text"]};">'
                f'<b>Season Series:</b> {hh["summary"]} \u00b7 '
                f'Avg total in H2H: <b>{_fmt(hh.get("avg_total"))}</b> '
                f'({hh["meetings"]} meetings)</span>'
                f'<div style="font-size:10.5px; color:{COLOR["gold"]}; margin-top:4px;">{scorelines}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="text-align:center; margin-top:10px;">'
                f'<span style="display:inline-block; padding:6px 14px; border-radius:6px; '
                f'background:{COLOR["surface_raised"]}; font-size:12px; color:{COLOR["gold"]};">'
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
        )

        if g.get("away_players") or g.get("home_players"):
            with st.expander(f'\U0001F3C0 Prop research \u2014 {away} @ {home}'):
                st.markdown(
                    f'<div class="pf-card-subtitle" style="color:{COLOR["magenta_purple"]}; margin-bottom:4px;">'
                    f'Real box-score data \u00b7 Season / L5 / L10 = averages over all, last 5, and last 10 '
                    f'games played \u00b7 vs OPP = this player\'s real averages in this season\'s meetings '
                    f'with tonight\'s opponent (H2H GP = how many) \u00b7 small samples are shown as small '
                    f'samples \u2014 judge accordingly</div>',
                    unsafe_allow_html=True,
                )
                tabs = st.tabs([t[0] for t in PROP_TABS])

                # ---- Player Trend: game-by-game bars + hit-rate chips ----
                st.markdown(
                    f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; '
                    f'margin:10px 0 2px 0;">Player Trend</div>'
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
                            "Stat", ["Points", "Rebounds", "Assists", "PRA", "3PM"],
                            default="Points", key=f"wnba_trend_stat_{gi}",
                            label_visibility="collapsed",
                        ) or "Points"
                        _pt_win = st.segmented_control(
                            "Window", ["L25", "L15", "L10", "L5"],
                            default="L10", key=f"wnba_trend_win_{gi}",
                            label_visibility="collapsed",
                        ) or "L10"
                        _pt_line = float(st.segmented_control(
                            "Line", ["0.5", "4.5", "9.5", "14.5", "19.5", "24.5"],
                            default="14.5", key=f"wnba_trend_line_{gi}",
                            label_visibility="collapsed",
                        ) or "14.5")
                        _pt_key = {"Points": "pts", "Rebounds": "reb",
                                   "Assists": "ast", "PRA": "pra", "3PM": "tpm"}[_pt_stat]
                        _pt_all = [(gl.get(_pt_key) or 0) for gl in _plog]
                        window_hit_chips(_pt_all, _pt_line, _pt_win,
                                         windows=("L25", "L15", "L10", "L5"))
                        _n = {"L25": 25, "L15": 15, "L10": 10, "L5": 5}[_pt_win]
                        _sub = _plog[-_n:]
                        _lbls, _seen = [], {}
                        for gl in _sub:
                            _b = str(gl.get("date") or "")[5:]
                            _seen[_b] = _seen.get(_b, 0) + 1
                            _lbls.append(_b if _seen[_b] == 1 else f"{_b} ({_seen[_b]})")
                        _vals = [(gl.get(_pt_key) or 0) for gl in _sub]
                        render_trend_bars(_lbls, _vals, _pt_stat, _pt_line)
                        _avg = sum(_vals) / len(_vals)
                        st.caption(
                            f"{_pl.get('name')} \u00b7 {_pt_win}: {len(_vals)} games \u00b7 "
                            f"avg {_avg:.1f} {_pt_stat}/game \u00b7 line {_pt_line} \u00b7 "
                            f"teal bars cleared it, red didn't \u00b7 real box scores."
                        )
                for tab, (label, season_k, l5_k, l10_k, h2h_k) in zip(tabs, PROP_TABS):
                    with tab:
                        for side, col in (("away", a_col), ("home", h_col)):
                            plist = g.get(f"{side}_players")
                            if not plist:
                                continue
                            st.markdown(
                                f'<div style="display:inline-block; padding:3px 10px; border-radius:4px; '
                                f'background:{col}22; border:1px solid {col}55; color:{col}; '
                                f'font-weight:700; font-size:11px; text-transform:uppercase; '
                                f'letter-spacing:0.05em; margin:12px 0 4px 0;">{g.get(side, "")}</div>',
                                unsafe_allow_html=True,
                            )
                            rows = []
                            for p in plist:
                                pos = p.get("pos") or ""
                                pname = f'{p.get("name")} \u00b7 {pos}' if pos else p.get("name")
                                row = {
                                    "Player": pname,
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
                            df = pd.DataFrame(rows)
                            num_cols = [c for c in df.columns if c != "Player"]
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
                            st.dataframe(styled, width="stretch",
                                         height=40 + 36 * len(df))
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