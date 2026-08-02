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
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def get_todays_games_with_weather(date_str: str = None):
    """
    Returns (games, error) for today's (or a given date's) slate with
    venue, start time, and weather condition/temp/wind if MLB has
    posted it yet. date_str: 'YYYY-MM-DD', defaults to today (US Eastern).

    Thin uncached wrapper: the cached layer below returns a JSON STRING,
    which this parses back into Python. A str always pickles, so
    st.cache_data's UnserializableReturnValueError is structurally
    impossible no matter what shape the MLB API returns.
    """
    if date_str is None:
        date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    try:
        payload = json.loads(_fetch_todays_games_json(date_str))
    except Exception as e:
        return [], f"Schedule cache error: {e}"
    return payload.get("games") or [], payload.get("error")


@st.cache_data(ttl=900, max_entries=8, show_spinner=False)
def _fetch_todays_games_json(date_str: str) -> str:
    """Cached fetch. Returns json.dumps({"games": [...], "error": ...})
    with default=str, so any non-JSON-native value that ever slips past
    the _clean() scrubbing below is coerced to its string form instead
    of blowing up the cache write. Keyed on date_str (now always passed
    explicitly) so each slate date caches separately."""

    def _done(games, error):
        return json.dumps({"games": games, "error": error}, default=str)

    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1,
        "date": date_str,
        "hydrate": "probablePitcher,linescore,weather,venue",
    }

    try:
        resp = requests.get(url, params=params, timeout=10).json()
    except Exception as e:
        return _done([], f"Schedule request failed: {e}")

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
        return _done([], f"Unexpected schedule response shape: {e}")

    games = []
    try:
        # WEATHER FALLBACK, FETCHED IN PARALLEL.
        #
        # Schedule hydration often omits weather early in the day, and
        # the fallback is one live-feed request PER GAME. Fired
        # sequentially inside this loop, a 15-game slate meant up to 15
        # round trips back to back before the Game Card could paint —
        # each with its own 10s timeout, so one slow response held up
        # every game behind it.
        #
        # They're independent reads, so they go out together. Threads
        # here only run `requests` — no Streamlit calls, which would
        # need a script context they don't have.
        _need_feed = [
            _clean_int(g.get("gamePk")) for g in games_list
            if not (isinstance(g.get("weather"), dict) and g.get("weather"))
            and _clean_int(g.get("gamePk"))
        ]
        _feed_weather = _fetch_weather_batch(_need_feed)

        for g in games_list:
            game_pk = _clean_int(g.get("gamePk"))
            weather = g.get("weather") or {}
            if not isinstance(weather, dict):
                weather = {}

            if not weather and game_pk:
                weather = _feed_weather.get(game_pk) or {}
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
        return _done([], f"Unexpected game data shape: {e}")

    return _done(games, None)


def _fetch_one_weather(game_pk):
    """Live feed weather for one game. Best-effort: {} on any failure,
    since weather is a nice-to-have, not a blocker for the page.

    Deliberately NOT st.cache_data-decorated any more: it's called from
    worker threads, which have no Streamlit script context, and the
    caching now lives one level up on _fetch_todays_games_json (keyed by
    date, 15-minute TTL) which covers the whole slate in one entry.
    """
    try:
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        data = requests.get(url, timeout=10).json()
        return data.get("gameData", {}).get("weather", {}) or {}
    except Exception:
        return {}


def _fetch_weather_batch(game_pks):
    """{game_pk: weather_dict} for every game that needs the fallback,
    fetched concurrently. Returns {} for anything that failed.

    Capped at 8 workers: a full slate is ~15 games and these all hit the
    same MLB host, so there's nothing to gain from opening one socket per
    game and a polite ceiling avoids looking like a burst of scraping.
    """
    if not game_pks:
        return {}
    out = {}
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(game_pks))) as pool:
            futures = {pool.submit(_fetch_one_weather, pk): pk for pk in game_pks}
            for fut in as_completed(futures):
                out[futures[fut]] = fut.result()
    except Exception:
        # Thread pool unavailable for any reason — fall back to serial
        # fetching rather than dropping weather entirely.
        for pk in game_pks:
            out[pk] = _fetch_one_weather(pk)
    return out
