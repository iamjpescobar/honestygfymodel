"""
Batter trend — game-by-game results for any hitter, from MLB's OFFICIAL
box-score game logs (statsapi), charted per stat and window.

Why statsapi and not this app's Statcast parquets: the parquets can
answer hits and home runs per game, but they carry no score or
baserunning columns, so RBI and runs simply are not derivable from
them — and this app does not derive what the data can't support. The
official game log carries H, HR, RBI, and R per game, which also makes
the H+R+RBI combo real.

Stats: Hits, 1B, 2B, 3B, HR, RBI, Runs, Total Bases, Walks, Strikeouts,
H+R+RBI.
Windows: 2026 / 2025 / H2H (vs tonight's opponent) / L25 / L15 / L5.

Cached as JSON strings (always pickle-serializable), 30 minutes, on
demand per batter — nothing is fetched until a batter is picked.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from engines.roster import _get_json

from engines.trend_chart import window_hit_chips, render_trend_bars
from engines.team_logos import logo_url_by_id

EASTERN = ZoneInfo("America/New_York")
_URL = "https://statsapi.mlb.com/api/v1/people/{pid}/stats"

_STAT_KEY = {
    "Hits": "h", "1B": "b1", "2B": "b2", "3B": "b3", "HR": "hr",
    "RBI": "rbi", "Runs": "r", "Total Bases": "tb", "Walks": "bb",
    "Strikeouts": "k", "H+R+RBI": "hrr",
}
# Count-style windows (last N games). Season/year and H2H are handled
# separately because they change WHICH games are pulled, not just how
# many of the loaded set to show.
_WIN_N = {"L25": 25, "L15": 15, "L5": 5}


@st.cache_data(ttl=1800, max_entries=32, show_spinner=False)
def _game_log_json(batter_id: int, season: int) -> str:
    try:
        data = _get_json(
            _URL.format(pid=batter_id),
            params={"stats": "gameLog", "group": "hitting", "season": season},
        ) or {}
        stats = data.get("stats") or []
        splits = (stats[0].get("splits") if stats else []) or []
    except Exception as e:
        return json.dumps({"games": [], "error": f"Game log request failed: {e}"})

    games = []
    for sp in splits:
        stat = sp.get("stat", {}) or {}
        try:
            h = int(stat.get("hits", 0))
            b2 = int(stat.get("doubles", 0))
            b3 = int(stat.get("triples", 0))
            hr = int(stat.get("homeRuns", 0))
            b1 = h - b2 - b3 - hr  # singles = hits minus extra-base hits
            rbi = int(stat.get("rbi", 0))
            r = int(stat.get("runs", 0))
            ab = int(stat.get("atBats", 0))
            bb = int(stat.get("baseOnBalls", 0))
            k = int(stat.get("strikeOuts", 0))
            # Total bases: use the official field if present, else derive.
            tb = stat.get("totalBases")
            tb = int(tb) if tb is not None else (b1 + 2 * b2 + 3 * b3 + 4 * hr)
        except Exception:
            continue
        if b1 < 0:  # guard against any odd box-score rounding
            b1 = 0
        opp = (sp.get("opponent") or {})
        opp_label = opp.get("abbreviation") or opp.get("teamName") or opp.get("name") or ""
        games.append({"date": sp.get("date", ""), "opp": opp_label,
                      "opp_id": opp.get("id"),
                      "h": h, "b1": b1, "b2": b2, "b3": b3, "hr": hr,
                      "rbi": rbi, "r": r, "ab": ab, "bb": bb, "k": k, "tb": tb,
                      "hrr": h + r + rbi})
    games.sort(key=lambda g: g["date"])
    return json.dumps({"games": games, "error": None})


def render_batter_trend(batter_id, name, stat_label: str = "Hits",
                        window_label: str = "L15", line: float = 0.5,
                        opp_id=None, opp_label: str = "") -> None:
    """Window chips (cleared/total per window vs the chosen line) +
    labeled bar chart for the chosen window, + honest summary line.

    Windows:
      2026 / 2025  — that full season's game log
      H2H          — this hitter's games vs tonight's opponent (opp_id),
                     across the seasons loaded; a real but often small
                     sample, so it's shown with its game count and never
                     padded
      L25 / L15 / L5 — the last N games of the current season
    """
    this_year = datetime.now(EASTERN).year
    prev_year = this_year - 1

    def _load(season):
        try:
            return json.loads(_game_log_json(int(batter_id), season)).get("games") or []
        except Exception:
            return []

    # Decide which season(s) to pull for the chosen window.
    if window_label == str(prev_year):
        games = _load(prev_year)
    elif window_label == "H2H":
        # Pull both seasons so H2H isn't limited to this year's meetings.
        games = _load(this_year) + _load(prev_year)
        games.sort(key=lambda g: g["date"])
    else:
        games = _load(this_year)

    if not games:
        st.caption("No official game log for this batter in that window yet.")
        return

    key = _STAT_KEY.get(stat_label, "h")

    # Slice to the window.
    if window_label == "H2H":
        if not opp_label:
            st.caption("No opponent set for a head-to-head view.")
            return
        # Match on the opponent's abbreviation/name (the game log stores
        # both an opp_id and an abbreviation; matching on the text label
        # avoids a separate team-ID lookup and is robust to either side).
        _t = opp_label.strip().lower()
        sub = [g for g in games
               if _t and (_t == str(g.get("opp", "")).strip().lower()
                          or (opp_id is not None and g.get("opp_id") == opp_id))]
        if not sub:
            st.caption(
                f"No games on record for {name} vs "
                f"{opp_label} in {prev_year}\u2013{this_year}."
            )
            return
    elif window_label in _WIN_N:
        sub = games[-_WIN_N[window_label]:]
    else:
        # a full-year window (2026 / 2025) — show every game that season
        sub = games

    # Window chips run off the SAME loaded games, using the windows that
    # make sense for the current view (last-N chips always apply).
    all_vals = [g[key] for g in games]
    window_hit_chips(all_vals, line, window_label if window_label in _WIN_N else "L15",
                     windows=("L25", "L15", "L5"))

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
    avg = sum(vals) / total_games if total_games else 0.0
    last5 = [g[key] for g in sub[-5:]]
    _win_desc = (f"H2H vs {opp_label}" if window_label == "H2H" else window_label)
    st.caption(
        f"{name} \u00b7 {_win_desc}: {total_games} games \u00b7 "
        f"avg {avg:.2f} {stat_label}/game \u00b7 line {line} \u00b7 "
        f"last 5: {', '.join(str(v) for v in last5)} \u00b7 "
        f"teal bars cleared the line, red didn't \u00b7 "
        f"Source: MLB official box-score game logs."
    )
