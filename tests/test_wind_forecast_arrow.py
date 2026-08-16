"""A morning wind forecast has to point at the field, not at north.

THE PROBLEM. MLB does not publish gameData.weather until close to first
pitch, so a card opened in the morning has only an NWS compass forecast
("SW 12 mph"). Two things went wrong with that:

  THE GRADE ignored it. _hr_weather was handed g["weather_wind"] —
  MLB-only — even though the row had already computed a forecast
  fallback four lines above and then never used it. Temperature fell
  back correctly; wind did not. So a morning card showed a real
  temperature beside a blank arrow and "wind pending".

  THE ARROW pointed at real-world north. A compass forecast drew a rose
  at its true bearing, which is correct and useless: it cannot tell you
  whether a ball carries.

Both were solvable already. wind_engine carries the home-plate-to-
centre-field bearing for 29 parks and was ALREADY resolving these
forecasts to score them elsewhere on the site — the Weather Board was
calling a wind "pending" while HR Edge had scored it.

WEATHER IS THE READ THAT MATTERS MOST BEFORE A SLATE, so a board that
only works after first pitch is a board that does not work.
"""
import sys, types
sys.path.insert(0, "app")
_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = _st

from engines.wind_engine import field_angle  # noqa: E402
from engines.weather_icons import wind_arrow  # noqa: E402

# --- 1. THE SAME FORECAST MEANS DIFFERENT THINGS IN DIFFERENT PARKS --
#
# This is the whole reason a compass reading needs the park. Wrigley
# faces roughly north-east, so a south-west wind blows straight out.
_wrigley = field_angle("CHC", "SW 12 mph")
_comerica = field_angle("DET", "SW 12 mph")
assert _wrigley is not None and _comerica is not None
assert abs(_wrigley) < 25, f"SW at Wrigley should blow out, got {_wrigley}"
assert abs(_comerica) > 60, f"SW at Comerica is not out, got {_comerica}"
print(f"PASS: SW 12 mph -> Wrigley {_wrigley:+.0f}\u00b0, Comerica {_comerica:+.0f}\u00b0")

# --- 2. THE REVERSE WIND BLOWS IN --------------------------------- --
_in = field_angle("CHC", "NE 12 mph")
assert abs(abs(_in) - 180) < 25, f"NE at Wrigley should blow in, got {_in}"
assert _in > 0, "straight-in should render as +180, not -180 — both are the "\
                "same rotation but a negative reads as a bug when debugging"
print(f"PASS: NE 12 mph at Wrigley reads {_in:+.0f}\u00b0 (blowing in)")

# --- 3. UNRESOLVABLE STAYS UNRESOLVED ------------------------------ --
#
# An unknown park or an unparseable string returns None rather than a
# guessed angle. A confidently wrong arrow is worse than no arrow, and
# weather is the input a whole slate gets read through.
assert field_angle("ZZZ", "SW 12 mph") is None, "an unknown park produced an angle"
assert field_angle("CHC", "breezy") is None, "an unparseable wind produced an angle"
assert field_angle("CHC", None) is None
assert field_angle(None, "SW 12 mph") is None
print("PASS: unknown park or unparseable wind yields no angle")

# --- 4. A FIELD-RELATIVE STRING STILL WINS ------------------------- --
#
# MLB's "Out To CF" is measured at the park; a bearing is modelled. When
# both exist the measurement has to win, or an official reading gets
# overwritten by a model.
_official = wind_arrow("12 mph, Out To CF", home_team="DET")
assert "rotate(0" in _official or "rotate(0.0" in _official, (
    "an official Out To CF at Comerica was overridden by the compass "
    "resolution — the measured direction must beat the modelled one")
print("PASS: an official field-relative wind is not overridden")

# --- 5. THE ARROW ONLY RESOLVES WHEN GIVEN THE PARK ---------------- --
#
# wind_arrow's old signature took no park, so every caller that has not
# been updated keeps the old behaviour rather than silently guessing.
_no_park = wind_arrow("SW 12 mph*")
_with_park = wind_arrow("SW 12 mph*", home_team="CHC")
assert _no_park != _with_park, (
    "the park made no difference — the arrow is not resolving the "
    "forecast against the ballpark")
print("PASS: the arrow resolves only when the park is supplied")

# --- 6. THE BOARD PASSES THE FORECAST TO BOTH THE GRADE AND ARROW -- --
_wb = open("app/views/Weather_Board.py", encoding="utf-8").read()
assert "_hr_weather(\n            _raw_temp, _wind_raw, roofed," in _wb, (
    "the grade is back on g['weather_wind'] — morning cards will show a "
    "temperature beside a blank wind again")
assert "wind_arrow(_wind_raw, home_team=" in _wb, (
    "the arrow no longer receives the park, so a forecast cannot point "
    "at the field")
print("PASS: the board feeds the forecast to both the grade and the arrow")


# --- 7. EVERY CALLER MUST PASS THE PARK ------------------------------
#
# THE MISS THIS CATCHES. The Weather Board was fixed and the Game Card
# was not — same forecast, same slate, resolved on one page and a
# neutral swirl on the other. That is the SECOND time in two days a fix
# reached one consumer and silently missed another (the arsenal window
# was fixed in one of three panels the same way).
#
# wind_arrow cannot resolve a compass bearing without knowing which way
# the park faces, so a call without home_team is not a style problem —
# it is a call that CANNOT work in the morning, which is exactly when
# the wind read matters most.
import re as _re  # noqa: E402
from pathlib import Path  # noqa: E402

_missing = []
for _f in sorted(Path("app").rglob("*.py")):
    _src = _f.read_text(encoding="utf-8")
    if _f.name == "weather_icons.py":
        continue                      # the definition itself
    for _m in _re.finditer(r"wind_arrow\(([^)]*)\)", _src):
        if "home_team" not in _m.group(1):
            _missing.append(f"{_f}: wind_arrow({_m.group(1)})")
assert not _missing, (
    "these callers do not pass the park, so a compass forecast cannot "
    "resolve to a field direction there:\n  " + "\n  ".join(_missing))
print("PASS: every wind_arrow caller passes the park")
