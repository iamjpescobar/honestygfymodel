import streamlit as st
"""
WNBA Defense Matchup — who's facing the softest defense tonight.

Basketball has no starting-pitcher analog, so the honest equivalent of
"which pitcher is easiest to hit" is "which team bleeds production to
this player's position." That's what this board ranks.

Every number comes from the same real box-score logs the rest of the
WNBA page uses. For each team, the pipeline credits opponents with
what each POSITION (G / F / C) actually did against them, per game.
A guard facing the team allowing 44 points per game to guards is in a
measurably different spot than one facing the team allowing 31.

Ranked by MATCHUP EDGE: how far above the league-average allowance
tonight's opponent sits for this player's position, scaled by the
player's own recent production so a bench player facing a soft
defense doesn't outrank a starter facing an average one.

Sample floors, applied before anything ranks:
  - the opposing team needs >= 5 games of positional data (enforced
    in the pipeline)
  - the player needs >= 5 games played
Anything below that is listed as unrated with the reason, never
estimated.
"""


_STATS = {"Points": "pts", "Rebounds": "reb", "Assists": "ast"}
MIN_PLAYER_GP = 5


# Shared with wnba_props so both boards apply the identical rule — two
# copies of an availability policy is how they drift apart.
from engines.wnba_props import availability


def _league_average(games, stat_key):
    """Average allowance per position across every team on the slate —
    the baseline each matchup is measured against."""
    totals = {}
    for g in games:
        for side in ("away", "home"):
            for pos, d in (g.get(f"{side}_pos_def_allowed") or {}).items():
                if d.get(stat_key) is None:
                    continue
                totals.setdefault(pos, []).append(d[stat_key])
    return {pos: (sum(v) / len(v)) for pos, v in totals.items() if v}


@st.cache_data(ttl=1800, max_entries=24, show_spinner=False)
def _build_board_cached(_games, stat_label, window, cache_key):
    return _build_board(_games, stat_label, window)


def build_board(games, stat_label="Points", window="l10", cache_key=None):
    """(rows, unrated) ranked by matchup edge for the chosen stat.

    Cached for the same reason as wnba_props.build_props: the page script
    re-runs on every widget click, and re-ranking the slate each time is
    what made this board slow. See that docstring for why _games is
    unhashed and cache_key carries the build timestamp instead.
    """
    if cache_key is None:
        return _build_board(games, stat_label, window)
    return _build_board_cached(games, stat_label, window, cache_key)


def _build_board(games, stat_label="Points", window="l10"):
    """(rows, unrated) ranked by matchup edge for the chosen stat."""
    stat_key = _STATS.get(stat_label, "pts")
    league = _league_average(games, stat_key)
    rows, unrated = [], []

    for g in games:
        for side, opp_side in (("away", "home"), ("home", "away")):
            opp_def = g.get(f"{opp_side}_pos_def_allowed") or {}
            opp_name = g.get(opp_side, "?")
            for p in g.get(f"{side}_players") or []:
                name = p.get("name")
                if not name:
                    continue
                pos = (p.get("pos") or "").upper()[:1]
                gp = p.get("gp") or 0
                base = {"player": name, "pos": p.get("pos") or "?",
                        "team": g.get(side, "?"), "opp": opp_name,
                        # carried so the calibration tracker can grade
                        # these picks against real box scores
                        "id": p.get("pid") or p.get("id")}

                # AVAILABILITY FIRST — same reasoning as wnba_props.
                # MIN_PLAYER_GP is a season total and passes happily for
                # a player who last appeared a month ago. This board
                # feeds the calibration record, so an unavailable player
                # here doesn't just show a bad row: it logs a pick that
                # can never hit and drags the graded rate down for a
                # reason that has nothing to do with the model.
                ok, why, _days = availability(p)
                if not ok:
                    unrated.append({**base, "reason": why})
                    continue

                if gp < MIN_PLAYER_GP:
                    unrated.append({**base, "reason": f"only {gp} games played"})
                    continue
                if pos not in opp_def:
                    unrated.append({**base,
                                    "reason": f"no positional data yet for {opp_name} vs {pos or '?'}"})
                    continue

                allowed = opp_def[pos].get(stat_key)
                lg = league.get(pos)
                if allowed is None or not lg:
                    unrated.append({**base, "reason": "league baseline unavailable"})
                    continue

                # form: the player's own recent production in this stat
                form = p.get(f"{window}_{ 'ppg' if stat_key=='pts' else 'rpg' if stat_key=='reb' else 'apg'}")
                if form is None:
                    form = p.get("ppg" if stat_key == "pts" else
                                 "rpg" if stat_key == "reb" else "apg")
                if form is None:
                    unrated.append({**base, "reason": "no recent production on file"})
                    continue

                # Edge: how much softer than league average this
                # matchup is, expressed as a percentage, then scaled by
                # the player's own production so volume matters.
                soft_pct = (allowed - lg) / lg * 100.0
                edge = round(form * (1 + soft_pct / 100.0) - form, 2)

                rows.append({
                    **base,
                    "gp": gp,
                    "form": round(float(form), 1),
                    "allowed": round(float(allowed), 1),
                    "league": round(float(lg), 1),
                    "soft_pct": round(soft_pct, 1),
                    "edge": edge,
                    "def_gp": opp_def[pos].get("gp", 0),
                })

    rows.sort(key=lambda r: -r["edge"])
    return rows, unrated
