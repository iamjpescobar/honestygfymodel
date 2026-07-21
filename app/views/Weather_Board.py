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
from engines.park_weather import get_park_forecast, is_roofed
from engines.team_logos import logo_for
from engines.team_abbreviations import team_abbr
from engines.live_sync import sync_latest_button

EASTERN = ZoneInfo("America/New_York")

inject_kc_theme()

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">WEATHER</span>'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">BOARD</span>'
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


def _logo_img(team):
    u = logo_for(team)
    if u:
        return f'<img src="{u}" width="22" height="22" style="vertical-align:middle;">'
    return f'<b style="font-size:11px;">{team_abbr(team or "?")}</b>'


def _precip_badge(pct, roofed):
    if roofed:
        return (f'<span style="padding:2px 8px; border-radius:4px; font-size:10.5px; font-weight:700; '
                f'background:{COLOR["text"]}1A; color:{COLOR["text"]};">\U0001F3DF\uFE0F ROOF \u2014 weather protected</span>')
    if pct is None:
        return ""
    if pct >= 50:
        col, label = COLOR["error"], f"\u2614 PPD RISK \u00b7 {pct}%"
    elif pct >= 25:
        col, label = COLOR["warn"], f"\U0001F326\uFE0F MONITOR \u00b7 {pct}%"
    else:
        col, label = COLOR["stat_high"], f"\u2713 {pct}% precip"
    return (f'<span style="padding:2px 8px; border-radius:4px; font-size:10.5px; font-weight:700; '
            f'background:{col}22; color:{col};">{label}</span>')


def _hr_weather(temp_val, wind_str, roofed):
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
    elif not w or "not posted" in w:
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
        if g.get("weather_wind"):
            wind_txt = f'{g["weather_wind"]} <span style="opacity:0.6; font-size:9px;">(official)</span>'
        elif fc and fc.get("wind"):
            wind_txt = f'{fc["wind"]}*'
        else:
            wind_txt = "\u2014"
        cond_txt = g.get("weather_condition") or (fc and fc.get("short")) or ("Roof/Dome" if roofed else "\u2014")
        precip = fc.get("precip") if fc else None

        _raw_temp = g.get("weather_temp") or (fc.get("temp") if fc else None)
        _hr_label, _hr_col, _hr_why = _hr_weather(_raw_temp, g.get("weather_wind"), roofed)

        rows_html.append(
            f'<div style="display:flex; align-items:center; gap:12px; padding:9px 12px; '
            f'border:1px solid {COLOR["text"]}1E; border-left:4px solid {_hr_col}; '
            f'background:{_hr_col}0A; border-radius:8px; margin-bottom:7px;">'
            f'<div style="min-width:110px;">{_logo_img(g.get("away"))}'
            f'<span style="margin:0 5px; opacity:0.5; font-size:10px;">@</span>'
            f'{_logo_img(g.get("home"))}</div>'
            f'<div style="flex:1.4; font-size:11px; color:{COLOR["text"]}; opacity:0.8;">{venue}<br>'
            f'<span style="color:{COLOR["gold"]}; font-weight:600;">{t_str}</span></div>'
            f'<div style="flex:1; font-size:11.5px; color:{COLOR["text"]};">{cond_txt}</div>'
            f'<div style="flex:0.6; font-size:12px; font-weight:700; color:{COLOR["stat_high"]};">{temp_txt}</div>'
            f'<div style="flex:1.2; font-size:11.5px; color:{COLOR["text"]};">{wind_txt}</div>'
            f'<div style="flex:1.15; text-align:center;">'
            f'<span style="padding:2px 8px; border-radius:4px; font-size:10.5px; font-weight:800; '
            f'background:{_hr_col}22; color:{_hr_col};">{_hr_label}</span>'
            f'<div style="font-size:8.5px; color:{COLOR["text"]}; opacity:0.55; margin-top:2px;">'
            f'{" \u00b7 ".join(_hr_why)}</div></div>'
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
