"""Per-reliever profiles for a team's bullpen, split by batter hand.

WHY THIS EXISTS.

Everything else on this site reads the STARTER. That research expires the
moment he's pulled — usually somewhere in the 5th or 6th — and roughly a
third of a hitter's plate appearances come after that, against arms
nobody has looked at. The edge module already folds a single pooled
bullpen HR/9 into the score, but one number for a whole pen answers
almost nothing you'd want to know when a reliever is warming up and
there's a live line on the board.

This is the missing half: every available reliever, what he actually
allows, and — the part that decides most late-game spots — what he allows
to LEFTIES versus RIGHTIES specifically. A pen whose only lefty has been
torched by right-handed bats is a completely different proposition
depending on who's due up, and no pooled team rate can express that.

Every number is computed from the pitcher's own Statcast rows by
get_pitcher_advanced_splits, the same function the Game Card's splits
tables use. Nothing here is estimated, and a reliever with no usable
sample against a given hand reports None rather than a filled-in guess.
"""
import json

import streamlit as st

from engines.roster import get_live_team_roster
from engines.statcast_engine import (
    get_pitcher_advanced_splits, get_pitcher_hand, get_pitcher_role,
)

# Stats surfaced per reliever, in display order. Keys match what
# get_pitcher_advanced_splits returns so nothing needs remapping.
#
# (key, label, higher_is_better_for_the_BATTER)
#
# The third field is from the HITTER's point of view on purpose: this
# board exists to answer "is this a good spot to bet the batter", so a
# high HR/9 allowed is GOOD here, the same way it reads as good on the
# Game Card's vulnerability tables.
PEN_STATS = [
    ("IP",         "IP",        None),
    ("BA",         "BA",        True),
    ("SLG",        "SLG",       True),
    ("ISO",        "ISO",       True),
    ("HR/9",       "HR/9",      True),
    ("WHIP",       "WHIP",      True),
    ("K%",         "K%",        False),
    ("BB%",        "BB%",       True),
    ("Whiff%",     "Whiff%",    False),
    ("SwStr%",     "SwStr%",    False),
    ("Putaway%",   "Putaway%",  False),
    ("Meatball%",  "Meatball%", True),
    ("1stPS%",     "1stPS%",    False),
]

# A reliever needs at least this many innings against a hand before his
# split is shown as a number. Below it the sample is noise, and a noisy
# ISO against lefties is exactly the kind of figure that looks like a
# signal and isn't.
MIN_SPLIT_IP = 5.0


@st.cache_data(ttl=1800, max_entries=64, show_spinner=False)
def _bullpen_json(team: str, starter_pid, window: str = "season") -> str:
    """Every available reliever on `team`, with overall and split lines.

    Mirrors the eligibility rules the edge module uses, deliberately, so
    this page and the score never disagree about who is in the bullpen:

      - active roster only (a 40-man carries IL and optioned arms who
        cannot pitch tonight)
      - relievers only, by get_pitcher_role
      - tonight's starter excluded

    Returns JSON because Streamlit caches it by value and a plain dict of
    dicts is cheaper to hand around as text.
    """
    out = []
    for p in (get_live_team_roster(team) or []):
        if not p.get("is_pitcher") or not p.get("id"):
            continue
        if starter_pid and p["id"] == starter_pid:
            continue
        if p.get("active") is False:
            continue
        if get_pitcher_role(p["id"]) != "RP":
            continue

        overall = get_pitcher_advanced_splits(p["id"], window=window) or {}
        if not (overall.get("IP") or 0):
            continue

        vs_r = get_pitcher_advanced_splits(p["id"], side="R", window=window) or {}
        vs_l = get_pitcher_advanced_splits(p["id"], side="L", window=window) or {}

        def _keep(split):
            """Blank a split that doesn't clear the innings floor.

            Returning the numbers anyway would put a 2-inning ISO on the
            board looking exactly like a 30-inning one.
            """
            if (split.get("IP") or 0) < MIN_SPLIT_IP:
                return {}
            return split

        out.append({
            "id": p["id"],
            "name": p.get("name") or "Unknown",
            "throws": get_pitcher_hand(p["id"]),
            "overall": overall,
            "vs_rhb": _keep(vs_r),
            "vs_lhb": _keep(vs_l),
        })

    # Most-used arms first: innings is the honest proxy for who actually
    # takes the ball in a close game.
    out.sort(key=lambda r: -(r["overall"].get("IP") or 0))
    return json.dumps(out)


def get_bullpen(team: str, starter_pid=None, window: str = "season"):
    """List of per-reliever dicts for a team. [] if nothing resolves."""
    try:
        return json.loads(_bullpen_json(team, starter_pid, window))
    except Exception:
        return []


def pen_totals(relievers):
    """Innings-weighted pen aggregate, plus the handedness mix.

    Weighted by IP rather than averaged across arms: a mop-up man with
    four innings should not move the number as much as the setup man with
    forty. A plain mean over relievers would let him.

    Returns None for any stat where nothing usable was found, rather than
    a zero that would read as a real value.
    """
    if not relievers:
        return {}
    tot_ip = sum((r["overall"].get("IP") or 0) for r in relievers)
    if tot_ip <= 0:
        return {}

    agg = {"IP": round(tot_ip, 1), "arms": len(relievers)}
    for key, _label, _hi in PEN_STATS:
        if key == "IP":
            continue
        num = 0.0
        seen = 0.0
        for r in relievers:
            v, ip = r["overall"].get(key), (r["overall"].get("IP") or 0)
            if v is None or ip <= 0:
                continue
            num += float(v) * ip
            seen += ip
        agg[key] = round(num / seen, 3) if seen > 0 else None

    lhp_ip = sum((r["overall"].get("IP") or 0) for r in relievers
                 if r.get("throws") == "L")
    agg["lhp_ip_share"] = round(lhp_ip / tot_ip, 3)
    agg["lhp_arms"] = sum(1 for r in relievers if r.get("throws") == "L")
    return agg


def worst_matchup(relievers, bats: str):
    """The reliever this hand of hitter has done the most damage to.

    `bats` is "L" or "R". Ranks on SLG allowed to that hand, because
    slugging is what a live home-run or extra-base bet actually needs —
    a high BA against with no power is a different story.

    Returns None when no reliever has a qualifying sample against that
    hand, which is common early in a season and is worth saying plainly
    rather than papering over.
    """
    side = "vs_lhb" if (bats or "").upper() == "L" else "vs_rhb"
    best, best_slg = None, None
    for r in relievers:
        slg = r.get(side, {}).get("SLG")
        if slg is None:
            continue
        if best_slg is None or slg > best_slg:
            best, best_slg = r, float(slg)
    return best
