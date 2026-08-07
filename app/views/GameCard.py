import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

from styles.kc_theme import (
    badge, card, footer, COLOR,
    pitch_color, pitch_name, edge_tag
)
from styles.table_style import (style_stat_table, plain_dark_table,
                                render_html_table, score_bar, bats_chip,
                                tier_legend, style_vs_league)

from engines.weather_engine import get_todays_games_with_weather
from engines.park_factors import get_park_factor
from engines.pitch_matchup import batter_pitch_profile as _batter_pitch_profile
from engines.headshots import get_headshot_url
from engines.roster import get_live_team_roster, get_active_player_ids, get_all_teams, get_confirmed_lineup, get_last_starting_lineup
from engines.statcast_engine import (
    get_pitcher_statcast, get_pitcher_advanced_splits, get_batter_profile_windowed, get_batter_vs_pitch_types,
    get_first_pitch_swing
, get_batter_iso_vs_hand, hand_tag
)
from engines.savant_leaderboard import load_percentile_ranks
from engines.live_sync import sync_latest_button
from engines.batter_trends import render_batter_trend
from engines.bvp import render_bvp_card, render_zone_map, render_spray_chart
from engines.edge import edge_components, pen_context, bvp_component
from engines.pick_badges import compute_badges, render_badge_row
from engines.pitcher_weakspots import get_weak_spots, XSLG_HOT, XSLG_COLD
from engines.team_logos import logo_for
from engines.weather_icons import (
    weather_icon, wind_arrow, temp_icon, park_icon,
)
from engines.park_weather import get_park_forecast
from engines.slam_engine import slam_from_profile
from engines.top_plays import rank_batters, confidence_tier, matchup_tier
from engines.team_abbreviations import team_abbr
from engines.matchup_grades import grade_matchup
from engines.matchup_grades_intl import render_matchup_grades_card

# page_icon repeated on purpose: set_page_config RE-APPLIES on every
# call, and omitting it here dropped the favicon app.py set, so the
# tab icon vanished on this page only.
st.set_page_config(page_title="Game Card", page_icon="⚾", layout="wide")
# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

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
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-sm);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">LOS</span>'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">CAPPERS</span>'
    f'</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Helpers hoisted out of the render block.
#

# ======================================================================
# Render sections, lifted out of the `with content_col:` block.
#
# Each was a top-level statement in that block. What it reads is now a
# parameter and what later code needs is a return, so every dependency
# is visible in the signature instead of being an ambient local.
#
# Streamlit's context is dynamic rather than lexical, so calling these
# from inside `with content_col:` still renders into that column.
# ======================================================================

def _render_game_carousel(_labels, games):
    """The whole slate in ONE swipeable row. No pages.

    WHY THIS REPLACED PAGINATION

    It used to show five games at a time behind a prev/next pager and a
    "Page 1 of 3" caption. On an eleven-game slate that meant three
    clicks to see everything and no way to compare the ends of the
    slate. Paging is a desktop compromise; this app is read on an iPad,
    where a horizontal swipe is the native gesture and a pager is two
    small targets to hit.

    HOW IT WORKS WITHOUT LEAVING STREAMLIT

    Streamlit has no carousel, and buttons cannot live inside raw HTML —
    so the row is still st.columns of real st.buttons, and the SCROLLING
    is pure CSS on the container: flex-wrap:nowrap, overflow-x:auto, and
    scroll-snap so each card settles under the thumb instead of stopping
    half-way. Momentum scrolling comes free on iOS.

    The CSS is scoped to this container's own key (st-key-gc_gamestrip),
    the same mechanism every card on the site already uses, so it cannot
    leak into another horizontal block. Rule 9 still holds: nothing here
    depends on a Streamlit-generated class NAME, only on the key we
    ourselves set and the two stable data-testids this file already
    targets elsewhere.

    Selection state is unchanged — same _pick_game callback, same
    gc_selected_game_idx — so nothing downstream had to know about this.
    """
    import streamlit as st

    if not _labels:
        return

    # min-width is what actually makes it scroll: without it Streamlit
    # divides the row evenly and eleven games become eleven slivers.
    # 116px fits a logo pair and an abbreviated matchup without
    # truncating, and shows about four and a half cards on an iPad —
    # the half card being the point, since a row that ends flush looks
    # like the end of the list.
    st.markdown(
        "<style>"
        'div[class*="st-key-gc_gamestrip"] div[data-testid="stHorizontalBlock"] {'
        "  flex-wrap: nowrap !important;"
        "  overflow-x: auto !important;"
        "  scroll-snap-type: x proximity;"
        "  -webkit-overflow-scrolling: touch;"
        "  gap: var(--lc-space-xs) !important;"
        "  padding-bottom: var(--lc-space-xs);"
        "  scrollbar-width: none;"
        "}"
        'div[class*="st-key-gc_gamestrip"] div[data-testid="stHorizontalBlock"]::-webkit-scrollbar {'
        "  display: none;"
        "}"
        'div[class*="st-key-gc_gamestrip"] div[data-testid="stColumn"] {'
        "  flex: 0 0 auto !important;"
        "  width: 116px !important;"
        "  min-width: 116px !important;"
        "  scroll-snap-align: center;"
        "}"
        'div[class*="st-key-gc_gamestrip"] button {'
        "  padding: var(--lc-space-hair) var(--lc-space-xs) !important;"
        "  min-height: 26px !important;"
        "}"
        'div[class*="st-key-gc_gamestrip"] button p {'
        "  font-size: var(--lc-text-tiny) !important;"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )

    with st.container(key="gc_gamestrip"):
        _cols = st.columns(len(_labels))
        for _gidx, (_lbl, _g) in enumerate(zip(_labels, games)):
            _sel = _gidx == st.session_state["gc_selected_game_idx"]
            _a, _h = logo_for(_g.get("away")), logo_for(_g.get("home"))
            _ai = (f'<img src="{_a}" width="21" height="21" style="vertical-align:middle;">'
                   if _a else f'<b style="font-size:var(--lc-text-caption);">{team_abbr(_g.get("away", "?"))}</b>')
            _hi = (f'<img src="{_h}" width="21" height="21" style="vertical-align:middle;">'
                   if _h else f'<b style="font-size:var(--lc-text-caption);">{team_abbr(_g.get("home", "?"))}</b>')
            # First pitch on the card itself. The picker used to carry
            # only the matchup, so choosing between an early game and a
            # night game meant selecting one, reading the breadcrumb,
            # and going back. The time is the second thing anyone wants
            # here and it costs one line.
            try:
                _t = (datetime.fromisoformat(_g["game_time"].replace("Z", "+00:00"))
                      .astimezone(EASTERN).strftime("%-I:%M %p")
                      if _g.get("game_time") else "")
            except Exception:
                _t = ""
            with _cols[_gidx]:
                st.markdown(
                    f'<div class="lc-gamecard" style="text-align:center; '
                    f'padding:var(--lc-space-xs) var(--lc-space-hair) var(--lc-space-hair); '
                    f'border-radius:var(--lc-radius-lg) var(--lc-radius-lg) 0 0; '
                    f'border:{"1px solid " + COLOR["stat_high"] if _sel else "1px solid " + COLOR["text"] + "1A"}; '
                    f'border-bottom:none; '
                    f'background:{COLOR["stat_high"] + "1F" if _sel else "transparent"}; '
                    # The selected card lifts instead of thickening its
                    # border. A 2px border on select and 1px otherwise
                    # shifted every neighbour by a pixel as you moved
                    # along the strip, which reads as jitter on a swipe.
                    f'box-shadow:{"0 0 0 1px " + COLOR["stat_high"] + ", 0 4px 16px -8px " + COLOR["stat_high"] if _sel else "none"};">'
                    f'<div style="white-space:nowrap;">{_ai}'
                    f'<span style="margin:var(--lc-space-none) var(--lc-space-xs); '
                    f'color:{COLOR["text"]}; opacity:0.5; font-size:var(--lc-text-micro);">@</span>{_hi}</div>'
                    f'<div style="font-size:var(--lc-text-micro); margin-top:2px; '
                    f'color:{COLOR["stat_high"] if _sel else COLOR["text"]}; '
                    f'opacity:{1 if _sel else 0.45};">{_t}</div></div>',
                    unsafe_allow_html=True,
                )
                st.button(
                    _lbl, key=f"gpick_{_gidx}", use_container_width=True,
                    type="primary" if _sel else "secondary",
                    on_click=_pick_game, args=(_gidx,),
                )


def _render_game_headline(game):
    """Centred headline: teams, then one meta line.

    The venue used to sit on its own gold line under the matchup, which
    made two headlines where there is one piece of information. Venue,
    first pitch and the park's HR factor are all context for the same
    game, so they read as one line separated by rules — the eye takes it
    in as a single band instead of three stacked announcements.
    """
    _bits = [game.get("venue") or ""]
    try:
        _bits.append(datetime.fromisoformat(
            game["game_time"].replace("Z", "+00:00")).astimezone(EASTERN)
            .strftime("%-I:%M %p ET") if game.get("game_time") else "")
    except Exception:
        _bits.append("")
    _meta = "".join(
        (f'<span style="color:{COLOR["text"]}; opacity:0.28; '
         f'margin:var(--lc-space-none) var(--lc-space-md);">|</span>' if i else "")
        + f'<span>{b}</span>'
        for i, b in enumerate([x for x in _bits if x])
    )
    st.markdown(
        f'<div style="text-align:center; margin-bottom:var(--lc-space-xs);">'
        f'<span style="font-size:var(--lc-text-display); font-weight:800; '
        f'color:{COLOR["headline"]};">{game["away"]} @ {game["home"]}</span></div>'
        f'<div style="text-align:center; color:{COLOR["gold"]}; '
        f'font-size:var(--lc-text-body); margin-bottom:var(--lc-space-xl);">{_meta}</div>',
        unsafe_allow_html=True,
    )


def _render_conditions_strip(_cond_display, _wind_display, park_display, temp_display):
    """Weather and park factor as one divided band.

    Was four blocks floating in a card with space-around, so the cells
    drifted apart on a wide screen and collided on a narrow one, and
    nothing said where one metric ended and the next began. Now it is a
    fixed four-column grid with hairline rules between the cells: equal
    widths, aligned baselines, and a visible boundary doing the work
    that whitespace was failing to do.

    Order is deliberate — condition, temp, wind, park. The first three
    change every hour and the last one never changes at all, so the
    thing you re-read sits first and the constant anchors the end.
    """
    _cells = (
        ("Condition", f'<div class="lc-weather-icon" style="height:28px;">'
                      f'{weather_icon(_cond_display)}</div>', _cond_display),
        ("Temp", f'<div style="height:28px;">{temp_icon(temp_display)}</div>',
         f"{temp_display}\u00b0F"),
        ("Wind", f'<div class="lc-wind-icon" style="height:28px;">'
                 f'{wind_arrow(_wind_display)}</div>', _wind_display),
        ("Park Factor", f'<div style="height:28px;">{park_icon(park_display)}</div>',
         park_display),
    )
    st.markdown(
        f'<div style="display:grid; grid-template-columns:repeat(4, 1fr); '
        f'border-top:1px solid {COLOR["text"]}14; border-bottom:1px solid {COLOR["text"]}14; '
        f'margin-bottom:var(--lc-space-lg);">'
        + "".join(
            f'<div style="text-align:center; padding:var(--lc-space-md) var(--lc-space-xs); '
            f'{"border-left:1px solid " + COLOR["text"] + "14;" if i else ""}">'
            f'<div style="font-size:var(--lc-text-micro); letter-spacing:0.12em; '
            f'text-transform:uppercase; color:{COLOR["text_muted"]};">{label}</div>'
            f'<div style="margin:var(--lc-space-hair) var(--lc-space-none);">{icon}</div>'
            f'<div style="font-size:var(--lc-text-body); color:{COLOR["text"]}; '
            f'font-weight:700;">{value}</div></div>'
            for i, (label, icon, value) in enumerate(_cells)
        )
        + '</div>',
        unsafe_allow_html=True,
    )


def _pick_starting_pitcher(pitcher_options):
    """Starting-pitcher segmented control."""
    pitcher_choice = st.segmented_control(
        "Select Pitcher", pitcher_options, default=pitcher_options[0],
        # Key includes the option labels. The labels can CHANGE mid-session:
        # hand_tag returns "" until the pitcher's dataframe is cached, then
        # "LHP"/"RHP" on a later rerun. With a fixed key, session state
        # would still hold the old label — a value no longer in the options
        # list — which Streamlit either errors on or silently resets.
        # Folding the labels into the key means a label change starts a
        # fresh widget that simply defaults to the away pitcher, exactly as
        # a first visit does.
        key=f"pitcher_choice_{st.session_state['gc_selected_game_idx']}_"
            f"{abs(hash(tuple(pitcher_options))) % 10**8}",
        label_visibility="collapsed",
    )
    return pitcher_choice

def _render_pitcher_header(pitcher_data, pitcher_id, selected_pitcher_name):
    """Pitcher header card — headshot, name, season pitch mix."""
    with card("pitcher_header"):
        col_head, col_mix = st.columns([1, 3])
        with col_head:
            if pitcher_id:
                st.image(get_headshot_url(pitcher_id), width=80)
            # Throwing hand, shown next to the name. It drives the whole
            # platoon side of the model — which side a switch hitter bats
            # from, the batter-vs-hand splits, the park factor that then
            # applies — and it appeared nowhere on the site.
            _hand = (pitcher_data or {}).get("p_throws")
            _hand_tag = (
                f'<span style="font-family:\'JetBrains Mono\',monospace; '
                f'font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; margin-left:var(--lc-space-sm);">'
                f'{_hand}HP</span>' if _hand in ("R", "L") else "")
            st.markdown(f'<span style="font-weight:700; color:{COLOR["text"]};">'
                        f'{selected_pitcher_name}</span>{_hand_tag}',
                        unsafe_allow_html=True)
            _baa = pitcher_data.get("BA") if pitcher_data else None
            if _baa is not None and (pitcher_data.get("AB") or 0) > 0:
                st.markdown(
                    f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-small); '
                    f'color:{COLOR["text"]}; margin-top:var(--lc-space-hair);">BA allowed '
                    f'<span style="font-weight:700; color:{COLOR["stat_high"]};">{_baa:.3f}</span></div>',
                    unsafe_allow_html=True,
                )

        with col_mix:
            st.markdown(f'<div class="pf-card-title" style="margin-bottom:var(--lc-space-md); color:{COLOR["gold"]};">Pitch Mix (Season)</div>', unsafe_allow_html=True)
            arsenal = pitcher_data.get("Pitch Arsenal", {}) if pitcher_data else {}
            if arsenal:
                bars_html = '<div style="display:flex; gap:18px; flex-wrap:wrap;">'
                for pt, usage in sorted(arsenal.items(), key=lambda x: -x[1])[:6]:
                    c = pitch_color(pt)
                    bars_html += (
                        f'<div style="min-width:100px;">'
                        f'<div style="font-size:var(--lc-text-caption); color:{c}; font-weight:600;">{pitch_name(pt)}</div>'
                        f'<div style="height:5px; width:100%; background:{COLOR["surface_raised"]}; border-radius:var(--lc-radius-sm); margin:var(--lc-space-xs) var(--lc-space-none);">'
                        f'<div style="height:5px; width:{min(usage,100)}%; background:{c}; border-radius:var(--lc-radius-sm);"></div>'
                        f'</div>'
                        f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-small); color:{COLOR["text"]};">{usage:.2f}%</div>'
                        f'</div>'
                    )
                bars_html += '</div>'
                st.markdown(bars_html, unsafe_allow_html=True)
            else:
                st.caption("No arsenal data available.")
    return arsenal

def _render_pitcher_detail(pitcher_id):
    """Pitcher detail: weak spots, splits and arsenal tables."""
    if pitcher_id:
        with st.expander("\U0001F3AF Weak spots \u2014 where he gets hurt"):
            _ws = get_weak_spots(pitcher_id)
            if _ws.get("error"):
                st.caption(_ws["error"])
            else:
                _render_weak_spots(_ws)


# ONE VISUAL LANGUAGE FOR THE WHOLE WEAK-SPOTS SECTION.
#
# This section used to render in four different idioms stacked on top of
# each other: a borderless HTML table for pitch types, bordered box
# grids for zone bands / times-through-order / batting-order slots, and
# two st.caption prose blobs for halves and caveats. Nothing shared a
# cell size, an alignment, or a legend, and the one sentence explaining
# what red, blue and the em dash meant sat in a paragraph above all of
# it. The reader had to re-learn how to read every block.
#
# Everything below is now the same unit: a labelled row with a
# left-anchored bar whose LENGTH is the xSLG and whose COLOUR is the
# verdict. Length gives you the comparison at a glance — which is the
# actual question, "where is he worst" — and colour gives you the
# threshold. One legend at the top covers every group because every
# group reads identically.
#
# WHY A BAR AND NOT A HEATMAP GRID. A grid of coloured squares makes you
# compare hues, which is slow and defeats anyone colour-blind. A bar
# encodes the same number as length first; colour is confirmation, not
# the only channel. The em-dash cases keep a visible empty track rather
# than vanishing, so "not measured" reads as a real state instead of a
# gap in the layout.

# The bar scale. xSLG below .250 is essentially unheard of and above
# .800 is a disaster, so anchoring the track there spends the full width
# on the range that actually varies instead of wasting half of it.
_WS_FLOOR, _WS_CEIL = 0.250, 0.800


def _ws_bar(v, sample_note=""):
    """One measurement, as a bar. Returns HTML for a table cell."""
    if v is None:
        return (f'<div style="height:14px; border-radius:7px; '
                f'background:{COLOR["text"]}0F;"></div>'
                f'<div style="font-size:var(--lc-text-micro); color:{COLOR["text"]}; '
                f'opacity:0.45; margin-top:2px;">\u2014 {sample_note}</div>')
    pct = max(4.0, min(100.0, (v - _WS_FLOOR) / (_WS_CEIL - _WS_FLOOR) * 100.0))
    c = (COLOR["error"] if v >= XSLG_HOT
         else COLOR["stat_high"] if v <= XSLG_COLD else COLOR["warn"])
    return (f'<div style="height:14px; border-radius:7px; background:{COLOR["text"]}0F; '
            f'position:relative; overflow:hidden;">'
            f'<div style="position:absolute; left:0; top:0; bottom:0; width:{pct:.1f}%; '
            f'background:{c}; opacity:0.85; border-radius:7px;"></div></div>'
            f'<div style="font-size:var(--lc-text-micro); margin-top:2px;">'
            f'<b style="color:{c};">{v:.3f}</b>'
            f'<span style="color:{COLOR["text"]}; opacity:0.45;"> {sample_note}</span></div>')


def _ws_group(title, rows, note=None):
    """A titled block of identical label/bar rows."""
    import streamlit as st
    if not rows:
        return
    st.markdown(
        f'<div style="font-size:var(--lc-text-small); font-weight:700; '
        f'color:{COLOR["text_muted"]}; margin-top:var(--lc-space-lg); '
        f'margin-bottom:var(--lc-space-xs);">{title}</div>',
        unsafe_allow_html=True)
    _tr = "".join(
        f'<tr>'
        f'<td style="width:34%; padding:var(--lc-space-hair) var(--lc-space-md) '
        f'var(--lc-space-hair) 0; font-size:var(--lc-text-caption); '
        f'color:{COLOR["text"]}; vertical-align:top; white-space:nowrap;">{lbl}'
        + (f'<span style="opacity:0.45; font-size:var(--lc-text-micro);"> {sub}</span>'
           if sub else "")
        + f'</td>'
        f'<td style="padding:var(--lc-space-hair) 0; vertical-align:top;">{bar}</td>'
        f'</tr>'
        for lbl, sub, bar in rows
    )
    st.markdown(f'<table style="width:100%; border-collapse:collapse;">{_tr}</table>',
                unsafe_allow_html=True)
    if note:
        st.caption(note)


def _render_weak_spots(_ws):
    """Every weak-spot group, one visual language, one legend."""
    import streamlit as st

    # THE LEGEND IS SHOWN, NOT DESCRIBED.
    #
    # The old version explained red/blue/em-dash in a sentence and then
    # asked you to hold it in your head through four differently-shaped
    # blocks. Three chips cost less space than the sentence did and
    # cannot be misremembered halfway down.
    st.markdown(
        f'<div style="display:flex; gap:var(--lc-space-md); flex-wrap:wrap; '
        f'align-items:center; margin-bottom:var(--lc-space-xs);">'
        + "".join(
            f'<span style="display:inline-flex; align-items:center; gap:6px; '
            f'font-size:var(--lc-text-micro); color:{COLOR["text"]}; opacity:0.8;">'
            f'<span style="width:18px; height:8px; border-radius:4px; '
            f'background:{c}; opacity:0.85; display:inline-block;"></span>{t}</span>'
            for c, t in (
                (COLOR["error"], f"hitters do real damage (\u2265{XSLG_HOT:.3f})"),
                (COLOR["warn"], "middling"),
                (COLOR["stat_high"], f"he wins here (\u2264{XSLG_COLD:.3f})"),
            ))
        + f'<span style="font-size:var(--lc-text-micro); color:{COLOR["text"]}; '
          f'opacity:0.55;">\u2014 = below its sample floor, not measured</span>'
        + '</div>',
        unsafe_allow_html=True)
    st.markdown(
        f'<div class="pf-card-subtitle" style="margin-bottom:var(--lc-space-none);">'
        f'xSLG allowed on contact \u00b7 longer bar = more damage. A rate off a thin '
        f'bucket is noise, so anything under its floor shows an empty track rather '
        f'than a number. Formula and floors in engines/pitcher_weakspots.py.</div>',
        unsafe_allow_html=True)

    _ws_group(
        "By pitch type",
        [(p["name"], f'{p["usage"]:.0f}% usage',
          _ws_bar(p.get("xslg"), p.get("reason", f'{p["bbe"]} batted balls')))
         for p in _ws.get("pitches", []) if p["usage"] >= 3])

    _ws_group(
        "By zone band",
        [(b["band"], "", _ws_bar(b.get("xslg"), f'{b["bbe"]} bbe'))
         for b in _ws.get("bands", [])])

    _tto = _ws.get("tto", [])
    _ws_group(
        "Times through the order",
        [(f'{t["pass"]}{"st" if t["pass"] == 1 else "nd" if t["pass"] == 2 else "rd"} time',
          "", _ws_bar(t.get("xslg"), f'{t["bbe"]} bbe'))
         for t in _tto],
        note=("Most starters decline the third time through a lineup \u2014 a steep "
              "jump here is a real bullpen and late-innings angle.") if _tto else None)

    # Halves stay prose-free but join the same grid, so the one group
    # that used to be a sentence now compares directly against the rest.
    _halves = _ws.get("halves", [])
    if any(h.get("xslg") is not None for h in _halves):
        _ws_group(
            "Top vs bottom of the order",
            [(h["half"], "", _ws_bar(h.get("xslg"), "")) for h in _halves],
            note=("Context only, deliberately not scored: a gap here mostly reflects "
                  "that better hitters bat at the top, not a repeatable weakness."))

    # Per batting-order slot (1-9) — the granular version, each slot
    # flagged only above its sample floor. Aligned to tonight's actual
    # hitters in the "vs this lineup" section below the lineup table.
    _slots = _ws.get("slots", [])
    if any(s.get("xslg") is not None for s in _slots):
        _ws_group(
            "By batting-order slot",
            [(f'Slot {s["slot"]}', "", _ws_bar(s.get("xslg"), f'{s["bbe"]} bbe'))
             for s in _slots],
            note=("Per-slot splits carry a real caveat \u2014 a slot's line partly "
                  "reflects which hitters happened to bat there across his starts, "
                  "not only his own skill. Slots below the sample floor show an "
                  "empty track and are never flagged. Read it alongside the lineup "
                  "mapping below."))


def _render_dual_arsenal(_arsenal_bars, game):
    """Both starters side by side for arsenal comparison."""
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
                st.markdown(f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:var(--lc-text-body);">{sp_name} <span style="color:{COLOR["text_muted"]}; font-weight:600;">({team_abbr(team_label)})</span></div>', unsafe_allow_html=True)
                if sp_id:
                    _arsenal_bars(get_pitcher_statcast(sp_id))
                else:
                    st.caption("Starter not posted yet.")

def _render_bullpen_browser(_arsenal_bars, game):
    """Bullpen browser — any rostered arm on either staff."""
    with st.expander("\U0001F9E4 Bullpen browser \u2014 any pitcher on either staff"):
        st.caption(
            "Bullpen changes flip matchups. Pick any rostered pitcher to see their real "
            "arsenal on demand \u2014 loaded only when you ask, so the page stays fast."
        )
        bp1, bp2 = st.columns(2)
        for colx, team_name in ((bp1, game.get("away")), (bp2, game.get("home"))):
            with colx:
                st.markdown(f'<div style="font-weight:700; color:{COLOR["text"]}; font-size:var(--lc-text-body);">{team_name}</div>', unsafe_allow_html=True)
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
                                    f'<div style="font-size:var(--lc-text-caption); font-weight:700; color:{COLOR["text_muted"]}; '
                                    f'margin-top:var(--lc-space-md);">{opp_label} vs this arsenal ({bp_names})</div>',
                                    unsafe_allow_html=True,
                                )
                                render_html_table(
                                    style_stat_table(
                                        # NOT set_index("Player").
                                        #
                                        # _base_styler calls .hide(axis="index"),
                                        # so anything left in the index is dropped
                                        # before render_html_table ever sees it —
                                        # its own docstring says the row label must
                                        # be a real COLUMN. Indexing by Player
                                        # deleted the batter names from this table
                                        # and left nine anonymous stat rows, which
                                        # is exactly as useful as no table. Keeping
                                        # Player as a column also gets it the
                                        # identity colouring _player_name_column
                                        # applies for free.
                                        pd.DataFrame(bp_rows),
                                        favor_high=["BA", "Brl %", "HH %"],
                                        favor_low=["Whiff %", "SwStr %"],
                                        gradient=True,
                                    ), key="gc_666")
                                st.caption(
                                    f"Season numbers vs those pitch types only \u2014 blue rows are the "
                                    f"batters who punish this stuff, red rows are the ones it beats. "
                                    f"Lineup source: {opp_src}. A small Pitches count means a small "
                                    f"sample \u2014 read those rows gently."
                                )
                    else:
                        st.caption("No ID for that pitcher \u2014 no data to show.")

def _resolve_lineup_batters(confirmed_lineup, lineup_confirmed, opposing_team):
    """Tonight’s batters, from the confirmed or projected lineup."""
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
            _raw = [p for p in last_lineup if not p["is_pitcher"]]

            # DROP ANYONE NO LONGER ON THE ACTIVE ROSTER.
            #
            # get_last_starting_lineup searches back FOURTEEN days for the
            # most recent completed game, and this fallback is what you're
            # looking at every morning before lineups post. A player who
            # went on the IL nine days ago is still sitting in that
            # lineup — and he'd be scored like anyone else: HR Score,
            # matchup, park, wind, the whole row. Every number correct
            # except whether he's playing.
            #
            # Active-roster membership is MLB's own state and is already
            # being fetched by get_live_team_roster, so this costs nothing.
            # An EMPTY set means the roster call failed, which is unknown,
            # not "nobody is active" — in that case show the lineup as-is
            # rather than blanking the page over one timed-out request.
            _active = get_active_player_ids(opposing_team)
            _dropped = []
            if _active:
                batters = []
                for _p in _raw:
                    if str(_p.get("id")) in _active:
                        batters.append(_p)
                    else:
                        _dropped.append(_p.get("name"))
            else:
                batters = _raw

            st.info(
                f"MLB hasn't posted {opposing_team}'s confirmed starting lineup yet "
                f"(usually posted 1\u20133 hours before first pitch) \u2014 showing their real "
                f"starting 9 from their last game ({last_game_date}) instead. This will switch "
                f"to today's confirmed batting order automatically once MLB posts it."
            )
            if _dropped:
                st.warning(
                    f"Removed from that lineup: {', '.join(_dropped)} — no longer on "
                    f"{opposing_team}'s active roster (traded, IL, optioned, or "
                    f"restricted). They played on {last_game_date} but aren't "
                    f"available today, so scoring them here would be a real-looking "
                    f"number on someone who isn't in the building."
                )
            # The other half of a trade. A player acquired since that game
            # was never in it, so he cannot appear in this fallback — the
            # nine below are real, they are just the nine from BEFORE the
            # deal. Without this line the omission is invisible: a card
            # showing nine correct hitters looks complete whether or not a
            # new bat is missing from it.
            st.caption(
                "This is the lineup from that date. Anyone acquired since then "
                "won't appear until MLB posts today's confirmed order."
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
    return batters

def _attach_batter_profiles(batter_profiles, batters):
    """Attach the ID-matched batted-ball profile to each batter."""
    for b in batters:
        # Real, ID-matched batted-ball profile — same reliable engine
        # SLAM uses, not the old name-matching one. Eliminates the
        # missing-fields bug AND the accented-name matching failures
        # in one move, since there's no name string involved at all.
        profile = get_batter_profile_windowed(b.get("id"), window="season", unit="bbe")
        # battingOrder carried through so the opportunity factor and the
        # 1-9 display order both have it. Present only on CONFIRMED
        # lineups — the fallback path has no batting order, and the slot
        # adjustment correctly sits out there rather than inventing one.
        batter_profiles.append({"name": b["name"], "bats": b.get("bats") or "?",
                                "id": b.get("id"), "profile": profile,
                                "battingOrder": b.get("battingOrder")})

def _compute_matchup_edges(_p_throws, game, opposing_team, pitcher_data, pitcher_id, ranked):
    """Per-batter matchup grade against this arsenal."""
    if ranked and pitcher_id:
        _pitcher_team = game["away"] if opposing_team == game["home"] else game["home"]
        # Wording no longer promises a ~30s wait. That was true when the
        # first lineup of the day built the slate-wide pen baseline live —
        # one roster call plus a splits derive and a hand lookup per arm,
        # for all 30 teams. precompute.build_bullpen_profiles now ships
        # that nightly and edge._pen_profile_json reads it locally, so the
        # warm path is microseconds. Telling a subscriber to expect half a
        # minute makes the app feel slower than it is.
        with st.spinner("Computing matchup edges\u2026"):
            # Warm-up call only — the RESULT is discarded. Its job is to
            # build the slate-wide pen baseline behind the spinner above,
            # which takes ~30s on the first game of the day. The values
            # that actually reach the board are resolved per batter
            # further down, since the pen adjustment now depends on each
            # hitter's platoon split.
            pen_context(_pitcher_team, pitcher_id)
            # Tonight's park, keyed by Statcast's team code — that's what
            # build_park_hr_factors groups on. game["home"] is the full
            # club name, so it has to be abbreviated here or every lookup
            # would silently miss and return no adjustment.
            _park_abbr = team_abbr(game["home"])
            _temp = game.get("weather_temp")
            # Compass forecasts ("SW 12 mph") are now usable: wind_engine
            # resolves them against this park's real orientation.
            _wind = game.get("weather_wind")
            # Full pitch-type interaction here: a Game Card is ~18
            # hitters, so per-pitch profiles are affordable. Limited to
            # the pitcher's top 3 offerings — beyond that usage is too
            # low to carry signal and the slices stop being free.
            _arsenal = (pitcher_data or {}).get("Pitch Arsenal") or {}
            _top_pitches = tuple(
                p for p, _u in sorted(_arsenal.items(), key=lambda kv: -kv[1])[:3])
            for _r in ranked:
                # EFFECTIVE hand for tonight. Park splits by hand are
                # large, so handing edge_components a raw "S" would apply
                # the wrong split to exactly the hitters it matters most
                # for. A switch hitter bats opposite the pitcher's throwing
                # hand; everyone else bats their own side.
                #
                # Resolved inline rather than via _side_for(), which does
                # the same thing but is defined further down in the lineup
                # table block and is NOT in scope here.
                _b = (_r.get("bats") or "").upper()
                if _b == "S":
                    _eff_bats = "L" if _p_throws == "R" else "R" if _p_throws == "L" else None
                else:
                    _eff_bats = _b
                # Per batter: the pen adjustment now includes how this
                # hitter handles the hand the pen actually throws, so the
                # matchup read doesn't expire when the starter is pulled.
                _pa, _pn = pen_context(_pitcher_team, pitcher_id,
                                       batter_id=_r.get("id"))
                _r.update(edge_components(_r.get("id"), pitcher_id,
                                          _r.get("hr_score"), _pa, _pn,
                                          home_team=_park_abbr,
                                          bats=_eff_bats,
                                          temp=_temp, wind=_wind,
                                          arsenal=_arsenal,
                                          batting_order=_r.get("battingOrder"),
                                          batter_vs_pitch=_batter_pitch_profile(
                                              _r.get("id"), _top_pitches)
                                          if _top_pitches and _r.get("id") else None))
                if _p_throws in ("R", "L") and _r.get("id"):
                    _r["iso_vs_hand"] = get_batter_iso_vs_hand(_r["id"], _p_throws)
                    _r["opp_hand"] = f"{_p_throws}HP"

def _render_top_plays(league_data_available, opposing_team, ranked):
    """Top plays panel: HR, hit and strikeout target tables."""
    if not ranked:
        st.info(f"No lineup data available for {opposing_team} right now.")
    else:
        if not league_data_available:
            st.caption("Scores below will show as N/A \u2014 see warning above.")

        def _targets_table(sort_field, label):
            """Rows for one targets card.

            Keeps None as None rather than passing through _score_num.
            _score_num's own docstring justifies substituting 0 on the
            grounds that it is "always paired with the N/A text elsewhere
            so it's never the only signal" — but in THIS table the number
            is the only signal. When Savant is unreachable every score
            rendered as a hard 0, which reads as "this hitter is the worst
            in the league" rather than "we couldn't measure him". The
            warning banner above even promised N/A while the table said 0.

            None becomes NaN in the frame and the styler renders it as
            N/A, matching both the banner and the Stack Pick card beside
            it — which was already correct.
            """
            rows = []
            for r in sorted(ranked, key=lambda x: _score_sort_key(x, sort_field))[:5]:
                rows.append({"Player": r["name"], "Bats": r["bats"],
                             label: r[sort_field]})
            return pd.DataFrame(rows)

        top_row1, top_row2 = st.columns(2)
        with top_row1:
            with card("hr_targets"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Top HR Targets</div>', unsafe_allow_html=True)
                hr_df = _targets_table("hr_score", "HR Score")
                render_html_table(
                    # Bar, not a flat coloured cell — same treatment as the
                    # lineup and HR Edge boards. favor_high dropped so the
                    # cell gradient does not sit behind the bar and swallow
                    # its track.
                    style_stat_table(hr_df, gradient=True).format(
                        {"HR Score": score_bar("stat_high")}, na_rep="N/A"),
                    key="gc_918")
        with top_row2:
            with card("hit_targets"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Best Hit Targets</div>', unsafe_allow_html=True)
                hit_df = _targets_table("hit_score", "Hit Score")
                render_html_table(
                    # Bar, not a flat coloured cell — same treatment as the
                    # lineup and HR Edge boards. favor_high dropped so the
                    # cell gradient does not sit behind the bar and swallow
                    # its track.
                    style_stat_table(hit_df, gradient=True).format(
                        {"Hit Score": score_bar("warn")}, na_rep="N/A"),
                    key="gc_923")

        bot_row1, bot_row2 = st.columns(2)
        with bot_row1:
            with card("k_targets"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Strikeout Targets</div>', unsafe_allow_html=True)
                k_df = _targets_table("k_score", "K Score")
                render_html_table(
                    # Bar, not a flat coloured cell — same treatment as the
                    # lineup and HR Edge boards. favor_high dropped so the
                    # cell gradient does not sit behind the bar and swallow
                    # its track.
                    style_stat_table(k_df, gradient=True).format(
                        {"K Score": score_bar("gold")}, na_rep="N/A"),
                    key="gc_930")
        with bot_row2:
            hr_vals = [r["hr_score"] for r in ranked if r["hr_score"] is not None]
            hit_vals = [r["hit_score"] for r in ranked if r["hit_score"] is not None]
            avg_hr = round(sum(hr_vals) / len(hr_vals)) if hr_vals else None
            avg_hit = round(sum(hit_vals) / len(hit_vals)) if hit_vals else None
            with card("stack_pick"):
                st.markdown(
                    f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Stack Pick</div>'
                    f'<div style="font-size:var(--lc-text-subhead); font-weight:800; color:{COLOR["text"]}; margin-bottom:var(--lc-space-lg);">{opposing_team}</div>'
                    f'<div style="display:flex; gap:16px;">'
                    f'<div><div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-stat); font-weight:700; color:{COLOR["stat_high"]};">{_score_display(avg_hr)}</div>'
                    f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]}; text-transform:uppercase;">Avg HR Score</div></div>'
                    f'<div><div style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-stat); font-weight:700; color:{COLOR["warn"]};">{_score_display(avg_hit)}</div>'
                    f'<div style="font-size:var(--lc-text-tiny); color:{COLOR["text_muted"]}; text-transform:uppercase;">Avg Hit Score</div></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

# These were defined INSIDE the 2,000-line `with content_col:` statement,
# so nothing could reach them — not a test, not another view, not even a
# different part of this file. All seven are closure-free: they read only
# their arguments and module-level names, so lifting them here changes no
# behaviour.
#
# Dedenting these is fussier than it looks. A plain textwrap.dedent also
# strips the leading spaces from CONTINUATION LINES OF MULTI-LINE STRINGS,
# where that whitespace is string content rather than indentation — it
# silently rewrote three format strings and test_gamecard_columns.py
# caught it. The lines inside multi-line string tokens are copied verbatim.
#
# The block still needs breaking up properly. This is the part that could
# be proven safe without running the app.
# ---------------------------------------------------------------------

def _pick_game(_gidx):
    st.session_state["gc_selected_game_idx"] = _gidx

def _xslg_chip(v):
    if v is None:
        return f'<span style="color:{COLOR["text"]}; opacity:0.4;">\u2014</span>'
    c = (COLOR["error"] if v >= XSLG_HOT
         else COLOR["stat_high"] if v <= XSLG_COLD else COLOR["warn"])
    return (f'<span style="font-weight:800; color:{c};">{v:.3f}</span>')

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

def _score_sort_key(r, field):
    v = r.get(field)
    return -1 if v is None else -v  # None sorts last regardless of view

def _score_display(v):
    return "N/A" if v is None else str(v)

def _score_num(v):
    """0 for display-only numeric contexts (progress bars) \u2014 always
        paired with the N/A text elsewhere so it's never the only signal."""
    return 0 if v is None else v

def _stat_row(name, bats_label, profile, *, matchup=None, slam=None,
              hr_edge=None, hr_score=None, hit_score=None,
              edge_cell=None, edge_label="", edge_tier="neutral",
              confidence="", batting_order=None):
    """One table row. Score/matchup fields are optional so a
                    switch hitter's non-matchup side can show stats only (its
                    HR/Hit scores would be for the wrong platoon side, so we
                    blank them rather than print a misleading number)."""
    return {
        "Player": name,
        "Bats": bats_label,
        # 1-9 as posted, sitting with the other identity
        # columns rather than mid-table between HR/FB and
        # Brl%, where it interrupted the run of rate
        # stats. Blank on the unconfirmed-lineup fallback,
        # which genuinely has no batting order.
        "Ord": (batting_order // 100) if batting_order else None,
        "Matchup": matchup if matchup is not None else "\u2014",
        "SLAM": round(slam, 1) if slam is not None else None,
        # NO ", 0" DEFAULTS ANYWHERE IN THIS ROW.
        #
        # A missing BA is not a .000 BA, a missing HH% is
        # not a 0.0 HH%. The engine now returns None for
        # anything it couldn't measure (see
        # _compute_batted_ball_metrics), and na_rep="N/A"
        # on the formatter below renders that honestly.
        # A zero-default here would have quietly undone
        # that at the last step — this table has no PA
        # column, so a fabricated 0.0 is indistinguishable
        # from a measured one.
        "BA": profile.get("BA"),
        "xwOBA": profile.get("xwOBA"),
        "xSLG": profile.get("xSLG"),
        "ISO": profile.get("ISO"),
        "HR/FB": profile.get("HR/FB"),
        "Brl%": profile.get("Brl %"),
        # Barrels per PLATE APPEARANCE, next to the
        # per-batted-ball rate. The gap between the two
        # IS the read: a bat with a high Brl% and a low
        # Brl/PA barrels well but doesn't put enough
        # balls in play to cash it in.
        "Brl/PA": profile.get("Brl/PA"),
        "HH%": profile.get("HH %"),
        # 90th-percentile exit velocity — the scored
        # power ceiling. Max EV sits beside it for
        # interest only; it's a sample of one.
        "EV90": profile.get("EV90"),
        "MaxEV": profile.get("MaxEV"),
        "LD%": profile.get("LD %"),
        "FB%": profile.get("FB %"),
        "GB%": profile.get("GB %"),
        "SweetSpot%": profile.get("SweetSpot %"),
        # Launch angle 20-40 — the HOME RUN band, which
        # is NOT SweetSpot% (8-32, built for overall
        # production and starting at a line drive). Both
        # are shown because they answer different
        # questions and the difference is informative.
        "HRWindow%": profile.get("HRWindow %"),
        "PullAir%": profile.get("PullAir %"),
        "PullBrl%": profile.get("PullBrl %"),
        "Blast%": profile.get("Blast %"),
        # Process, not outcome: bat speed + swing plane +
        # pull tendency. Every other column here is
        # downstream of results, so they all sag together
        # when a power bat goes cold. This one doesn't.
        "HRIntent": profile.get("HRIntent"),
        # Hard-hit FLY BALLS. HH% and FB% are both already
        # above, on their own; this is the intersection,
        # and it's the one that predicts home runs. A 95
        # mph ground ball is a single and a 78 mph fly
        # ball is an out — each inflates one of those two
        # parent columns without being a HR trajectory.
        "FB95%": profile.get("FB95 %"),
        # The launch floor that gets out of ANY park,
        # measured off the league's own outcomes rather
        # than a fence diagram. There is no single angle
        # that does it — the angle needed falls as exit
        # velocity rises — so this is a curve, and these
        # are the balls that sit above it. Rare on
        # purpose: league average is a fraction of a
        # percent, so a bat showing anything here is
        # producing genuine no-doubt contact.
        "Clears%": profile.get("ClearsAnywhere %"),
        # 60% outcome, 40% process. HRIntent above stays
        # visible beside it deliberately — when the two
        # disagree, that gap is the read: high intent with
        # low threat is a home-run swing that isn't
        # landing yet.
        "HRThreat": profile.get("HRThreat"),
        # No ", 0" default: a missing SwStr% is not a
        # 0.00 SwStr%, and 0.00 in this column reads as
        # the best possible value. na_rep on the
        # formatter below renders None as N/A.
        "SwStr%": profile.get("SwStr %"),
        "HR Edge": hr_edge,
        "HR Score": hr_score,
        "Hit Score": hit_score,
        "Edge": edge_cell if edge_cell is not None else edge_tag("\u2014", "neutral"),
        "EdgeLabel": edge_label,
        "EdgeTier": edge_tier,
        "Confidence": confidence,
    }

# Plain container instead of st.columns — keeps the `with content_col:`
# indentation below untouched while letting the page use the full width
# app.py's main column gives it.
sync_latest_button(key="sync_gamecard")

content_col = st.container()

with content_col:
    # -----------------------------------------------------
    # GAME PICKER — one swipeable row, the whole slate, no pages.
    # -----------------------------------------------------
    st.session_state.setdefault("gc_selected_game_idx", 0)
    # Clamp the SELECTED GAME.
    #
    # This index survives reruns, but `games` does not stay the same
    # length: the slate shrinks as games go final and rebuilds shorter on
    # the next data refresh. Someone sitting on game 8 of a 9-game slate
    # would come back to a 6-game slate and hit an IndexError on the
    # lookups below — a hard crash on page load, and an intermittent one,
    # since it depends entirely on which game you last looked at.
    st.session_state["gc_selected_game_idx"] = min(
        st.session_state["gc_selected_game_idx"], len(games) - 1)

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

    _render_game_carousel(_labels, games)

    # No "Page 1 of 3" any more — there are no pages. The count still
    # earns its place: it tells you how far the strip scrolls, which a
    # row with a half-visible card at the edge only hints at.
    st.markdown(
        f'<div style="color:{COLOR["text"]}; font-size:var(--lc-text-body); font-weight:600; '
        f'margin:var(--lc-space-xs) var(--lc-space-none) var(--lc-space-lg) var(--lc-space-none);">'
        f'{len(games)} game{"s" if len(games) != 1 else ""} today '
        f'<span style="opacity:0.5; font-weight:400; font-size:var(--lc-text-small);">'
        f'\u2014 swipe to see them all</span></div>',
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
        f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]}; margin-bottom:var(--lc-space-lg);">'
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
    _render_game_headline(game)

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





    _render_conditions_strip(_cond_display, _wind_display, park_display, temp_display)

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
    # Handedness in the SELECTOR, not just after you've picked. Which way
    # a starter throws is often the reason you'd pick one side of the
    # matchup to look at, so having to select him first to find out had it
    # backwards. Both ids are resolved here anyway and get_pitcher_hand is
    # cached, so labelling both costs nothing.
    #
    # The name stays FIRST in each label: the startswith() checks below
    # match on game['away_pitcher'] / game['home_pitcher'], so anything
    # appended is safe but a prefix would break the selection.
    _away_ht = hand_tag(game.get("away_pitcher_id"))
    _home_ht = hand_tag(game.get("home_pitcher_id"))
    pitcher_options = [
        f"{game['away_pitcher']} ({game['away']}{', ' + _away_ht if _away_ht else ''})",
        f"{game['home_pitcher']} ({game['home']}{', ' + _home_ht if _home_ht else ''})",
    ]
    st.markdown(f'<div style="font-size:var(--lc-text-body-lg); font-weight:600; color:{COLOR["text"]}; margin-bottom:var(--lc-space-xs);">Select Pitcher</div>', unsafe_allow_html=True)
    pitcher_choice = _pick_starting_pitcher(pitcher_options)

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
    arsenal = _render_pitcher_header(pitcher_data, pitcher_id, selected_pitcher_name)

    # -----------------------------------------------------
    # WEAK SPOTS — where this starter actually gets hurt
    # -----------------------------------------------------
    _render_pitcher_detail(pitcher_id)

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
    # ONE RENDERER FOR EVERY SPORT.
    #
    # This block used to be a hand-rolled copy of the same card the
    # KBO/NPB/WNBA pages render through
    # engines/matchup_grades_intl.render_matchup_grades_card. Two copies
    # meant the improvements — the grade as a coloured badge, the
    # dropped "Lean:" prefix that only restated its own heading, the
    # retired checkmarks — landed on the international pages and never
    # reached the MLB Game Card, which is the page most people actually
    # open.
    #
    # The renderer lives in the _intl module for historical reasons
    # only; nothing in it is sport-specific. MLB passes no accent, so it
    # keeps the house gold exactly as before.
    render_matchup_grades_card(
        grades,
        subtitle=("This app's own signal checklists from real Statcast splits, "
                  "park factor, and posted weather \u2014 formula documented in "
                  "engines/matchup_grades.py. Not calibrated probabilities."),
        source_line=None,
        key="mlb",
        title=f"Matchup Grades \u00b7 {_gw_label}",
    )

    # -----------------------------------------------------
    # BOTH STARTERS + BULLPEN — full-staff arsenal browser
    # -----------------------------------------------------
    def _arsenal_bars(p_data):
        arsenal_d = p_data.get("Pitch Arsenal", {}) if p_data else {}
        if not arsenal_d:
            st.caption("No arsenal data available.")
            return
        html = ""
        for pt, usage in sorted(arsenal_d.items(), key=lambda x: -x[1])[:6]:
            c = pitch_color(pt)
            html += (
                f'<div style="margin-bottom:var(--lc-space-sm);">'
                f'<div style="display:flex; justify-content:space-between;">'
                f'<span style="font-size:var(--lc-text-caption); color:{c}; font-weight:600;">{pitch_name(pt)}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace; font-size:var(--lc-text-caption); color:{COLOR["text"]};">{usage:.1f}%</span>'
                f'</div>'
                f'<div style="height:5px; width:100%; background:{COLOR["surface_raised"]}; border-radius:var(--lc-radius-sm);">'
                f'<div style="height:5px; width:{min(usage,100)}%; background:{c}; border-radius:var(--lc-radius-sm);"></div>'
                f'</div></div>'
            )
        st.markdown(html, unsafe_allow_html=True)

    _render_dual_arsenal(_arsenal_bars, game)

    _render_bullpen_browser(_arsenal_bars, game)

    # -----------------------------------------------------
    # LOAD LINEUP + SCORES (shared across everything below)
    # -----------------------------------------------------
    opposing_side = "home" if opposing_team == game["home"] else "away"
    confirmed_lineup, lineup_confirmed = get_confirmed_lineup(game.get("game_pk"), opposing_side)

    batters = _resolve_lineup_batters(confirmed_lineup, lineup_confirmed, opposing_team)

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
    _attach_batter_profiles(batter_profiles, batters)

    ranked = rank_batters(batter_profiles, savant_df) if batter_profiles else []

    # ---- Matchup Edge layer (Phase 2): HR Edge = HR Score + BvP(±15)
    # + Zone Fit(±15) + Bullpen(±10). Every component sample-floored
    # and shown in the Edge breakdown below the table. engines/edge.py
    # documents the exact tiers and math.
    # Defined unconditionally: the lineup table reads this for switch
    # hitters even when no probable is posted, and a NameError there
    # would take down the whole page.
    _p_throws = (pitcher_data or {}).get("p_throws") or (pitcher_data or {}).get("Throws")

    _compute_matchup_edges(_p_throws, game, opposing_team, pitcher_data, pitcher_id, ranked)

    # -----------------------------------------------------
    # TODAY'S TOP PLAYS \u2014 plain section label, not its own card,
    # since each item below is now its own standalone card \u2014 a card
    # wrapping four more cards would just nest borders inside borders.
    # -----------------------------------------------------
    st.markdown(
        f'<div class="pf-card-title" style="margin-top:var(--lc-space-sm); color:{COLOR["gold"]};">Today\'s Top Plays</div>'
        f'<div class="pf-card-subtitle">This app\'s own composite scores \u2014 see engines/top_plays.py</div>',
        unsafe_allow_html=True,
    )
    _render_top_plays(league_data_available, opposing_team, ranked)

    # =======================================================
    # VIEW: MATCHUP
    # =======================================================
    if view == "\U0001F3E0 Matchup":
        st.markdown(
            f'<div class="pf-card-title" style="margin-top:var(--lc-space-sm); color:{COLOR["gold"]};">Splits</div>'
            f'<div class="pf-card-subtitle" style="color:{COLOR["text_muted"]};">Blue = favorable for batter, red = favorable for pitcher \u00b7 IP estimated from Statcast out events (no official box-score feed)</div>',
            unsafe_allow_html=True,
        )
        splits_overall = get_pitcher_advanced_splits(pitcher_id) if pitcher_id else None
        rows = {"Overall": splits_overall, "vs RHB": splits_vs_r, "vs LHB": splits_vs_l}
        rows = {k: v for k, v in rows.items() if v is not None}

        if rows:
            # .T makes the DICT KEYS the index: "Overall", "vs RHB",
            # "vs LHB". That label IS the data — it's the only thing
            # saying which platoon side each row describes, and this is
            # where you read what a pitcher allows to lefties vs righties.
            #
            # reset_index() turns it into a real "Split" COLUMN, which it
            # has to be: _base_styler calls .hide(axis="index"), so
            # anything left in the index is dropped before rendering.
            # That is why the labels disappeared — and why toggling
            # st.dataframe's hide_index did nothing to bring them back.
            #
            # Rendered as HTML rather than st.dataframe so the Split
            # column can be genuinely sticky while the stats scroll under
            # it. st.dataframe is canvas-drawn and CSS cannot reach it.
            full_df = pd.DataFrame(rows).T.reset_index().rename(
                columns={"index": "Split"})
            stats_cols = ["Split", "IP", "BA", "SLG", "ISO", "WHIP", "HR", "HR/9"]
            strikes_cols = ["Split", "BB%", "Whiff%", "K%", "Putaway%", "SwStr%", "K/9", "1stPS%", "Meatball%"]
            g1, g2 = st.columns(2)
            with g1:
                with card("stats_table"):
                    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">STATS</div>', unsafe_allow_html=True)
                    render_html_table(
                        style_stat_table(full_df[stats_cols], favor_high=["BA", "SLG", "ISO", "HR", "HR/9"], favor_low=["WHIP"], gradient=True),
                        key="splits_stats",
                    )
            with g2:
                with card("strikes_table"):
                    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">STRIKES</div>', unsafe_allow_html=True)
                    render_html_table(
                        style_stat_table(full_df[strikes_cols], favor_low=["BB%", "Whiff%", "K%", "Putaway%", "SwStr%", "K/9", "Meatball%"], favor_high=["1stPS%"], gradient=True),
                        key="splits_strikes",
                    )
            st.caption("Computed by this app directly from raw Statcast pitch data \u2014 see get_pitcher_advanced_splits() for exact definitions.")

            # -------------------------------------------------
            # HR VULNERABILITY (ALLOWED)
            #
            # These have been computed on every pitcher all along and
            # displayed nowhere: _compute_batted_ball_metrics runs on the
            # pitcher's OWN rows inside get_pitcher_statcast, so Brl %,
            # HH %, FB %, HRWindow % and EV90 there already describe the
            # contact hitters made AGAINST him. The pitcher half of the
            # HR model was invisible despite the numbers existing.
            #
            # Every value here is bad-for-the-pitcher when high, so the
            # whole card is favor_low — the opposite of the STATS card
            # above, where the same names mean the pitcher's own output.
            # -------------------------------------------------
            _hv = {
                "Brl% Allowed": pitcher_data.get("Brl % Allowed"),
                "HH% Allowed": pitcher_data.get("HH % Allowed"),
                "FB% Allowed": pitcher_data.get("FB % Allowed"),
                "FB95% Allowed": pitcher_data.get("FB95 % Allowed"),
                "HRWindow% Allowed": pitcher_data.get("HRWindow % Allowed"),
                # The trajectories he gives up that leave ANY park. The
                # strictest column on this card: a pitcher with a number
                # here is surrendering contact that no building holds.
                "Clears% Allowed": pitcher_data.get("ClearsAnywhere % Allowed"),
                "EV90 Allowed": pitcher_data.get("EV90 Allowed"),
                "HR Allowed": pitcher_data.get("HR Allowed"),
                "xHR Allowed": pitcher_data.get("xHR Allowed"),
                "xHR Gap": pitcher_data.get("xHR Gap Allowed"),
            }
            if any(v is not None for v in _hv.values()):
                with card("hr_vuln_table"):
                    st.markdown(
                        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                        f'HR VULNERABILITY (ALLOWED)</div>', unsafe_allow_html=True)
                    # "Season" as a real column, not an index — see the
                    # splits note above: _base_styler hides the index, so
                    # an index-only label never renders.
                    _hv_df = pd.DataFrame([{"Span": "Season", **_hv}])
                    render_html_table(
                        # Graded against the LEAGUE, not within the row.
                        #
                        # style_stat_table ranks a column against the other
                        # rows in the same table — and this table has one
                        # row, so every cell came out the same flat shade.
                        # style_vs_league compares each value to where it
                        # sits among all qualified pitchers (deciles built
                        # nightly by build_pitcher_allowed_percentiles).
                        #
                        # No favor_low: this card is read from the BATTER's
                        # side, so a pitcher allowing MORE hard contact
                        # than the league grades as the better target.
                        # Columns the league file doesn't cover render
                        # plain rather than falsely graded.
                        style_vs_league(_hv_df).format({
                            "Brl% Allowed": "{:.1f}", "HH% Allowed": "{:.1f}",
                            "FB% Allowed": "{:.1f}", "FB95% Allowed": "{:.1f}",
                            "HRWindow% Allowed": "{:.1f}",
                            "Clears% Allowed": "{:.2f}",
                            "EV90 Allowed": "{:.1f}",
                            # Counting stat — no decimals.
                            "HR Allowed": "{:.0f}",
                            # Expected values carry one decimal because a
                            # fractional expectation is the point.
                            "xHR Allowed": "{:.1f}", "xHR Gap": "{:+.1f}",
                        }, na_rep="N/A"),
                        key="hr_vuln",
                    )
                    st.caption(
                        "Contact allowed, from this pitcher's own Statcast rows. "
                        "HRWindow% Allowed is launch angle 20-40 \u2014 the home-run "
                        "band, not the 8-32 sweet spot. xHR Gap = expected home runs "
                        "allowed minus actual: a POSITIVE gap means he's been giving "
                        "up home-run trajectories that stayed in the park, and that "
                        "luck tends to run out. Park-neutral, so tonight's venue is "
                        "not baked in."
                    )
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
                        f'<div style="padding:var(--lc-space-sm) var(--lc-space-lg); border-radius:var(--lc-radius-md); background:{c}22; '
                        f'border:1px solid {c}66; color:{c}; font-weight:700; font-size:var(--lc-text-body); '
                        f'font-family:\'JetBrains Mono\',monospace;">{pitch_name(pt)} {usage:.0f}%</div>'
                    )
                badges_html += '</div>'
                st.markdown(badges_html, unsafe_allow_html=True)

        table_rows = []
        with card("lineup"):
            st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{opposing_team} Lineup</div><div class="pf-card-subtitle" style="color:{COLOR["text_muted"]};">vs {selected_pitcher_name}</div>', unsafe_allow_html=True)

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
                        # "Batting Order" first and default: when MLB has
                        # posted a real lineup, the natural way to read it
                        # is 1 through 9. Ranking by score buried the
                        # leadoff hitter in the middle of the table and
                        # made the card harder to scan against the actual
                        # lineup card. Every analytic sort is still one
                        # click away.
                        "Sort by", ["Batting Order", "SLAM", "HR Edge", "HR Score",
                                    "Hit Score", "xwOBA", "xSLG", "ISO", "Brl%",
                                    "Brl/PA", "HH%", "EV90", "HRWindow%", "HRIntent",
                                    "HRThreat", "FB95%", "Clears%"],
                        key="lineup_sort_by"
                    )
                with window_col:
                    window_choice = st.selectbox(
                        "Window",
                        [
                            "Season",
                            "Last 25 Games", "Last 15 Games", "Last 10 Games",
                            "Last 5 Games",
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
                    # l25 has always been supported by apply_window and by
                    # every OTHER window control in the app (Bullpen Board,
                    # Player of the Day, WNBA form, the grade window right
                    # above). This one list was the only place missing it.
                    "Last 25 Games": ("l25", "games"),
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
                    # 1 through 9 as MLB posted it. Rows without a batting
                    # order (the unconfirmed-lineup fallback) sort last
                    # rather than jumping to the top, since 0 would
                    # otherwise read as "bats first".
                    "Batting Order": lambda r: -((r.get("battingOrder") or 9999) // 100
                                                 if r.get("battingOrder") else 9999),
                    "SLAM": lambda r: slam_bvp_cache[r["name"]]["final"] or 0.0,
                    "HR Edge": lambda r: _score_num(r.get("edge")),
                    "HR Score": lambda r: _score_num(r["hr_score"]),
                    "Hit Score": lambda r: _score_num(r["hit_score"]),
                    "xwOBA": lambda r: windowed_profile_cache[r["name"]].get("xwOBA") or 0,
                    "xSLG": lambda r: windowed_profile_cache[r["name"]].get("xSLG") or 0,
                    "ISO": lambda r: windowed_profile_cache[r["name"]].get("ISO") or 0,
                    # `or 0`, not a .get default: the key now EXISTS with
                    # a None value when barrels weren't measurable, so a
                    # default never fires and sorted() would raise
                    # TypeError comparing None to float — taking out the
                    # whole lineup table. Same reasoning as Brl/PA below.
                    "Brl%": lambda r: windowed_profile_cache[r["name"]].get("Brl %") or 0,
                    # The new HR axes are sortable too — Brl/PA and
                    # HRWindow% are the two most useful ways to reorder
                    # this board for a home-run read, and neither was
                    # reachable before. `or 0` because these are None
                    # (not 0) for bats we can't measure, and None breaks
                    # the sort.
                    "Brl/PA": lambda r: windowed_profile_cache[r["name"]].get("Brl/PA") or 0,
                    # `or 0` for consistency with every other key here.
                    # HH% is not currently nullable, but a .get default is
                    # the wrong guard for a sort key regardless — it can't
                    # protect against a present-but-None value.
                    "HH%": lambda r: windowed_profile_cache[r["name"]].get("HH %") or 0,
                    "EV90": lambda r: windowed_profile_cache[r["name"]].get("EV90") or 0,
                    "HRWindow%": lambda r: windowed_profile_cache[r["name"]].get("HRWindow %") or 0,
                    "HRIntent": lambda r: windowed_profile_cache[r["name"]].get("HRIntent") or 0,
                    "HRThreat": lambda r: windowed_profile_cache[r["name"]].get("HRThreat") or 0,
                    "FB95%": lambda r: windowed_profile_cache[r["name"]].get("FB95 %") or 0,
                    "Clears%": lambda r: windowed_profile_cache[r["name"]].get("ClearsAnywhere %") or 0,
                }
                filtered = sorted(filtered, key=sort_key_map[sort_choice], reverse=True)

                if not filtered:
                    st.info(f"No batters match that Bats filter for {opposing_team}.")

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
                    # EVERY SWITCH-HITTER ROW SAYS WHAT IT IS.
                    #
                    # A switch hitter produces two or three rows here,
                    # because his two sides are often two different
                    # hitters and blending them hides the split that
                    # decides the matchup. The rows were not labelled
                    # well enough to tell apart:
                    #
                    #   probable posted -> "S->L" primary, "S (R)" split.
                    #     Readable.
                    #   NO probable     -> "S" primary, then "S (L)" and
                    #     "S (R)". Three rows, same name, same batting
                    #     order, different numbers — and the first one
                    #     labelled with a bare "S" that looks like a
                    #     third platoon side.
                    #
                    # The bare row is NOT a side. windowed_profile_cache
                    # builds it with stand=None, so it is every plate
                    # appearance from BOTH sides combined. Labelling it
                    # "S (L)" would have been a straight lie about which
                    # numbers those are; labelling it "S" left the reader
                    # to guess. It now says so: "S (both)".
                    #
                    # _bats_column colours any label naming a side, and
                    # "both" names none, so the combined row stays neutral
                    # while its two split siblings take platoon colours —
                    # which is the right visual hierarchy anyway.
                    if _is_switch:
                        _primary_label = (f'S\u2192{_tonight}' if _tonight
                                          else "S (both)")
                    else:
                        _primary_label = r["bats"]
                    table_rows.append(_stat_row(
                        r["name"], _primary_label, profile,
                        matchup=tier, slam=slam,
                        hr_edge=r.get("edge"), hr_score=r["hr_score"], hit_score=r["hit_score"],
                        edge_cell=edge_tag(tag_label, tag_tier),
                        edge_label=tag_label, edge_tier=tag_tier,
                        confidence=f"{conf_label} \u2014 n={sample}",
                        batting_order=r.get("battingOrder"),
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
                                batting_order=r.get("battingOrder"),
                            ))

                display_df = pd.DataFrame(table_rows) if table_rows else None
                if display_df is not None:
                    edge_col = display_df.pop("Edge")

                    # COLUMN GROUPS — 27 columns is unusable on a phone.
                    #
                    # Not a mobile-only hack: Streamlit can't detect screen
                    # size server-side, and a CSS approach can't work here
                    # because st.dataframe draws on a canvas. So it's a
                    # user choice that works the same everywhere, and it
                    # DEFAULTS TO ALL — desktop behaviour is byte-identical
                    # unless someone picks a narrower set. The choice
                    # persists in session state, so picking "Power" once on
                    # a phone keeps it across reruns.
                    #
                    # Player/Bats/Ord lead every group: they're what tells
                    # you whose row you're reading, and losing that while
                    # scrolling sideways was the other half of the problem.
                    _ident = ["Player", "Bats", "Ord"]
                    _groups = {
                        "All": None,
                        # CAPPED AT 14 (see tests/test_column_groups) and it
                        # was already at 14, so the two new columns had to
                        # displace two. What went, and why:
                        #
                        #   MaxEV     the comment on its own row calls it
                        #             interest only — it's a sample of one.
                        #             EV90 is the scored power ceiling and
                        #             stays.
                        #   PullBrl%  overlaps PullAir% and Brl% almost
                        #             entirely, and both of those stay.
                        #
                        # Neither is gone: "All" still shows every column,
                        # and both remain sortable. This group is the
                        # narrow phone view, not the full table.
                        "Power": _ident + ["HR Edge", "HR Score", "HRThreat",
                                           "Brl%", "Brl/PA", "Clears%",
                                           "EV90", "HRWindow%", "HRIntent",
                                           "PullAir%", "Blast%"],
                        "Contact": _ident + ["Hit Score", "SLAM", "BA", "xwOBA", "xSLG",
                                             "ISO", "HH%", "LD%", "FB%", "GB%",
                                             "SweetSpot%"],
                        "Quick": _ident + ["HR Edge", "HR Score", "Hit Score", "SLAM",
                                           "xwOBA", "Brl/PA", "HH%"],
                    }
                    _grp = st.segmented_control(
                        "Columns", list(_groups),
                        default="All", key="lineup_col_group",
                        label_visibility="collapsed",
                    ) or "All"

                    _table_df = display_df.drop(
                        columns=["Matchup", "Confidence", "EdgeLabel", "EdgeTier"])
                    _keep = _groups.get(_grp)
                    if _keep:
                        # Intersect rather than reindex: a column can be
                        # absent (no Statcast rows for anyone in the
                        # lineup), and asking for a missing one would
                        # produce an all-NaN column that looks like real
                        # missing data instead of a column we never had.
                        _table_df = _table_df[[c for c in _keep if c in _table_df.columns]]

                    # (The st.column_config pinned-Player block that used to
                    # sit here went with the st.dataframe call below —
                    # render_html_table pins the first column in CSS.)
                    styled = style_stat_table(
                        _table_df,
                        favor_high=["SLAM", "BA", "xwOBA", "xSLG", "ISO", "HR/FB", "Brl%", "Brl/PA", "HH%", "EV90", "MaxEV", "LD%", "FB%", "SweetSpot%", "HRWindow%", "PullAir%", "PullBrl%", "Blast%", "HRIntent", "HRThreat", "FB95%", "Clears%"],
                        # HR Edge / HR Score / Hit Score are deliberately
                        # NOT in favor_high: score_bar already encodes each
                        # one as a filled bar, and a gradient cell behind
                        # the bar is a SECOND encoding of the same number.
                        # The two colours fought each other and the result
                        # read as mud — neither the bar length nor the cell
                        # shade was legible.
                        favor_low=["GB%", "SwStr%"],
                        gradient=True,
                    )
                    # EVERY numeric column needs an entry here. Anything
                    # missing falls through to style_stat_table's global
                    # .format(precision=2), which is why the new columns
                    # first rendered as 104.00 and 91.70 while their
                    # neighbours showed 104.0 and 91.7.
                    styled = styled.format({
                        "Ord": "{:.0f}",
                        "SLAM": "{:.1f}", "BA": "{:.3f}", "xwOBA": "{:.3f}", "xSLG": "{:.3f}",
                        "ISO": "{:.3f}", "HR/FB": "{:.1f}",
                        "Brl%": "{:.1f}", "HH%": "{:.1f}", "LD%": "{:.1f}",
                        "FB%": "{:.1f}", "GB%": "{:.1f}", "SweetSpot%": "{:.1f}", "PullAir%": "{:.1f}",
                        "PullBrl%": "{:.1f}", "Blast%": "{:.1f}", "SwStr%": "{:.1f}",
                        # Rates: one decimal, matching Brl%/HH% beside them.
                        "Brl/PA": "{:.1f}", "HRWindow%": "{:.1f}",
                        # Exit velocities read as mph — one decimal is how
                        # Statcast publishes them.
                        "EV90": "{:.1f}", "MaxEV": "{:.1f}",
                        # 0-100 composite, formatted like HR/Hit Score.
                        "HRIntent": "{:.0f}", "HRThreat": "{:.0f}",
                        "FB95%": "{:.1f}",
                        # Two decimals, not one. League average clears-anywhere
                        # contact is a fraction of a percent, so {:.1f} would
                        # print 0.0 for most of the league and throw away the
                        # only resolution this column has.
                        "Clears%": "{:.2f}",
                        # Inline filled bars, same three columns that used
                        # st.column_config.ProgressColumn before this table
                        # moved off st.dataframe. score_bar returns markup
                        # and pandas doesn't escape formatter output, so
                        # the bar renders where the number used to.
                        # Handedness as a chip, not a bare letter. Most of
                        # the platoon logic in this app turns on this
                        # column, and an L or R sitting in a dense row of
                        # numbers reads as just another character.
                        "Bats": bats_chip(),
                        "HR Edge": score_bar("gold"),
                        "HR Score": score_bar("stat_high"),
                        "Hit Score": score_bar("warn"),
                    }, na_rep="N/A")
                    # LAST TABLE OFF st.dataframe.
                    #
                    # This one held out longest because its HR Edge / HR
                    # Score / Hit Score columns used
                    # st.column_config.ProgressColumn for inline bars. But
                    # Streamlit's grid has drag-to-reorder built in with no
                    # way to switch it off (streamlit#11222), so on a phone
                    # a scroll gesture scattered the columns of the single
                    # table people spend the most time in.
                    #
                    # The bars did NOT have to be sacrificed: score_bar()
                    # in table_style renders the same filled bar as markup
                    # in the cell, so this is a straight win over the
                    # widget rather than a trade.
                    #
                    # The first column stays put either way:
                    # render_html_table makes it sticky in CSS, which works
                    # on touch where the grid's pinning did not.
                    # Colour key with the table. The lineup has both tier-
                    # coloured cells AND tier-coloured bars, so without it a
                    # reader has to infer that gold means "good" — and on
                    # the pitcher tables above, colour reads the other way.
                    tier_legend(favor_note="Higher is better for the BATTER \u2014 "
                                           "colour is his grade in that column.")
                    render_html_table(styled, key="gc_lineup")
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
                                    f'margin-top:var(--lc-space-lg);">Weak spot vs this lineup</div>'
                                    f'<div class="pf-card-subtitle">{selected_pitcher_name}\u2019s xSLG '
                                    f'allowed by batting slot, mapped to tonight\u2019s hitters. '
                                    f'Green = a real, well-sampled slot where he gets hit and a '
                                    f'live bat is sitting. Slots below the sample floor show \u2014.'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                                _hdr = (
                                    f'<tr style="font-size:var(--lc-text-tiny); color:{COLOR["text"]}; opacity:0.55;">'
                                    f'<td style="padding:var(--lc-space-xs) var(--lc-space-md);">#</td>'
                                    f'<td style="padding:var(--lc-space-xs) var(--lc-space-md);">Hitter</td>'
                                    f'<td style="padding:var(--lc-space-xs) var(--lc-space-md);">B</td>'
                                    f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); text-align:right;">xSLG vs slot</td>'
                                    f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); text-align:right;">n</td></tr>'
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
                                        f'<tr style="{_bg} font-size:var(--lc-text-caption);">'
                                        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); color:{COLOR["text"]}; opacity:0.6;">{_r["slot"]}</td>'
                                        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); color:{COLOR["text"]}; font-weight:600;">{_r["name"]}'
                                        + (' \U0001F3AF' if _r["weak"] else '') + '</td>'
                                        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); color:{COLOR["text"]}; opacity:0.6;">{_r["bats"]}</td>'
                                        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); text-align:right;">{_xcell}</td>'
                                        f'<td style="padding:var(--lc-space-xs) var(--lc-space-md); text-align:right; color:{COLOR["text"]}; opacity:0.45; font-size:var(--lc-text-tiny);">{_r["bbe"]}</td>'
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
                        # DELIBERATELY NOT LOGGING hr_edge HERE ANY MORE.
                        #
                        # This used to write the top 5 bats from THIS ONE
                        # GAME to the "hr_edge" calibration board every
                        # time a game card rendered. calibration_picks.py
                        # now writes the SLATE-WIDE top 5 to that same
                        # board key from CI.
                        #
                        # Two writers, one key, same date. Opening a game
                        # card overwrote the real slate board with one
                        # game's bats — and neither is graded early in
                        # the day, so which one survived the merge was
                        # effectively arbitrary. The hr_edge record would
                        # have been sometimes the model's actual board and
                        # sometimes whichever matchup you happened to
                        # click, with no way to tell them apart after the
                        # fact. That silently invalidates the exact
                        # measurement the slate board was built to make
                        # honest.
                        #
                        # engines/hr_edge_board.py owns this board now.
                        # Browsing the site can no longer alter the record.

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
                                        f'margin-top:var(--lc-space-md);">Why these bats</div>',
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
                            f'<div class="pf-card-title" style="color:{COLOR["text"]}; margin-top:var(--lc-space-lg);">Batter Trend</div>'
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
                                    f'<div style="font-size:var(--lc-text-tiny); opacity:0.65; '
                                    f'margin-top:var(--lc-space-hair);">{_extra_txt}</div>'
                                ) if _extra else ""
                                st.markdown(
                                    f'<div style="font-family:\'JetBrains Mono\',monospace; '
                                    f'font-size:var(--lc-text-small); color:{COLOR["text"]}; margin:var(--lc-space-sm) var(--lc-space-none);">'
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
                                "Window", [str(_yr), str(_yr - 1), "H2H", "L25", "L15", "L10", "L5"],
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
                    render_html_table(
                        style_stat_table(matchup_df, favor_high=["xwOBA", "ISO", "Brl%", "HH%", "Zone Fit"], favor_low=["Whiff%"], gradient=True).format(
                            {"xwOBA": "{:.3f}", "ISO": "{:.3f}", "Brl%": "{:.1f}", "HH%": "{:.1f}", "Whiff%": "{:.1f}"}, na_rep="\u2014"), key="gc_1809")
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
                        render_html_table(
                            style_stat_table(
                                fam_df, favor_high=["BA", "xwOBA", "xSLG", "ISO", "Brl%", "HH%"],
                                favor_low=["Whiff%"], gradient=True,
                            ).format(
                                {"BA": "{:.3f}", "xwOBA": "{:.3f}", "xSLG": "{:.3f}", "ISO": "{:.3f}",
                                 "Brl%": "{:.1f}", "HH%": "{:.1f}", "Whiff%": "{:.1f}"},
                                na_rep="\u2014",
                            ), key="gc_1862")
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
                        f'<div style="margin:var(--lc-space-md) var(--lc-space-none) var(--lc-space-sm) var(--lc-space-none);">{edge_tag(f"{tier_label} ({len(tier_rows)})", tier_key)}</div>',
                        unsafe_allow_html=True,
                    )
                    tier_df = pd.DataFrame([
                        {"Player": r["Player"], "Bats": r["Bats"], "Detail": r["EdgeLabel"], "Confidence": r["Confidence"]}
                        for r in tier_rows
                    ])
                    render_html_table(plain_dark_table(tier_df), key="gc_1903")

        tab_arsenal, tab_scout = st.tabs(["Pitch Arsenal", "\U0001F52D Scout Report"])
        with tab_arsenal:
            with card("pitch_arsenal_tab"):
                st.markdown(
                    f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Pitch Arsenal</div>'
                    f'<div class="pf-card-subtitle" style="color:{COLOR["text_muted"]};">What each pitch actually does, not just how often it\'s thrown</div>',
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
                            f'<div style="margin-bottom:var(--lc-space-lg);">'
                            f'<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:var(--lc-space-xs);">'
                            f'<span style="font-weight:700; color:{c}; font-size:var(--lc-text-body-lg);">{pitch_name(pt)}</span>'
                            f'<span style="font-family:\'JetBrains Mono\',monospace; color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">n={d["n"]}</span>'
                            f'</div>'
                            f'<div style="height:8px; width:100%; background:{COLOR["surface_raised"]}; border-radius:var(--lc-radius-sm); margin-bottom:var(--lc-space-sm);">'
                            f'<div style="height:8px; width:{min(d["usage"],100)}%; background:{c}; border-radius:var(--lc-radius-sm);"></div>'
                            f'</div>'
                            f'<div style="display:flex; gap:18px; font-size:var(--lc-text-small); font-family:\'JetBrains Mono\',monospace;">'
                            f'<span style="color:{COLOR["text_muted"]};">Usage <b style="color:{COLOR["text"]};">{d["usage"]:.1f}%</b></span>'
                            f'<span style="color:{COLOR["text_muted"]};">Whiff <b style="color:{COLOR["stat_high"] if (d["whiff"] or 0) >= 25 else COLOR["text"]};">{whiff_display}</b></span>'
                            f'<span style="color:{COLOR["text_muted"]};">Hard-Hit Allowed <b style="color:{COLOR["error"] if (d["hh_allowed"] or 0) >= 40 else COLOR["text"]};">{hh_display}</b></span>'
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
                            render_html_table(plain_dark_table(hitters_df), key="gc_1985")
                        else:
                            st.caption("No position players found.")

                    with card("scout_pitchers"):
                        st.markdown('<div class="pf-card-title">Pitchers</div>', unsafe_allow_html=True)
                        if pitchers:
                            pitchers_df = pd.DataFrame(pitchers)[["name", "position", "bats", "throws"]]
                            pitchers_df.columns = ["Name", "Pos", "Bats", "Throws"]
                            render_html_table(plain_dark_table(pitchers_df), key="gc_1994")
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
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["text"]};">Matchup Summary</div>', unsafe_allow_html=True)
                top_arsenal = ", ".join(pitch_name(k) for k, v in sorted(arsenal.items(), key=lambda x: -x[1])[:2]) if arsenal else "an unclear arsenal"
                top_hr_names = ", ".join(r["name"] for r in sorted(ranked, key=lambda x: _score_sort_key(x, "hr_score"))[:2]) if ranked else "the lineup"
                st.markdown(
                    f'<span style="color:{COLOR["text_muted"]};">'
                    f"{selected_pitcher_name} relies heavily on {top_arsenal}. "
                    f"{top_hr_names} rate highest on HR Score against this arsenal. "
                    f"These are this app's own composite scores, not a certified prediction."
                    f'</span>',
                    unsafe_allow_html=True,
                )
        with s2:
            with card("key_insights"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["text"]};">Key Insights</div>', unsafe_allow_html=True)
                above_avg_hr = sum(1 for r in ranked if r["hr_score"] is not None and r["hr_score"] >= 60)
                high_k_risk = sum(1 for r in ranked if r["k_score"] is not None and r["k_score"] >= 70)
                st.markdown(f'<span style="color:{COLOR["text_muted"]};">\u2713 {above_avg_hr} batters with above-average HR Score</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="color:{COLOR["text_muted"]};">\u2713 {high_k_risk} batters carrying elevated strikeout risk</span>', unsafe_allow_html=True)
                if park["verified"]:
                    st.markdown(f'<span style="color:{COLOR["text_muted"]};">\u2713 {park["venue"]} park factor: {park["park_factor"]}</span>', unsafe_allow_html=True)
        with s3:
            with card("legend"):
                st.markdown(f'<div class="pf-card-title" style="color:{COLOR["text"]};">Legend</div>', unsafe_allow_html=True)
                st.markdown(
                    edge_tag("Strong Edge", "strong") + " " + edge_tag("Good Pick", "good") + "<br><br>"
                    + edge_tag("Neutral", "neutral") + " " + edge_tag("Risk / Avoid", "risk"),
                    unsafe_allow_html=True,
                )

    footer()
