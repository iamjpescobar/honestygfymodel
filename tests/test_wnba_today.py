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

# --- slate rows must carry a player id --------------------------------
# Without pid every row was anonymous. likely_starters had nothing to key
# on and always returned an empty set (blank Role column for everyone),
# the app couldn't match ESPN's per-game availability back to a player,
# and wnba_defense logged calibration picks as {"id": None} — that board's
# record could never be graded against a box score.
build = open("wnba_precompute.py").read()
row_keys = build[build.index("row_keys = ("):build.index("h2h_keys")]
assert '"pid"' in row_keys, "slate rows must carry pid"
print("PASS: slate rows carry pid (Role, ESPN matching and grading all need it)")

# Anonymous rows must not silently produce an empty starter set.
anon = [{"name": f"P{i}", "log": [{"date": "2026-07-27", "min": 30.0}]}
        for i in range(8)]
assert likely_starters(anon, today=TODAY) == set()
identified = [{**r, "pid": i} for i, r in enumerate(anon)]
assert len(likely_starters(identified, today=TODAY)) == 5
print("PASS: with pid present, starters resolve; without, the set is empty")

# --- the whole roster, not the top 9 scorers --------------------------
# The cap was applied at BUILD time, sorted by scoring, before anyone
# knew who was available — so injured stars consumed slots and their
# replacements were cut from the file entirely. The sixth option matters
# most on exactly the nights the starters are out.
#
# This assertion used to grep for the cap NUMBER and require it to be
# >= 12. The cap has since been removed outright: picks are built by
# walking the team's full ESPN roster, so there is no number left to
# find and the old regex could only ever fail. That failure took the
# whole nightly down with it (the "Run tests" step gates the fetch), so
# the check is now written against the PROPERTY rather than the
# spelling of one line: the build must walk the roster, and nothing may
# slice the pick list back down. The gp >= 3 filter still exists but
# only as a fallback for when the roster fetch itself fails.
import re
_slate = build[build.index("picks = []"):build.index("row_keys = (")]
assert "_roster.items()" in _slate, (
    "slate players must be built from the team's full roster, not from "
    "whoever happens to have box-score rows")
_cap = re.search(r"\]\[:\s*(\d+)\]|picks\s*=\s*picks\[:\s*(\d+)\]", _slate)
assert _cap is None, (
    f"a roster cap is back in the slate build ({_cap.group(0)!r}); the "
    f"sixth option matters most on the nights the starters are out")
print("PASS: slate keeps every rostered player (no build-time cap)")
