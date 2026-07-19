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


def _pitcher_vuln_signals(pitcher_id, batter_bats, window: str = "season"):
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
    splits = get_pitcher_advanced_splits(pitcher_id, side=side, window=window)
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
def get_mlb_player_of_the_day(window: str = "season"):
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

                signals, signals_note = _pitcher_vuln_signals(opp_pitcher_id, b.get("bats"), window=window)
                batter_quality = round((hr + hit) / 2, 1)
                score = round(batter_quality + 10 * len(signals), 1)

                candidates.append({
                    "name": b.get("name"), "team": team_name, "id": pid,
                    "opp_pitcher_id": opp_pitcher_id,
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

    # Career BvP vs tonight's starter — official MLB vs-player split,
    # checked for the TOP 10 candidates only (one API call each,
    # cached 6h). Documented, capped adjustment worth exactly one
    # signal on the existing scale:
    #   +10 when PA >= 8 and SLG >= .500 (real career damage vs him)
    #   -10 when PA >= 10 and AVG <= .150 (real career futility)
    # Smaller samples or anything in between changes nothing; the raw
    # line is attached to the candidate either way so the page can
    # show it.
    from engines.bvp import career_bvp
    for c in candidates[:10]:
        opp_pid = c.get("opp_pitcher_id")
        if not opp_pid:
            continue
        d = career_bvp(c["id"], opp_pid)
        if not d or not d.get("ab"):
            continue
        avg, slg, pa = d.get("avg"), d.get("slg"), d.get("pa", 0)
        line = f'{d["h"]}-for-{d["ab"]}, {d["hr"]} HR ({pa} PA)'
        c["bvp_line"] = line
        if pa >= 8 and slg is not None and slg >= 0.500:
            c["score"] = round(c["score"] + 10, 1)
            c["pitcher_signals"] = list(c.get("pitcher_signals") or []) + [
                f"Career BvP edge vs this starter: {line}, SLG {slg:.3f}"]
        elif pa >= 10 and avg is not None and avg <= 0.150:
            c["score"] = round(c["score"] - 10, 1)
            c["pitcher_signals"] = list(c.get("pitcher_signals") or []) + [
                f"Career BvP struggle vs this starter: {line}, AVG {avg:.3f}"]
    candidates.sort(key=lambda c: -c["score"])
    return candidates[0], candidates, None


@st.cache_data(ttl=600, show_spinner=False)
def get_wnba_player_of_the_day(form_window: str = "l5"):
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


    # Slate-average points allowed, for the opponent-defense factor.
    _pa_vals = []
    for _g in games:
        for _s in ("away", "home"):
            _v = _g.get(f"{_s}_pa_pg")
            if _v:
                _pa_vals.append(float(_v))
    slate_pa_avg = (sum(_pa_vals) / len(_pa_vals)) if _pa_vals else None
    candidates = []
    for g in games:
        for side, opp_side in (("away", "home"), ("home", "away")):
            team_name = g.get(side, "")
            plist = g.get(f"{side}_players") or []
            for p in plist:
                gp = p.get("gp") or 0
                if gp < 5:
                    continue  # real games played, but too small a sample to crown
                form_pra, season_pra = p.get(f"{form_window}_pra"), p.get("pra")
                if form_pra is None or season_pra is None:
                    continue
                # Opponent-defense context: how many points the opponent
                # actually allows per game vs the slate average, capped
                # to +/-10% so one leaky defense can't swing the pick by
                # itself. Real box-score-derived numbers; the factor is
                # shown on the pick.
                opp_pa = g.get(f"{opp_side}_pa_pg")
                factor = 1.0
                if opp_pa and slate_pa_avg:
                    factor = min(max(float(opp_pa) / slate_pa_avg, 0.9), 1.1)
                candidates.append({
                    "name": p.get("name"), "team": team_name,
                    "opponent": g.get(opp_side, ""),
                    "pos": p.get("pos"), "gp": gp,
                    "form_window": form_window,
                    "form_pra": form_pra, "season_pra": season_pra,
                    "adj_pra": round(form_pra * factor, 1),
                    "def_factor": round(factor, 3),
                    "opp_pa_pg": opp_pa,
                    "slate_pa_avg": round(slate_pa_avg, 1) if slate_pa_avg else None,
                    "form_ppg": p.get(f"{form_window}_ppg"),
                    "form_rpg": p.get(f"{form_window}_rpg"),
                    "form_apg": p.get(f"{form_window}_apg"),
                })

    if not candidates:
        msg = "No eligible real candidates today — need at least 5 real games played this season."
        if form_window in ("l15", "l25"):
            msg += " (L15/L25 form appears after the next nightly data build.)"
        return None, [], msg

    candidates.sort(key=lambda c: (-c.get("adj_pra", c["form_pra"]), -c["season_pra"]))
    return candidates[0], candidates, None
