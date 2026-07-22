"""
Pitcher trend — game-by-game results for any starter, from MLB's
OFFICIAL box-score game logs (statsapi), charted per stat and window.

Mirrors engines/batter_trends.py deliberately: same source, same
chart engine, same chip row — so a K trend reads exactly like a hit
trend. The Statcast parquets can produce strikeout counts but carry
no opponent team columns (they're trimmed on ingest), so the official
log is what makes opponent logos possible on this chart too.

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
from engines.team_logos import logo_url_by_id

EASTERN = ZoneInfo("America/New_York")
_URL = "https://statsapi.mlb.com/api/v1/people/{pid}/stats"

_STAT_KEY = {"Strikeouts": "k", "Earned Runs": "er", "Hits Allowed": "ha",
             "Walks": "bb", "Innings": "ip"}
_WIN_N = {"Season": None, "L25": 25, "L10": 10, "L5": 5}


@st.cache_data(ttl=1800, max_entries=32, show_spinner=False)
def _game_log_json(batter_id: int, season: int) -> str:
    try:
        resp = requests.get(
            _URL.format(pid=batter_id),
            params={"stats": "gameLog", "group": "pitching", "season": season},
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
            k = int(stat.get("strikeOuts", 0))
            er = int(stat.get("earnedRuns", 0))
            ha = int(stat.get("hits", 0))
            bb = int(stat.get("baseOnBalls", 0))
        except Exception:
            continue
        # MLB reports IP as "6.2" meaning 6 and 2/3 — convert to a real
        # number so the chart and averages aren't quietly wrong.
        ip_raw = str(stat.get("inningsPitched", "0") or "0")
        try:
            whole, _, frac = ip_raw.partition(".")
            ip = int(whole) + (int(frac) / 3.0 if frac else 0.0)
        except Exception:
            ip = 0.0
        opp = (sp.get("opponent") or {})
        opp_label = opp.get("abbreviation") or opp.get("teamName") or opp.get("name") or ""
        games.append({"date": sp.get("date", ""), "opp": opp_label,
                      "opp_id": opp.get("id"),
                      "k": k, "er": er, "ha": ha, "bb": bb,
                      "ip": round(ip, 1)})
    games.sort(key=lambda g: g["date"])
    return json.dumps({"games": games, "error": None})


def render_pitcher_trend(pitcher_id, name, stat_label: str = "Strikeouts",
                        window_label: str = "L10", line: float = 5.5) -> None:
    """Window chips (cleared/total per window vs the chosen line) +
    labeled bar chart for the chosen window, + honest summary line."""
    season = datetime.now(EASTERN).year
    try:
        payload = json.loads(_game_log_json(int(pitcher_id), season))
    except Exception as e:
        st.warning(f"Couldn't load the game log ({e}).")
        return
    games, err = payload.get("games") or [], payload.get("error")
    if err:
        st.warning(err)
        return
    if not games:
        st.caption("No official game log for this pitcher yet this season.")
        return

    key = _STAT_KEY.get(stat_label, "k")
    all_vals = [g[key] for g in games]
    window_hit_chips(all_vals, line, window_label,
                     windows=("Season", "L25", "L10", "L5"))
    n = _WIN_N.get(window_label)
    sub = games if n is None else games[-n:]
    vals = [g[key] for g in sub]

    # Short x labels (dates only — the opponent shows as a LOGO under
    # each bar instead of a long team name). Doubleheader same-day
    # games get a suffix so two real games never merge into one bar.
    labels, seen, logos = [], {}, []
    for g in sub:
        base = g["date"][5:]
        seen[base] = seen.get(base, 0) + 1
        labels.append(base if seen[base] == 1 else f"{base} ({seen[base]})")
        logos.append(logo_url_by_id(g.get("opp_id")))

    render_trend_bars(labels, vals, stat_label, line, logos=logos)

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
