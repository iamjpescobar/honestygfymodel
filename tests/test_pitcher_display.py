"""Pitcher handedness, pitch counts, and the WNBA stale-data anchor."""
import re, sys, types
from datetime import date, timedelta

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
          "statcast_batter_percentile_ranks", "statcast"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

# --- pitcher handedness was never returned at all ---------------------
eng = open("app/engines/statcast_engine.py").read()
assert 'metrics["p_throws"]' in eng, "get_pitcher_statcast still doesn't return p_throws"
assert ".mode()" in eng, "hand should be the modal value, not a stray first row"
print("PASS: get_pitcher_statcast returns p_throws (it never did)")

gc = open("app/views/GameCard.py").read()
assert '_hand = (pitcher_data or {}).get("p_throws")' in gc
assert "HP</span>" in gc, "handedness not rendered on the pitcher header"
print("PASS: throwing hand displayed on the pitcher header")

# This is what silently broke: switch-hitter resolution reads _p_throws.
i_read = gc.index('_p_throws = (pitcher_data or {})')
assert '_eff_bats = "L" if _p_throws == "R"' in gc
print("PASS: switch-hitter resolution now has a real hand to read")

# --- Ord sits with the identity columns -------------------------------
row = gc[gc.index('"Player": name,'):]
row = row[:row.index('"Brl%"')]
assert '"Ord":' in row, "Ord should sit near Player/Bats"
i_bats, i_ord, i_hrfb = row.index('"Bats"'), row.index('"Ord"'), row.index('"HR/FB"')
assert i_bats < i_ord < i_hrfb, "Ord must sit right after Bats, before the rate stats"
print("PASS: Ord moved next to Bats, out of the middle of the rate columns")

# --- pitch counts -----------------------------------------------------
pt = open("app/engines/pitcher_trends.py").read()
assert '"pitches": pitches' in pt, "pitch count not carried on game-log entries"
assert '"Pitches Thrown": "pitches"' in pt, "not selectable as a stat"
assert 'int(stat.get("numberOfPitches"))' in pt
assert "pitches = None" in pt, "missing pitch count must be None, not 0"
assert 'g.get("pitches") is not None' in pt, "games without a count must be dropped"
print("PASS: pitch count carried, selectable, and None-safe (never a fake 0)")

sb = open("app/views/Strikeout_Board.py").read()
assert '"Pitches Thrown"' in sb, "not offered in the stat selector"
print("PASS: Pitches Thrown offered in the Strikeout Board selector")

# --- WNBA: stale data must not read as a league-wide injury report ----
from engines.wnba_props import league_reference_date, availability

TODAY = date(2026, 7, 28)
def pl(days_ago):
    return {"log": [{"date": (TODAY - timedelta(days=days_ago)).isoformat(),
                     "min": 30.0}]}

# A feed that stopped updating 20 days ago: everyone's last game is old.
stale = [{"home_players": [pl(20), pl(21)], "away_players": [pl(20), pl(22)]}]
ref = league_reference_date(stale)
assert ref == TODAY - timedelta(days=20), ref
print(f"PASS: reference date tracks the data's newest game ({ref})")

# Against the wall clock every one of them looks absent...
assert availability(pl(20), today=TODAY)[0] is False
# ...but against the data's own reference they're playing normally.
assert availability(pl(20), today=ref)[0] is True
print("PASS: a 20-day-stale feed no longer flags the whole league as out")

# A genuine absence still stands out within stale data.
genuinely_out = pl(45)
assert availability(genuinely_out, today=ref)[0] is False
print("PASS: a real absence is still caught inside stale data")

assert league_reference_date([]) is None
assert league_reference_date([{"home_players": [{"log": []}]}]) is None
print("PASS: no dates anywhere -> None (callers fall back to the clock)")

w = open("app/views/WNBA.py").read()
assert "_REF = _ref_date(games)" in w
assert "days old" in w, "user should be told when the data itself is stale"
print("PASS: WNBA page warns when its own data is stale")
