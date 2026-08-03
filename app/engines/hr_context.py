"""
Where the ball is being hit, and into what air.

The skill layer (HR Score) answers "how good is this bat at hitting home
runs." It is deliberately PARK-NEUTRAL — the xHR grid pools all 30 parks
— because a hitter's skill shouldn't change when he goes on the road.
This module supplies the other half: tonight's building, and tonight's
air. Both belong in the matchup layer alongside BvP and bullpen, not
baked into the hitter's own number, or they'd be counted twice.

These matter more than people expect. The difference between a lefty in
Yankee Stadium and the same lefty in Comerica is a larger swing in home
run probability than a couple of points of barrel rate.

WHAT'S HERE AND WHAT ISN'T
--------------------------
park_hr_adj    - real, measured from this season's own batted balls by
                 (park, batter hand). See build_park_hr_factors.
temp_hr_adj    - real, and directionally certain: warm air is less dense
                 and the ball carries further.
wind_hr_adj    - real, via engines/wind_engine. Resolves a compass
                 forecast against each park's published home-plate-to-
                 centre-field bearing, so "SW 12 mph" becomes blowing
                 out at Wrigley and blowing in at Comerica. Bearings are
                 transcribed from a citable source, not remembered; the
                 Athletics are absent from that source and therefore get
                 no wind adjustment rather than a guessed one.
"""
import streamlit as st
import pandas as pd
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# data/statcast/, NOT data/ — see the note in engines/savant_leaderboard.py.
# This read one directory too high, so _park_table() returned None and
# park_hr_adj() returned (0, None) for every batter, league-wide. Park is
# the widest band in the whole matchup layer (+/-10) and it was inert.
_PARK_PATH = _DATA_DIR / "statcast" / "park_hr_factors.parquet"

# Bounded, like every other matchup component in engines/edge.py. Park is
# the single largest context effect, so it gets the widest band — but
# still a band. A raw venue rate carries some roster bias (Coors reads
# high partly because Rockies hitters bat there), which a cap contains
# and a multiplier would not.
PARK_CAP = 10.0
# ~1 point per 10F away from a 70F baseline, capped at +/-4. Small on
# purpose: the direction is certain, the magnitude is not precisely
# known, and it should never outweigh the park.
TEMP_BASELINE_F = 70.0
TEMP_CAP = 4.0


@st.cache_data(ttl=21600, max_entries=1, show_spinner=False)
def _park_table():
    """{(park, hand): hr_index} or None when the nightly file is absent."""
    path = _PARK_PATH
    if not path.exists():
        # A data package predating the statcast/ layout — use it rather
        # than silently losing the table a second time.
        legacy = path.parent.parent / path.name
        if not legacy.exists():
            return None
        path = legacy
    try:
        t = pd.read_parquet(path)
        return {(str(r.park), str(r.hand)): float(r.hr_index)
                for r in t.itertuples(index=False)}
    except Exception:
        return None


def park_hr_adj(home_team_abbr, bats):
    """(adj, note) — tonight's park, for THIS batter's hand.

    home_team_abbr is Statcast's team code ("NYY", "BOS"), which is what
    the nightly build keys on. bats is "R" or "L".

    Switch hitters ("S") return 0: which side they bat depends on the
    pitcher, so the caller must resolve the effective hand first and
    pass R or L. Guessing here would silently apply the wrong park split
    to exactly the hitters it matters most for.

    Returns (0, None) when unmeasurable — no table yet, unknown park, or
    a park-hand cell under the sample floor. Never a fabricated number.
    """
    if not home_team_abbr or bats not in ("R", "L"):
        return 0, None
    table = _park_table()
    if not table:
        return 0, None
    idx = table.get((str(home_team_abbr), bats))
    if idx is None:
        return 0, None
    # index 100 = neutral. Scale the deviation into edge points.
    adj = (idx - 100.0) / 100.0 * PARK_CAP
    adj = round(max(-PARK_CAP, min(PARK_CAP, adj)), 1)
    if abs(adj) < 0.5:
        return 0, None
    hand = "LHB" if bats == "L" else "RHB"
    return adj, f"{home_team_abbr} park, {hand} ({idx:.0f} idx, {adj:+.1f})"


def _parse_temp(temp_str):
    """Degrees F from MLB's weather string, or None.

    Arrives as "78 degrees" or plain "78"; domes report things like
    "72 degrees, Roof Closed". Returns None rather than guessing so an
    unparseable value produces no adjustment instead of a wrong one.
    """
    if temp_str is None:
        return None
    import re
    m = re.search(r"(-?\d+)", str(temp_str))
    if not m:
        return None
    val = int(m.group(1))
    # Sanity band: anything outside this is a parse error, not weather.
    return val if -20 <= val <= 130 else None


def temp_hr_adj(temp_str, roof_closed=False):
    """(adj, note) — air density from temperature.

    Warm air is less dense, so the ball carries further; cold air holds
    it up. The direction is settled physics. Magnitude is kept small and
    capped because the precise per-degree effect isn't pinned down here.

    Under a closed roof the climate is controlled and outside air
    temperature is irrelevant, so this returns 0.
    """
    if roof_closed:
        return 0, None
    temp = _parse_temp(temp_str)
    if temp is None:
        return 0, None
    adj = (temp - TEMP_BASELINE_F) / 10.0
    adj = round(max(-TEMP_CAP, min(TEMP_CAP, adj)), 1)
    if abs(adj) < 0.5:
        return 0, None
    word = "warm air carries" if adj > 0 else "cold air holds it up"
    return adj, f"{temp}\u00b0F, {word} ({adj:+.1f})"


def context_hr_adj(home_team_abbr, bats, temp_str=None, roof_closed=False,
                   wind_str=None):
    """Combined park + temperature + wind adjustment for one batter.

    Returns (total, notes) with notes listing only the components that
    actually fired, so the UI can show why without inventing reasons.

    wind_str is optional and keyword-safe: callers that don't pass it get
    park and temperature exactly as before rather than an error.
    """
    p_adj, p_note = park_hr_adj(home_team_abbr, bats)
    t_adj, t_note = temp_hr_adj(temp_str, roof_closed=roof_closed)
    w_adj, w_note = 0, None
    if wind_str:
        from engines.wind_engine import wind_hr_adj
        w_adj, w_note = wind_hr_adj(home_team_abbr, wind_str,
                                    roof_closed=roof_closed)
    notes = [n for n in (p_note, t_note, w_note) if n]
    return round(p_adj + t_adj + w_adj, 1), notes
