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


@st.cache_data(ttl=900)
def get_todays_games_with_weather(date_str: str = None):
    """
    Returns today's (or a given date's) games with venue, start time,
    and weather condition/temp/wind if MLB has posted it yet.
    date_str: 'YYYY-MM-DD', defaults to today.
    """
    if date_str is None:
        date_str = datetime.today().strftime("%Y-%m-%d")

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

    games_list = resp.get("dates", [{}])[0].get("games", []) if resp.get("dates") else []

    games = []
    for g in games_list:
        game_pk = g.get("gamePk")
        weather = g.get("weather", {})

        # Schedule hydration doesn't always carry weather — fall back to
        # the live game feed, which reliably does once MLB posts it.
        if not weather and game_pk:
            weather = _fetch_weather_from_feed(game_pk)

        games.append({
            "game_pk": game_pk,
            "away": g.get("teams", {}).get("away", {}).get("team", {}).get("name", "TBD"),
            "home": g.get("teams", {}).get("home", {}).get("team", {}).get("name", "TBD"),
            "away_pitcher": g.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("fullName", "TBD"),
            "home_pitcher": g.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("fullName", "TBD"),
            "away_pitcher_id": g.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("id"),
            "home_pitcher_id": g.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("id"),
            "venue": g.get("venue", {}).get("name", "Unknown Venue"),
            "game_time": g.get("gameDate"),
            "weather_condition": weather.get("condition"),
            "weather_temp": weather.get("temp"),
            "weather_wind": weather.get("wind"),
        })

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
