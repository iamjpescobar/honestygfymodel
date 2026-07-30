"""
Pitchers to Target — every posted probable on today's slate, ranked by
how much power they're actually giving up.

All numbers come from each pitcher's own real Statcast rows, through
the same engines the Game Card uses:
  - HR, HR/9, ISO allowed, SLG allowed, Meatball% -> the splits engine
  - Brl% allowed, HH% allowed, FB% allowed        -> the batted-ball
    metrics engine (batter-perspective damage, read against a pitcher)

Ranking is deliberately simple and transparent: HR/9 allowed,
descending (the most direct "giving up the most HR" stat), with Brl%
allowed as the tiebreaker. No composite score, no weights to argue
with — every column is on the table and color-graded from the
BATTER's perspective (high = friendlier for power).

Basis: "season" (default) or "l10" — the same formula on the
pitcher's last 10 appearances, for current form.

Qualification: at least 3 appearances and 10 estimated IP in the
chosen basis; below that, the sample can't honestly rank and the
pitcher is listed with the reason instead.

Cached layers return JSON strings (always pickle-serializable).
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from engines.weather_engine import get_todays_games_with_weather
from engines.statcast_engine import (
    get_pitcher_advanced_splits, _get_pitcher_df, _compute_batted_ball_metrics,
    hand_tag,
)
from engines.recency_windows import apply_window
from engines.team_abbreviations import team_abbr

EASTERN = ZoneInfo("America/New_York")

_MIN_GAMES = 3
_MIN_IP = 10.0


@st.cache_data(ttl=900, max_entries=4, show_spinner=False)
def _targets_json(date_str: str, basis: str = "season") -> str:
    games, games_error = get_todays_games_with_weather()
    if not games:
        return json.dumps({"rows": [], "skipped": [],
                           "warning": games_error or "No games on today's slate."},
                          default=str)

    window = "l10" if basis == "l10" else "season"
    rows, skipped = [], []
    for g in games:
        matchup = f"{team_abbr(g.get('away', '?'))} @ {team_abbr(g.get('home', '?'))}"
        for side, opp_side in (("away", "home"), ("home", "away")):
            name = g.get(f"{side}_pitcher") or "TBD"
            pid = g.get(f"{side}_pitcher_id")
            # See k_projection: hand on the name, not a new column.
            _ht = hand_tag(pid)
            base = {"matchup": matchup,
                    "pitcher": f"{name} ({_ht})" if _ht else name,
                    "team": team_abbr(g.get(side, "?")),
                    "opp": team_abbr(g.get(opp_side, "?"))}
            if not pid:
                skipped.append({**base, "status": "Probable not posted yet"})
                continue

            sp = get_pitcher_advanced_splits(pid, window=window)
            ip = float(sp.get("IP") or 0.0)
            games_n = int(sp.get("_games") or 0)
            if games_n < _MIN_GAMES or ip < _MIN_IP:
                skipped.append({**base, "status": sp.get("_error") or (
                    f"Sample too small to rank honestly "
                    f"({games_n} game(s), {ip:.1f} est IP in this basis)")})
                continue

            # Batted-ball damage allowed, sliced to the same basis so
            # every column on the row describes the same games.
            brl = hh = fb = None
            try:
                df, _err = _get_pitcher_df(pid)
                if df is not None and not df.empty:
                    if window != "season":
                        df = apply_window(df, window, "games")
                    m = _compute_batted_ball_metrics(df)
                    brl, hh, fb = m.get("Brl %"), m.get("HH %"), m.get("FB %")
            except Exception:
                pass

            rows.append({
                **base,
                "ip": round(ip, 1),
                "hr": int(sp.get("HR") or 0),
                "hr9": sp.get("HR/9"),
                "iso": sp.get("ISO"),
                "slg": sp.get("SLG"),
                "brl": brl, "hh": hh, "fb": fb,
                "meatball": sp.get("Meatball%"),
            })

    rows.sort(key=lambda r: (-(r["hr9"] or 0), -(r["brl"] or 0)))
    return json.dumps({"rows": rows, "skipped": skipped, "warning": None},
                      default=str)


def get_pitchers_to_target(basis: str = "season"):
    """(rows, skipped, warning) for today's slate (US Eastern)."""
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    try:
        payload = json.loads(_targets_json(date_str, basis))
    except Exception as e:
        return [], [], f"Targets cache error: {e}"
    return (payload.get("rows") or [], payload.get("skipped") or [],
            payload.get("warning"))
