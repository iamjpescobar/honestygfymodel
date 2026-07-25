"""
Slate picks (pipeline side) — computes tonight's picks for calibration.

This runs inside the nightly build, right after the player parquets are
written, so it scores off exactly the data the app will serve.

It is deliberately a SIMPLIFIED, self-contained version of the app's
boards. It cannot import the app's engines (those depend on streamlit
and the app's caching), so it reimplements the ranking core:

  daily13  - qualifying hitters ranked by recent form (L15/L5 hit rate)
             against the opposing starter's real contact profile.
  hr_edge  - hitters ranked by barrel rate, hard-hit rate, and HR/FB
             from their own Statcast rows.

Because it's simplified, the tracked record measures the CORE ranking
signal rather than the app's full Edge stack (which adds BvP, zone
fit, and bullpen context at request time). That's stated plainly on
the calibration page: it's a floor on model quality, not a ceiling,
and it's consistent night to night, which is what makes a rate mean
anything.

Everything here reads real data: the parquets this build just wrote,
and MLB's official schedule and lineup feeds.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

EASTERN = ZoneInfo("America/New_York")
_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"

HIT_EVENTS = {"single", "double", "triple", "home_run"}

# floors mirror the app's boards
MIN_GAMES = 25
MIN_HIT_RATE = 50.0
MIN_BBE = 30          # batted balls before power rates are trusted
MIN_FB = 25           # fly balls before HR/FB is trusted

DAILY13_N = 13
HR_EDGE_N = 10


def _todays_games(date_str: str):
    """(games, all_team_ids) from MLB's official schedule, with
    probable pitchers where posted."""
    try:
        resp = requests.get(
            _SCHEDULE_URL,
            params={"sportId": 1, "date": date_str,
                    "hydrate": "probablePitcher,lineups"},
            timeout=20,
        )
        resp.raise_for_status()
        dates = resp.json().get("dates") or []
    except Exception as exc:
        print(f"[picks] could not fetch schedule ({exc})")
        return []
    games = []
    for d in dates:
        for g in d.get("games", []):
            teams = g.get("teams") or {}
            away, home = teams.get("away") or {}, teams.get("home") or {}
            lineups = g.get("lineups") or {}
            games.append({
                "away_id": ((away.get("team") or {}).get("id")),
                "home_id": ((home.get("team") or {}).get("id")),
                "away_name": ((away.get("team") or {}).get("abbreviation")
                              or (away.get("team") or {}).get("name")),
                "home_name": ((home.get("team") or {}).get("abbreviation")
                              or (home.get("team") or {}).get("name")),
                "away_sp": ((away.get("probablePitcher") or {}).get("id")),
                "home_sp": ((home.get("probablePitcher") or {}).get("id")),
                "away_lineup": [p.get("id") for p in (lineups.get("awayPlayers") or [])],
                "home_lineup": [p.get("id") for p in (lineups.get("homePlayers") or [])],
            })
    return games


def _roster_ids(team_id: int):
    try:
        resp = requests.get(
            f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster",
            params={"rosterType": "active"}, timeout=20,
        )
        resp.raise_for_status()
        roster = resp.json().get("roster") or []
    except Exception:
        return []
    out = []
    for p in roster:
        pos = ((p.get("position") or {}).get("abbreviation") or "")
        if pos == "P":
            continue
        pid = (p.get("person") or {}).get("id")
        name = (p.get("person") or {}).get("fullName")
        if pid:
            out.append((pid, name))
    return out


def _batter_form(data_dir: Path, pid: int):
    """(games, hit_games, l15_rate, l5_rate) from the batter's parquet."""
    path = data_dir / "batters" / f"{pid}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path, columns=["game_pk", "game_date", "events"])
    except Exception:
        return None
    if df.empty or "events" not in df.columns:
        return None
    per_game = []
    for _gpk, gdf in df.sort_values(["game_date", "game_pk"]).groupby("game_pk", sort=False):
        had_hit = bool(gdf["events"].dropna().isin(HIT_EVENTS).any())
        per_game.append((str(gdf["game_date"].iloc[0])[:10], had_hit))
    if not per_game:
        return None
    per_game.sort(key=lambda x: x[0])
    hits = [h for _d, h in per_game]
    games_n = len(hits)
    hit_games = sum(1 for h in hits if h)
    l15 = hits[-15:]
    l5 = hits[-5:]
    return (games_n, hit_games,
            sum(1 for h in l15 if h) / len(l15) * 100 if l15 else 0.0,
            sum(1 for h in l5 if h) / len(l5) * 100 if l5 else 0.0)


def _batter_power(data_dir: Path, pid: int):
    """(brl_pct, hh_pct, hrfb) from the batter's parquet, or None."""
    path = data_dir / "batters" / f"{pid}.parquet"
    if not path.exists():
        return None
    cols = ["type", "launch_speed", "launch_angle", "bb_type", "events"]
    try:
        df = pd.read_parquet(path, columns=[c for c in cols])
    except Exception:
        return None
    if df.empty or "type" not in df.columns:
        return None
    bbe = df[df["type"] == "X"]
    if len(bbe) < MIN_BBE:
        return None
    ev = pd.to_numeric(bbe.get("launch_speed"), errors="coerce")
    la = pd.to_numeric(bbe.get("launch_angle"), errors="coerce")
    hh = float((ev >= 95).mean() * 100)
    # Statcast barrel definition (simplified to its standard core):
    # 98+ mph with launch angle in the 26-30 band, widening with speed.
    barrel = ((ev >= 98) & (la >= 24) & (la <= 33)) | ((ev >= 104) & (la >= 20) & (la <= 38))
    brl = float(barrel.mean() * 100)
    hrfb = None
    if "bb_type" in bbe.columns and "events" in bbe.columns:
        fb = bbe[bbe["bb_type"] == "fly_ball"]
        if len(fb) >= MIN_FB:
            hrfb = float((fb["events"] == "home_run").mean() * 100)
    return brl, hh, hrfb


def _starter_contact(data_dir: Path, pid):
    """(ba_allowed, k_pct) from the pitcher's parquet, or (None, None)."""
    if not pid:
        return None, None
    path = data_dir / "pitchers" / f"{pid}.parquet"
    if not path.exists():
        return None, None
    try:
        df = pd.read_parquet(path, columns=["events"])
    except Exception:
        return None, None
    ev = df["events"].dropna() if "events" in df.columns else pd.Series(dtype=str)
    if ev.empty:
        return None, None
    ab_events = HIT_EVENTS | {"field_out", "strikeout", "strikeout_double_play",
                              "double_play", "grounded_into_double_play",
                              "force_out", "fielders_choice_out", "field_error"}
    ab = int(ev.isin(ab_events).sum())
    if ab < 100:
        return None, None
    hits = int(ev.isin(HIT_EVENTS).sum())
    ks = int(ev.isin({"strikeout", "strikeout_double_play"}).sum())
    return round(hits / ab, 3), round(ks / ab * 100, 1)


def build_picks(data_dir: Path, date_str: str = None):
    """(daily13_picks, hr_edge_picks) for tonight's slate."""
    date_str = date_str or datetime.now(EASTERN).strftime("%Y-%m-%d")
    games = _todays_games(date_str)
    if not games:
        print("[picks] no games on the schedule — nothing logged")
        return [], []

    hit_rows, power_rows = [], []
    for g in games:
        for side, opp_side in (("away", "home"), ("home", "away")):
            team_id = g[f"{side}_id"]
            team_name = g[f"{side}_name"]
            opp_sp = g[f"{opp_side}_sp"]
            if not team_id:
                continue
            sp_ba, sp_k = _starter_contact(data_dir, opp_sp)

            lineup = g[f"{side}_lineup"]
            if lineup:
                players = [(pid, None) for pid in lineup]
            else:
                players = _roster_ids(team_id)

            for pid, name in players:
                form = _batter_form(data_dir, pid)
                if form:
                    games_n, hit_games, l15_rate, l5_rate = form
                    rate = hit_games / games_n * 100 if games_n else 0.0
                    if games_n >= MIN_GAMES and rate >= MIN_HIT_RATE:
                        form_score = l15_rate * 0.75 + l5_rate * 0.25
                        # contact-friendly starters help a hit prop
                        matchup = 50.0
                        if sp_ba is not None:
                            matchup = max(0.0, min(100.0,
                                          (sp_ba - 0.200) / 0.100 * 100))
                        if sp_k is not None:
                            k_part = max(0.0, min(100.0, (32.0 - sp_k) / 18.0 * 100))
                            matchup = (matchup + k_part) / 2
                        hit_rows.append({
                            "id": pid, "name": name, "team": team_name,
                            "score": round(form_score * 0.6 + matchup * 0.4, 1),
                        })

                power = _batter_power(data_dir, pid)
                if power:
                    brl, hh, hrfb = power
                    score = brl * 2.0 + hh * 0.5
                    if hrfb is not None:
                        score += hrfb * 0.5
                    power_rows.append({
                        "id": pid, "name": name, "team": team_name,
                        "score": round(score, 1),
                    })

    hit_rows.sort(key=lambda r: -r["score"])
    power_rows.sort(key=lambda r: -r["score"])
    return hit_rows[:DAILY13_N], power_rows[:HR_EDGE_N]
