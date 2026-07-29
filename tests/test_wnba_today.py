"""Tonight's real availability beats inference from past game logs.

Game logs are a record of the PAST and cannot answer "is she playing
tonight": a player returning today reads as absent, one ruled out this
morning reads as fine. ESPN's game summary carries the actual injury
report and announced lineups, and those settle it.
"""
import sys, types
from datetime import date, timedelta

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, "app"); sys.path.insert(0, ".")

from engines.wnba_props import availability, likely_starters

TODAY = date(2026, 7, 28)
def logged(days_ago, **extra):
    return {"log": [{"date": (TODAY - timedelta(days=days_ago)).isoformat(),
                     "min": 30.0}], **extra}

# --- the exact failure reported: played recently, ruled out tonight ---
played_yesterday_but_out = logged(1, today_out=True, today_status="Out")
ok, why, _ = availability(played_yesterday_but_out, today=TODAY)
assert ok is False, "a player ESPN says is OUT was shown as available"
assert "tonight" in why.lower(), why
print(f"PASS: played yesterday but ruled out tonight -> {why!r}")

# --- the mirror: long absence, but active tonight (a return) ---------
returning = logged(25, today_out=False)
ok, why, _ = availability(returning, today=TODAY)
assert ok is True, "a player ESPN lists as active was hidden as stale"
print("PASS: 25-day absence but active tonight -> available (a return)")

# --- None means UNKNOWN, not available -------------------------------
no_feed_recent = logged(1)
no_feed_stale = logged(30)
assert availability(no_feed_recent, today=TODAY)[0] is True
assert availability(no_feed_stale, today=TODAY)[0] is False
print("PASS: without ESPN data the log inference still applies unchanged")

assert availability(logged(30, today_out=None), today=TODAY)[0] is False, \
    "today_out=None must not read as 'available'"
print("PASS: today_out=None falls through rather than clearing everyone")

# --- announced lineups beat the minutes guess ------------------------
roster = [{"pid": i, "today_starter": (i <= 5),
           "log": [{"date": (TODAY - timedelta(days=1)).isoformat(),
                    "min": 5.0 if i <= 5 else 34.0}]} for i in range(1, 11)]
s = likely_starters(roster, today=TODAY)
assert s == {1, 2, 3, 4, 5}, s
print("PASS: announced starters override the minutes inference entirely")

# Without announcements, fall back to minutes.
no_announce = [{"pid": i,
                "log": [{"date": (TODAY - timedelta(days=1)).isoformat(),
                         "min": 40.0 - i}]} for i in range(1, 11)]
assert likely_starters(no_announce, today=TODAY) == {1, 2, 3, 4, 5}
print("PASS: no announcement -> minutes inference still works")

# --- the build side ---------------------------------------------------
src = open("wnba_precompute.py").read()
assert "def fetch_game_availability" in src
assert '"today_out"' in src and '"today_starter"' in src
assert 'g["event_id"] = _eid' in src, "event id must be kept or nothing can be fetched"
assert "summary?event=" in src
print("PASS: build fetches ESPN summary per game and attaches today's status")

# Defensive: unknown shapes must yield {}, never partial garbage.
import wnba_precompute as wp
wp.get_json = lambda url: (_ for _ in ()).throw(RuntimeError("404"))
assert wp.fetch_game_availability("123") == {}
wp.get_json = lambda url: {}
assert wp.fetch_game_availability("123") == {}
wp.get_json = lambda url: {"injuries": [{"injuries": [{"athlete": {}, "status": "Out"}]}]}
assert wp.fetch_game_availability("123") == {}, "an athlete with no id must be skipped"
print("PASS: fetch failure and unknown shapes return {} (fall back, never guess)")

wp.get_json = lambda url: {
    "injuries": [{"injuries": [{"athlete": {"id": 7}, "status": "Out"}]}],
    "rosters": [{"roster": [{"athlete": {"id": 9}, "starter": True}]}],
}
got = wp.fetch_game_availability("123")
assert got["7"]["out"] is True and got["9"]["starter"] is True
assert got["9"]["out"] is False, "being on the game roster means available"
print("PASS: injuries and announced lineups both parsed correctly")
