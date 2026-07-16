"""
Game/weather lookup for today's slate, using the MLB Stats API — the
same free, no-key-required source Lineup Analysis already pulls from.

NOTE: I could not test this endpoint live from the sandbox this was
built in (no network access to statsapi.mlb.com there). The schedule
hydration and live-feed structure below match documented API behavior,
but please verify it actually returns weather once you run this in
your Codespace — if a field comes back empty, MLB simply may not have
posted weather for that game yet (common for games more than a day out).
"""
import requests
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

# "Today" for an MLB slate means today in US EASTERN time, not the
# server's clock. Render's servers run on UTC, which rolls over to the
# next date at 8 PM ET — using the server's date made the app start
# asking MLB for TOMORROW's (usually unposted) slate every night at 8,
# blanking the Game Card during prime hours while games were live.
EASTERN = ZoneInfo("America/New_York")


@st.cache_data(ttl=900)
def get_todays_games_with_weather(date_str: str = None):
    """
    Returns today's (or a given date's) games with venue, start time,
    and weather condition/temp/wind if MLB has posted it yet.
    date_str: 'YYYY-MM-DD', defaults to today (US Eastern).
    """
    if date_str is None:
        date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")

    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1,
        "date": date_str,
        "hydrate": "probablePitcher,linescore,weather,venue",
    }

    try:
        resp = requests.get(url, params=params, timeout=10).json()
    except Exception as e:
        return [], f"Schedule request failed: {e}"

    # Defensive: st.cache_data pickles whatever this function returns, so
    # every field below is forced to a plain str/int/None rather than
    # trusted as-is. If the MLB API ever changes shape (e.g. returns a
    # nested object where a string is expected), a stray non-primitive
    # here is exactly the kind of thing that causes an
    # UnserializableReturnValueError crash on the Game Card page — this
    # makes that class of crash structurally impossible going forward.
    def _clean(v, default=None):
        if v is None:
            return default
        if isinstance(v, (str, int, float, bool)):
            return v
        return str(v) if v not in ({}, []) else default

    def _clean_int(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    try:
        games_list = resp.get("dates", [{}])[0].get("games", []) if resp.get("dates") else []
    except Exception as e:
        return [], f"Unexpected schedule response shape: {e}"

    games = []
    try:
        for g in games_list:
            game_pk = _clean_int(g.get("gamePk"))
            weather = g.get("weather") or {}
            if not isinstance(weather, dict):
                weather = {}

            # Schedule hydration doesn't always carry weather — fall back to
            # the live game feed, which reliably does once MLB posts it.
            if not weather and game_pk:
                weather = _fetch_weather_from_feed(game_pk)
                if not isinstance(weather, dict):
                    weather = {}

            games.append({
                "game_pk": game_pk,
                "away": _clean(g.get("teams", {}).get("away", {}).get("team", {}).get("name"), "TBD"),
                "home": _clean(g.get("teams", {}).get("home", {}).get("team", {}).get("name"), "TBD"),
                "away_pitcher": _clean(g.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("fullName"), "TBD"),
                "home_pitcher": _clean(g.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("fullName"), "TBD"),
                "away_pitcher_id": _clean_int(g.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("id")),
                "home_pitcher_id": _clean_int(g.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("id")),
                "venue": _clean(g.get("venue", {}).get("name"), "Unknown Venue"),
                "game_time": _clean(g.get("gameDate")),
                "weather_condition": _clean(weather.get("condition")),
                "weather_temp": _clean(weather.get("temp")),
                "weather_wind": _clean(weather.get("wind")),
            })
    except Exception as e:
        return [], f"Unexpected game data shape: {e}"

    return games, None


def _fetch_weather_from_feed(game_pk):
    """Live game feed carries weather even when the schedule hydration
    doesn't. Best-effort — returns {} on any failure rather than raising,
    since weather is a nice-to-have, not a blocker for the page."""
    try:
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        data = requests.get(url, timeout=10).json()
        return data.get("gameData", {}).get("weather", {}) or {}
    except Exception:
        return {}