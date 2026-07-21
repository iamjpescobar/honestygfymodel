"""
Park weather — this app's own in-house weather desk.

Source: the National Weather Service API (api.weather.gov) — US
government data, PUBLIC DOMAIN, free for commercial use, no API key.
That's the whole reason this exists: republishing someone else's
weather breakdowns (however freely viewable) on a paid site isn't
something this app does; building the same capability from
public-domain government forecasts is.

How it fills the Game Card: MLB's own posted park weather remains the
source of truth the moment it exists (it includes field-relative wind
like "Out To CF", which a compass forecast can't know). Before MLB
posts — i.e., most of the day — the card shows the REAL game-time
NWS forecast for that ballpark instead of "Not posted yet", clearly
marked as a forecast. Toronto (Rogers Centre) sits outside NWS
coverage and simply keeps the honest empty state until MLB posts.

Coordinates are well-established public facts per park; forecasts are
matched to the scheduled first pitch and cached 30 minutes.
"""
import json
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

_UA = {"User-Agent": "loscappers.site park weather (admin@loscappers.site)"}

# Ballpark coordinates (public facts). Multiple aliases where venues
# have been renamed or teams are in temporary homes.
PARK_COORDS = {
    "Angel Stadium": (33.8003, -117.8827),
    "Chase Field": (33.4455, -112.0667),
    "Truist Park": (33.8908, -84.4678),
    "Oriole Park at Camden Yards": (39.2839, -76.6217),
    "Camden Yards": (39.2839, -76.6217),
    "Fenway Park": (42.3467, -71.0972),
    "Wrigley Field": (41.9484, -87.6553),
    "Rate Field": (41.8299, -87.6338),
    "Guaranteed Rate Field": (41.8299, -87.6338),
    "Great American Ball Park": (39.0975, -84.5066),
    "Progressive Field": (41.4962, -81.6852),
    "Coors Field": (39.7559, -104.9942),
    "Comerica Park": (42.3390, -83.0485),
    "Daikin Park": (29.7573, -95.3555),
    "Minute Maid Park": (29.7573, -95.3555),
    "Kauffman Stadium": (39.0517, -94.4803),
    "Dodger Stadium": (34.0739, -118.2400),
    "loanDepot park": (25.7781, -80.2196),
    "American Family Field": (43.0280, -87.9712),
    "Target Field": (44.9817, -93.2776),
    "Citi Field": (40.7571, -73.8458),
    "Yankee Stadium": (40.8296, -73.9262),
    "Sutter Health Park": (38.5806, -121.5133),
    "Citizens Bank Park": (39.9061, -75.1665),
    "PNC Park": (40.4469, -80.0057),
    "Petco Park": (32.7076, -117.1570),
    "Oracle Park": (37.7786, -122.3893),
    "T-Mobile Park": (47.5914, -122.3325),
    "Busch Stadium": (38.6226, -90.1928),
    "Tropicana Field": (27.7683, -82.6534),
    "George M. Steinbrenner Field": (27.9803, -82.5064),
    "Globe Life Field": (32.7473, -97.0842),
    "Nationals Park": (38.8730, -77.0074),
    # Rogers Centre intentionally listed so lookups resolve, but NWS
    # doesn't cover Canada — the fetch returns None and the card keeps
    # its honest empty state until MLB posts.
    "Rogers Centre": (43.6414, -79.3894),
}


# Roofed / retractable-roof parks (public facts): rain here means the
# roof closes, not a postponement risk — the Weather Board says so
# instead of waving a false PPD flag.
ROOF_PARKS = {
    "Tropicana Field", "Rogers Centre", "Chase Field", "Daikin Park",
    "Minute Maid Park", "American Family Field", "T-Mobile Park",
    "loanDepot park", "Globe Life Field",
}


def is_roofed(venue: str) -> bool:
    if not venue:
        return False
    return any(name.lower() in venue.lower() for name in ROOF_PARKS)


def _coords_for(venue: str):
    if not venue:
        return None
    if venue in PARK_COORDS:
        return PARK_COORDS[venue]
    # Light alias tolerance for prefixes/suffixes ("Wrigley Field
    # presented by ..."): match on a known name contained in the venue.
    for name, ll in PARK_COORDS.items():
        if name.lower() in venue.lower():
            return ll
    return None


@st.cache_data(ttl=1800, max_entries=40, show_spinner=False)
def _forecast_json(venue: str, game_time_iso: str) -> str:
    ll = _coords_for(venue)
    if not ll:
        return json.dumps(None)
    try:
        pts = requests.get(f"https://api.weather.gov/points/{ll[0]},{ll[1]}",
                           headers=_UA, timeout=10)
        pts.raise_for_status()
        hourly_url = ((pts.json().get("properties") or {}).get("forecastHourly"))
        if not hourly_url:
            return json.dumps(None)
        fc = requests.get(hourly_url, headers=_UA, timeout=10)
        fc.raise_for_status()
        periods = ((fc.json().get("properties") or {}).get("periods")) or []
    except Exception:
        return json.dumps(None)
    if not periods:
        return json.dumps(None)

    # Target hour: scheduled first pitch; fallback ~3h from now.
    try:
        target = datetime.fromisoformat(game_time_iso.replace("Z", "+00:00"))
    except Exception:
        target = datetime.now(timezone.utc) + timedelta(hours=3)

    best = None
    for p in periods:
        try:
            start = datetime.fromisoformat(p["startTime"])
            end = datetime.fromisoformat(p["endTime"])
        except Exception:
            continue
        if start <= target < end:
            best = p
            break
        if best is None:
            best = p  # earliest as last resort
    if best is None:
        return json.dumps(None)

    precip = ((best.get("probabilityOfPrecipitation") or {}).get("value"))
    wind_speed = str(best.get("windSpeed") or "").strip()      # "12 mph"
    wind_dir = str(best.get("windDirection") or "").strip()    # "SW"
    try:
        hour_local = datetime.fromisoformat(best["startTime"]).strftime("%-I %p")
    except Exception:
        hour_local = ""
    return json.dumps({
        "temp": best.get("temperature"),
        "unit": best.get("temperatureUnit", "F"),
        "wind": f"{wind_dir} {wind_speed}".strip(),
        "short": best.get("shortForecast"),
        "precip": precip if precip is not None else 0,
        "hour_local": hour_local,
    })


def get_park_forecast(venue: str, game_time_iso: str):
    """dict or None — game-time NWS forecast for this park."""
    try:
        return json.loads(_forecast_json(venue or "", game_time_iso or ""))
    except Exception:
        return None
