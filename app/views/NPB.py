import json
from pathlib import Path

import streamlit as st

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, badge, footer, COLOR
from auth import render_account_sidebar
from engines.matchup_grades_intl import grade_npb_matchup, render_matchup_grades_card

# NOTE: no st.set_page_config here — app.py already sets it once.

from engines.live_sync import sync_latest_button

inject_kc_theme()
sync_latest_button(key="sync_npb", include_data_package=True)
render_account_sidebar()

_NPB_GAMES = Path(__file__).resolve().parent.parent / "data" / "npb" / "games.json"

page_header("NPB Analytics", "Nippon Professional Baseball — game-level markets", eyebrow="IN ACTIVE DEVELOPMENT")


def _load_games():
    """Reads the NPB slate produced by the nightly pipeline. Returns
    (games, generated_at) or (None, None) when the engine hasn't shipped
    data yet — the page then shows the honest in-development panel
    instead of anything fabricated."""
    try:
        payload = json.loads(_NPB_GAMES.read_text())
        return payload.get("games", []), payload.get("generated_at_jst")
    except Exception:
        return None, None


games, generated_at = _load_games()

if games is None:
    st.markdown(card_open("\u26be NPB engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["gold"]}; font-size:14px; line-height:1.7;">'
        f'NPB coverage is in active development on the same standard as the MLB engine: '
        f'every number traced to a real, verifiable source \u2014 no placeholders, no estimates. '
        f'This page lights up with the real slate the moment the data pipeline ships; '
        f'nothing appears here before that.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(card_close(), unsafe_allow_html=True)

    st.markdown(card_open("What launches first"), unsafe_allow_html=True)
    for name, desc in [
        ("Daily Slate", "Every NPB game with starters, park, and start time (JST + ET) - ties shown as ties, since NPB games can legitimately end drawn"),
        ("Team Profiles", "Real offense/pitching form for totals and run-line handicapping"),
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
    st.markdown(badge("MLB \u2014 live now", "good") + badge("NPB \u2014 in development", "accent"), unsafe_allow_html=True)
    footer()
    st.stop()

# ------------------------------------------------------------
# REAL SLATE (renders only when the pipeline has shipped data)
# ------------------------------------------------------------
if generated_at:
    st.caption(f"Slate data as of {generated_at} JST \u2014 refreshed by the nightly pipeline.")

if not games:
    st.info("No NPB games on today\'s schedule \u2014 likely a league off-day.")
else:
    def _team_line(g, side):
        """One team's real season line — only renders fields the data
        actually contains."""
        name = g.get(side, "TBD")
        bits = []
        if g.get(f"{side}_record"):
            bits.append(f'{g[f"{side}_record"]}')
        if g.get(f"{side}_rs_pg") is not None and g.get(f"{side}_ra_pg") is not None:
            bits.append(f'{g[f"{side}_rs_pg"]} RS / {g[f"{side}_ra_pg"]} RA per game')
        if g.get(f"{side}_last10"):
            bits.append(f'L10: {g[f"{side}_last10"]}')
        if not bits:
            return ""
        dot = " \u00b7 "
        joined = dot.join(bits)
        return (f'<div style="display:flex; justify-content:space-between; gap:12px; '
                f'font-size:12.5px; margin-bottom:6px;">'
                f'<span style="font-weight:700; color:{COLOR["text"]};">{name}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["gold"]};">'
                f'{joined}</span></div>')

    for gi, g in enumerate(games):
        status = g.get("status", "scheduled")
        subtitle = f'{g.get("stadium", "")} \u00b7 {g.get("time_jst", "TBD")} JST / {g.get("time_et", "TBD")} ET'
        st.markdown(card_open(f'{g.get("away", "TBD")} @ {g.get("home", "TBD")}', subtitle), unsafe_allow_html=True)

        status_style = {"postponed": "bad", "final": "good", "final (tie)": "good"}.get(status, "neutral")
        badges = badge(status.upper(), status_style)
        if g.get("final"):
            badges += badge(g["final"], "accent")
        if g.get("starters_raw"):
            badges += badge(f'Pitchers: {g["starters_raw"]}', "neutral")
        else:
            badges += (badge(f'Away SP: {g.get("away_starter", "TBD")}', "neutral")
                       + badge(f'Home SP: {g.get("home_starter", "TBD")}', "neutral"))
        st.markdown(badges, unsafe_allow_html=True)

        # Real season lines for the announced starters — straight from
        # npb.jp's own leaderboards, rendered only when a confident
        # team-scoped match exists.
        dotsp = " \u00b7 "
        for side in ("away", "home"):
            sp = g.get(f"{side}_starter_stats")
            if not sp:
                continue
            name = g.get(f"{side}_starter", "")
            bits = []
            if sp.get("era"):
                bits.append(f'ERA {sp["era"]}')
            if sp.get("wins") is not None and sp.get("losses") is not None:
                bits.append(f'{sp["wins"]}-{sp["losses"]}')
            if sp.get("innings_pitched"):
                bits.append(f'{sp["innings_pitched"]} IP')
            if sp.get("strikeouts"):
                bits.append(f'{sp["strikeouts"]} K')
            for k, lbl in (("saves", "SV"), ("holds", "HLD")):
                v = sp.get(k)
                if v and str(v) not in ("0", "-"):
                    bits.append(f'{v} {lbl}')
            if not bits:
                continue
            joined = dotsp.join(bits)
            st.markdown(
                f'<div style="display:flex; justify-content:space-between; gap:12px; '
                f'font-size:12px; margin-top:4px;">'
                f'<span style="font-weight:700; color:{COLOR["text"]}; white-space:nowrap;">'
                f'{g.get(side, "")} SP \u2014 {name}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["gold"]}; '
                f'text-align:right;">{joined}</span></div>',
                unsafe_allow_html=True,
            )

        stats_html = _team_line(g, "away") + _team_line(g, "home")
        if g.get("h2h"):
            stats_html += (f'<div style="font-size:11.5px; color:{COLOR["gold"]}; '
                           f'margin-top:4px;">Season H2H: {g["h2h"]}</div>')
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
        if stats_html:
            st.markdown(f'<div style="margin-top:10px;">{stats_html}</div>', unsafe_allow_html=True)
        st.markdown(card_close(), unsafe_allow_html=True)

        grades = grade_npb_matchup(g)
        render_matchup_grades_card(
            grades,
            subtitle=("This app's own signal checklist \u2014 starter vs. starter (WHIP/ERA/K9/HR9, "
                      "computed from npb.jp's own leaderboard) when both probables are matched to a "
                      "real stat line, team form otherwise. Formula documented in "
                      "engines/matchup_grades_intl.py. Not calibrated probabilities."),
            source_line="Source: npb.jp official leaderboards \u00b7 starter or team form.",
            key=f'npb_{gi}_{g.get("away","")}_{g.get("home","")}',
        )

footer()