"""
Player of the Day — MLB and WNBA.

HONESTY CONTRACT (read this before trusting a pick):
Every INPUT here is real and already used elsewhere in this app — real
Baseball Savant percentiles (engines/top_plays.py), real pitcher splits
computed from raw Statcast rows (engines/statcast_engine.py), real
today's lineups (engines/roster.py), and real WNBA box-score data
(wnba_precompute.py). Nothing here is fabricated, estimated, or
back-filled when a real number is missing.

The RANKING FORMULA on top of those real inputs is this app's OWN
transparent heuristic — a "best real matchup edge by the numbers," not
a calibrated prediction and not a guarantee of anything:

    MLB score = avg(HR Score, Hit Score)            [real Savant percentiles, 0-100]
              + 10 x (number of real pitcher-weakness
                       signals that fire against this batter)

    Pitcher-weakness signals use the SAME thresholds this app's own
    Matchup Grades already use (engines/matchup_grades.py), filtered to
    this batter's real bat side when it's known:
        WHIP  >= 1.30
        HR/9  >= 1.20
        SLG   >= .420

    WNBA score = L5 PRA (points + rebounds + assists over the player's
    real last 5 games) — recent real form, not a season number alone,
    so a currently-hot player outranks someone coasting on stats from
    a hot streak that's since cooled. Season PRA is the tiebreaker.

Eligibility (no small-sample crownings, ever):
  MLB  — batter must be in today's REAL confirmed lineup, or (if MLB
         hasn't posted it yet) their team's real last starting lineup.
         Baseball Savant must have enough plate appearances tracked on
         them this season to compute BOTH HR Score and Hit Score.
  WNBA — player must have played at least 5 real games this season.

K Score (a real Savant Whiff% percentile) is shown as a caution flag
on the MLB pick, never folded into the score — it's a risk signal, not
an opportunity signal, and mixing the two directions into one number
would make it harder to trust, not easier.
"""
import json
from pathlib import Path

import streamlit as st

from engines.weather_engine import get_todays_games_with_weather
from engines.roster import get_confirmed_lineup, get_last_starting_lineup
from engines.savant_leaderboard import load_percentile_ranks
from engines.top_plays import hr_score, hit_score, k_score
from engines.statcast_engine import get_pitcher_advanced_splits

# Same thresholds engines/matchup_grades.py already uses for "starter is
# vulnerable" over/under signals — reused here rather than inventing new
# ones, so the two features never quietly disagree about what "bad" means.
PITCHER_VULN_CHECKS = [
    ("WHIP", 1.30),
    ("HR/9", 1.20),
    ("SLG", 0.420),
]

_WNBA_GAMES = Path(__file__).resolve().parent.parent / "data" / "wnba" / "games.json"


def _pitcher_vuln_signals(pitcher_id, batter_bats):
    """
    Real signals only. Returns (signals, note) — note explains WHY there
    are zero signals when that's because of missing data, so the page
    can tell "this pitcher has no real weaknesses" apart from "we don't
    have real data on this pitcher yet." Never treats missing data as a
    silent zero.
    """
    if not pitcher_id:
        return [], "Opposing starter not posted yet."

    side = batter_bats if batter_bats in ("L", "R") else None
    splits = get_pitcher_advanced_splits(pitcher_id, side=side)
    if splits.get("_error"):
        return [], splits["_error"]

    signals = []
    for label, thresh in PITCHER_VULN_CHECKS:
        v = splits.get(label)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue  # a real 0.0 here almost always means no real pitches for this split, not a literal zero stat
        if v >= thresh:
            signals.append(f"{label} {v:g} (>= {thresh:g})")
    return signals, None


@st.cache_data(ttl=600, show_spinner=False)
def get_mlb_player_of_the_day():
    """
    Returns (pick, all_candidates, error).
    pick: the top-ranked real candidate dict, or None if nothing
    qualified today (off-day, or Savant doesn't have season samples yet).
    all_candidates: the full ranked list, so a page can show a top 5
    instead of just the single pick.
    """
    games, games_error = get_todays_games_with_weather()
    if games_error:
        return None, [], games_error
    if not games:
        return None, [], "No MLB games on today's schedule."

    savant_df, savant_error = load_percentile_ranks()
    if savant_df is None or savant_df.empty:
        return None, [], f"Baseball Savant percentile data isn't reachable right now ({savant_error})."

    candidates = []
    for g in games:
        sides = [
            ("away", g.get("away"), g.get("home_pitcher_id")),
            ("home", g.get("home"), g.get("away_pitcher_id")),
        ]
        for side, team_name, opp_pitcher_id in sides:
            if not team_name or team_name == "TBD":
                continue

            lineup, confirmed = get_confirmed_lineup(g.get("game_pk"), side)
            lineup_note = "Today's confirmed lineup"
            if not confirmed:
                lineup, _, last_confirmed = get_last_starting_lineup(team_name)
                lineup_note = "Team's last real starting lineup (today's not posted yet)"
                if not last_confirmed:
                    continue  # no real lineup source available for this team right now

            batters = [p for p in lineup if not p.get("is_pitcher")]
            for b in batters:
                pid = b.get("id")
                if not pid:
                    continue
                hr = hr_score(pid, savant_df)
                hit = hit_score(pid, savant_df)
                if hr is None or hit is None:
                    continue  # not enough real Savant sample yet — never crown a guess
                k = k_score(pid, savant_df)

                signals, signals_note = _pitcher_vuln_signals(opp_pitcher_id, b.get("bats"))
                batter_quality = round((hr + hit) / 2, 1)
                score = round(batter_quality + 10 * len(signals), 1)

                candidates.append({
                    "name": b.get("name"), "team": team_name, "id": pid,
                    "bats": b.get("bats") or "?",
                    "opponent": g.get("home") if side == "away" else g.get("away"),
                    "hr_score": hr, "hit_score": hit, "k_score": k,
                    "batter_quality": batter_quality,
                    "pitcher_signals": signals, "pitcher_note": signals_note,
                    "lineup_note": lineup_note,
                    "score": score,
                })

    if not candidates:
        return None, [], ("No eligible real candidates today — either an off-day, or Baseball "
                           "Savant doesn't have enough season samples for today's lineups yet.")

    candidates.sort(key=lambda c: -c["score"])
    return candidates[0], candidates, None


@st.cache_data(ttl=600, show_spinner=False)
def get_wnba_player_of_the_day():
    """
    Same honesty contract, WNBA version — see module docstring. Returns
    (pick, all_candidates, error) exactly like get_mlb_player_of_the_day.
    """
    try:
        payload = json.loads(_WNBA_GAMES.read_text())
    except Exception as e:
        return None, [], f"WNBA data isn't available right now ({e})."

    games = payload.get("games", [])
    if not games:
        return None, [], "No WNBA games on today's slate."

    candidates = []
    for g in games:
        for side, opp_side in (("away", "home"), ("home", "away")):
            team_name = g.get(side, "")
            plist = g.get(f"{side}_players") or []
            for p in plist:
                gp = p.get("gp") or 0
                if gp < 5:
                    continue  # real games played, but too small a sample to crown
                l5_pra, season_pra = p.get("l5_pra"), p.get("pra")
                if l5_pra is None or season_pra is None:
                    continue
                candidates.append({
                    "name": p.get("name"), "team": team_name,
                    "opponent": g.get(opp_side, ""),
                    "pos": p.get("pos"), "gp": gp,
                    "l5_pra": l5_pra, "season_pra": season_pra,
                    "l5_ppg": p.get("l5_ppg"), "l5_rpg": p.get("l5_rpg"), "l5_apg": p.get("l5_apg"),
                })

    if not candidates:
        return None, [], "No eligible real candidates today — need at least 5 real games played this season."

    candidates.sort(key=lambda c: (-c["l5_pra"], -c["season_pra"]))
    return candidates[0], candidates, None
