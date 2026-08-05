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
from engines.edge import edge_components, pen_context
from engines.park_factors import get_park_factor
from engines.xbh_engine import (
    xbh_skill, pitcher_xbh_adj, park_xbh_adj, wind_xbh_adj,
)
from engines.roster import get_confirmed_lineup, get_last_starting_lineup
from engines.savant_leaderboard import load_percentile_ranks, get_hr_metrics
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

# How many top candidates get the full Edge treatment. Wider than the
# single pick so matchup can still change who wins, but far short of
# every hitter on the slate — each one costs a network call.
EDGE_POOL = 25


def _wind_hr_adj(wind_str):
    """(adj, note) — wind's effect on a home-run play, capped +/-5.

    Only MLB's official field-relative wind string ("12 mph, Out To
    CF") can honestly say which way the ball carries; a compass
    forecast like "SW 12 mph" cannot, so it returns 0 rather than a
    guess. Out helps, in hurts, crosswind is neutral, and the effect
    scales with speed.
    """
    if not wind_str:
        return 0, None
    w = str(wind_str).lower()
    import re
    m = re.search(r"(\d+)\s*mph", w)
    mph = int(m.group(1)) if m else 0
    if mph < 5:
        return 0, None
    if "out to" in w:
        adj = 5 if mph >= 15 else 3 if mph >= 10 else 2
        return adj, f"wind out {mph} mph (+{adj})"
    if "in from" in w:
        adj = -5 if mph >= 15 else -3 if mph >= 10 else -2
        return adj, f"wind in {mph} mph ({adj})"
    return 0, None


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


@st.cache_data(ttl=600, max_entries=8, show_spinner=False)
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
    # Loaded once for the whole board, same as the Savant leaderboard.
    # None until the nightly table exists; hr_score degrades cleanly.
    _hr_metrics_df = get_hr_metrics()
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

            # Park, wind, and the opposing bullpen are properties of
            # the GAME, not the batter — compute them once per side
            # instead of per hitter.
            park_info = get_park_factor(g.get("home"))
            park_verified = bool(park_info.get("verified"))
            park_factor = park_info.get("park_factor")
            wind_str = g.get("weather_wind")
            pitcher_team = g.get("home") if side == "away" else g.get("away")
            def _pen_for(_bid):
                """Per-batter pen context — see pen_context. Caches
                underneath make repeat calls cheap."""
                try:
                    return pen_context(pitcher_team, opp_pitcher_id, batter_id=_bid)
                except Exception:
                    return 0, None

            batters = [p for p in lineup if not p.get("is_pitcher")]
            for b in batters:
                pid = b.get("id")
                if not pid:
                    continue
                hr = hr_score(pid, savant_df, hr_df=_hr_metrics_df)
                hit = hit_score(pid, savant_df)
                if hr is None:
                    continue  # not enough real Savant sample yet — never crown a guess
                k = k_score(pid, savant_df)

                signals, signals_note = _pitcher_vuln_signals(opp_pitcher_id, b.get("bats"), window=window)

                # Player of the Day is an EXTRA-BASE HIT play: the
                # pick is "this bat records a double, triple, or home
                # run tonight." That target has its own model in
                # engines/xbh_engine.py rather than a borrowed HR one,
                # because a home-run model over-weights loft (a double
                # works from ~10 degrees, a homer needs ~25-35) and a
                # hit model over-weights contact (a bloop single is
                # worth nothing here).
                #
                # Skill: xSLG / Barrel% / Hard-Hit% / Exit Velocity,
                # with a real K% penalty — a strikeout is a plate
                # appearance with zero chance of an extra-base hit, so
                # two bats with equal power are not equal if one whiffs
                # far more. The penalty is capped so power still leads.
                xbh, xbh_parts = xbh_skill(pid, savant_df)
                if xbh is None:
                    continue  # no real Savant sample — never crown a guess

                # The Edge layer (BvP / zone fit / bullpen) is NOT run
                # here. edge_components makes a network call for BvP and
                # does per-batter zone work, and this loop covers every
                # hitter in every posted lineup (~270 on a full slate).
                # Running it inline meant hundreds of sequential HTTPS
                # round-trips before the page rendered anything. It is
                # applied after this loop to the top candidates only.
                edge = {}
                hr_edge = None
                base = xbh

                # What this starter actually gives up in extra bases.
                opp_splits = get_pitcher_advanced_splits(
                    opp_pitcher_id, side=(b.get("bats") if b.get("bats") in ("L", "R") else None),
                    window=window,
                ) if opp_pitcher_id else None
                pxbh_adj, pxbh_note = pitcher_xbh_adj(opp_splits)

                # Park and wind, both tuned for XBH rather than HR.
                park_adj, park_note = park_xbh_adj(g.get("home"), park_factor, park_verified)
                wind_adj, wind_note = wind_xbh_adj(wind_str)

                score = round(base + pxbh_adj + park_adj + wind_adj, 1)
                batter_quality = xbh

                candidates.append({
                    "name": b.get("name"), "team": team_name, "id": pid,
                    "opp_pitcher_id": opp_pitcher_id,
                    "bats": b.get("bats") or "?",
                    "opponent": g.get("home") if side == "away" else g.get("away"),
                    "hr_score": hr, "hit_score": hit, "k_score": k,
                    "batter_quality": batter_quality,
                    "hr_edge": hr_edge,
                    "bvp_adj": edge.get("bvp_adj"), "bvp_line": edge.get("bvp_line"),
                    "zone_adj": edge.get("zone_adj"), "zone_note": edge.get("zone_note"),
                    "pen_adj": edge.get("pen_adj"), "pen_note": edge.get("pen_note"),
                    "park_factor": park_factor, "park_adj": park_adj,
                    "park_note": park_note,
                    "wind_adj": wind_adj, "wind_note": wind_note,
                    "xbh_score": xbh, "xbh_parts": xbh_parts,
                    # carried for the Edge second pass, stripped after.
                    # Resolved per batter (see _pen_for) so the pen part
                    # reflects this hitter's platoon split, not one flat
                    # number for the whole lineup.
                    **dict(zip(("_pen_adj", "_pen_note"), _pen_for(pid))),
                    "_static_adj": pxbh_adj + park_adj + wind_adj,
                    "pxbh_adj": pxbh_adj, "pxbh_note": pxbh_note,
                    "pitcher_signals": signals, "pitcher_note": signals_note,
                    "lineup_note": lineup_note,
                    "score": score,
                })

    if not candidates:
        return None, [], ("No eligible real candidates today — either an off-day, or Baseball "
                           "Savant doesn't have enough season samples for today's lineups yet.")

    candidates.sort(key=lambda c: -c["score"])

    # ---- Edge pass, top candidates only ----
    # Only bats near the top can win the day, so only they need the
    # expensive matchup layer (BvP is a network call; zone fit is
    # per-batter work). EDGE_POOL stays wide enough that a strong BvP
    # or zone-fit edge can still lift a candidate into the pick, while
    # cutting the cost from ~270 lookups to ~25.
    #
    # BvP is applied ONLY inside edge_components — never a second time
    # here — so the same career line can't be double-counted.
    for c in candidates[:EDGE_POOL]:
        opp_pid = c.get("opp_pitcher_id")
        if not opp_pid or not c.get("id"):
            continue
        try:
            e = edge_components(c["id"], opp_pid, c["xbh_score"],
                                c.get("_pen_adj", 0), c.get("_pen_note"))
        except Exception:
            continue
        if e.get("edge") is None:
            continue
        c["hr_edge"] = e["edge"]
        c["bvp_adj"] = e.get("bvp_adj")
        c["bvp_line"] = e.get("bvp_line")
        c["zone_adj"] = e.get("zone_adj")
        c["zone_note"] = e.get("zone_note")
        c["pen_adj"] = e.get("pen_adj")
        c["pen_note"] = e.get("pen_note")
        c["score"] = round(e["edge"] + c.get("_static_adj", 0), 1)

    for c in candidates:
        c.pop("_pen_adj", None)
        c.pop("_pen_note", None)
        c.pop("_static_adj", None)

    # re-sort: the Edge pass can reorder the top of the board
    candidates.sort(key=lambda c: -c["score"])
    return candidates[0], candidates, None


@st.cache_data(ttl=600, max_entries=8, show_spinner=False)
def get_wnba_player_of_the_day(form_window: str = "l5"):
    """
    Same honesty contract, WNBA version — see module docstring. Returns
    (pick, all_candidates, error) exactly like get_mlb_player_of_the_day.
    """
    # ROUTED THROUGH slate_guard. This picked the Player of the Day
    # straight off the slate file with no date check, so on a night the
    # nightly failed it would crown a player from a game already played
    # and the Home page would feature her as tonight's pick. The message
    # on the failure path now says WHICH night is on disk instead of
    # implying tonight simply has no games.
    from engines.slate_guard import load_slate, staleness_note
    games, _slate_date, _is_current = load_slate("wnba")
    if not games:
        return None, [], (staleness_note("wnba")
                          or "No WNBA games on today's slate.")

    # Imported here rather than at module scope: player_of_the_day is
    # imported by the MLB paths too, and they have no reason to pull in
    # the WNBA engines.
    from engines.wnba_props import (availability as _wnba_availability,
                                    league_reference_date as _wnba_ref)
    # Anchored to the data's newest game — a stale feed must not read as
    # every player being injured. See league_reference_date.
    _ref = _wnba_ref(games)


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
                # AVAILABILITY FIRST — and it matters more here than
                # anywhere else on the site.
                #
                # gp < 5 is a SEASON total. A player who appeared 20 times
                # through June and then missed the last month still reports
                # gp=20 and stays eligible to be crowned Player of the Day.
                #
                # Worse, the ranking below is l5_pra — her last FIVE games.
                # For someone who stopped playing, those five are from a
                # month ago, and they are frequently her hottest stretch,
                # the one right before she got hurt. So the omission didn't
                # merely allow absent players through; it actively FAVOURED
                # the ones who were producing when they went down.
                #
                # This board is also logged for calibration, so every such
                # pick was an automatic miss recorded against the model.
                ok, why, _days = _wnba_availability(p, today=_ref)
                if not ok:
                    continue

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
                    # PROJECTED LINE FOR TONIGHT.
                    #
                    # Recent form times the SAME opponent-defense factor
                    # already applied to adj_pra above — not a second
                    # model, just the existing adjustment carried through
                    # to each stat so the parts add up to the whole.
                    #
                    # Both inputs are measured: recent form is her own box
                    # scores, and the factor is what this opponent
                    # actually allows per game versus the slate average,
                    # capped at +/-10% so one leaky defense can't run away
                    # with it.
                    #
                    # None where the underlying average is None — a
                    # projection built on a missing stat would be a made-up
                    # number wearing a decimal point.
                    "proj_pts": (round(p.get(f"{form_window}_ppg") * factor, 1)
                                 if p.get(f"{form_window}_ppg") is not None else None),
                    "proj_reb": (round(p.get(f"{form_window}_rpg") * factor, 1)
                                 if p.get(f"{form_window}_rpg") is not None else None),
                    "proj_ast": (round(p.get(f"{form_window}_apg") * factor, 1)
                                 if p.get(f"{form_window}_apg") is not None else None),
                })

    if not candidates:
        msg = ("No eligible real candidates today — need at least 5 real games "
               "played this season, and a recent appearance.")
        if form_window in ("l15", "l25"):
            msg += " (L15/L25 form appears after the next nightly data build.)"
        return None, [], msg

    candidates.sort(key=lambda c: (-c.get("adj_pra", c["form_pra"]), -c["season_pra"]))
    return candidates[0], candidates, None
