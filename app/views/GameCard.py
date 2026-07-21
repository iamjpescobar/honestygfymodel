import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

from styles.kc_theme import (
    inject_kc_theme, badge, card, footer, COLOR,
    sport_switcher, pitch_color, pitch_name, edge_tag
)
from styles.table_style import style_stat_table, plain_dark_table

from engines.weather_engine import get_todays_games_with_weather
from engines.park_factors import get_park_factor
from engines.headshots import get_headshot_url
from engines.roster import get_live_team_roster, get_all_teams, get_confirmed_lineup, get_last_starting_lineup
from engines.statcast_engine import (
    get_pitcher_id, get_pitcher_statcast, get_pitcher_advanced_splits, get_batter_profile_windowed, get_batter_vs_pitch_types
)
from engines.savant_leaderboard import load_percentile_ranks
from engines.live_sync import sync_latest_button
from engines.batter_trends import render_batter_trend
from engines.bvp import render_bvp_card, render_zone_map, render_spray_chart
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
    PAGE_SIZE = 4
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
        default_pill = current_global_label if current_global_label in visible_labels else None
        selected_label = st.pills(
            "Today's Games", visible_labels, default=default_pill,
            label_visibility="collapsed", key=f"game_picker_p{page}"
        )
        if selected_label:
            # labels are unique now (G1/G2 suffixes), so this index is
            # exact — game 2 of a doubleheader is directly reachable
            st.session_state["gc_selected_game_idx"] = _labels.index(selected_label)

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
    temp_display = game["weather_temp"] if game["weather_temp"] else "\u2014"
    park_display = f'{park["park_factor"]}' if park["verified"] else "Not verified"

    def _weather_icon(condition: str) -> str:
        c = (condition or "").lower()
        if "rain" in c or "shower" in c:
            return "\U0001F327\uFE0F"
        if "storm" in c or "thunder" in c:
            return "\u26C8\uFE0F"
        if "cloud" in c or "overcast" in c:
            return "\u2601\uFE0F"
        if "clear" in c or "sunny" in c:
            return "\u2600\uFE0F"
        if "dome" in c or "roof" in c:
            return "\U0001F3DF\uFE0F"
        return "\U0001F324\uFE0F"

    st.markdown(
        f'<div class="pf-card" style="display:flex; justify-content:space-around; text-align:center; padding:10px 16px;">'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Condition</div>'
        f'<div style="font-size:20px; margin:2px 0;" class="lc-weather-icon">{_weather_icon(game["weather_condition"])}</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{game["weather_condition"] or "Not posted yet"}</div></div>'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Temp</div>'
        f'<div style="font-size:20px; margin:2px 0;">\U0001F321\uFE0F</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{temp_display}\u00b0F</div></div>'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Wind</div>'
        f'<div style="font-size:20px; margin:2px 0;" class="lc-wind-icon">\U0001F4A8</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{game["weather_wind"] or "Not posted yet"}</div></div>'
        f'<div><div class="pf-metric-label" style="color:{COLOR["gold"]};">Park Factor</div>'
        f'<div style="font-size:20px; margin:2px 0;">\U0001F3DF\uFE0F</div>'
        f'<div style="font-size:13px; color:{COLOR["gold"]}; font-weight:600;">{park_display}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
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
                                    vs = get_batter_vs_pitch_types(ob.get("id"), bp_top3, window="season", unit="bbe")
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
                        "Sort by", ["SLAM", "HR Score", "Hit Score", "Brl%", "HH%"], key="lineup_sort_by"
                    )
                with window_col:
                    window_choice = st.selectbox(
                        "Window", ["Season", "Last 60 BBE", "Last 25 BBE", "Last 15 BBE", "Last 5 BBE"], key="lineup_window"
                    )
                window_map = {"Season": "season", "Last 60 BBE": "l60", "Last 25 BBE": "l25", "Last 15 BBE": "l15", "Last 5 BBE": "l5"}
                window_key = window_map[window_choice]

                filtered = ranked if not bats_filter or bats_filter == "All" else [r for r in ranked if r["bats"] == bats_filter]

                # Real windowed profile fetched ONCE per batter for the
                # selected window — both SLAM and the raw stat columns
                # (Brl%, HH%, etc.) below now come from this SAME real
                # pull, so they always agree with each other and both
                # genuinely respect the Window filter, not just SLAM.
                windowed_profile_cache = {
                    r["name"]: get_batter_profile_windowed(r.get("id"), window=window_key, unit="bbe")
                    for r in filtered
                }
                slam_cache = {name: slam_from_profile(p) for name, p in windowed_profile_cache.items()}

                sort_key_map = {
                    "SLAM": lambda r: slam_cache[r["name"]]["slam_score"] or 0.0,
                    "HR Score": lambda r: _score_num(r["hr_score"]),
                    "Hit Score": lambda r: _score_num(r["hit_score"]),
                    "Brl%": lambda r: windowed_profile_cache[r["name"]].get("Brl %", 0),
                    "HH%": lambda r: windowed_profile_cache[r["name"]].get("HH %", 0),
                }
                filtered = sorted(filtered, key=sort_key_map[sort_choice], reverse=True)

                if not filtered:
                    st.info(f"No batters match that Bats filter for {opposing_team}.")

                table_rows = []
                for r in filtered:
                    profile = windowed_profile_cache[r["name"]]
                    slam_result = slam_cache[r["name"]]
                    slam = slam_result["slam_score"] if slam_result["slam_score"] is not None else 0.0
                    tier = matchup_tier(slam)
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

                    table_rows.append({
                        "Player": r["name"],
                        "Bats": r["bats"],
                        "Matchup": tier,
                        "SLAM": round(slam, 1),
                        "BA": profile.get("BA", 0),
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
                        "HR Score": r["hr_score"],
                        "Hit Score": r["hit_score"],
                        "Edge": edge_tag(tag_label, tag_tier),
                        "EdgeLabel": tag_label,
                        "EdgeTier": tag_tier,
                        "Confidence": f"{conf_label} \u2014 n={sample}",
                    })

                display_df = pd.DataFrame(table_rows) if table_rows else None
                if display_df is not None:
                    edge_col = display_df.pop("Edge")

                    styled = style_stat_table(
                        display_df.drop(columns=["Matchup", "Confidence", "EdgeLabel", "EdgeTier"]),
                        favor_high=["SLAM", "BA", "Brl%", "HH%", "LD%", "FB%", "SweetSpot%", "PullAir%", "PullBrl%", "Blast%", "HR Score", "Hit Score"],
                        favor_low=["GB%", "SwStr%"],
                        gradient=True,
                    )
                    styled = styled.format({
                        "SLAM": "{:.1f}", "BA": "{:.3f}", "Brl%": "{:.1f}", "HH%": "{:.1f}", "LD%": "{:.1f}",
                        "FB%": "{:.1f}", "GB%": "{:.1f}", "SweetSpot%": "{:.1f}", "PullAir%": "{:.1f}",
                        "PullBrl%": "{:.1f}", "Blast%": "{:.1f}", "SwStr%": "{:.1f}",
                        "HR Score": "{:.0f}", "Hit Score": "{:.0f}",
                    }, na_rep="N/A")
                    st.dataframe(
                        styled,
                        width="stretch",
                        column_config={
                            "HR Score": st.column_config.ProgressColumn("HR Score", min_value=0, max_value=100, format="%d", color=COLOR["stat_high"]),
                            "Hit Score": st.column_config.ProgressColumn("Hit Score", min_value=0, max_value=100, format="%d", color=COLOR["warn"]),
                        },
                    )
                    if not league_data_available:
                        st.caption("HR Score / Hit Score / K Score show N/A above because Baseball Savant's live percentile rankings aren't reachable right now (see warning above) \u2014 not because these players lack power or contact skill.")
                    else:
                        st.caption("HR Score / Hit Score are this app's own composite scores from real, live MLB percentile rankings (baseballsavant.mlb.com) \u2014 not calibrated predictive probabilities. See engines/top_plays.py for the exact formula.")

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
                            _bt_stat = st.segmented_control(
                                "Stat", ["Hits", "HR", "RBI", "H+R+RBI"],
                                default="Hits", key="bt_stat", label_visibility="collapsed",
                            )
                            _bt_win = st.segmented_control(
                                "Window", ["Season", "L25", "L10", "L5"],
                                default="L10", key="bt_window", label_visibility="collapsed",
                            )
                            _bt_line = st.segmented_control(
                                "Line", ["0.5", "1.5", "2.5", "3.5"],
                                default="0.5", key="bt_line", label_visibility="collapsed",
                            )
                            render_batter_trend(
                                _bt_ids[_bt_pick], _bt_pick,
                                _bt_stat or "Hits", _bt_win or "L10",
                                line=float(_bt_line or "0.5"),
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
                        vs_profile = get_batter_vs_pitch_types(r.get("id"), top_3_pitches, window=window_key, unit="bbe")
                        pitches_seen = vs_profile.get("_pitches_seen", 0)
                        matchup_rows.append({
                            "Player": r["name"],
                            "Bats": r["bats"],
                            "Pitches Seen": pitches_seen,
                            "Brl%": vs_profile.get("Brl %") if pitches_seen > 0 else None,
                            "HH%": vs_profile.get("HH %") if pitches_seen > 0 else None,
                            "Whiff%": vs_profile.get("Whiff %") if pitches_seen > 0 else None,
                        })
                    matchup_df = pd.DataFrame(matchup_rows)
                    st.dataframe(
                        style_stat_table(matchup_df, favor_high=["Brl%", "HH%"], favor_low=["Whiff%"], gradient=True),
                        width="stretch",
                    )
                    st.caption(
                        "\"Pitches Seen\" is the real sample size behind each row \u2014 a low number is a real, honest "
                        "small sample, not a hidden flaw. Blank cells mean this batter hasn't faced any of these "
                        "specific pitch types in the selected window yet."
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