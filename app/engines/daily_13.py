"""
The Daily 13 — the 13 most consistent hitters on today's MLB slate.

For every hitter on every roster playing today, this scans his ENTIRE
game log in this app's Statcast files (the full current season — the
deepest real history the pipeline carries) and computes:

    hit rate = games with at least 1 hit / games played

Qualification bar, applied before ranking:
    - hit rate >= 60%
    - at least 25 games played (a 6-game 100% is noise, not
      consistency, and doesn't belong on this board)

The 13 highest qualifying rates make the board (games played breaks
ties). If fewer than 13 hitters clear the bar, the board shows fewer —
it does not pad with players below the minimum.

Honesty contract: this is HISTORICAL consistency measured from real
per-game outcomes. It is not a probability that a player gets a hit
tonight, and it ignores tonight's pitcher entirely by design — it's a
season-long reliability screen, meant to be crossed with the Game
Card's matchup work, not to replace it.

Caching: local-parquet reads only (no live pulls — scanning ~400
hitters through the network would take minutes; hitters without a
local file are counted and skipped). Cached layers return JSON strings
(always pickle-serializable), same pattern as weather_engine.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from engines.weather_engine import get_todays_games_with_weather
from engines.roster import get_live_team_roster
from engines.statcast_engine import _read_local_parquet, _HIT_EVENTS
from engines.team_abbreviations import team_abbr

EASTERN = ZoneInfo("America/New_York")

MIN_HIT_RATE = 60.0   # percent of games with >= 1 hit
MIN_GAMES = 25        # sample floor before a rate counts as "consistent"
BOARD_SIZE = 13


def _hit_log(pid):
    """(games_played, games_with_hit, active_streak) from the player's
    local parquet, or None when there's no usable file."""
    df = _read_local_parquet("batters", pid)
    if df is None or df.empty:
        return None
    if "events" not in df.columns or "game_pk" not in df.columns:
        return None
    per_game = []
    sort_cols = [c for c in ("game_date", "game_pk") if c in df.columns]
    for gpk, gdf in df.sort_values(sort_cols).groupby("game_pk", sort=False):
        had_hit = bool(gdf["events"].dropna().isin(_HIT_EVENTS).any())
        gdate = str(gdf["game_date"].iloc[0])[:10] if "game_date" in gdf.columns else ""
        per_game.append((gdate, had_hit))
    if not per_game:
        return None
    per_game.sort(key=lambda x: x[0])
    games_n = len(per_game)
    hit_games = sum(1 for _d, h in per_game if h)
    streak = 0
    for _d, h in reversed(per_game):
        if h:
            streak += 1
        else:
            break
    return games_n, hit_games, streak


@st.cache_data(ttl=1800, show_spinner=False)
def _daily13_json(date_str: str) -> str:
    games, games_error = get_todays_games_with_weather()
    if not games:
        return json.dumps({"rows": [], "scanned": 0, "qualified": 0,
                           "warning": games_error or "No games on today's slate."},
                          default=str)

    teams = []
    for g in games:
        for side in ("away", "home"):
            t = g.get(side)
            if t and t not in teams:
                teams.append(t)

    scanned, no_file = 0, 0
    qualified = []
    for team in teams:
        roster = get_live_team_roster(team) or []
        for p in roster:
            if p.get("is_pitcher") or not p.get("id"):
                continue
            scanned += 1
            log = _hit_log(p["id"])
            if log is None:
                no_file += 1
                continue
            games_n, hit_games, streak = log
            if games_n < MIN_GAMES:
                continue
            rate = hit_games / games_n * 100.0
            if rate < MIN_HIT_RATE:
                continue
            qualified.append({
                "name": p.get("name", "?"),
                "team": team_abbr(team),
                "gp": games_n,
                "hit_gp": hit_games,
                "rate": round(rate, 1),
                "streak": streak,
            })

    qualified.sort(key=lambda r: (-r["rate"], -r["gp"]))
    return json.dumps({
        "rows": qualified[:BOARD_SIZE],
        "scanned": scanned,
        "no_file": no_file,
        "qualified": len(qualified),
        "warning": games_error,
    }, default=str)


def get_daily_13():
    """(rows, meta) for today's slate (US Eastern)."""
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    try:
        payload = json.loads(_daily13_json(date_str))
    except Exception as e:
        return [], {"warning": f"Daily 13 cache error: {e}", "scanned": 0,
                    "qualified": 0, "no_file": 0}
    rows = payload.pop("rows", []) or []
    return rows, payload
