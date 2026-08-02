"""
Wind, resolved against the direction each ballpark actually faces.

THE PROBLEM THIS SOLVES
-----------------------
MLB reports weather in two different shapes. Sometimes it's already
field-relative — "12 mph, Out To CF" — and engines/player_of_the_day.py
handles that correctly today. Often it's a plain compass forecast:
"SW 12 mph". Southwest tells you nothing on its own. A southwest wind
blows straight out at Wrigley and straight in at Comerica, because those
two parks point in nearly opposite directions.

Faced with that, the existing code returns 0 — honest, but it means wind
is silently ignored on a large share of games, including the ones where
it matters most.

ORIENTATIONS
------------
Real values, transcribed from Andrew Clem's Stadium Statistics page
(andrewclem.com/Baseball/Stadium_statistics.html), which publishes the
compass direction from home plate to center field for every park. Same
provenance approach as engines/park_factors.py: a real, citable source
read off the published table, not inferred and not remembered.

Clem's page gives compass points (NE, ENE, NNE), which convert exactly:
each point is 22.5 degrees, N = 0.

The Athletics are absent. They play at Sutter Health Park in Sacramento,
which isn't in that table, so they stay unverified rather than guessed —
exactly as they are in park_factors.py. An unknown park produces no wind
adjustment instead of a wrong one.

THE GEOMETRY
------------
Meteorological convention reports the direction wind comes FROM. A
"southwest wind" travels toward the northeast. So:

    travelling_toward = (reported_from + 180) mod 360

Compare that to the park's home-plate-to-centre-field bearing:

    0 degrees apart   -> blowing straight out to centre  (helps)
    180 degrees apart -> blowing straight in from centre (hurts)
    90 degrees apart  -> pure crosswind                  (~neutral)

cos() of the difference gives exactly that curve, and multiplying by
speed scales it. A 5 mph breeze straight out is worth far less than a
20 mph gale, and the cosine handles every angle between.
"""
import math
import re


# Compass point -> degrees. Each point is 360/16 = 22.5 degrees.
_POINTS = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}

# Home plate -> centre field bearing, in degrees, per Clem's table.
# Keyed by the same Statcast-style abbreviation build_park_hr_factors
# groups on, so both context layers look up the same way.
PARK_CF_BEARING = {
    "BOS": _POINTS["NE"],     # Fenway Park
    "CHC": _POINTS["NE"],     # Wrigley Field
    "LAA": _POINTS["NE"],     # Angel Stadium
    "KC":  _POINTS["NE"],     # Kauffman Stadium
    "TOR": _POINTS["NNW"],    # Rogers Centre
    "CWS": _POINTS["ESE"],    # Rate Field
    "BAL": _POINTS["NNE"],    # Oriole Park at Camden Yards
    "CLE": _POINTS["N"],      # Progressive Field
    "COL": _POINTS["N"],      # Coors Field
    "TB":  _POINTS["NE"],     # Tropicana Field
    "ARI": _POINTS["N"],      # Chase Field
    "SEA": _POINTS["NE"],     # T-Mobile Park
    "SF":  _POINTS["ESE"],    # Oracle Park
    "HOU": _POINTS["ENE"],    # Daikin Park
    "DET": _POINTS["SSE"],    # Comerica Park
    "MIL": _POINTS["SE"],     # American Family Field
    "PIT": _POINTS["ESE"],    # PNC Park
    "CIN": _POINTS["ESE"],    # Great American Ball Park
    "PHI": _POINTS["NNE"],    # Citizens Bank Park
    "SD":  _POINTS["N"],      # Petco Park
    "STL": _POINTS["NE"],     # Busch Stadium
    "WSH": _POINTS["NNE"],    # Nationals Park
    "NYY": _POINTS["ENE"],    # Yankee Stadium
    "NYM": _POINTS["NNE"],    # Citi Field
    "MIN": _POINTS["E"],      # Target Field
    "MIA": _POINTS["ESE"],    # loanDepot park
    "ATL": _POINTS["SSE"],    # Truist Park
    "TEX": _POINTS["ENE"],    # Globe Life Field
    "LAD": _POINTS["NNE"],    # Dodger Stadium
    # ATH deliberately absent — Sutter Health Park is not in the source
    # table. Unknown park -> no adjustment, never a guessed bearing.
}

# Parks that play under a roof often enough that an outdoor wind reading
# is meaningless. When MLB reports a closed roof the caller passes
# roof_closed and this returns 0 regardless; this list is only a
# fallback for when roof state is unknown.
_DOMED = {"TB", "ARI", "HOU", "MIL", "TOR", "SEA", "MIA", "TEX"}

WIND_CAP = 6.0          # bounded like every other context component
_MPH_FOR_FULL = 15.0    # a 15 mph straight-out wind reaches the cap


def _parse_wind(wind_str):
    """(speed_mph, from_degrees) or (None, None).

    Handles "SW 12 mph", "12 mph SW", "Wind 8 mph out of the NNE".
    Returns None for field-relative strings ("Out To CF") — those are
    already handled by player_of_the_day._wind_hr_adj and don't need a
    bearing. Returns None rather than guessing on anything unparseable.
    """
    if not wind_str:
        return None, None
    s = str(wind_str).upper()
    speed_m = re.search(r"(\d+)\s*MPH", s) or re.search(r"(\d+)", s)
    if not speed_m:
        return None, None
    speed = float(speed_m.group(1))
    if speed <= 0 or speed > 80:      # 80+ is a parse error, not weather
        return None, None
    # Longest compass tokens first so "SSW" isn't matched as "S".
    for point in sorted(_POINTS, key=len, reverse=True):
        if re.search(rf"\b{point}\b", s):
            return speed, _POINTS[point]
    return None, None


def wind_hr_adj(home_team_abbr, wind_str, roof_closed=False):
    """(adj, note) — wind resolved against this park's orientation.

    Positive helps home runs (blowing out), negative suppresses them.
    Returns (0, None) whenever it can't be resolved honestly: closed
    roof, unknown park, unparseable wind, or a field-relative string
    that a different code path already handles.
    """
    if roof_closed:
        return 0, None
    bearing = PARK_CF_BEARING.get(str(home_team_abbr or "").upper())
    if bearing is None:
        return 0, None
    speed, from_deg = _parse_wind(wind_str)
    if speed is None:
        return 0, None
    if str(home_team_abbr).upper() in _DOMED and roof_closed is None:
        return 0, None

    # Wind travels OPPOSITE the direction it is reported as coming from.
    toward = (from_deg + 180.0) % 360.0
    delta = math.radians(toward - bearing)
    # cos: 1.0 straight out to centre, -1.0 straight in, 0 crosswind.
    component = math.cos(delta)

    adj = component * (speed / _MPH_FOR_FULL) * WIND_CAP
    adj = round(max(-WIND_CAP, min(WIND_CAP, adj)), 1)
    if abs(adj) < 0.5:
        return 0, None

    if component > 0.5:
        word = "blowing out"
    elif component < -0.5:
        word = "blowing in"
    else:
        word = "crosswind"
    return adj, f"{int(speed)} mph {word} ({adj:+.1f})"
