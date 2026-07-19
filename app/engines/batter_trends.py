"""
Batter trend — game-by-game results for any hitter, from MLB's OFFICIAL
box-score game logs (statsapi), charted per stat and window.

Why statsapi and not this app's Statcast parquets: the parquets can
answer hits and home runs per game, but they carry no score or
baserunning columns, so RBI and runs simply are not derivable from
them — and this app does not derive what the data can't support. The
official game log carries H, HR, RBI, and R per game, which also makes
the H+R+RBI combo real.

Stats: Hits, HR, RBI, H+R+RBI.
Windows: Season / L25 / L10 / L5 (L10 is the default in the UI).

Cached as JSON strings (always pickle-serializable), 30 minutes, on
demand per batter — nothing is fetched until a batter is picked.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from styles.kc_theme import COLOR
from engines.trend_chart import window_hit_chips, render_trend_bars

EASTERN = ZoneInfo("America/New_York")
_URL = "https://statsapi.mlb.com/api/v1/people/{pid}/stats"

_STAT_KEY = {"Hits": "h", "HR": "hr", "RBI": "rbi", "H+R+RBI": "hrr"}
_WIN_N = {"Season": None, "L25": 25, "L10": 10, "L5": 5}


@st.cache_data(ttl=1800, max_entries=32, show_spinner=False)
def _game_log_json(batter_id: int, season: int) -> str:
    try:
        resp = requests.get(
            _URL.format(pid=batter_id),
            params={"stats": "gameLog", "group": "hitting", "season": season},
            timeout=10,
        )
        resp.raise_for_status()
        stats = resp.json().get("stats") or []
        splits = (stats[0].get("splits") if stats else []) or []
    except Exception as e:
        return json.dumps({"games": [], "error": f"Game log request failed: {e}"})

    games = []
    for sp in splits:
        stat = sp.get("stat", {}) or {}
        try:
            h = int(stat.get("hits", 0))
            hr = int(stat.get("homeRuns", 0))
            rbi = int(stat.get("rbi", 0))
            r = int(stat.get("runs", 0))
            ab = int(stat.get("atBats", 0))
        except Exception:
            continue
        opp = (sp.get("opponent") or {})
        opp_label = opp.get("abbreviation") or opp.get("teamName") or opp.get("name") or ""
        games.append({"date": sp.get("date", ""), "opp": opp_label,
                      "h": h, "hr": hr, "rbi": rbi, "r": r, "ab": ab,
                      "hrr": h + r + rbi})
    games.sort(key=lambda g: g["date"])
    return json.dumps({"games": games, "error": None})


def render_batter_trend(batter_id, name, stat_label: str = "Hits",
                        window_label: str = "L10", line: float = 0.5) -> None:
    """Window chips (cleared/total per window vs the chosen line) +
    labeled bar chart for the chosen window, + honest summary line."""
    season = datetime.now(EASTERN).year
    try:
        payload = json.loads(_game_log_json(int(batter_id), season))
    except Exception as e:
        st.warning(f"Couldn't load the game log ({e}).")
        return
    games, err = payload.get("games") or [], payload.get("error")
    if err:
        st.warning(err)
        return
    if not games:
        st.caption("No official game log for this batter yet this season.")
        return

    key = _STAT_KEY.get(stat_label, "h")
    all_vals = [g[key] for g in games]
    window_hit_chips(all_vals, line, window_label,
                     windows=("Season", "L25", "L10", "L5"))
    n = _WIN_N.get(window_label)
    sub = games if n is None else games[-n:]
    vals = [g[key] for g in sub]

    # Unique x labels — doubleheader same-day games get a suffix so the
    # chart never merges two real games into one bar.
    labels, seen = [], {}
    for g in sub:
        base = f'{g["date"][5:]} {g["opp"]}'.strip()
        seen[base] = seen.get(base, 0) + 1
        labels.append(base if seen[base] == 1 else f"{base} ({seen[base]})")

    render_trend_bars(labels, vals, stat_label, line)

    total_games = len(vals)
    avg = sum(vals) / total_games
    last5 = [g[key] for g in games[-5:]]
    st.caption(
        f"{name} \u00b7 {window_label}: {total_games} games \u00b7 "
        f"avg {avg:.2f} {stat_label}/game \u00b7 line {line} \u00b7 "
        f"last 5: {', '.join(str(v) for v in last5)} \u00b7 "
        f"teal bars cleared the line, red didn't \u00b7 "
        f"Source: MLB official box-score game logs."
    )
