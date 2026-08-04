"""
Weather Board — every game on today's slate, one weather view.

Per game: matchup (official logos), venue + first pitch, condition,
game-time temperature, wind, and a precipitation flag with honest
tiers:
    >= 50%  ->  PPD RISK (red)
    25-49%  ->  MONITOR (gold)
    < 25%   ->  CLEAR-ish (teal)
Roofed / retractable parks show a ROOF badge instead — rain there
closes a roof, it doesn't postpone a game, and this board won't wave
a false flag.

Wind: MLB's official posted park weather wins the moment it exists
(it's field-relative — "Out To CF" — which a compass forecast can't
honestly claim). Until then, the NWS game-time forecast fills in,
marked as a forecast. Sources on the page.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from styles.kc_theme import inject_kc_theme, footer, COLOR
from engines.weather_engine import get_todays_games_with_weather
from engines.park_weather import (get_park_forecast, is_roofed,
                                  prefetch_forecasts)
from engines.team_logos import logo_for
from engines.weather_icons import weather_icon, wind_arrow, temp_icon
from engines.team_abbreviations import team_abbr
from engines.live_sync import sync_latest_button

EASTERN = ZoneInfo("America/New_York")

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-sm);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">WEATHER</span>'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">BOARD</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_weather")

games, games_error = get_todays_games_with_weather()
if games_error:
    st.warning(games_error)
if not games:
    st.info("No MLB games on today's schedule.")
    footer()
    st.stop()


def _small(svg: str) -> str:
    """The shared icons are drawn at 30px for the Game Card's weather
    strip; the Weather Board packs one row per game, so they render at
    20px here. Scaling the SVG attributes keeps them crisp instead of
    letting the browser resize a bitmap."""
    return svg.replace('width="30" height="30"', 'width="20" height="20"')


def _logo_img(team):
    u = logo_for(team)
    if u:
        return f'<img src="{u}" width="22" height="22" style="vertical-align:middle;">'
    return f'<b style="font-size:var(--lc-text-caption);">{team_abbr(team or "?")}</b>'


def _drop_icon(col: str, filled: bool = True) -> str:
    """A raindrop, drawn — sized to sit inline with the badge text."""
    return (
        '<svg width="11" height="11" viewBox="0 0 24 24" style="vertical-align:-1px;" '
        'fill="none">'
        f'<path d="M12 3.5c3.6 4.4 6 7.4 6 10a6 6 0 0 1-12 0c0-2.6 2.4-5.6 6-10z" '
        f'fill="{col}" opacity="{"0.9" if filled else "0.25"}" stroke="{col}" '
        'stroke-width="1.3"/></svg>'
    )


def _roof_icon(col: str) -> str:
    """A covered stadium, drawn."""
    return (
        '<svg width="12" height="12" viewBox="0 0 24 24" style="vertical-align:-1px;" '
        'fill="none">'
        f'<path d="M3 12a9 9 0 0 1 18 0" stroke="{col}" stroke-width="1.8" '
        'stroke-linecap="round"/>'
        f'<rect x="4" y="12" width="16" height="7" rx="1.5" stroke="{col}" '
        'stroke-width="1.4" opacity="0.75"/></svg>'
    )


def _precip_badge(pct, roofed):
    """Precipitation risk, with a drawn icon instead of an emoji.

    Roofed parks are labelled rather than flagged: rain there closes a
    roof, it does not postpone a game, so a red umbrella would be a
    false alarm.
    """
    if roofed:
        return (f'<span style="padding:var(--lc-space-hair) var(--lc-space-md); border-radius:var(--lc-radius-sm); font-size:var(--lc-text-tiny); '
                f'font-weight:700; background:{COLOR["text"]}1A; color:{COLOR["text"]};">'
                f'{_roof_icon(COLOR["text"])} ROOF \u2014 weather protected</span>')
    if pct is None:
        return ""
    if pct >= 50:
        col, label = COLOR["error"], f"PPD RISK \u00b7 {pct}%"
        icon = _drop_icon(col, True)
    elif pct >= 25:
        col, label = COLOR["warn"], f"MONITOR \u00b7 {pct}%"
        icon = _drop_icon(col, True)
    else:
        col, label = COLOR["stat_high"], f"{pct}% precip"
        icon = _drop_icon(col, False)
    return (f'<span style="padding:var(--lc-space-hair) var(--lc-space-md); border-radius:var(--lc-radius-sm); font-size:var(--lc-text-tiny); '
            f'font-weight:700; background:{col}22; color:{col};">{icon} {label}</span>')


def _hr_weather(temp_val, wind_str, roofed, home_team=None):
    """(label, color, reasons) — HR-friendliness of the AIR, from two
    real inputs with documented tiers:
      TEMP (any source):  >=85F +2 · 78-84 +1 · 60-69 -1 · <60 -2
      WIND (MLB official field-relative ONLY — a compass forecast
      can't honestly claim "out to CF"):
        Out >=12mph +3 · Out 8-11 +2 · Out 5-7 +1
        In  >=12mph -3 · In  8-11 -2 · In  5-7 -1 · cross 0
    Tag: total >=3 HR FRIENDLY · 1-2 Leans HR · -1..-2 Leans under
    · <=-3 SUPPRESSIVE. Roofed parks: CONTROLLED (still air, no
    weather help either way). Reasons always shown — the tag is an
    honest sum, not a vibe."""
    if roofed:
        return "CONTROLLED", COLOR["text"], ["roof/dome — still air"]
    score, reasons = 0, []
    if temp_val is not None:
        try:
            t = int(str(temp_val).replace("*", ""))
            if t >= 85:
                score += 2; reasons.append(f"{t}°F hot (+2)")
            elif t >= 78:
                score += 1; reasons.append(f"{t}°F warm (+1)")
            elif t < 60:
                score -= 2; reasons.append(f"{t}°F cold (-2)")
            elif t < 70:
                score -= 1; reasons.append(f"{t}°F cool (-1)")
            else:
                reasons.append(f"{t}°F neutral")
        except Exception:
            pass
    w = (wind_str or "").lower()
    import re as _re
    m = _re.search(r"(\d+)\s*mph", w)
    mph = int(m.group(1)) if m else 0
    if "out to" in w and mph >= 5:
        pts = 3 if mph >= 12 else (2 if mph >= 8 else 1)
        score += pts; reasons.append(f"wind out {mph}mph (+{pts})")
    elif "in from" in w and mph >= 5:
        pts = 3 if mph >= 12 else (2 if mph >= 8 else 1)
        score -= pts; reasons.append(f"wind in {mph}mph (-{pts})")
    elif w and ("l to r" in w or "r to l" in w):
        reasons.append("crosswind (0)")
    else:
        # COMPASS FORECAST — now resolvable.
        #
        # This branch used to say "wind pending official" and score zero,
        # on the stated grounds that a compass reading can't be mapped to
        # the field without knowing the park's orientation. That was true
        # when it was written. It isn't any more: engines/wind_engine
        # carries the real home-plate-to-centre-field bearing for 29
        # parks, so "SW 12 mph" at Wrigley resolves to blowing out and
        # the same wind at Comerica to blowing in.
        #
        # Leaving it unresolved would also put this page in direct
        # disagreement with HR Edge, which already applies that wind —
        # the Weather Board would call it "pending" while the Game Card
        # was scoring it.
        #
        # Scored on the same tiers as the official string, and labelled
        # "forecast" so the reader knows it came from a compass reading
        # rather than MLB's field-relative post.
        _resolved = False
        if home_team:
            try:
                from engines.wind_engine import wind_hr_adj
                adj, note = wind_hr_adj(home_team, wind_str, roof_closed=roofed)
            except Exception:
                adj, note = 0, None
            if note and mph >= 5:
                pts = 3 if mph >= 12 else (2 if mph >= 8 else 1)
                if adj > 0:
                    score += pts
                    reasons.append(f"wind out {mph}mph, forecast (+{pts})")
                    _resolved = True
                elif adj < 0:
                    score -= pts
                    reasons.append(f"wind in {mph}mph, forecast (-{pts})")
                    _resolved = True
            elif adj == 0 and note is None and wind_str:
                reasons.append("crosswind, forecast (0)")
                _resolved = True
        if not _resolved and (not w or "not posted" in w):
            reasons.append("wind pending official")
    if score >= 3:
        return "🔥 HR FRIENDLY", COLOR["gold"], reasons
    if score >= 1:
        return "Leans HR", COLOR["stat_high"], reasons
    if score <= -3:
        return "❄️ SUPPRESSIVE", COLOR["error"], reasons
    if score <= -1:
        return "Leans under", COLOR["warn"], reasons
    return "Neutral", COLOR["text"], reasons


with st.spinner("Pulling game-time forecasts for every park\u2026 (30-min cache after the first load)"):
    # Every open-air park's forecast, fetched concurrently before the
    # serial loop below. Roofed parks are skipped here for the same
    # reason they are skipped there — no forecast is requested for them
    # at all.
    prefetch_forecasts(g.get("venue") for g in games
                       if g.get("venue") and not is_roofed(g["venue"]))

    rows_html = []
    for g in games:
        venue = g.get("venue") or ""
        roofed = is_roofed(venue)
        fc = None if roofed else get_park_forecast(venue, g.get("game_time"))

        try:
            t_str = datetime.fromisoformat(
                g["game_time"].replace("Z", "+00:00")
            ).astimezone(EASTERN).strftime("%-I:%M %p ET") if g.get("game_time") else "TBD"
        except Exception:
            t_str = "TBD"

        # MLB official first, forecast (marked *) second, honesty third
        if g.get("weather_temp"):
            temp_txt = f'{g["weather_temp"]}\u00b0F'
        elif fc and fc.get("temp") is not None:
            temp_txt = f'{fc["temp"]}\u00b0F*'
        else:
            temp_txt = "\u2014"
        # The arrow can only claim a field direction from MLB's official
        # field-relative string; a compass forecast ("SW 12 mph") gets a
        # neutral swirl, which wind_arrow() handles.
        _wind_raw = g.get("weather_wind") or (fc.get("wind") if fc else None)
        if g.get("weather_wind"):
            wind_txt = f'{g["weather_wind"]} <span style="opacity:0.6; font-size:var(--lc-text-micro);">(official)</span>'
        elif fc and fc.get("wind"):
            wind_txt = f'{fc["wind"]}*'
        else:
            wind_txt = "\u2014"
        cond_txt = g.get("weather_condition") or (fc and fc.get("short")) or ("Roof/Dome" if roofed else "\u2014")
        precip = fc.get("precip") if fc else None

        _raw_temp = g.get("weather_temp") or (fc.get("temp") if fc else None)
        # Park abbreviation so a compass wind can be resolved against
        # this stadium's real orientation — same key wind_engine and the
        # HR park factors use, so all three agree.
        _hr_label, _hr_col, _hr_why = _hr_weather(
            _raw_temp, g.get("weather_wind"), roofed,
            home_team=team_abbr(g.get("home") or ""))
        _why_txt = " \u00b7 ".join(_hr_why)

        rows_html.append(
            f'<div style="display:flex; align-items:center; gap:12px; padding:var(--lc-space-md) var(--lc-space-lg); '
            f'border:1px solid {COLOR["text"]}1E; border-left:4px solid {_hr_col}; '
            f'background:{_hr_col}0A; border-radius:var(--lc-radius-lg); margin-bottom:var(--lc-space-sm);">'
            f'<div style="min-width:110px;">{_logo_img(g.get("away"))}'
            f'<span style="margin:var(--lc-space-none) var(--lc-space-xs); opacity:0.5; font-size:var(--lc-text-tiny);">@</span>'
            f'{_logo_img(g.get("home"))}</div>'
            f'<div style="flex:1.4; font-size:var(--lc-text-caption); color:{COLOR["text"]}; opacity:0.8;">{venue}<br>'
            f'<span style="color:{COLOR["text"]}; font-weight:600;">{t_str}</span></div>'
            f'<div style="flex:1; font-size:var(--lc-text-caption); color:{COLOR["text"]}; '
            f'display:flex; align-items:center; gap:6px;">'
            f'<span style="flex-shrink:0;">{_small(weather_icon(cond_txt))}</span>'
            f'<span>{cond_txt}</span></div>'
            f'<div style="flex:0.7; font-size:var(--lc-text-small); font-weight:700; '
            f'color:{COLOR["stat_high"]}; display:flex; align-items:center; gap:5px;">'
            f'<span style="flex-shrink:0;">{_small(temp_icon(temp_txt))}</span>'
            f'<span>{temp_txt}</span></div>'
            f'<div style="flex:1.3; font-size:var(--lc-text-caption); color:{COLOR["text"]}; '
            f'display:flex; align-items:center; gap:6px;">'
            f'<span style="flex-shrink:0;">{_small(wind_arrow(_wind_raw))}</span>'
            f'<span>{wind_txt}</span></div>'
            f'<div style="flex:1.15; text-align:center;">'
            f'<span style="padding:var(--lc-space-hair) var(--lc-space-md); border-radius:var(--lc-radius-sm); font-size:var(--lc-text-tiny); font-weight:800; '
            f'background:{_hr_col}22; color:{_hr_col};">{_hr_label}</span>'
            f'<div style="font-size:var(--lc-text-micro); color:{COLOR["text"]}; opacity:0.55; margin-top:var(--lc-space-hair);">'
            + _why_txt + '</div></div>'
            f'<div style="flex:1.1; text-align:right;">{_precip_badge(precip, roofed)}</div>'
            f'</div>'
        )

st.markdown("".join(rows_html), unsafe_allow_html=True)

st.caption(
    "* = game-time forecast from the National Weather Service (public-domain US government data) "
    "\u2014 this app's own weather desk, matched to each park and first pitch, refreshed every 30 "
    "minutes. MLB's official posted park weather (field-relative wind) takes over automatically per "
    "game once it exists. PPD RISK \u2265 50% precip chance \u00b7 MONITOR 25\u201349% \u00b7 roofed "
    "parks are labeled instead of flagged \u2014 rain closes their roof, it doesn't postpone their "
    "game. Rogers Centre sits outside NWS coverage and shows MLB data only. HR-friendliness is a "
    "documented sum of temperature tiers plus official field-relative wind (exact points shown under "
    "each tag \u2014 wind joins the score only once MLB posts it); gold rows are the games to attack "
    "for power, red rows the ones to respect the air in."
)

footer()
