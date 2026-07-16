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

inject_kc_theme()
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
    ("Stocks", "stocks", "l5_stocks", "l10_stocks", "h2h_stocks"),
    ("Volume", "fga", "l5_fga", "l10_fga", "h2h_fga"),
]
TAB_NOTES = {
    "Stocks": "Stocks = steals + blocks combined \u2014 the STL/BLK columns show the season split.",
    "Volume": "FGA per game \u2014 shot volume drives points props; FTA and TO shown for context.",
}


def _render_slate():
    live = _live_overrides()
    any_live = False

    for g in games:
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

        grades = grade_wnba_matchup(g)
        render_matchup_grades_card(
            grades,
            subtitle=("This app's own signal checklist from real team scoring, shooting, and "
                      "turnover rates \u2014 there's no starting-pitcher analog in basketball, so this "
                      "is graded on team form. Formula documented in "
                      "engines/matchup_grades_intl.py. Not calibrated probabilities."),
            source_line="Source: real WNBA box-score-derived team stats.",
        )

        if g.get("away_players") or g.get("home_players"):
            with st.expander(f'\U0001F3C0 Prop research \u2014 {away} @ {home}'):
                st.caption(
                    "Real box-score data. Season / L5 / L10 = averages over all, last 5, "
                    "and last 10 games played. vs OPP = this player's real averages in "
                    "this season's meetings with tonight's opponent (H2H GP = how many). "
                    "Small samples are shown as small samples \u2014 judge accordingly."
                )
                tabs = st.tabs([t[0] for t in PROP_TABS])
                for tab, (label, season_k, l5_k, l10_k, h2h_k) in zip(tabs, PROP_TABS):
                    with tab:
                        for side, col in (("away", a_col), ("home", h_col)):
                            plist = g.get(f"{side}_players")
                            if not plist:
                                continue
                            st.markdown(
                                f'<div style="font-weight:700; color:{col}; '
                                f'font-size:13px; margin:6px 0 2px 0;">{g.get(side, "")}</div>',
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
                                rows.append(row)
                            df = pd.DataFrame(rows)
                            num_cols = [c for c in df.columns if c != "Player"]
                            for c in num_cols:
                                df[c] = pd.to_numeric(df[c], errors="coerce")
                            fmts = {c: "{:.1f}" for c in num_cols}
                            fmts["GP"] = "{:.0f}"
                            fmts["H2H GP"] = "{:.0f}"
                            # The Styler already hides its own index (see
                            # table_style._base_styler) — passing hide_index or
                            # column_config on TOP of a Styler makes Streamlit
                            # lay columns out against a different grid than the
                            # styles were computed for, which is exactly the
                            # floating/misaligned column bug. So: hand the
                            # widget the Styler and NOTHING else that touches
                            # column layout.
                            styled = style_stat_table(
                                df, favor_high=["Season", "L5", "L10", "vs OPP"],
                                gradient=True,
                            ).format(fmts, na_rep="\u2014")
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