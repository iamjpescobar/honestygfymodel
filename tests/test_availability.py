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
# player_of_the_day pulls in the MLB engines on import; stub the
# dependency so this test exercises the WNBA path without it.
pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks", "statcast"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
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

# --- WNBA Player of the Day -------------------------------------------
# The worst instance: this board only checked gp < 5 (a season total) AND
# ranks by l5_pra — her last five games. For someone who stopped playing,
# those five are from a month ago and are often her hottest stretch, the
# one right before she went down. So the omission didn't merely let absent
# players through, it FAVOURED the ones producing when they got hurt.
pod_src = open("app/engines/player_of_the_day.py").read()
seg = pod_src[pod_src.index("def get_wnba_player_of_the_day"):]
assert "_wnba_availability(p)" in seg, "WNBA POTD doesn't check availability"
# Match the CODE line, not the prose — the explanatory comment above the
# check also contains "gp < 5", and an earlier version of this assertion
# found the comment first and failed against correct code.
i_av = seg.index("_wnba_availability(p)")
i_gp = seg.index("                if gp < 5:")
assert i_av < i_gp, "availability must be checked before the season-total floor"
print("PASS: WNBA Player of the Day checks availability before gp < 5")

# --- WNBA slate tables flag rather than hide --------------------------
w = open("app/views/WNBA.py").read()
assert "_availability(p)" in w, "slate tables don't check availability"
assert '"Status"' in w, "slate tables need a status column"
assert "OUT" in w
print("PASS: slate tables FLAG unavailable players (roster view, not a pick list)")

# One rule, four consumers — a page disagreeing with another about who is
# playing is how this bug comes back.
import engines.player_of_the_day as pod
for mod, name in (("engines.wnba_props", "props"),
                  ("engines.wnba_defense", "defense")):
    m = __import__(mod, fromlist=["availability"])
    assert m.availability is availability, f"{name} carries its own copy"
# Check the IMPORT SOURCE, not one literal line — WNBA.py's import
# became multi-line when likely_starters was added, and pinning the exact
# text broke against unchanged behaviour.
assert "from engines.wnba_props import" in w and "availability as _availability" in w
assert "from engines.wnba_props import availability" in pod_src
print("PASS: props, defense, POTD and the slate view share one rule")

# --- likely starters --------------------------------------------------
from engines.wnba_props import likely_starters, _recent_minutes, STARTERS_PER_TEAM

def mk(pid, mins_recent, days_ago=1, season_min=None):
    """A player whose LAST 5 games ran `mins_recent` minutes."""
    log = [{"date": (TODAY - timedelta(days=days_ago + i * 2)).isoformat(),
            "min": mins_recent} for i in range(5)]
    return {"pid": pid, "min": season_min if season_min is not None else mins_recent,
            "log": list(reversed(log))}

roster = [mk(i, m) for i, m in enumerate([32, 30, 28, 26, 24, 12, 9, 6], start=1)]
s = likely_starters(roster, today=TODAY)
assert s == {1, 2, 3, 4, 5}, s
print(f"PASS: top {STARTERS_PER_TEAM} by recent minutes identified as starters")

# RECENT minutes, not season. A player promoted two weeks ago carries a
# low season average and would be ranked as a bench player by any
# season-total measure — the same mistake that let absent players through.
promoted = mk(99, 33, season_min=8.0)
s2 = likely_starters(roster[:4] + [promoted], today=TODAY)
assert 99 in s2, "a recently promoted starter was missed by season minutes"
print("PASS: recent promotion is caught (recent minutes beat season average)")

# An absent former starter must not hold a starting spot.
out_star = {"pid": 77, "min": 34.0,
            "log": [{"date": (TODAY - timedelta(days=30)).isoformat(), "min": 34.0}]}
s3 = likely_starters(roster[:4] + [out_star], today=TODAY)
assert 77 not in s3, "a 30-day-absent player was still listed as a starter"
print("PASS: an absent former starter doesn't hold the spot")

assert likely_starters([], today=TODAY) == set()
assert likely_starters([{"pid": 5, "log": []}], today=TODAY) == set()
print("PASS: unreadable minutes -> empty set (unknown, not 'nobody starts')")

# --- the Status column must survive rendering -------------------------
w = open("app/views/WNBA.py").read()
assert '_TEXT_COLS' in w, "Status/Role must be excluded from numeric coercion"
assert '"Status", "Role"' in w
i_text = w.index("_TEXT_COLS = ")
i_num = w.index("num_cols = [c for c in df.columns")
assert i_text < i_num, "text columns must be excluded before num_cols is built"
print("PASS: Status and Role excluded from numeric coercion (they'd blank to em-dash)")

assert '"Role": ("OUT" if not _ok' in w, "Role column missing"
assert '_order = {"START": 0' in w, "rows not ordered by role"
print("PASS: starters sort first, bench next, unavailable last")
