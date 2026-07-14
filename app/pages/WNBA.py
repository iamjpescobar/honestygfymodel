import json
from pathlib import Path

import pandas as pd
import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR
from auth import render_account_sidebar

# NOTE: no st.set_page_config here — app.py already sets it once.

inject_kc_theme()
render_account_sidebar()

_WNBA_GAMES = Path(__file__).resolve().parent.parent / "data" / "wnba" / "games.json"

page_header("WNBA Analytics", "Live season coverage — game & prop research", eyebrow="LIVE")


def _load_games():
    try:
        payload = json.loads(_WNBA_GAMES.read_text())
        return payload.get("games", []), payload.get("generated_at_et")
    except Exception:
        return None, None


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

if generated_at:
    st.caption(f"Data as of {generated_at} ET \u2014 refreshed by the nightly pipeline. "
               f"All stats computed from real box scores; H2H = this season's actual meetings.")

if not games:
    st.info("No WNBA games on today's schedule \u2014 likely a league off-day or break.")


def _hex(c, fallback):
    if c and isinstance(c, str) and len(c) in (3, 6):
        return f"#{c}"
    return fallback


def _fmt(v):
    return "\u2014" if v is None else v


TAPE_ROWS = [
    ("Record", "record"), ("Last 10", "l10"),
    ("Points For / G", "pf_pg"), ("Points Against / G", "pa_pg"),
    ("Avg Game Total", "avg_total"),
]

for g in games:
    away, home = g.get("away", "TBD"), g.get("home", "TBD")
    a_col = _hex(g.get("away_color"), COLOR["stat_high"])
    h_col = _hex(g.get("home_color"), COLOR["stat_high"])
    status = g.get("status", "scheduled")

    # ---- Header: team names in their real colors ----
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
    if g.get("final"):
        center += badge(g["final"], "accent")
    if g.get("score"):
        center += badge(g["score"], "accent")
    if g.get("line"):
        center += badge(f'Line: {g["line"]}', "neutral")
    st.markdown(f'<div style="text-align:center;">{center}</div>', unsafe_allow_html=True)

    # ---- Tale of the tape: away | label | home ----
    rows_html = ""
    for label, key in TAPE_ROWS:
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

    # ---- Season series (team H2H) ----
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

    # ---- Leaders line ----
    dot = " \u00b7 "
    for side, col in (("away", a_col), ("home", h_col)):
        leaders = g.get(f"{side}_leaders") or []
        if leaders:
            joined = dot.join(f'{ld["name"]} {ld["value"]} {ld["cat"]}' for ld in leaders)
            st.markdown(
                f'<div style="display:flex; justify-content:space-between; gap:12px; '
                f'font-size:12px; margin-top:6px;">'
                f'<span style="font-weight:700; color:{col}; white-space:nowrap;">{g.get(side)}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; '
                f'color:{COLOR["gold"]}; text-align:right;">{joined}</span></div>',
                unsafe_allow_html=True,
            )
    kind = g.get("leaders_kind", "season")
    if g.get("away_leaders") or g.get("home_leaders"):
        cap = ("Leaders are season averages." if kind == "season"
               else "Leaders are this game's actual totals.")
        st.markdown(f'<div style="font-size:10.5px; color:{COLOR["gold"]}; opacity:0.8;">{cap}</div>',
                    unsafe_allow_html=True)

    st.markdown(card_close(), unsafe_allow_html=True)

    # ---- Player research ----
    if g.get("away_players") or g.get("home_players"):
        with st.expander(f'\U0001F3C0 Player research \u2014 {away} @ {home}'):
            st.caption(
                "Real box-score data: season averages, last-5 / last-10 form, and each "
                "player's averages in this season's actual meetings with tonight's "
                "opponent (vs OPP). GP counts are shown so small samples read as small "
                "samples \u2014 an honest flag, not a hidden flaw."
            )
            for side in ("away", "home"):
                plist = g.get(f"{side}_players")
                if not plist:
                    continue
                st.markdown(
                    f'<div style="font-weight:700; color:{COLOR["text"]}; '
                    f'font-size:13px; margin:6px 0 2px 0;">{g.get(side, "")}</div>',
                    unsafe_allow_html=True,
                )
                df = pd.DataFrame(plist).rename(columns={
                    "name": "Player", "pos": "Pos", "gp": "GP", "min": "MIN",
                    "ppg": "PPG", "rpg": "RPG", "apg": "APG",
                    "l5_ppg": "L5 PPG", "l10_ppg": "L10 PPG",
                    "l5_rpg": "L5 RPG", "l5_apg": "L5 APG",
                    "h2h_ppg": "vs OPP PPG", "h2h_rpg": "vs OPP RPG",
                    "h2h_apg": "vs OPP APG", "h2h_gp": "H2H GP",
                })
                st.dataframe(df, width="stretch", hide_index=True,
                             height=40 + 36 * len(df))

footer()