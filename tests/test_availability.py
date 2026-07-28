"""Player availability — the rule that stops absent players being picked.

Every qualification filter on the WNBA boards was a SEASON TOTAL: games
played, minutes per game, length of game log. None of them knows what day
it is. A player who appeared 20 times through June and then missed the
last 14 games clears all of them and gets ranked on month-old numbers.

That's the worst failure these pages can have — a confident, well-formed
prop on someone who isn't in the building, where every other number on
the row is correct.
"""
import sys, types
from datetime import date, timedelta

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, "app")

from engines.wnba_props import availability, STALE_DAYS, MIN_LAST_MIN, _parse_log_date

TODAY = date(2026, 7, 28)

def player(days_ago_list, minutes=28.0):
    return {"log": [{"date": (TODAY - timedelta(days=d)).isoformat(), "min": minutes}
                    for d in sorted(days_ago_list, reverse=True)]}

# --- the reported bug -------------------------------------------------
# 20 games through June, nothing since — 30 days out.
absent = player([30, 32, 34, 36, 38], minutes=30.0)
ok, why, days = availability(absent, today=TODAY)
assert ok is False, "a player 30 days absent was marked available"
assert "30 days" in why, why
print(f"PASS: 30-day absence caught -> {why!r}")

# --- a player who IS playing --------------------------------------------
active = player([1, 3, 5, 7, 9], minutes=31.0)
ok, why, days = availability(active, today=TODAY)
assert ok is True and why is None, (ok, why)
print(f"PASS: played 1 day ago -> available (days_since={days})")

# --- boundary -----------------------------------------------------------
edge_ok, _, _ = availability(player([STALE_DAYS]), today=TODAY)
edge_bad, why_bad, _ = availability(player([STALE_DAYS + 1]), today=TODAY)
assert edge_ok is True, f"{STALE_DAYS} days should still pass"
assert edge_bad is False, f"{STALE_DAYS+1} days should fail"
print(f"PASS: boundary exact — {STALE_DAYS}d available, {STALE_DAYS+1}d not")

# --- minutes restriction ------------------------------------------------
restricted = player([1, 3, 5], minutes=4.0)
ok, why, _ = availability(restricted, today=TODAY)
assert ok is False and "min in her last game" in why, why
print(f"PASS: {MIN_LAST_MIN:.0f}-minute floor catches a restricted return")

# The floor applies to the MOST RECENT game only — a bad night weeks ago
# shouldn't disqualify someone playing full minutes now.
mixed = {"log": [
    {"date": (TODAY - timedelta(days=20)).isoformat(), "min": 3.0},
    {"date": (TODAY - timedelta(days=2)).isoformat(), "min": 30.0},
]}
ok, why, _ = availability(mixed, today=TODAY)
assert ok is True, why
print("PASS: only the latest appearance is judged, not an old short night")

# --- fails OPEN on missing dates, CLOSED on real evidence ---------------
no_dates = {"log": [{"date": None, "min": 30.0}, {"date": "", "min": 28.0}]}
ok, why, _ = availability(no_dates, today=TODAY)
assert ok is True, "no dates means no evidence of absence — must not drop everyone"
print("PASS: unparseable dates fail OPEN (no evidence != evidence of absence)")

ok, why, _ = availability({"log": []}, today=TODAY)
assert ok is False and "no game log" in why
print("PASS: an empty log fails closed")

# --- date parsing -------------------------------------------------------
assert _parse_log_date("2026-07-27") == date(2026, 7, 27)
assert _parse_log_date("2026-07-27T19:05:00Z") == date(2026, 7, 27)
assert _parse_log_date("garbage") is None
assert _parse_log_date(None) is None
print("PASS: date parsing handles ISO, ISO-datetime, Z suffix, and junk")

# --- both boards must apply the SAME rule -------------------------------
import engines.wnba_defense as wd
assert wd.availability is availability, \
    "the defense board must share this function, not carry its own copy"
print("PASS: props and defense boards share one availability rule")

# --- and it must run BEFORE the season-total filters ---------------------
src = open("app/engines/wnba_props.py").read()
body = src[src.index("for p in g.get(f\"{side}_players\")"):]
i_avail, i_gp = body.index("availability(p)"), body.index("gp < MIN_GP")
assert i_avail < i_gp, "availability must be checked before season totals"
print("PASS: availability is the first filter, ahead of every season total")
