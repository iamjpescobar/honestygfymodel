import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

from styles.kc_theme import (
    inject_kc_theme, badge, card, footer, COLOR,
    pitch_color, pitch_name, edge_tag
)
from styles.table_style import style_stat_table, plain_dark_table

from engines.weather_engine import get_todays_games_with_weather
from engines.park_factors import get_park_factor
from engines.headshots import get_headshot_url
from engines.roster import get_live_team_roster, get_all_teams, get_confirmed_lineup, get_last_starting_lineup
from engines.statcast_engine import (
    get_pitcher_statcast, get_pitcher_advanced_splits, get_batter_profile_windowed, get_batter_vs_pitch_types,
    get_first_pitch_swing
, get_batter_iso_vs_hand
)
from engines.savant_leaderboard import load_percentile_ranks
from engines.live_sync import sync_latest_button
from engines.batter_trends import render_batter_trend
from engines.bvp import render_bvp_card, render_zone_map, render_spray_chart
from engines.edge import edge_components, pen_context, bvp_component
from engines.pick_badges import compute_badges, render_badge_row
from engines.pitcher_weakspots import get_weak_spots, XSLG_HOT, XSLG_COLD
from engines.calibration import log_picks as _log_picks
from engines.team_logos import logo_for
from engines.weather_icons import (
    weather_icon, wind_arrow, temp_icon, park_icon,
)
from engines.park_weather import get_park_forecast
from engines.slam_engine import slam_from_profile
from engines.top_plays import rank_batters, confidence_tier, matchup_tier
from engines.team_abbreviations import team_abbr
from engines.matchup_grades import grade_matchup

st.set_page_config(page_title="Game Card", layout="wide")
inject_kc_theme()

games, games_error = get_todays_games_with_weather()

if games_error:
    st.error(f"Couldn't load today's schedule: {games_error}")
    st.stop()

if not games:
    st.info("No MLB games on today's schedule \u2014 likely an off-day or the All-Star break. The slate returns here automatically on the next game day.")
    st.stop()

# ---------------------------------------------------------
# LAYOUT — full-width content. The old in-page right sidebar
# (account card + Matchup/Lineups/... view radio + Glossary) is gone:
# navigation and the Glossary now live in the single unified right
# sidebar rendered by app.py. Only the Matchup view was ever live —
# the other views were "coming soon" placeholders and will return as
# real pages once they're built.
# ---------------------------------------------------------
view = "\U0001F3E0 Matchup"
LIVE_VIEWS = {"\U0001F3E0 Matchup"}

# -----------------------------------------------------
# WORDMARK — spans full width, anchors brand identity without
# eating into the game carousel's fixed height (a text mark, not an
# image, since there's no logo asset to work from yet)
# -----------------------------------------------------
st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">LOS</span>'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">CAPPERS</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Plain container instead of st.columns — keeps the `with content_col:`
# indentation below untouched while letting the page use the full width
# app.py's main column gives it.
sync_latest_button(key="sync_gamecard")

content_col = st.container()

with content_col:
    # -----------------------------------------------------
    # GAME PICKER \u2014 paginated carousel, fixed height no matter
    # how many games are on the slate (was wrapping into a tall
    # multi-row block before; this caps it at one row, always)
    # -----------------------------------------------------
    PAGE_SIZE = 5
    total_pages = max(1, (len(games) + PAGE_SIZE - 1) // PAGE_SIZE)
    st.session_state.setdefault("gc_page", 0)
    st.session_state.setdefault("gc_selected_game_idx", 0)
    st.session_state["gc_page"] = min(st.session_state["gc_page"], total_pages - 1)

    nav_prev, nav_pills, nav_next = st.columns([0.6, 8, 0.6])
    with nav_prev:
        if st.button("\u25c0", key="gc_prev_page", disabled=st.session_state["gc_page"] == 0):
            st.session_state["gc_page"] -= 1
            st.rerun()
    with nav_next:
        if st.button("\u25b6", key="gc_next_page", disabled=st.session_state["gc_page"] >= total_pages - 1):
            st.session_state["gc_page"] += 1
            st.rerun()

    page = st.session_state["gc_page"]
    visible_games = games[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]
    # Doubleheader-safe labels: two games with the same teams used to
    # produce IDENTICAL pills, so selecting by label could only ever
    # reach game 1 of a doubleheader. Append G1/G2 (schedule order)
    # whenever a matchup appears more than once on the slate, keeping
    # single games clean.
    _base_labels = [f"{team_abbr(x['away'])} @ {team_abbr(x['home'])}" for x in games]
    _dh_counter = {}
    _labels = []
    for _lbl in _base_labels:
        if _base_labels.count(_lbl) > 1:
            _dh_counter[_lbl] = _dh_counter.get(_lbl, 0) + 1
            _labels.append(f"{_lbl} \u00b7 G{_dh_counter[_lbl]}")
        else:
            _labels.append(_lbl)
    visible_labels = _labels[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]
    current_global_label = _labels[st.session_state["gc_selected_game_idx"]]


    with nav_pills:
        # ONE control: clickable logo matchup cards. Each card is the
        # official away/home logos (MLB's own CDN, text fallback) over
        # a button carrying the unique G1/G2-safe label. on_click
        # callbacks run BEFORE the rerun renders, so the selection AND
        # the teal highlight update together on the first click.
        st.markdown(
            "<style>"
            "div[data-testid='stHorizontalBlock']:has(.lc-gamecard)"
            ":not(:has(div[data-testid='stHorizontalBlock'])) button {"
            "  padding: 1px 4px !important; min-height: 26px !important; }"
            "div[data-testid='stHorizontalBlock']:has(.lc-gamecard)"
            ":not(:has(div[data-testid='stHorizontalBlock'])) button p {"
            "  font-size: 10px !important; }"
            "</style>",
            unsafe_allow_html=True,
        )

        def _pick_game(_gidx):
            st.session_state["gc_selected_game_idx"] = _gidx

        _card_cols = st.columns(len(visible_labels)) if visible_labels else []
        for _ci, (_lbl, _vg) in enumerate(zip(visible_labels, visible_games)):
            _gidx = _labels.index(_lbl)
            _sel = _gidx == st.session_state["gc_selected_game_idx"]
            _a, _h = logo_for(_vg.get("away")), logo_for(_vg.get("home"))
            _ai = (f'<img src="{_a}" width="21" height="21" style="vertical-align:middle;">'
                   if _a else f'<b style="font-size:11px;">{team_abbr(_vg.get("away", "?"))}</b>')
            _hi = (f'<img src="{_h}" width="21" height="21" style="vertical-align:middle;">'
                   if _h else f'<b style="font-size:11px;">{team_abbr(_vg.get("home", "?"))}</b>')
            with _card_cols[_ci]:
                st.markdown(
                    f'<div class="lc-gamecard" style="text-align:center; padding:3px 2px 1px 2px; border-radius:8px 8px 0 0; '
                    f'border:{"2px solid " + COLOR["stat_high"] if _sel else "1px solid " + COLOR["text"] + "22"}; '
                    f'border-bottom:none; background:{COLOR["stat_high"] + "14" if _sel else "transparent"};">'
                    f'{_ai}<span style="margin:0 5px; color:{COLOR["text"]}; opacity:0.55; '
                    f'font-size:9px;">@</span>{_hi}</div>',
                    unsafe_allow_html=True,
                )
                st.button(
                    _lbl, key=f"gpick_{_gidx}", use_container_width=True,
                    type="primary" if _sel else "secondary",
                    on_click=_pick_game, args=(_gidx,),
                )

    st.markdown(
        f'<div style="color:{COLOR["text"]}; font-size:13px; font-weight:600; margin:4px 0 12px 0;">'
        f'Page {page + 1} of {total_pages} \u2014 {len(games)} game{"s" if len(games) != 1 else ""} today</div>',
        unsafe_allow_html=True,
    )
    game = games[st.session_state["gc_selected_game_idx"]]

    # -----------------------------------------------------
    # BREADCRUMB
    # -----------------------------------------------------
    try:
        game_time_str = datetime.fromisoformat(game["game_time"].replace("Z", "+00:00")).astimezone(EASTERN).strftime("%-I:%M %p ET") if game.get("game_time") else "TBD"
    except Exception:
        game_time_str = "TBD"
    st.markdown(
        f'<div style="font-size:12.5px; color:{COLOR["gold"]}; margin-bottom:14px;">'
        f'MLB &nbsp;\u203a&nbsp; {game["away"]} @ {game["home"]} &nbsp;\u203a&nbsp; Today, {game_time_str}</div>',
        unsafe_allow_html=True,
    )

    if view not in LIVE_VIEWS:
        with card("coming_soon"):
            st.markdown(f'<div class="pf-card-title">{view}</div><div class="pf-card-subtitle">Coming soon \u2014 not wired up yet</div>', unsafe_allow_html=True)
            st.info(f"The {view} view isn't built yet. Matchup and Top Plays are live; the rest are next.")
        footer()
        st.stop()

    # -----------------------------------------------------
    # MATCHUP HEADER
    # -----------------------------------------------------
    st.markdown(
        f"""
        <div style="text-align:center; margin-bottom:6px;">
            <span style="font-size:26px; font-weight:800; color:{COLOR['headline']};">
                {game['away']} @ {game['home']}
            </span>
        </div>
        <div style="text-align:center; color:{COLOR['gold']}; font-size:13px; margin-bottom:18px;">
            {game['venue']}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------
    # WEATHER + PARK FACTOR \u2014 one compact row, not 4 separate cards
    # -----------------------------------------------------
    park = get_park_factor(game["home"])

    # In-house weather desk: MLB's posted park weather is the source of
    # truth the moment it exists (it carries field-relative wind like
    # "Out To CF"). Until then — most of the day — fill the card with
    # the REAL game-time forecast from the National Weather Service
    # (public-domain US government data), marked with * as a forecast.
    _fc = None
    if not game.get("weather_temp") or not game.get("weather_wind"):
        _fc = get_park_forecast(game.get("venue"), game.get("game_time"))
    _cond_display = game["weather_condition"] or (_fc and _fc.get("short")) or "Not posted yet"
    if game["weather_temp"]:
        temp_display = game["weather_temp"]
    elif _fc and _fc.get("temp") is not None:
        temp_display = f'{_fc["temp"]}*'
    else:
        temp_display = "\u2014"
    _wind_display = game["weather_wind"] or (
        f'{_fc["wind"]}*' if _fc and _fc.get("wind") else "Not posted yet")
    park_display = f'{park["park_factor"]}' if park["verified"] else "Not verified"





    st.markdown(
        f'<div class="pf-card" style="display:flex; justify-content:space-around; text-align:center; padding:10px 16px;">'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Condition</div>'
        f'<div style="margin:2px 0; height:30px;" class="lc-weather-icon">{weather_icon(_cond_display)}</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{_cond_display}</div></div>'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Temp</div>'
        f'<div style="margin:2px 0; height:30px;">{temp_icon(temp_display)}</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{temp_display}\u00b0F</div></div>'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Wind</div>'
        f'<div style="margin:2px 0; height:30px;" class="lc-wind-icon">{wind_arrow(_wind_display)}</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{_wind_display}</div></div>'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Park Factor</div>'
        f'<div style="margin:2px 0; height:30px;">{park_icon(park_display)}</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{park_display}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if _fc:
        st.caption(
            f"* Game-time forecast for {game.get('venue', 'this park')} "
            f"(around {_fc.get('hour_local', '?')} local) \u00b7 precip chance {_fc.get('precip', 0)}% \u00b7 "
            f"Source: National Weather Service \u2014 public-domain US government data, this app's own "
            f"weather desk. Switches to MLB's official park weather (with field-relative wind) "
            f"automatically once posted."
        )

    # -----------------------------------------------------
    # PITCHER SELECTOR
    # -----------------------------------------------------
    pitcher_options = [f"{game['away_pitcher']} ({game['away']})", f"{game['home_pitcher']} ({game['home']})"]
    st.markdown(f'<div style="font-size:14px; font-weight:600; color:{COLOR["magenta_purple"]}; margin-bottom:4px;">Select Pitcher</div>', unsafe_allow_html=True)
    pitcher_choice = st.segmented_control(
        "Select Pitcher", pitcher_options, default=pitcher_options[0], key=f"pitcher_choice_{st.session_state['gc_selected_game_idx']}",
        label_visibility="collapsed",
    )
    if not pitcher_choice:
        pitcher_choice = pitcher_options[0]
    selected_pitcher_name = game["away_pitcher"] if pitcher_choice.startswith(game["away_pitcher"]) else game["home_pitcher"]
    opposing_team = game["home"] if pitcher_choice.startswith(game["away_pitcher"]) else game["away"]

    # The pitcher's real MLBAM id comes from MLB's schedule feed. If MLB
    # hasn't posted a probable pitcher yet, we show the honest warning
    # below instead of falling back to a name lookup (which downloaded
    # pybaseball's entire player register into memory).
    real_pitcher_id = game["away_pitcher_id"] if pitcher_choice.startswith(game["away_pitcher"]) else game["home_pitcher_id"]
    pitcher_id = real_pitcher_id
    pitcher_data = get_pitcher_statcast(pitcher_id) if pitcher_id else {}

    if pitcher_id is None:
        st.warning(f"Couldn't resolve a player ID for {selected_pitcher_name} \u2014 stats below will be empty.")

    splits_vs_r = get_pitcher_advanced_splits(pitcher_id, side="R") if pitcher_id else None
    splits_vs_l = get_pitcher_advanced_splits(pitcher_id, side="L") if pitcher_id else None

    # -----------------------------------------------------
    # PITCHER HEADER + PITCH MIX (colored bars, real usage%)
    # -----------------------------------------------------
    with card("pitcher_header"):
        col_head, col_mix = st.columns([1, 3])
        with col_head:
            if pitcher_id:
                st.image(get_headshot_url(pitcher_id), width=80)
            st.markdown(f'<span style="font-weight:700; color:{COLOR["gold"]};">{selected_pitcher_name}</span>', unsafe_allow_html=True)
            _baa = pitcher_data.get("BA") if pitcher_data else None
            if _baa is not None and (pitcher_data.get("AB") or 0) > 0:
                st.markdown(
                    f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:12px; '
                    f'color:{COLOR["text"]}; margin-top:2px;">BA allowed '
                    f'<span style="font-weight:700; color:{COLOR["stat_high"]};">{_baa:.3f}</span></div>',
                    unsafe_allow_html=True,
                )

        with col_mix:
            st.markdown(f'<div class="pf-card-title" style="margin-bottom:8px; color:{COLOR["gold"]};">Pitch Mix (Season)</div>', unsafe_allow_html=True)
            arsenal = pitcher_data.get("Pitch Arsenal", {}) if pitcher_data else {}
            if arsenal:
                bars_html = '<div style="display:flex; gap:18px; flex-wrap:wrap;">'
                for pt, usage in sorted(arsenal.items(), key=lambda x: -x[1])[:6]:
                    c = pitch_color(pt)
                    bars_html += (
                        f'<div style="min-width:100px;">'
                        f'<div style="font-size:11px; color:{c}; font-weight:600;">{pitch_name(pt)}</div>'
                        f'<div style="height:5px; width:100%; background:{COLOR["surface_raised"]}; border-radius:3px; margin:4px 0;">'
                        f'<div style="height:5px; width:{min(usage,100)}%; background:{c}; border-radius:3px;"></div>'
                        f'</div>'
                        f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:12px; color:{COLOR["text"]};">{usage:.2f}%</div>'
                        f'</div>'
                    )
                bars_html += '</div>'
                st.markdown(bars_html, unsafe_allow_html=True)
            else:
                st.caption("No arsenal data available.")

    # -----------------------------------------------------
    # WEAK SPOTS — where this starter actually gets hurt
    # -----------------------------------------------------
    if pitcher_id:
        with st.expander("\U0001F3AF Weak spots \u2014 where he gets hurt"):
            _ws = get_weak_spots(pitcher_id)
            if _ws.get("error"):
                st.caption(_ws["error"])
            else:
                def _xslg_chip(v):
                    if v is None:
                        return f'<span style="color:{COLOR["text"]}; opacity:0.4;">\u2014</span>'
                    c = (COLOR["error"] if v >= XSLG_HOT
                         else COLOR["stat_high"] if v <= XSLG_COLD else COLOR["warn"])
                    return (f'<span style="font-weight:800; color:{c};">{v:.3f}</span>')

                st.markdown(
                    f'<div class="pf-card-subtitle">xSLG allowed on contact \u00b7 '
                    f'red = hitters do real damage, blue = he wins there \u00b7 '
                    f'anything below its sample floor shows \u2014 instead of a number, '
                    f'because a rate off a thin bucket is noise. Formula and floors in '
                    f'engines/pitcher_weakspots.py.</div>',
                    unsafe_allow_html=True,
                )

                _pitches = [p for p in _ws.get("pitches", []) if p["usage"] >= 3]
                if _pitches:
                    st.markdown(
                        f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; '
                        f'margin-top:8px;">By pitch type</div>', unsafe_allow_html=True)
                    _rows = "".join(
                        f'<tr><td style="padding:3px 8px 3px 0; font-size:11.5px; '
                        f'color:{COLOR["text"]};">{p["name"]}</td>'
                        f'<td style="padding:3px 8px; font-size:11px; color:{COLOR["text"]}; '
                        f'opacity:0.6;">{p["usage"]:.0f}% usage</td>'
                        f'<td style="padding:3px 8px; font-size:12px;">{_xslg_chip(p.get("xslg"))}</td>'
                        f'<td style="padding:3px 0; font-size:10px; color:{COLOR["text"]}; '
                        f'opacity:0.5;">{p.get("reason", str(p["bbe"]) + " batted balls")}</td></tr>'
                        for p in _pitches
                    )
                    st.markdown(f'<table style="width:100%;">{_rows}</table>',
                                unsafe_allow_html=True)

                _bands = _ws.get("bands", [])
                if _bands:
                    st.markdown(
                        f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; '
                        f'margin-top:10px;">By zone band</div>', unsafe_allow_html=True)
                    _cells = "".join(
                        f'<td style="text-align:center; padding:6px; border:1px solid '
                        f'{COLOR["text"]}1E; border-radius:6px;">'
                        f'<div style="font-size:10px; color:{COLOR["text"]}; opacity:0.6;">{b["band"]}</div>'
                        f'<div style="font-size:13px;">{_xslg_chip(b.get("xslg"))}</div>'
                        f'<div style="font-size:9px; color:{COLOR["text"]}; opacity:0.45;">'
                        f'{b["bbe"]} bbe</div></td>'
                        for b in _bands
                    )
                    st.markdown(
                        f'<table style="width:100%; border-spacing:4px; '
                        f'border-collapse:separate;"><tr>{_cells}</tr></table>',
                        unsafe_allow_html=True)

                _tto = _ws.get("tto", [])
                if _tto:
                    st.markdown(
                        f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; '
                        f'margin-top:10px;">Times through the order</div>', unsafe_allow_html=True)
                    _cells = "".join(
                        f'<td style="text-align:center; padding:6px; border:1px solid '
                        f'{COLOR["text"]}1E; border-radius:6px;">'
                        f'<div style="font-size:10px; color:{COLOR["text"]}; opacity:0.6;">'
                        f'{t["pass"]}{"st" if t["pass"]==1 else "nd" if t["pass"]==2 else "rd"} time</div>'
                        f'<div style="font-size:13px;">{_xslg_chip(t.get("xslg"))}</div>'
                        f'<div style="font-size:9px; color:{COLOR["text"]}; opacity:0.45;">'
                        f'{t["bbe"]} bbe</div></td>'
                        for t in _tto
                    )
                    st.markdown(
                        f'<table style="width:100%; border-spacing:4px; '
                        f'border-collapse:separate;"><tr>{_cells}</tr></table>',
                        unsafe_allow_html=True)
                    st.caption("Most starters decline the third time through a lineup \u2014 "
                               "a steep jump here is a real bullpen and late-innings angle.")

                _halves = _ws.get("halves", [])
                if any(h.get("xslg") is not None for h in _halves):
                    _txt = " \u00b7 ".join(
                        f'{h["half"]}: ' + (f'{h["xslg"]:.3f}' if h.get("xslg") is not None else "\u2014")
                        for h in _halves
                    )
                    st.caption(
                        f"Top vs bottom of order \u2014 {_txt}. Shown for context only and "
                        f"deliberately not scored: a gap here mostly reflects that better hitters "
                        f"bat at the top, not a repeatable weakness."
                    )

                # Per batting-order slot (1-9) — the granular version, each
                # slot flagged only above its sample floor. Aligned to
                # tonight's actual hitters in the "vs this lineup" section
                # below the lineup table.
                _slots = _ws.get("slots", [])
                if any(s.get("xslg") is not None for s in _slots):
                    st.markdown(
                        f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; '
                        f'margin-top:10px;">By batting-order slot</div>', unsafe_allow_html=True)
                    _cells = "".join(
                        f'<td style="text-align:center; padding:5px; border:1px solid '
                        f'{COLOR["text"]}1E; border-radius:6px;">'
                        f'<div style="font-size:10px; color:{COLOR["text"]}; opacity:0.6;">{s["slot"]}</div>'
                        f'<div style="font-size:12px;">{_xslg_chip(s.get("xslg"))}</div>'
                        f'<div style="font-size:8.5px; color:{COLOR["text"]}; opacity:0.45;">'
                        f'{s["bbe"]}</div></td>'
                        for s in _slots
                    )
                    st.markdown(
                        f'<table style="width:100%; border-spacing:3px; '
                        f'border-collapse:separate;"><tr>{_cells}</tr></table>',
                        unsafe_allow_html=True)
                    st.caption("Per-slot splits carry a real caveat \u2014 a slot's line partly "
                               "reflects which hitters happened to bat there across his starts, "
                               "not only his own skill. Slots below the sample floor show \u2014 "
                               "and are never flagged. Read it alongside the lineup mapping below.")

    # -----------------------------------------------------
    # MATCHUP GRADES — transparent signal checklists, both starters
    # -----------------------------------------------------
    # Grade window — Season is the exact formula that's been hitting;
    # L25/L15/L10/L5 re-run the SAME checklist on both starters' last
    # N games only. Widget return value is read directly, so it takes
    # effect on the first click.
    _gw_opts = {"Season": "season", "L25": "l25", "L15": "l15", "L10": "l10", "L5": "l5"}
    _gw_choice = st.segmented_control(
        "Grade window", list(_gw_opts.keys()), default="Season",
        key="gc_grade_window", label_visibility="collapsed",
    )
    _gw_label = _gw_choice or "Season"
    _grade_window = _gw_opts.get(_gw_label, "season")
    grades = grade_matchup(
        game.get("away_pitcher_id"), game.get("home_pitcher_id"),
        game.get("away_pitcher", "Away"), game.get("home_pitcher", "Home"),
        park_factor=park.get("park_factor"), park_verified=park.get("verified", False),
        temp=game.get("weather_temp"), window=_grade_window,
    )
    with card("matchup_grades_card"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Matchup Grades \u00b7 {_gw_label}</div>'
            f'<div class="pf-card-subtitle">This app\'s own signal checklists from real Statcast splits, '
            f'park factor, and posted weather \u2014 formula documented in engines/matchup_grades.py. '
            f'Not calibrated probabilities.</div>',
            unsafe_allow_html=True,
        )
        if grades.get("error"):
            st.info(grades["error"])
        else:
            gcol1, gcol2 = st.columns(2)
            for gcol, key, title in ((gcol1, "ml", "Moneyline"), (gcol2, "ou", "Over / Under")):
                with gcol:
                    res = grades.get(key)
                    st.markdown(f'<div style="font-weight:700; color:{COLOR["magenta_purple"]}; font-size:13px;">{title}</div>', unsafe_allow_html=True)
                    if not res:
                        st.caption("No qualifying signals \u2014 no lean either way.")
                        continue
                    if res.get("lean"):
                        st.markdown(
                            f'<div style="font-size:16px; font-weight:800; color:{COLOR["stat_high"]};">'
                            f'Lean: {res["lean"]} \u00b7 Grade {res["grade"]}</div>'
                            f'<div style="font-size:11px; color:{COLOR["gold"]};">{res["score"]}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f'<div style="font-size:13px; color:{COLOR["gold"]};">{res["score"]}</div>', unsafe_allow_html=True)
                    for s in res.get("signals", []):
                        st.markdown(f'<div style="font-size:11.5px; color:{COLOR["text"]};">\u2713 {s}</div>', unsafe_allow_html=True)

    # -----------------------------------------------------
    # BOTH STARTERS + BULLPEN — full-staff arsenal browser
    # -----------------------------------------------------
    def _bullpen_opponent_batters(gpk, team_label, side):
        """Light lineup fetch for the bullpen browser, same honest
        fallback order as the main lineup section but without the
        banners: today's confirmed lineup -> real starting 9 from the
        team's last game -> roster. Returns (batters, source_label)."""
        lineup, ok = get_confirmed_lineup(gpk, side)
        if ok:
            return [p for p in lineup if not p.get("is_pitcher")], "today's confirmed lineup"
        last, last_date, ok2 = get_last_starting_lineup(team_label)
        if ok2:
            return [p for p in last if not p.get("is_pitcher")], f"real starting 9 from their last game ({last_date})"
        roster_p = get_live_team_roster(team_label) or []
        return [p for p in roster_p if not p.get("is_pitcher")][:9], "team roster (no lineup posted yet)"

    def _arsenal_bars(p_data):
        arsenal_d = p_data.get("Pitch Arsenal", {}) if p_data else {}
        if not arsenal_d:
            st.caption("No arsenal data available.")
            return
        html = ""
        for pt, usage in sorted(arsenal_d.items(), key=lambda x: -x[1])[:6]:
            c = pitch_color(pt)
            html += (
                f'<div style="margin-bottom:6px;">'
                f'<div style="display:flex; justify-content:space-between;">'
                f'<span style="font-size:11px; color:{c}; font-weight:600;">{pitch_name(pt)}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; font-size:11px; color:{COLOR["text"]};">{usage:.1f}%</span>'
                f'</div>'
                f'<div style="height:5px; width:100%; background:{COLOR["surface_raised"]}; border-radius:3px;">'
                f'<div style="height:5px; width:{min(usage,100)}%; background:{c}; border-radius:3px;"></div>'
                f'</div></div>'
            )
        st.markdown(html, unsafe_allow_html=True)

    with card("dual_arsenal"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Both Starters \u2014 Arsenal Comparison</div>'
            f'<div class="pf-card-subtitle">Real usage from each starter\'s own Statcast pitches</div>',
            unsafe_allow_html=True,
        )
        ac, hc = st.columns(2)
        for colx, sp_name, sp_id, team_label in (
            (ac, game.get("away_pitcher", "TBD"), game.get("away_pitcher_id"), game.get("away")),
            (hc, game.get("home_pitcher", "TBD"), game.get("home_pitcher_id"), game.get("home")),
        ):
            with colx:
                st.markdown(f'<div style="font-weight:700; color:{COLOR["magenta_purple"]}; font-size:13px;">{sp_name} <span style="color:{COLOR["gold"]}; font-weight:600;">({team_abbr(team_label)})</span></div>', unsafe_allow_html=True)
                if sp_id:
                    _arsenal_bars(get_pitcher_statcast(sp_id))
                else:
                    st.caption("Starter not posted yet.")

    with st.expander("\U0001F9E4 Bullpen browser \u2014 any pitcher on either staff"):
        st.caption(
            "Bullpen changes flip matchups. Pick any rostered pitcher to see their real "
            "arsenal on demand \u2014 loaded only when you ask, so the page stays fast."
        )
        bp1, bp2 = st.columns(2)
        for colx, team_name in ((bp1, game.get("away")), (bp2, game.get("home"))):
            with colx:
                st.markdown(f'<div style="font-weight:700; color:{COLOR["gold"]}; font-size:13px;">{team_name}</div>', unsafe_allow_html=True)
                staff = [p for p in (get_live_team_roster(team_name) or []) if p.get("is_pitcher")]
                if not staff:
                    st.caption("Roster unavailable right now.")
                    continue
                pick = st.selectbox(
                    "Pitcher", [p["name"] for p in staff],
                    index=None, placeholder="Choose a pitcher\u2026",
                    key=f'bp_{team_name}_{st.session_state["gc_selected_game_idx"]}',
                    label_visibility="collapsed",
                )
                if pick:
                    sel = next((p for p in staff if p["name"] == pick), None)
                    if sel and sel.get("id"):
                        bp_data = get_pitcher_statcast(sel["id"])
                        _arsenal_bars(bp_data)
                        # Opposing lineup vs this arsenal — same real
                        # engine the starter's pitch-matchup stat uses
                        # (get_batter_vs_pitch_types), pointed at this
                        # reliever's top 3 pitches.
                        bp_arsenal = bp_data.get("Pitch Arsenal", {}) if bp_data else {}
                        bp_top3 = [pt for pt, _u in sorted(bp_arsenal.items(), key=lambda x: -x[1])[:3]]
                        if bp_top3:
                            opp_label = game.get("home") if team_name == game.get("away") else game.get("away")
                            opp_side = "home" if opp_label == game.get("home") else "away"
                            opp_batters, opp_src = _bullpen_opponent_batters(game.get("game_pk"), opp_label, opp_side)
                            if opp_batters:
                                bp_rows = []
                                for ob in opp_batters[:9]:
                                    vs = get_batter_vs_pitch_types(ob.get("id"), tuple(bp_top3), window="season", unit="bbe")
                                    bp_rows.append({
                                        "Player": ob.get("name", "?"),
                                        "BA": vs.get("BA"),
                                        "Brl %": vs.get("Brl %"),
                                        "HH %": vs.get("HH %"),
                                        "Whiff %": vs.get("Whiff %"),
                                        "SwStr %": vs.get("SwStr %"),
                                        "Pitches": vs.get("_pitches_seen", 0),
                                    })
                                bp_names = ", ".join(pitch_name(p) for p in bp_top3)
                                st.markdown(
                                    f'<div style="font-size:11px; font-weight:700; color:{COLOR["gold"]}; '
                                    f'margin-top:10px;">{opp_label} vs this arsenal ({bp_names})</div>',
                                    unsafe_allow_html=True,
                                )
                                st.dataframe(
                                    style_stat_table(
                                        pd.DataFrame(bp_rows).set_index("Player"),
                                        favor_high=["BA", "Brl %", "HH %"],
                                        favor_low=["Whiff %", "SwStr %"],
                                        gradient=True,
                                    ),
                                    width="stretch",
                                )
                                st.caption(
                                    f"Season numbers vs those pitch types only \u2014 blue rows are the "
                                    f"batters who punish this stuff, red rows are the ones it beats. "
                                    f"Lineup source: {opp_src}. A small Pitches count means a small "
                                    f"sample \u2014 read those rows gently."
                                )
                    else:
                        st.caption("No ID for that pitcher \u2014 no data to show.")

    # -----------------------------------------------------
    # LOAD LINEUP + SCORES (shared across everything below)
    # -----------------------------------------------------
    opposing_side = "home" if opposing_team == game["home"] else "away"
    confirmed_lineup, lineup_confirmed = get_confirmed_lineup(game.get("game_pk"), opposing_side)

    if lineup_confirmed:
        batters = [p for p in confirmed_lineup if not p["is_pitcher"]]
    else:
        # MLB hasn't posted today's real lineup yet (normal 1-3 hours
        # before first pitch). Honest fallback #1: this team's REAL 9
        # starters from their most recently completed game (real posted
        # data, not a guess) — this is what belongs here, not an
        # arbitrary slice of the roster. The old fallback below took the
        # first 9 non-pitchers in whatever order the MLB API happened to
        # return the roster in (not sorted by playing time or batting
        # order at all) — which silently cut regulars like a cleanup
        # hitter or DH from the page any time they didn't happen to land
        # in that arbitrary first 9, while bench/depth players did.
        last_lineup, last_game_date, last_confirmed = get_last_starting_lineup(opposing_team)
        if last_confirmed:
            batters = [p for p in last_lineup if not p["is_pitcher"]]
            st.info(
                f"MLB hasn't posted {opposing_team}'s confirmed starting lineup yet "
                f"(usually posted 1\u20133 hours before first pitch) \u2014 showing their real "
                f"starting 9 from their last game ({last_game_date}) instead. This will switch "
                f"to today's confirmed batting order automatically once MLB posts it."
            )
        else:
            # Fallback #2: no completed game in the last 14 days to pull a
            # real lineup from (e.g. after a long break) — show the full
            # position-player roster rather than an arbitrary, misleading
            # slice of it, clearly labeled as just the roster.
            roster = get_live_team_roster(opposing_team)
            batters = [p for p in roster if not p["is_pitcher"]]
            st.info(
                f"MLB hasn't posted {opposing_team}'s confirmed starting lineup yet, and there's "
                f"no recent game to pull a real starting 9 from \u2014 showing their full roster "
                f"below instead. This will switch to the real confirmed batting order automatically "
                f"once MLB posts it."
            )

    # HR Score / Hit Score / K Score come from a SEPARATE, real, live
    # source: MLB's own Statcast percentile rankings, matched by player
    # ID. This doesn't depend on FanGraphs at all, so it doesn't have
    # the "blocked from cloud hosts" problem the old version did.
    savant_df, savant_error = load_percentile_ranks()
    league_data_available = savant_df is not None and not savant_df.empty
    if not league_data_available:
        st.warning(
            f"Baseball Savant's live percentile rankings aren't reachable right now "
            f"({savant_error}). HR Score / Hit Score / K Score below will show as N/A "
            f"until that's back \u2014 raw stats (Brl%, HH%, LD%) are unaffected."
        )

    batter_profiles = []
    for b in batters:
        # Real, ID-matched batted-ball profile — same reliable engine
        # SLAM uses, not the old name-matching one. Eliminates the
        # missing-fields bug AND the accented-name matching failures
        # in one move, since there's no name string involved at all.
        profile = get_batter_profile_windowed(b.get("id"), window="season", unit="bbe")
        batter_profiles.append({"name": b["name"], "bats": b.get("bats") or "?", "id": b.get("id"), "profile": profile})

    ranked = rank_batters(batter_profiles, savant_df) if batter_profiles else []

    # ---- Matchup Edge layer (Phase 2): HR Edge = HR Score + BvP(±15)
    # + Zone Fit(±15) + Bullpen(±10). Every component sample-floored
    # and shown in the Edge breakdown below the table. engines/edge.py
    # documents the exact tiers and math.
    # Defined unconditionally: the lineup table reads this for switch
    # hitters even when no probable is posted, and a NameError there
    # would take down the whole page.
    _p_throws = (pitcher_data or {}).get("p_throws") or (pitcher_data or {}).get("Throws")

    if ranked and pitcher_id:
        _pitcher_team = game["away"] if opposing_team == game["home"] else game["home"]
        with st.spinner("Computing matchup edges \u2014 the first lineup of the day also "
                        "builds the slate-wide bullpen baseline (~30s once, cached all day; "
                        "instant after)\u2026"):
            _pen_adj, _pen_note = pen_context(_pitcher_team, pitcher_id)
            for _r in ranked:
                _r.update(edge_components(_r.get("id"), pitcher_id,
                                          _r.get("hr_score"), _pen_adj, _pen_note))
                if _p_throws in ("R", "L") and _r.get("id"):
                    _r["iso_vs_hand"] = get_batter_iso_vs_hand(_r["id"], _p_throws)
                    _r["opp_hand"] = f"{_p_throws}HP"

    def _score_sort_key(r, field):
        v = r.get(field)
        return -1 if v is None else -v  # None sorts last regardless of view

    def _score_display(v):
        return "N/A" if v is None else str(v)

    def _score_num(v):
        """0 for display-only numeric contexts (progress bars) \u2014 always
        paired with the N/A text elsewhere so it's never the only signal."""
        return 0 if v is None else v

    # -----------------------------------------------------
    # TODAY'S TOP PLAYS \u2014 plain section label, not its own card,
    # since each item below is now its own standalone card \u2014 a card
    # wrapping four more cards would just nest borders inside borders.
    # -----------------------------------------------------
    st.markdown(
        f'<div class="pf-card-title" style="margin-top:6px; color:{COLOR["gold"]};">Today\'s Top Plays</div>'
        f'<div class="pf-card-subtitle">This app\'s own composite scores \u2014 see engines/top_plays.py</div>',
        unsafe_allow_html=True,
    )
    if not ranked:
        st.info(f"No lineup data available for {opposing_team} right now.")
    else:
        if not league_data_available:
            st.caption("Scores below will show as N/A \u2014 see warning above.")

        def _targets_table(sort_field, label):
            rows = []
            for r in sorted(ranked, key=lambda x: _score_sort_key(x, sort_field))[:5]:
                rows.append({"Player": r["name"], "Bats": r["bats"], label: _score_num(r[sort_field])})
            return pd.DataFrame(rows)

        top_row1, top_row2 = st.columns(2)
        with top_row1:
            with card("hr_targets"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Top HR Targets</div>', unsafe_allow_html=True)
                hr_df = _targets_table("hr_score", "HR Score")
                st.dataframe(style_stat_table(hr_df, favor_high=["HR Score"], gradient=True), width="stretch")
        with top_row2:
            with card("hit_targets"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Best Hit Targets</div>', unsafe_allow_html=True)
                hit_df = _targets_table("hit_score", "Hit Score")
                st.dataframe(style_stat_table(hit_df, favor_high=["Hit Score"], gradient=True), width="stretch")

        bot_row1, bot_row2 = st.columns(2)
        with bot_row1:
            with card("k_targets"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Strikeout Targets</div>', unsafe_allow_html=True)
                k_df = _targets_table("k_score", "K Score")
                st.dataframe(style_stat_table(k_df, favor_high=["K Score"], gradient=True), width="stretch")
        with bot_row2:
            hr_vals = [r["hr_score"] for r in ranked if r["hr_score"] is not None]
            hit_vals = [r["hit_score"] for r in ranked if r["hit_score"] is not None]
            avg_hr = round(sum(hr_vals) / len(hr_vals)) if hr_vals else None
            avg_hit = round(sum(hit_vals) / len(hit_vals)) if hit_vals else None
            with card("stack_pick"):
                st.markdown(
                    f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Stack Pick</div>'
                    f'<div style="font-size:17px; font-weight:800; color:{COLOR["magenta_purple"]}; margin-bottom:12px;">{opposing_team}</div>'
                    f'<div style="display:flex; gap:16px;">'
                    f'<div><div style="font-family:\'JetBrains Mono\',monospace; font-size:22px; font-weight:700; color:{COLOR["stat_high"]};">{_score_display(avg_hr)}</div>'
                    f'<div style="font-size:10px; color:{COLOR["gold"]}; text-transform:uppercase;">Avg HR Score</div></div>'
                    f'<div><div style="font-family:\'JetBrains Mono\',monospace; font-size:22px; font-weight:700; color:{COLOR["warn"]};">{_score_display(avg_hit)}</div>'
                    f'<div style="font-size:10px; color:{COLOR["gold"]}; text-transform:uppercase;">Avg Hit Score</div></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # =======================================================
    # VIEW: MATCHUP
    # =======================================================
    if view == "\U0001F3E0 Matchup":
        st.markdown(
            f'<div class="pf-card-title" style="margin-top:6px; color:{COLOR["gold"]};">Splits</div>'
            f'<div class="pf-card-subtitle" style="color:{COLOR["magenta_purple"]};">Blue = favorable for batter, red = favorable for pitcher \u00b7 IP estimated from Statcast out events (no official box-score feed)</div>',
            unsafe_allow_html=True,
        )
        splits_overall = get_pitcher_advanced_splits(pitcher_id) if pitcher_id else None
        rows = {"Overall": splits_overall, "vs RHB": splits_vs_r, "vs LHB": splits_vs_l}
        rows = {k: v for k, v in rows.items() if v is not None}

        if rows:
            full_df = pd.DataFrame(rows).T
            stats_cols = ["IP", "BA", "SLG", "ISO", "WHIP", "HR", "HR/9"]
            strikes_cols = ["BB%", "Whiff%", "K%", "Putaway%", "SwStr%", "K/9", "1stPS%", "Meatball%"]
            g1, g2 = st.columns(2)
            with g1:
                with card("stats_table"):
                    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">STATS</div>', unsafe_allow_html=True)
                    st.dataframe(
                        style_stat_table(full_df[stats_cols], favor_high=["BA", "SLG", "ISO", "HR", "HR/9"], favor_low=["WHIP"], gradient=True),
                        width="stretch",
                    )
            with g2:
                with card("strikes_table"):
                    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">STRIKES</div>', unsafe_allow_html=True)
                    st.dataframe(
                        style_stat_table(full_df[strikes_cols], favor_low=["BB%", "Whiff%", "K%", "Putaway%", "SwStr%", "K/9", "Meatball%"], favor_high=["1stPS%"], gradient=True),
                        width="stretch",
                    )
            st.caption("Computed by this app directly from raw Statcast pitch data \u2014 see get_pitcher_advanced_splits() for exact definitions.")
        else:
            st.info("No split data available for this pitcher yet.")

        # -------------------------------------------------
        # DENSE LINEUP TABLE \u2014 percentiles, progress bars,
        # matchup/edge tags, confidence \u2014 all from real data
        # -------------------------------------------------
        if arsenal:
            with card("arsenal_pills"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Pitcher\'s arsenal (overall usage)</div>', unsafe_allow_html=True)
                badges_html = '<div style="display:flex; gap:8px; flex-wrap:wrap;">'
                for pt, usage in sorted(arsenal.items(), key=lambda x: -x[1]):
                    c = pitch_color(pt)
                    badges_html += (
                        f'<div style="padding:6px 14px; border-radius:6px; background:{c}22; '
                        f'border:1px solid {c}66; color:{c}; font-weight:700; font-size:13px; '
                        f'font-family:\'JetBrains Mono\',monospace;">{pitch_name(pt)} {usage:.0f}%</div>'
                    )
                badges_html += '</div>'
                st.markdown(badges_html, unsafe_allow_html=True)

        table_rows = []
        with card("lineup"):
            st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{opposing_team} Lineup</div><div class="pf-card-subtitle" style="color:{COLOR["magenta_purple"]};">vs {selected_pitcher_name}</div>', unsafe_allow_html=True)

            if not ranked:
                st.info(f"No lineup data available for {opposing_team} right now.")
            else:
                filt_col, sort_col, window_col = st.columns([1, 1, 1])
                with filt_col:
                    bats_present = sorted(set(r["bats"] for r in ranked if r["bats"] in ("R", "L", "S")))
                    bats_filter = st.segmented_control(
                        "Bats", ["All"] + bats_present, default="All", key="lineup_bats_filter"
                    )
                with sort_col:
                    sort_choice = st.selectbox(
                        "Sort by", ["SLAM", "HR Edge", "HR Score", "Hit Score", "xwOBA", "xSLG", "ISO", "Brl%", "HH%"], key="lineup_sort_by"
                    )
                with window_col:
                    window_choice = st.selectbox(
                        "Window",
                        [
                            "Season",
                            "Last 15 Games", "Last 10 Games", "Last 5 Games",
                            "Last 60 PA", "Last 25 PA", "Last 15 PA",
                            "Last 60 BBE", "Last 25 BBE", "Last 15 BBE", "Last 5 BBE",
                        ],
                        key="lineup_window",
                    )
                # Each label maps to a (window, unit) pair. "unit" decides
                # what "last N" counts: games played, plate appearances, or
                # batted-ball events. Games/PA give a fuller, more stable
                # recent-form read; BBE zooms in on contact quality only.
                window_unit_map = {
                    "Season": ("season", "bbe"),
                    "Last 15 Games": ("l15", "games"),
                    "Last 10 Games": ("l10", "games"),
                    "Last 5 Games": ("l5", "games"),
                    "Last 60 PA": ("l60", "pa"),
                    "Last 25 PA": ("l25", "pa"),
                    "Last 15 PA": ("l15", "pa"),
                    "Last 60 BBE": ("l60", "bbe"),
                    "Last 25 BBE": ("l25", "bbe"),
                    "Last 15 BBE": ("l15", "bbe"),
                    "Last 5 BBE": ("l5", "bbe"),
                }
                window_key, unit_key = window_unit_map[window_choice]

                filtered = ranked if not bats_filter or bats_filter == "All" else [r for r in ranked if r["bats"] == bats_filter]

                # Real windowed profile fetched ONCE per batter for the
                # selected window — both SLAM and the raw stat columns
                # (Brl%, HH%, etc.) below now come from this SAME real
                # pull, so they always agree with each other and both
                # genuinely respect the Window filter, not just SLAM.
                # Switch hitters are profiled from the side they will
                # ACTUALLY bat tonight, which the opposing starter's
                # throwing hand decides (S vs RHP means batting left).
                # Blending both sides into one number hid real platoon
                # splits — often the difference between a good matchup
                # and a bad one for the very same player.
                def _side_for(row):
                    if (row.get("bats") or "").upper() != "S":
                        return None
                    if _p_throws == "R":
                        return "L"
                    if _p_throws == "L":
                        return "R"
                    return None

                windowed_profile_cache = {
                    r["name"]: get_batter_profile_windowed(
                        r.get("id"), window=window_key, unit=unit_key,
                        stand=_side_for(r))
                    for r in filtered
                }

                # For switch hitters, also pull the OTHER side so the table
                # can show both L and R as separate rows. _side_for gives
                # tonight's side (opposite the pitcher's hand); this fetches
                # the reverse. Keyed by name; only populated for S bats.
                def _other_side(row):
                    s = _side_for(row)
                    if s == "L":
                        return "R"
                    if s == "R":
                        return "L"
                    # no probable posted (_p_throws unknown): show both sides
                    # explicitly for switch hitters so neither is hidden
                    return None
                switch_other_cache = {}
                for r in filtered:
                    if (r.get("bats") or "").upper() != "S":
                        continue
                    _os = _other_side(r)
                    if _os is None:
                        # no probable: fetch BOTH sides, neither is "tonight's"
                        switch_other_cache[r["name"]] = {
                            "L": get_batter_profile_windowed(r.get("id"), window=window_key, unit=unit_key, stand="L"),
                            "R": get_batter_profile_windowed(r.get("id"), window=window_key, unit=unit_key, stand="R"),
                        }
                    else:
                        switch_other_cache[r["name"]] = {
                            _os: get_batter_profile_windowed(r.get("id"), window=window_key, unit=unit_key, stand=_os),
                        }
                slam_cache = {name: slam_from_profile(p) for name, p in windowed_profile_cache.items()}

                # BvP joins SLAM: the SAME documented tiers HR Edge uses
                # (±15 / ±10 with PA floors — engines/edge.py). Base and
                # adjustment are both kept so the Edge breakdown can show
                # the movement, and the Matchup Edges tiers below inherit
                # the ADJUSTED number — real career ownership of this
                # starter now moves a bat between tiers.
                _name_to_id = {_rr["name"]: _rr.get("id") for _rr in ranked}
                slam_bvp_cache = {}
                for _nm, _sr in slam_cache.items():
                    _base = _sr.get("slam_score")
                    _adj, _line = 0, None
                    if _base is not None and pitcher_id and _name_to_id.get(_nm):
                        _adj, _line = bvp_component(_name_to_id[_nm], pitcher_id)
                    slam_bvp_cache[_nm] = {
                        "final": (round(max(0.0, _base + _adj), 1) if _base is not None else None),
                        "base": _base, "adj": _adj, "line": _line,
                    }

                sort_key_map = {
                    "SLAM": lambda r: slam_bvp_cache[r["name"]]["final"] or 0.0,
                    "HR Edge": lambda r: _score_num(r.get("edge")),
                    "HR Score": lambda r: _score_num(r["hr_score"]),
                    "Hit Score": lambda r: _score_num(r["hit_score"]),
                    "xwOBA": lambda r: windowed_profile_cache[r["name"]].get("xwOBA") or 0,
                    "xSLG": lambda r: windowed_profile_cache[r["name"]].get("xSLG") or 0,
                    "ISO": lambda r: windowed_profile_cache[r["name"]].get("ISO") or 0,
                    "Brl%": lambda r: windowed_profile_cache[r["name"]].get("Brl %", 0),
                    "HH%": lambda r: windowed_profile_cache[r["name"]].get("HH %", 0),
                }
                filtered = sorted(filtered, key=sort_key_map[sort_choice], reverse=True)

                if not filtered:
                    st.info(f"No batters match that Bats filter for {opposing_team}.")

                def _stat_row(name, bats_label, profile, *, matchup=None, slam=None,
                              hr_edge=None, hr_score=None, hit_score=None,
                              edge_cell=None, edge_label="", edge_tier="neutral",
                              confidence=""):
                    """One table row. Score/matchup fields are optional so a
                    switch hitter's non-matchup side can show stats only (its
                    HR/Hit scores would be for the wrong platoon side, so we
                    blank them rather than print a misleading number)."""
                    return {
                        "Player": name,
                        "Bats": bats_label,
                        "Matchup": matchup if matchup is not None else "\u2014",
                        "SLAM": round(slam, 1) if slam is not None else None,
                        "BA": profile.get("BA", 0),
                        "xwOBA": profile.get("xwOBA"),
                        "xSLG": profile.get("xSLG"),
                        "ISO": profile.get("ISO", 0),
                        "HR/FB": profile.get("HR/FB"),
                        "Brl%": profile.get("Brl %", 0),
                        "HH%": profile.get("HH %", 0),
                        "LD%": profile.get("LD %", 0),
                        "FB%": profile.get("FB %", 0),
                        "GB%": profile.get("GB %", 0),
                        "SweetSpot%": profile.get("SweetSpot %", 0),
                        "PullAir%": profile.get("PullAir %", 0),
                        "PullBrl%": profile.get("PullBrl %", 0),
                        "Blast%": profile.get("Blast %", 0),
                        "SwStr%": profile.get("SwStr %", 0),
                        "HR Edge": hr_edge,
                        "HR Score": hr_score,
                        "Hit Score": hit_score,
                        "Edge": edge_cell if edge_cell is not None else edge_tag("\u2014", "neutral"),
                        "EdgeLabel": edge_label,
                        "EdgeTier": edge_tier,
                        "Confidence": confidence,
                    }

                table_rows = []
                for r in filtered:
                    profile = windowed_profile_cache[r["name"]]
                    slam_result = slam_cache[r["name"]]
                    _sb = slam_bvp_cache[r["name"]]
                    # Keep a missing SLAM as None so the table shows "—",
                    # not 0.0 — a real 0.0 would read as a genuinely awful
                    # score and could make you fade a good hitter whose
                    # expected stats simply weren't available in this
                    # window. matchup_tier still needs a number, so it
                    # gets 0.0 only for its own tiering, never displayed.
                    slam = _sb["final"]
                    tier = matchup_tier(slam if slam is not None else 0.0)
                    r["slam_base"], r["slam_adj"] = _sb["base"], _sb["adj"]
                    conf_label, sample = confidence_tier(profile.get("BBE", 0))

                    hr_s, hit_s, k_s = r["hr_score"], r["hit_score"], r["k_score"]

                    if hr_s is None and hit_s is None and k_s is None:
                        tag_label, tag_tier = "No League Data", "neutral"
                    elif hr_s is not None and hr_s >= 20:
                        tag_label, tag_tier = f"Strong HR Target +{hr_s-10}%", "strong"
                    elif k_s is not None and k_s >= 70:
                        tag_label, tag_tier = f"K Risk -{k_s-60}%", "risk"
                    elif hit_s is not None and hit_s >= 60:
                        tag_label, tag_tier = f"Good Hit Pick +{hit_s-50}%", "good"
                    elif hr_s is not None and hit_s is not None and hr_s < 15 and hit_s < 30:
                        tag_label, tag_tier = "Avoid", "risk"
                    else:
                        tag_label, tag_tier = "Neutral", "neutral"

                    _is_switch = (r.get("bats") or "").upper() == "S"
                    _tonight = _side_for(r)  # L / R / None

                    # Primary row: tonight's matchup side (or plain side for
                    # non-switch). Carries the real scores/matchup.
                    _primary_label = (f'S\u2192{_tonight}' if _tonight else r["bats"])
                    table_rows.append(_stat_row(
                        r["name"], _primary_label, profile,
                        matchup=tier, slam=slam,
                        hr_edge=r.get("edge"), hr_score=r["hr_score"], hit_score=r["hit_score"],
                        edge_cell=edge_tag(tag_label, tag_tier),
                        edge_label=tag_label, edge_tier=tag_tier,
                        confidence=f"{conf_label} \u2014 n={sample}",
                    ))

                    # Switch hitter: add row(s) for the other side(s), stats
                    # only. If a probable is posted we already showed tonight's
                    # side above and add just the reverse; if not, _tonight is
                    # None and we add both L and R explicitly.
                    if _is_switch and r["name"] in switch_other_cache:
                        for _sd, _prof in switch_other_cache[r["name"]].items():
                            if _tonight and _sd == _tonight:
                                continue  # already shown as the primary row
                            _c_lbl, _c_n = confidence_tier(_prof.get("BBE", 0))
                            table_rows.append(_stat_row(
                                r["name"], f'S ({_sd})', _prof,
                                confidence=f"{_c_lbl} \u2014 n={_c_n}",
                                edge_label="split view", edge_tier="neutral",
                            ))

                display_df = pd.DataFrame(table_rows) if table_rows else None
                if display_df is not None:
                    edge_col = display_df.pop("Edge")

                    styled = style_stat_table(
                        display_df.drop(columns=["Matchup", "Confidence", "EdgeLabel", "EdgeTier"]),
                        favor_high=["SLAM", "BA", "xwOBA", "xSLG", "ISO", "HR/FB", "Brl%", "HH%", "LD%", "FB%", "SweetSpot%", "PullAir%", "PullBrl%", "Blast%", "HR Edge", "HR Score", "Hit Score"],
                        favor_low=["GB%", "SwStr%"],
                        gradient=True,
                    )
                    styled = styled.format({
                        "SLAM": "{:.1f}", "BA": "{:.3f}", "xwOBA": "{:.3f}", "xSLG": "{:.3f}",
                        "ISO": "{:.3f}", "HR/FB": "{:.1f}",
                        "Brl%": "{:.1f}", "HH%": "{:.1f}", "LD%": "{:.1f}",
                        "FB%": "{:.1f}", "GB%": "{:.1f}", "SweetSpot%": "{:.1f}", "PullAir%": "{:.1f}",
                        "PullBrl%": "{:.1f}", "Blast%": "{:.1f}", "SwStr%": "{:.1f}",
                        "HR Edge": "{:.0f}", "HR Score": "{:.0f}", "Hit Score": "{:.0f}",
                    }, na_rep="N/A")
                    st.dataframe(
                        styled,
                        width="stretch",
                        column_config={
                            "HR Edge": st.column_config.ProgressColumn("HR Edge", min_value=0, max_value=100, format="%d", color=COLOR["gold"]),
                            "HR Score": st.column_config.ProgressColumn("HR Score", min_value=0, max_value=100, format="%d", color=COLOR["stat_high"]),
                            "Hit Score": st.column_config.ProgressColumn("Hit Score", min_value=0, max_value=100, format="%d", color=COLOR["warn"]),
                        },
                    )
                    if not league_data_available:
                        st.caption("HR Score / Hit Score / K Score show N/A above because Baseball Savant's live percentile rankings aren't reachable right now (see warning above) \u2014 not because these players lack power or contact skill.")

                    # -------------------------------------------------
                    # WEAK SPOT vs THIS LINEUP — the alignment view:
                    # tonight's starter's per-slot weakness mapped onto
                    # the actual hitters batting those slots. This is the
                    # bettable read: a real, well-sampled weak slot that
                    # a dangerous hitter is sitting in tonight.
                    # -------------------------------------------------
                    if pitcher_id:
                        _wsl = get_weak_spots(pitcher_id)
                        _slot_map = {s["slot"]: s for s in _wsl.get("slots", [])}
                        # batters is in real batting order; index+1 = slot.
                        _order = [b for b in batters][:9]
                        if _slot_map and _order:
                            _align_rows = []
                            for _i, _b in enumerate(_order, start=1):
                                _s = _slot_map.get(_i, {})
                                _xslg = _s.get("xslg")
                                # weak = pitcher gets hit here AND it's a
                                # real sample (xslg present means it cleared
                                # the floor in the engine).
                                _is_weak = _xslg is not None and _xslg >= XSLG_HOT
                                _align_rows.append({
                                    "slot": _i,
                                    "name": _b.get("name", "\u2014"),
                                    "bats": _b.get("bats", ""),
                                    "xslg": _xslg,
                                    "bbe": _s.get("bbe", 0),
                                    "weak": _is_weak,
                                })
                            if any(r["xslg"] is not None for r in _align_rows):
                                st.markdown(
                                    f'<div class="pf-card-title" style="color:{COLOR["gold"]}; '
                                    f'margin-top:12px;">Weak spot vs this lineup</div>'
                                    f'<div class="pf-card-subtitle">{selected_pitcher_name}\u2019s xSLG '
                                    f'allowed by batting slot, mapped to tonight\u2019s hitters. '
                                    f'Green = a real, well-sampled slot where he gets hit and a '
                                    f'live bat is sitting. Slots below the sample floor show \u2014.'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                                _hdr = (
                                    f'<tr style="font-size:10px; color:{COLOR["text"]}; opacity:0.55;">'
                                    f'<td style="padding:4px 8px;">#</td>'
                                    f'<td style="padding:4px 8px;">Hitter</td>'
                                    f'<td style="padding:4px 8px;">B</td>'
                                    f'<td style="padding:4px 8px; text-align:right;">xSLG vs slot</td>'
                                    f'<td style="padding:4px 8px; text-align:right;">n</td></tr>'
                                )
                                _body = ""
                                for _r in _align_rows:
                                    _bg = (f'background:{COLOR["stat_high"]}22;'
                                           if _r["weak"] else "")
                                    if _r["xslg"] is None:
                                        _xcell = f'<span style="color:{COLOR["text"]}; opacity:0.4;">\u2014</span>'
                                    else:
                                        _c = (COLOR["error"] if _r["xslg"] >= XSLG_HOT
                                              else COLOR["stat_high"] if _r["xslg"] <= XSLG_COLD
                                              else COLOR["warn"])
                                        _xcell = f'<span style="font-weight:800; color:{_c};">{_r["xslg"]:.3f}</span>'
                                    _body += (
                                        f'<tr style="{_bg} font-size:11.5px;">'
                                        f'<td style="padding:4px 8px; color:{COLOR["text"]}; opacity:0.6;">{_r["slot"]}</td>'
                                        f'<td style="padding:4px 8px; color:{COLOR["text"]}; font-weight:600;">{_r["name"]}'
                                        + (' \U0001F3AF' if _r["weak"] else '') + '</td>'
                                        f'<td style="padding:4px 8px; color:{COLOR["text"]}; opacity:0.6;">{_r["bats"]}</td>'
                                        f'<td style="padding:4px 8px; text-align:right;">{_xcell}</td>'
                                        f'<td style="padding:4px 8px; text-align:right; color:{COLOR["text"]}; opacity:0.45; font-size:10px;">{_r["bbe"]}</td>'
                                        f'</tr>'
                                    )
                                st.markdown(
                                    f'<table style="width:100%; border-collapse:collapse;">'
                                    f'{_hdr}{_body}</table>',
                                    unsafe_allow_html=True,
                                )
                                _weak_names = [r["name"] for r in _align_rows if r["weak"]]
                                if _weak_names:
                                    st.caption(
                                        "\U0001F3AF Target spots tonight: " + ", ".join(_weak_names)
                                        + " \u2014 real, well-sampled slots where this starter gets hit. "
                                        "Still cross-check the hitter\u2019s own form above; this flags "
                                        "the matchup, not a lock."
                                    )
                                else:
                                    st.caption(
                                        "No slot clears both the damage threshold and the sample "
                                        "floor against this lineup \u2014 no standout target spot tonight."
                                    )

                    if league_data_available:
                        st.caption("HR Score / Hit Score are this app's own composite scores from real, live MLB percentile rankings (baseballsavant.mlb.com); HR Score now includes the Exit Velocity percentile. HR Edge = HR Score + the matchup layer (BvP \u00b115, Zone Fit \u00b115, Bullpen \u00b110 \u2014 engines/edge.py has every tier). Not calibrated predictive probabilities.")
                        # Named qualification badges — the "why upside"
                        # read, from thresholds documented in
                        # engines/pick_badges.py. Top 5 by Edge only, so
                        # it stays a highlight reel rather than a second
                        # copy of the table.
                        _badge_pool = sorted(
                            [r for r in filtered if r.get("edge") is not None],
                            key=lambda r: -(r.get("edge") or 0),
                        )
                        # log the top HR Edge bats for calibration
                        if _badge_pool:
                            try:
                                _log_picks("hr_edge", [
                                    {"id": r.get("id"), "name": r.get("name"),
                                     "team": team_abbr(opposing_team)}
                                    for r in _badge_pool[:5]
                                ])
                            except Exception:
                                pass

                        _any_badges = False
                        for _br in _badge_pool[:5]:
                            _bd, _why = compute_badges(
                                _br, windowed_profile_cache.get(_br["name"], {}),
                                pitcher_data, park.get("park_factor"),
                                game.get("weather_wind"),
                            )
                            if _bd:
                                if not _any_badges:
                                    st.markdown(
                                        f'<div class="pf-card-title" style="color:{COLOR["gold"]}; '
                                        f'margin-top:10px;">Why these bats</div>',
                                        unsafe_allow_html=True,
                                    )
                                    _any_badges = True
                                render_badge_row(st, COLOR, _bd, _why, _br["name"],
                                                 _br.get("hr_score"), _br.get("edge"))

                        with st.expander("\U0001F9EE Edge breakdown \u2014 why each bat moved"):
                            for _r in filtered:
                                if _r.get("edge") is None:
                                    continue
                                _parts = []
                                if _r.get("bvp_adj"):
                                    _parts.append(f'BvP {_r["bvp_adj"]:+d} ({_r.get("bvp_line")})')
                                elif _r.get("bvp_line"):
                                    _parts.append(f'BvP 0 ({_r.get("bvp_line")})')
                                if _r.get("zone_adj"):
                                    _parts.append(f'Zone {_r["zone_adj"]:+d} ({_r.get("zone_note")})')
                                elif _r.get("zone_note"):
                                    _parts.append(f'Zone 0 ({_r.get("zone_note")})')
                                if _r.get("pen_note"):
                                    _parts.append(f'Pen {_r.get("pen_adj", 0):+d} ({_r.get("pen_note")})')
                                _slam_bit = ""
                                if _r.get("slam_adj"):
                                    _slam_bit = (f'SLAM {_r.get("slam_base")} \u2192 '
                                                 f'{round(max(0.0, (_r.get("slam_base") or 0) + _r["slam_adj"]), 1)} '
                                                 f'(BvP {_r["slam_adj"]:+d}) \u00b7 ')
                                st.caption(f'**{_r["name"]}** \u2014 ' + _slam_bit +
                                           f'HR Score {_r["hr_score"]} \u2192 '
                                           f'Edge {_r["edge"]} \u00b7 ' + " \u00b7 ".join(_parts))

                        # ---- Batter Trend: pick any batter in this lineup,
                        # see his real game-by-game results (official MLB
                        # box scores — the source that actually carries RBI
                        # and runs, which Statcast pitch data doesn't) ----
                        st.markdown(
                            f'<div class="pf-card-title" style="color:{COLOR["magenta_purple"]}; margin-top:14px;">Batter Trend</div>'
                            f'<div class="pf-card-subtitle">Game-by-game Hits / HR / RBI / H+R+RBI from MLB official box scores.</div>',
                            unsafe_allow_html=True,
                        )
                        _bt_ids = {r["name"]: r["id"] for r in ranked if r.get("id")}
                        _bt_pick = st.selectbox(
                            "Batter trend",
                            ["Select a batter\u2026"] + list(_bt_ids.keys()),
                            key=f"bt_pick_{st.session_state['gc_selected_game_idx']}",
                            label_visibility="collapsed",
                        )
                        if _bt_pick in _bt_ids:
                            # ---- First-pitch tendency + switch-hitter sides ----
                            # A switch hitter's two sides are often different
                            # hitters; showing one blended number hides the
                            # split that decides the matchup, so both are
                            # offered whenever he actually bats both ways.
                            _bt_row = next((r for r in ranked if r["name"] == _bt_pick), {})
                            _bt_bats = (_bt_row.get("bats") or "").upper()
                            _side_opts = ["Combined", "as RHB", "as LHB"] if _bt_bats == "S" else ["Combined"]
                            _side_pick = "Combined"
                            if len(_side_opts) > 1:
                                _side_pick = st.segmented_control(
                                    "Batting side", _side_opts, default="Combined",
                                    key=f"bt_side_{st.session_state['gc_selected_game_idx']}",
                                    label_visibility="collapsed",
                                ) or "Combined"
                            _stand = {"as RHB": "R", "as LHB": "L"}.get(_side_pick)

                            _fp = get_first_pitch_swing(_bt_ids[_bt_pick],
                                                        window="season", stand=_stand)
                            if _fp.get("swing_pct") is not None:
                                _fp_col = (COLOR["error"] if _fp["swing_pct"] >= 40
                                           else COLOR["stat_high"] if _fp["swing_pct"] <= 20
                                           else COLOR["warn"])
                                _extra = []
                                if _fp.get("contact") is not None:
                                    _extra.append(f'{_fp["contact"]:.0f}% contact when he swings')
                                if _fp.get("hard_hit") is not None:
                                    _extra.append(f'{_fp["hard_hit"]:.0f}% hard-hit')
                                if _fp.get("xslg") is not None:
                                    _extra.append(f'{_fp["xslg"]:.3f} xSLG on first-pitch contact')
                                # NOTE: no backslash escapes inside f-string
                                # expressions — Python 3.11 (Render) rejects
                                # them even though 3.12 allows it.
                                _sep = " \u00b7 "
                                _side_txt = (_sep + _side_pick.lower()) if _stand else ""
                                _extra_txt = _sep.join(_extra)
                                _extra_html = (
                                    f'<div style="font-size:10.5px; opacity:0.65; '
                                    f'margin-top:2px;">{_extra_txt}</div>'
                                ) if _extra else ""
                                st.markdown(
                                    f'<div style="font-family:\'JetBrains Mono\',monospace; '
                                    f'font-size:12px; color:{COLOR["text"]}; margin:6px 0;">'
                                    f'First-pitch swing '
                                    f'<b style="color:{_fp_col};">{_fp["swing_pct"]:.1f}%</b> '
                                    f'<span style="opacity:0.6;">({_fp["pa"]} first pitches'
                                    f'{_side_txt})</span>'
                                    + _extra_html
                                    + '</div>',
                                    unsafe_allow_html=True,
                                )
                            elif _fp.get("reason"):
                                st.caption(f'First-pitch swing rate: {_fp["reason"]}.')

                            _bt_stat = st.segmented_control(
                                "Stat", ["Hits", "1B", "2B", "3B", "HR", "RBI",
                                         "Runs", "Total Bases", "Walks",
                                         "Strikeouts", "H+R+RBI"],
                                default="Hits", key="bt_stat", label_visibility="collapsed",
                            )
                            from datetime import datetime as _dtn
                            _yr = _dtn.now().year
                            _bt_win = st.segmented_control(
                                "Window", [str(_yr), str(_yr - 1), "H2H", "L25", "L15", "L5"],
                                default="L15", key="bt_window", label_visibility="collapsed",
                            )
                            # Line options follow the stat, and the key
                            # includes it so switching stats doesn't carry a
                            # stale line across (a 3.5 HR line is nonsense).
                            _BT_LINES = {
                                "Hits": (["0.5", "1.5", "2.5"], "0.5"),
                                "1B": (["0.5", "1.5"], "0.5"),
                                "2B": (["0.5", "1.5"], "0.5"),
                                "3B": (["0.5"], "0.5"),
                                "HR": (["0.5", "1.5"], "0.5"),
                                "RBI": (["0.5", "1.5", "2.5"], "0.5"),
                                "Runs": (["0.5", "1.5"], "0.5"),
                                "Total Bases": (["0.5", "1.5", "2.5", "3.5"], "1.5"),
                                "Walks": (["0.5", "1.5"], "0.5"),
                                "Strikeouts": (["0.5", "1.5", "2.5"], "0.5"),
                                "H+R+RBI": (["1.5", "2.5", "3.5", "4.5"], "2.5"),
                            }
                            _bt_opts, _bt_dflt = _BT_LINES.get(_bt_stat or "Hits",
                                                               (["0.5", "1.5"], "0.5"))
                            _bt_line = st.segmented_control(
                                "Line", _bt_opts, default=_bt_dflt,
                                key=f"bt_line_{_bt_stat or 'Hits'}",
                                label_visibility="collapsed",
                            )
                            # For H2H the opponent is the pitcher's team
                            # (the team this lineup is facing tonight).
                            _bt_opp_team = game["away"] if pitcher_choice.startswith(game["away_pitcher"]) else game["home"]
                            render_batter_trend(
                                _bt_ids[_bt_pick], _bt_pick,
                                _bt_stat or "Hits", _bt_win or "L15",
                                line=float(_bt_line or _bt_dflt),
                                opp_label=team_abbr(_bt_opp_team),
                            )
                            # Deep dive: career BvP vs tonight's selected
                            # pitcher, then zone map + spray chart on the
                            # SAME window the trend chart is showing.
                            render_bvp_card(
                                _bt_ids[_bt_pick], _bt_pick,
                                pitcher_id, selected_pitcher_name,
                            )
                            _dd1, _dd2 = st.columns([1, 1.35])
                            with _dd1:
                                render_zone_map(_bt_ids[_bt_pick], _bt_pick,
                                                _bt_win or "L10")
                            with _dd2:
                                render_spray_chart(_bt_ids[_bt_pick], _bt_pick,
                                                   _bt_win or "L10",
                                                   wind=game.get("weather_wind"))

        if table_rows:
            top_3_pitches = [pt for pt, usage in sorted(arsenal.items(), key=lambda x: -x[1])[:3]] if arsenal else []
            with card("vs_top_pitches"):
                top_3_names = ", ".join(pitch_name(pt) for pt in top_3_pitches) if top_3_pitches else "unknown"
                st.markdown(
                    f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Vs {selected_pitcher_name}\'s Top 3 Pitches</div>'
                    f'<div class="pf-card-subtitle">Real per-batter performance specifically against {top_3_names} \u2014 same {window_choice} window as the Lineup table above</div>',
                    unsafe_allow_html=True,
                )
                if not top_3_pitches:
                    st.info("No real pitch arsenal data available for this pitcher yet \u2014 nothing to honestly compare batters against.")
                else:
                    matchup_rows = []
                    for r in filtered:
                        vs_profile = get_batter_vs_pitch_types(r.get("id"), tuple(top_3_pitches), window=window_key, unit=unit_key)
                        pitches_seen = vs_profile.get("_pitches_seen", 0)
                        matchup_rows.append({
                            "Player": r["name"],
                            "Bats": r["bats"],
                            "Pitches Seen": pitches_seen,
                            "xwOBA": vs_profile.get("xwOBA") if pitches_seen > 0 else None,
                            "ISO": vs_profile.get("ISO") if pitches_seen > 0 else None,
                            "Brl%": vs_profile.get("Brl %") if pitches_seen > 0 else None,
                            "HH%": vs_profile.get("HH %") if pitches_seen > 0 else None,
                            "Whiff%": vs_profile.get("Whiff %") if pitches_seen > 0 else None,
                            "Zone Fit": (f'{r["zone_adj"]:+d}' if r.get("zone_adj") else "\u2014"),
                            "BvP (career)": r.get("bvp_line") or "\u2014",
                        })
                    matchup_df = pd.DataFrame(matchup_rows)
                    st.dataframe(
                        style_stat_table(matchup_df, favor_high=["xwOBA", "ISO", "Brl%", "HH%", "Zone Fit"], favor_low=["Whiff%"], gradient=True).format(
                            {"xwOBA": "{:.3f}", "ISO": "{:.3f}", "Brl%": "{:.1f}", "HH%": "{:.1f}", "Whiff%": "{:.1f}"}, na_rep="\u2014"),
                        width="stretch",
                    )
                    st.caption(
                        "\"Pitches Seen\" is the real sample size behind each row \u2014 a low number is a real, honest "
                        "small sample, not a hidden flaw. Blank cells mean this batter hasn't faced any of these "
                        "specific pitch types in the selected window yet. BvP (career) is his real career line vs "
                        "THIS starter (MLB official vs-player split) \u2014 the same history that now moves SLAM and "
                        "the Matchup Edges tiers, per the tiers documented in engines/edge.py."
                    )

        if table_rows:
            # Full per-pitch-category profile: how each hitter does against
            # Fastballs / Breaking / Offspeed across the board (not just
            # tonight's arsenal). Grouped into three families rather than
            # every individual code, because a single hitter rarely has a
            # usable sample against, say, sweepers alone in a recent window.
            _PITCH_GROUPS = {
                "Fastballs": ("FF", "FA", "SI", "FC"),
                "Breaking": ("SL", "ST", "CU", "KC", "CS", "SV"),
                "Offspeed": ("CH", "FS", "FO", "EP"),
            }
            with card("vs_pitch_family"):
                st.markdown(
                    f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Batter vs Pitch Type</div>'
                    f'<div class="pf-card-subtitle">How one hitter performs against each pitch family \u2014 '
                    f'same {window_choice} window. Pick a batter.</div>',
                    unsafe_allow_html=True,
                )
                _names = [r["name"] for r in filtered]
                if _names:
                    _pick = st.selectbox("Batter", _names, key="vs_pitch_family_pick")
                    _row = next((r for r in filtered if r["name"] == _pick), None)
                    if _row is not None:
                        fam_rows = []
                        for fam_label, fam_codes in _PITCH_GROUPS.items():
                            vp = get_batter_vs_pitch_types(
                                _row.get("id"), fam_codes, window=window_key, unit=unit_key)
                            seen = vp.get("_pitches_seen", 0)
                            fam_rows.append({
                                "Pitch Type": fam_label,
                                "Pitches Seen": seen,
                                "BA": vp.get("BA") if seen > 0 else None,
                                "xwOBA": vp.get("xwOBA") if seen > 0 else None,
                                "xSLG": vp.get("xSLG") if seen > 0 else None,
                                "ISO": vp.get("ISO") if seen > 0 else None,
                                "Brl%": vp.get("Brl %") if seen > 0 else None,
                                "HH%": vp.get("HH %") if seen > 0 else None,
                                "Whiff%": vp.get("Whiff %") if seen > 0 else None,
                            })
                        fam_df = pd.DataFrame(fam_rows)
                        st.dataframe(
                            style_stat_table(
                                fam_df, favor_high=["BA", "xwOBA", "xSLG", "ISO", "Brl%", "HH%"],
                                favor_low=["Whiff%"], gradient=True,
                            ).format(
                                {"BA": "{:.3f}", "xwOBA": "{:.3f}", "xSLG": "{:.3f}", "ISO": "{:.3f}",
                                 "Brl%": "{:.1f}", "HH%": "{:.1f}", "Whiff%": "{:.1f}"},
                                na_rep="\u2014",
                            ),
                            width="stretch",
                        )
                        st.caption(
                            "Fastballs = 4-seam, sinker, cutter. Breaking = slider, sweeper, curve, "
                            "knuckle-curve, slurve. Offspeed = changeup, splitter, forkball. "
                            "\"Pitches Seen\" is the real sample \u2014 blank rows mean he hasn't faced "
                            "that family in this window. A hitter strong vs one family and weak vs "
                            "another is a matchup edge once you know what the starter throws most."
                        )

        if table_rows:
            with card("matchup_edges"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Matchup Edges</div>', unsafe_allow_html=True)

                tier_order = [
                    ("strong", "Strong Targets"),
                    ("good", "Good Picks"),
                    ("neutral", "Neutral"),
                    ("risk", "Risk / Avoid"),
                ]
                for tier_key, tier_label in tier_order:
                    tier_rows = [r for r in table_rows if r["EdgeTier"] == tier_key]
                    if not tier_rows:
                        continue
                    st.markdown(
                        f'<div style="margin:10px 0 6px 0;">{edge_tag(f"{tier_label} ({len(tier_rows)})", tier_key)}</div>',
                        unsafe_allow_html=True,
                    )
                    tier_df = pd.DataFrame([
                        {"Player": r["Player"], "Bats": r["Bats"], "Detail": r["EdgeLabel"], "Confidence": r["Confidence"]}
                        for r in tier_rows
                    ])
                    st.dataframe(plain_dark_table(tier_df), width="stretch", height=min(250, 40 + 35 * len(tier_rows)))

        tab_arsenal, tab_scout = st.tabs(["Pitch Arsenal", "\U0001F52D Scout Report"])
        with tab_arsenal:
            with card("pitch_arsenal_tab"):
                st.markdown(
                    f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Pitch Arsenal</div>'
                    f'<div class="pf-card-subtitle" style="color:{COLOR["magenta_purple"]};">What each pitch actually does, not just how often it\'s thrown</div>',
                    unsafe_allow_html=True,
                )
                arsenal_detail = pitcher_data.get("Pitch Arsenal Detail", {}) if pitcher_data else {}
                if not arsenal_detail:
                    st.info("No pitch-level data available for this pitcher yet.")
                else:
                    sorted_pitches = sorted(arsenal_detail.items(), key=lambda x: -x[1]["usage"])
                    for pt, d in sorted_pitches:
                        c = pitch_color(pt)
                        whiff_display = f"{d['whiff']:.1f}%" if d["whiff"] is not None else "N/A"
                        hh_display = f"{d['hh_allowed']:.1f}%" if d["hh_allowed"] is not None else "N/A"
                        st.markdown(
                            f'<div style="margin-bottom:14px;">'
                            f'<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">'
                            f'<span style="font-weight:700; color:{c}; font-size:14px;">{pitch_name(pt)}</span>'
                            f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["gold"]}; font-size:12px;">n={d["n"]}</span>'
                            f'</div>'
                            f'<div style="height:8px; width:100%; background:{COLOR["surface_raised"]}; border-radius:4px; margin-bottom:6px;">'
                            f'<div style="height:8px; width:{min(d["usage"],100)}%; background:{c}; border-radius:4px;"></div>'
                            f'</div>'
                            f'<div style="display:flex; gap:18px; font-size:12px; font-family:\'JetBrains Mono\',monospace;">'
                            f'<span style="color:{COLOR["gold"]};">Usage <b style="color:{COLOR["text"]};">{d["usage"]:.1f}%</b></span>'
                            f'<span style="color:{COLOR["gold"]};">Whiff <b style="color:{COLOR["stat_high"] if (d["whiff"] or 0) >= 25 else COLOR["text"]};">{whiff_display}</b></span>'
                            f'<span style="color:{COLOR["gold"]};">Hard-Hit Allowed <b style="color:{COLOR["error"] if (d["hh_allowed"] or 0) >= 40 else COLOR["text"]};">{hh_display}</b></span>'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    st.caption("Whiff% / Hard-Hit% are real, computed per pitch type from this pitcher's own raw Statcast data \u2014 not league averages.")

        with tab_scout:
            st.markdown(
                f'<div class="pf-card-title">Scout Report</div>'
                f'<div class="pf-card-subtitle">Pull any team\'s roster \u2014 not just today\'s matchups. Get ahead of tomorrow\'s opponent before anyone else does.</div>',
                unsafe_allow_html=True,
            )
            all_teams = get_all_teams()
            if not all_teams:
                st.warning("Couldn't load the team list from the MLB Stats API right now.")
            else:
                with card("scout_controls"):
                    sel_col, refresh_col = st.columns([4, 1])
                    with sel_col:
                        lookup_team = st.selectbox("Team", all_teams, key="scout_team_lookup")
                    with refresh_col:
                        st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)
                        if st.button("\U0001F504 Refresh", key="scout_refresh", help="Forces a fresh pull instead of the cached roster (cached up to 30 min) \u2014 use this right before first pitch for the most current confirmed roster."):
                            get_live_team_roster.clear()
                            st.session_state["scout_fetch_time"] = datetime.now(EASTERN).strftime("%-I:%M:%S %p ET")
                            st.rerun()

                    if "scout_fetch_time" not in st.session_state:
                        st.session_state["scout_fetch_time"] = datetime.now(EASTERN).strftime("%-I:%M:%S %p ET")

                    st.caption(f"Roster as of {st.session_state['scout_fetch_time']} \u2014 auto-refreshes every 30 min, or hit Refresh for the latest right now.")

                    lookup_roster = get_live_team_roster(lookup_team)
                    if lookup_roster:
                        pitchers = [p for p in lookup_roster if p.get("is_pitcher")]
                        hitters = [p for p in lookup_roster if not p.get("is_pitcher")]

                        st.markdown(
                            badge(f"{len(lookup_roster)} Total", "neutral")
                            + badge(f"{len(pitchers)} Pitchers", "accent")
                            + badge(f"{len(hitters)} Position Players", "good"),
                            unsafe_allow_html=True,
                        )

                if lookup_roster:
                    with card("scout_position_players"):
                        st.markdown('<div class="pf-card-title">Position Players</div>', unsafe_allow_html=True)
                        if hitters:
                            hitters_df = pd.DataFrame(hitters)[["name", "position", "bats", "throws"]]
                            hitters_df.columns = ["Name", "Pos", "Bats", "Throws"]
                            st.dataframe(plain_dark_table(hitters_df), width="stretch", height=min(370, 40 + 35 * len(hitters)))
                        else:
                            st.caption("No position players found.")

                    with card("scout_pitchers"):
                        st.markdown('<div class="pf-card-title">Pitchers</div>', unsafe_allow_html=True)
                        if pitchers:
                            pitchers_df = pd.DataFrame(pitchers)[["name", "position", "bats", "throws"]]
                            pitchers_df.columns = ["Name", "Pos", "Bats", "Throws"]
                            st.dataframe(plain_dark_table(pitchers_df), width="stretch", height=min(370, 40 + 35 * len(pitchers)))
                        else:
                            st.caption("No pitchers found.")
                else:
                    st.info(f"No roster data available for {lookup_team} right now.")

        # -------------------------------------------------
        # AI MATCHUP SUMMARY / KEY INSIGHTS / LEGEND
        # (template-generated from real numbers, no live LLM call)
        # -------------------------------------------------
        s1, s2, s3 = st.columns(3)
        with s1:
            with card("matchup_summary"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["magenta_purple"]};">Matchup Summary</div>', unsafe_allow_html=True)
                top_arsenal = ", ".join(pitch_name(k) for k, v in sorted(arsenal.items(), key=lambda x: -x[1])[:2]) if arsenal else "an unclear arsenal"
                top_hr_names = ", ".join(r["name"] for r in sorted(ranked, key=lambda x: _score_sort_key(x, "hr_score"))[:2]) if ranked else "the lineup"
                st.markdown(
                    f'<span style="color:{COLOR["gold"]};">'
                    f"{selected_pitcher_name} relies heavily on {top_arsenal}. "
                    f"{top_hr_names} rate highest on HR Score against this arsenal. "
                    f"These are this app's own composite scores, not a certified prediction."
                    f'</span>',
                    unsafe_allow_html=True,
                )
        with s2:
            with card("key_insights"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["magenta_purple"]};">Key Insights</div>', unsafe_allow_html=True)
                above_avg_hr = sum(1 for r in ranked if r["hr_score"] is not None and r["hr_score"] >= 60)
                high_k_risk = sum(1 for r in ranked if r["k_score"] is not None and r["k_score"] >= 70)
                st.markdown(f'<span style="color:{COLOR["gold"]};">\u2713 {above_avg_hr} batters with above-average HR Score</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="color:{COLOR["gold"]};">\u2713 {high_k_risk} batters carrying elevated strikeout risk</span>', unsafe_allow_html=True)
                if park["verified"]:
                    st.markdown(f'<span style="color:{COLOR["gold"]};">\u2713 {park["venue"]} park factor: {park["park_factor"]}</span>', unsafe_allow_html=True)
        with s3:
            with card("legend"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["magenta_purple"]};">Legend</div>', unsafe_allow_html=True)
                st.markdown(
                    edge_tag("Strong Edge", "strong") + " " + edge_tag("Good Pick", "good") + "<br><br>"
                    + edge_tag("Neutral", "neutral") + " " + edge_tag("Risk / Avoid", "risk"),
                    unsafe_allow_html=True,
                )

    footer()