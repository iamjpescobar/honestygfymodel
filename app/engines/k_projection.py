"""
Projected strikeout lines for every posted probable starter on today's
slate.

TRANSPARENT FORMULA — no black box, every input shown in the UI:

    proj_K = (K/9 / 9) * (season est IP / starts) * opp_factor

    opp_factor = opposing team's season K% / league K%,
                 clamped to [0.85, 1.15] so one extreme lineup can't
                 swing a projection by more than 15% either way.

Every input is real:
  - K/9 and estimated IP come from the pitcher's own Statcast rows
    (the exact same engine that powers the Splits table on the Game
    Card — get_pitcher_advanced_splits).
  - Team and league K% come from MLB's own season hitting stats
    (statsapi.mlb.com), fetched once and cached.

This is this app's own projection — NOT a sportsbook line and NOT a
certified prediction. Pitchers with no posted probable, or too little
Statcast data to project honestly, are listed with the reason instead
of a made-up number.

Caching note: the cached layers return JSON STRINGS (always
pickle-serializable), same pattern as engines/weather_engine.py.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from engines.weather_engine import get_todays_games_with_weather
from engines.statcast_engine import (
    get_pitcher_advanced_splits, get_pitcher_k_game_log_json,
)
from engines.team_abbreviations import team_abbr

EASTERN = ZoneInfo("America/New_York")
_TEAM_STATS_URL = "https://statsapi.mlb.com/api/v1/teams/stats"
_PLAYER_STATS_URL = "https://statsapi.mlb.com/api/v1/people/{pid}/stats"


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def _k_vs_team_json(pid: int, opp_team: str, season: int) -> str:
    """The pitcher's real strikeout counts in starts AGAINST this
    opponent, this season + last, from MLB official game logs.
    Returns {"avg", "n", "ks"} — n=0 means they simply haven't met."""
    ks = []
    for yr in (season, season - 1):
        try:
            resp = requests.get(
                _PLAYER_STATS_URL.format(pid=pid),
                params={"stats": "gameLog", "group": "pitching", "season": yr},
                timeout=10,
            )
            resp.raise_for_status()
            stats = resp.json().get("stats") or []
            splits = (stats[0].get("splits") if stats else []) or []
        except Exception:
            continue
        for sp in splits:
            if ((sp.get("opponent") or {}).get("name") or "") == opp_team:
                try:
                    ks.append(int((sp.get("stat") or {}).get("strikeOuts", 0)))
                except Exception:
                    pass
    if not ks:
        return json.dumps({"avg": None, "n": 0, "ks": []})
    return json.dumps({"avg": round(sum(ks) / len(ks), 1), "n": len(ks), "ks": ks})

# Minimum real work before a projection is honest enough to print.
_MIN_STARTS = 2
_MIN_IP = 6.0


@st.cache_data(ttl=21600, show_spinner=False)
def _team_k_rates_json() -> str:
    """Season K% (strikeouts / plate appearances) for every MLB team,
    plus the league rate, from MLB's own team hitting stats. Cached 6h —
    these rates move slowly. Returns a JSON string (pickle-proof)."""
    try:
        resp = requests.get(
            _TEAM_STATS_URL,
            params={"sportId": 1, "group": "hitting", "stats": "season"},
            timeout=10,
        )
        resp.raise_for_status()
        splits = resp.json()["stats"][0]["splits"]
    except Exception as e:
        return json.dumps(
            {"teams": {}, "league": None, "error": f"Team K-rate request failed: {e}"},
            default=str,
        )

    teams, total_k, total_pa = {}, 0, 0
    for sp in splits:
        try:
            name = sp["team"]["name"]
            k = int(sp["stat"]["strikeOuts"])
            pa = int(sp["stat"]["plateAppearances"])
        except Exception:
            continue
        if pa > 0:
            teams[name] = round(k / pa * 100, 2)
            total_k += k
            total_pa += pa

    league = round(total_k / total_pa * 100, 2) if total_pa > 0 else None
    return json.dumps({"teams": teams, "league": league, "error": None}, default=str)


@st.cache_data(ttl=900, show_spinner=False)
def _slate_projections_json(date_str: str, basis: str = "season") -> str:
    """Builds the full board for a date. Cached 15 min so the page is
    instant for everyone after the first load. Returns a JSON string."""
    games, games_error = get_todays_games_with_weather()
    if not games:
        return json.dumps(
            {"rows": [], "warning": games_error or "No games found for today."},
            default=str,
        )

    tk = json.loads(_team_k_rates_json())
    team_k, league_k, k_err = tk.get("teams", {}), tk.get("league"), tk.get("error")

    rows = []
    for g in games:
        matchup = f"{team_abbr(g.get('away', '?'))} @ {team_abbr(g.get('home', '?'))}"
        for side, opp_side in (("away", "home"), ("home", "away")):
            name = g.get(f"{side}_pitcher") or "TBD"
            pid = g.get(f"{side}_pitcher_id")
            team = g.get(side, "?")
            opp = g.get(opp_side, "?")
            row = {
                "matchup": matchup,
                "pitcher": name,
                "pid": pid,
                "team": team_abbr(team),
                "opp": team_abbr(opp),
                "ip_gs": None, "k9": None, "opp_k_pct": None,
                "factor": None, "proj": None, "status": None,
            }

            if not pid:
                row["status"] = "Probable not posted yet"
                rows.append(row)
                continue

            # basis="season": K/9 and IP/start from the full season —
            # a stable baseline, but by midseason it still carries
            # April ramp-up outings and short hooks, so it can run
            # under a starter's CURRENT strikeout pace.
            # basis="l10": same math on his last 10 appearances only —
            # tonight's actual leash and current form.
            sp = get_pitcher_advanced_splits(
                pid, window=("l10" if basis == "l10" else "season")
            )
            ip = float(sp.get("IP") or 0.0)
            k9 = float(sp.get("K/9") or 0.0)
            starts = int(sp.get("_games") or 0)

            if starts < _MIN_STARTS or ip < _MIN_IP:
                row["status"] = sp.get("_error") or (
                    f"Not enough Statcast data to project honestly "
                    f"({starts} game(s), {ip:.1f} est IP)"
                )
                rows.append(row)
                continue

            ip_per_start = ip / starts
            opp_k_pct = team_k.get(opp)
            factor = 1.0
            if opp_k_pct and league_k:
                factor = min(max(opp_k_pct / league_k, 0.85), 1.15)

            _vs = {"avg": None, "n": 0}
            try:
                _vs = json.loads(_k_vs_team_json(pid, opp, datetime.now(EASTERN).year))
            except Exception:
                pass
            l5_avg = None
            try:
                _log = json.loads(get_pitcher_k_game_log_json(pid))
                if _log:
                    _last5 = [e["k"] for e in _log[-5:]]
                    l5_avg = round(sum(_last5) / len(_last5), 1)
            except Exception:
                pass
            row.update({
                "vs_opp_avg": _vs.get("avg"),
                "vs_opp_n": _vs.get("n", 0),
                "l5_avg": l5_avg,
                "ip_gs": round(ip_per_start, 1),
                "k9": round(k9, 2),
                "opp_k_pct": opp_k_pct,
                "factor": round(factor, 3),
                "proj": round((k9 / 9.0) * ip_per_start * factor, 1),
            })
            rows.append(row)

    warning = None
    if k_err:
        warning = f"{k_err} — projections shown without the opponent adjustment (factor 1.0)."
    return json.dumps({"rows": rows, "warning": warning}, default=str)


def get_slate_k_projections(basis: str = "season"):
    """(rows, warning) for today's slate (US Eastern). basis:
    "season" (default, the original formula) or "l10" (same formula
    computed on each starter's last 10 appearances). Thin uncached
    wrapper around the JSON-string cache layer."""
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    try:
        payload = json.loads(_slate_projections_json(date_str, basis))
    except Exception as e:
        return [], f"Projection cache error: {e}"
    return payload.get("rows") or [], payload.get("warning")
