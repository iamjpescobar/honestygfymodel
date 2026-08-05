import json
from pathlib import Path

import streamlit as st

from engines.intl_venues import (roof as _roof_kind,
                                  roof_note as _roof_note)
_LEAGUE = "npb"

from styles.kc_theme import (page_header, card_open, card_close,
                             badge, footer, COLOR, SPORT_ACCENTS)
from engines.matchup_grades_intl import grade_npb_matchup, render_matchup_grades_card

# NOTE: no st.set_page_config here — app.py already sets it once.

from engines.live_sync import sync_latest_button

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.
sync_latest_button(key="sync_npb", include_data_package=True)

_NPB_GAMES = Path(__file__).resolve().parent.parent / "data" / "npb" / "games.json"

page_header("NPB Analytics", "Nippon Professional Baseball — game-level markets", eyebrow="IN ACTIVE DEVELOPMENT")


# CACHED. Streamlit re-runs this whole script on every widget
# interaction, so without this the slate JSON was parsed from disk on
# each click. The file only changes when the nightly build publishes.
@st.cache_data(ttl=900, show_spinner=False)
def _load_games():
    """Reads the NPB slate produced by the nightly pipeline. Returns
    (games, generated_at, slate_date), or (None, None, None) when the
    engine hasn't shipped data yet — the page then shows the honest
    in-development panel instead of anything fabricated."""
    try:
        payload = json.loads(_NPB_GAMES.read_text())
        return (payload.get("games", []), payload.get("generated_at_jst"),
                payload.get("slate_date_jst"))
    except Exception:
        # THREE values, not two — the same bug already fixed in KBO.py.
        # The success path returns a 3-tuple and the caller below unpacks
        # three names, so returning two here turned every failure to read
        # the slate file (missing, truncated, mid-write) into
        # "ValueError: not enough values to unpack" and took the whole
        # page down, instead of degrading into the in-development panel
        # this function was written to reach.
        return None, None, None


games, generated_at, slate_date = _load_games()

# Date-boundary guard: NPB plays on Japan time (UTC+9); see the KBO
# view for the full rationale. Compare the file's slate date to today
# in Japan and flag staleness instead of showing yesterday's slate.
from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _ZI
_today_jst = _dt.now(_ZI("Asia/Tokyo")).strftime("%Y-%m-%d")
_stale = bool(slate_date and slate_date != _today_jst)
if _stale:
    if slate_date > _today_jst:
        # Intended: no games today in Japan, so the pipeline advanced
        # to the next date that has them.
        st.info(
            f"No NPB games today in Japan ({_today_jst}) \u2014 "
            f"showing the next slate: {slate_date}."
        )
    else:
        # File is behind today: the build hasn't run since the date
        # rolled. Prompt a sync.
        st.warning(
            f"Showing the {slate_date} JST slate \u2014 today in Japan is "
            f"{_today_jst}. The nightly build hasn't refreshed yet; press "
            f"\u27f3 Sync latest above to pull the current slate."
        )

if games is None:
    st.markdown(card_open("\u26be NPB engine is being connected"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-body-lg); line-height:1.7;">'
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
            f'<div style="margin-bottom:var(--lc-space-lg);">'
            f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:var(--lc-text-body);">{name}</div>'
            f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">{desc}</div>'
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

if not games and not _stale:
    st.info("No NPB games on today\'s schedule \u2014 likely a league off-day.")
else:
    from engines.run_total import project_total as _project_total, league_run_average
    
    # League baselines, measured from the teams on file rather than assumed.
    # Recomputed per render but trivial — a dict comprehension over ~12 teams.
    def _league_baselines(games):
        teams = {}
        for gm in games or []:
            for sd in ("home", "away"):
                if gm.get(f"{sd}_rs_pg") is not None:
                    teams[gm.get(sd)] = {"rs_pg": gm.get(f"{sd}_rs_pg")}
        return league_run_average(teams)
    
    
    def _starter_era(gm, side):
        """Announced starter's ERA, or None. Never a guess."""
        sp = gm.get(f"{side}_starter_stats") or {}
        try:
            return float(sp.get("era"))
        except (TypeError, ValueError):
            return None
    

    # Measured once per render from the teams actually on this slate.
    # None when there isn't enough data yet, which makes project_total
    # return None and the block simply not render — better than a total
    # built on an assumed league average.
    _LEAGUE_RS = _league_baselines(games)
    _LEAGUE_ERA = None   # NPB team ERA isn't on the slate payload; the
                         # starter term sits out rather than being guessed.

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
                f'font-size:var(--lc-text-small); margin-bottom:var(--lc-space-sm);">'
                f'<span style="font-weight:700; color:{COLOR["text"]};">{name}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["text"]};">'
                f'{joined}</span></div>')

    for gi, g in enumerate(games):
        status = g.get("status", "scheduled")
        subtitle = f'{g.get("stadium", "")} \u00b7 {g.get("time_jst", "TBD")} JST / {g.get("time_et", "TBD")} ET'
        st.markdown(card_open(f'{g.get("away", "TBD")} @ {g.get("home", "TBD")}', subtitle), unsafe_allow_html=True)

        status_style = {"postponed": "bad", "final": "good", "final (tie)": "good"}.get(status, "neutral")
        badges = badge(status.upper(), status_style)

        # ROOF BADGE — the only postponement signal this site can give
        # honestly today.
        #
        # Both leagues report a postponement only once it has been
        # ANNOUNCED, which is routinely after a bet is placed; that is
        # where the voids come from. A forecast would need a weather
        # provider the site does not have. A roof needs nothing: a game
        # under one cannot be called for rain, full stop.
        #
        # Shown only BEFORE the game resolves. On a final, the roof is
        # no longer information — the outcome already answered it — and
        # a badge on every finished game is noise.
        if status == "scheduled":
            _roof = _roof_kind(_LEAGUE, g.get("stadium"))
            if _roof in ("dome", "retractable"):
                badges += badge(_roof_note(_LEAGUE, g.get("stadium")), "good")
            elif _roof == "open":
                badges += badge("open air", "neutral")
            # _roof is None -> say NOTHING. An unlisted venue is unknown,
            # not open air, and a wrong "open air" badge on a domed park
            # is worse than no badge: it invents a risk that is not there.
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
            # English where npb.jp publishes it, Japanese otherwise. A
            # correct Japanese name beats an invented romanisation — see
            # build_name_map in npb_precompute for why these are fetched
            # rather than transliterated.
            name = (sp.get("name_en") or g.get(f"{side}_sp_en")
                    or g.get(f"{side}_starter", "") or g.get(f"{side}_sp", ""))
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
                f'font-size:var(--lc-text-small); margin-top:var(--lc-space-xs);">'
                f'<span style="font-weight:700; color:{COLOR["text"]}; white-space:nowrap;">'
                f'{g.get(side, "")} SP \u2014 {name}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["text"]}; '
                f'text-align:right;">{joined}</span></div>',
                unsafe_allow_html=True,
            )


        # PROJECTED RUN TOTAL — arithmetic on measured run rates, shown
        # with its parts so it reads as a derivation rather than a price.
        # Deliberately NOT a moneyline: see engines/run_total for why a
        # win probability needs fitted history this site doesn't have yet.
        _tot, _det = _project_total(
            {"rs_pg": g.get("home_rs_pg"), "ra_pg": g.get("home_ra_pg")},
            {"rs_pg": g.get("away_rs_pg"), "ra_pg": g.get("away_ra_pg")},
            _LEAGUE_RS,
            league_era=_LEAGUE_ERA,
            home_starter_era=_starter_era(g, "home"),
            away_starter_era=_starter_era(g, "away"),
        )
        if _tot is not None:
            _sp_note = ""
            if _det.get("home_starter_adj") or _det.get("away_starter_adj"):
                _sp_note = " (starters applied)"
            st.markdown(
                f'<div style="display:flex; justify-content:space-between; gap:12px; '
                f'font-size:var(--lc-text-small); margin-top:var(--lc-space-sm);">'
                f'<span style="font-weight:700; color:{COLOR["text"]};">PROJECTED TOTAL</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["text"]};">'
                f'{_tot} runs \u00b7 {g.get("away","")} {_det["away_exp"]} / '
                f'{g.get("home","")} {_det["home_exp"]}{_sp_note}</span></div>',
                unsafe_allow_html=True)

        stats_html = _team_line(g, "away") + _team_line(g, "home")
        if g.get("h2h"):
            stats_html += (f'<div style="font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; '
                           f'margin-top:var(--lc-space-xs);">Season H2H: {g["h2h"]}</div>')
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
        if stats_html:
            st.markdown(f'<div style="margin-top:var(--lc-space-md);">{stats_html}</div>', unsafe_allow_html=True)
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
            # Card carries this page's own identity colour, the same way
            # the WNBA page does. Grade badge colours are grade-driven,
            # so they are identical everywhere — only the title follows
            # the sport.
            accent=SPORT_ACCENTS.get("NPB"),
        )

footer()
