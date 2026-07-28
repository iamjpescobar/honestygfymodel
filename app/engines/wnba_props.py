"""
WNBA Props Board — the best prop bets on tonight's slate.

The basketball counterpart to the Daily 13, built on the same
philosophy: consistency qualifies you, tonight's specifics rank you.

For each player and each stat (Points / Rebounds / Assists / PRA /
3PM), the board asks how likely he is to clear a realistic line
tonight, using four real inputs:

  CONSISTENCY  35%  half how often he cleared the line over his last
                    15 and 10 games, half how often he stayed within
                    20% of it even when he missed. That second half is
                    the important one: a line set at a player's own
                    average is cleared ~50% of the time by anyone, so
                    only downside risk separates a steady 20-a-night
                    scorer from one alternating 2 and 38.
  FORM         25%  recent production vs his own season baseline
  MATCHUP      25%  how much this stat tonight's opponent allows to
                    his position, vs the slate average
  PACE         15%  the game's combined scoring environment vs the
                    slate average — more possessions, more chances

The line each player is measured against is his own recent AVERAGE
rounded to the nearest .5 — a realistic number rather than a
sportsbook's, since this app doesn't carry odds. (An average-based
line is the point: a volatile player and a steady one with the same
average clear it at very different rates, and that gap is the
signal.) That line is shown
on every row and is what the calibration tracker grades against.

Floors: 8 games played, 15 minutes per game, and 10 games of log
history. Below any of those a player is listed unrated with the
reason rather than ranked on noise.
"""

import streamlit as st
from datetime import datetime, timedelta, timezone

MIN_GP = 8
MIN_MPG = 15.0
MIN_LOG = 10

# ------------------------------------------------------------
# AVAILABILITY
#
# Every filter above is a SEASON TOTAL, and none of them knows what day
# it is. A player who appeared in 20 games through June and then missed
# the last 14 still reports gp=20, mpg=28, and 20 games of log — she
# clears every threshold and gets ranked on month-old numbers, against
# tonight's defense, as though she were playing.
#
# That is not a thin edge case. It is the single worst failure this page
# can have: a confident, well-formed prop on a player who is not in the
# building. Every other number on the row is correct, which is exactly
# what makes it dangerous.
#
# There is no injury feed here, and inventing one would mean trusting a
# scrape nobody verified. But the game log already answers the question
# directly: if a player has not appeared in a game recently, she is not
# available, whatever the reason. Measured, not guessed.
#
# STALE_DAYS is deliberately generous. The WNBA plays roughly every 2-3
# days, so a healthy rotation player appears within a few days; 8 days
# clears an All-Star break or a scheduled rest without flagging anyone,
# while still catching a genuine multi-week absence.
STALE_DAYS = 8
# Below this many minutes in her most recent appearance, she was on a
# minutes restriction or in garbage time — her season line no longer
# describes what she is being asked to do.
MIN_LAST_MIN = 8.0

W_CONSISTENCY = 0.35
W_FORM = 0.25
W_MATCHUP = 0.25
W_PACE = 0.15

STATS = {
    "Points": {"key": "pts", "season": "ppg", "l10": "l10_ppg", "l5": "l5_ppg",
               "def_key": "pts"},
    "Rebounds": {"key": "reb", "season": "rpg", "l10": "l10_rpg", "l5": "l5_rpg",
                 "def_key": "reb"},
    "Assists": {"key": "ast", "season": "apg", "l10": "l10_apg", "l5": "l5_apg",
                "def_key": "ast"},
    "PRA": {"key": "pra", "season": "pra", "l10": "l10_pra", "l5": "l5_pra",
            "def_key": None},
    "3PM": {"key": "tpm", "season": "tpm", "l10": "l10_tpm", "l5": "l5_tpm",
            "def_key": None},
}


def _scale(value, low, high):
    if value is None:
        return None
    try:
        v = (float(value) - low) / (high - low) * 100.0
    except Exception:
        return None
    return max(0.0, min(100.0, v))


def _line_for(values):
    """A realistic line: the player's recent AVERAGE rounded to the
    nearest .5 — the number a book would hang.

    Deliberately not the median: a median line is cleared ~50% of the
    time BY CONSTRUCTION, which would make the consistency component
    measure nothing (a wildly volatile player and a metronome would
    both score ~50%). An average-based line lets a consistent player
    clear it far more often than a boom-or-bust one with the same
    average, which is exactly the distinction this board exists to
    find."""
    if not values:
        return None
    avg = sum(values) / len(values)
    return round(avg * 2) / 2


def _clear_rate(values, line):
    if not values or line is None:
        return None
    return sum(1 for v in values if v > line) / len(values) * 100.0


def _floor_rate(values, line):
    """How often he stayed CLOSE to his number even when he missed it —
    within 20% below the line rather than collapsing.

    This is what "consistent" means for a prop: clear-rate against a
    player's own average is ~50% for everyone by construction, so it
    can't separate a metronome from a boom-or-bust scorer. Downside
    risk can. A 20-point-per-game player who never drops below 16 is a
    fundamentally safer prop than one averaging 20 on alternating
    2-and-38 nights, and this measures exactly that gap."""
    if not values or not line:
        return None
    floor = line * 0.8
    return sum(1 for v in values if v >= floor) / len(values) * 100.0


def _parse_log_date(value):
    """A date from a game-log entry, or None.

    Accepts ISO ("2026-07-27"), ISO datetimes, and the "2026-07-27T00:00:00Z"
    shape MLB-style feeds emit. Returns None rather than guessing on
    anything else — an unparseable date must not read as "played today".
    """
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for parse in (
        lambda t: datetime.fromisoformat(t),
        lambda t: datetime.strptime(t[:10], "%Y-%m-%d"),
    ):
        try:
            dt = parse(text)
            return dt.date()
        except (ValueError, TypeError):
            continue
    return None


def availability(player, today=None):
    """(ok, reason, days_since) — has this player actually been playing?

    The one question every season-total filter fails to ask. Returns
    ok=True when her most recent logged appearance is recent enough and
    substantial enough to believe her season line still applies.

    Deliberately fails OPEN when the log carries no usable dates: with no
    dates there is no evidence of absence, and silently dropping every
    player because a feed changed shape would be a worse bug than the one
    this fixes. It fails CLOSED — marking her unavailable — only on
    positive evidence: a real date that is too old, or a real last
    appearance too short to be a normal shift.
    """
    log = player.get("log") or []
    if not log:
        return False, "no game log", None

    dates = [(_parse_log_date(gl.get("date")), gl) for gl in log]
    dated = [(d, gl) for d, gl in dates if d is not None]
    if not dated:
        # No parseable dates anywhere — no evidence either way.
        return True, None, None

    today = today or datetime.now(timezone.utc).date()
    last_date, last_game = max(dated, key=lambda pair: pair[0])
    days = (today - last_date).days

    if days > STALE_DAYS:
        return False, f"hasn't played in {days} days (last game {last_date})", days

    last_min = last_game.get("min")
    if last_min is not None and last_min < MIN_LAST_MIN:
        return (False,
                f"only {last_min:.0f} min in her last game \u2014 restricted or "
                f"out of the rotation", days)

    return True, None, days


@st.cache_data(ttl=1800, max_entries=24, show_spinner=False)
def _build_props_cached(_games, stat_label, window, cache_key):
    return _build_props(_games, stat_label, window)


def build_props(games, stat_label="Points", window="l10", cache_key=None):
    """(rows, unrated) — every qualifying player ranked for this stat.

    CACHED, because Streamlit re-runs the whole page script on every
    widget interaction. Without this, tapping the Stat selector re-ranked
    every player on the slate from scratch — the reason these pages took
    so long to respond.

    `_games` is underscore-prefixed so Streamlit skips hashing it: it's a
    large list of nested dicts and hashing it would cost more than the
    work being cached. `cache_key` carries the data build's timestamp
    instead, which is what actually determines whether the result is
    stale. Callers that pass no key fall back to uncached behaviour
    rather than silently serving one slate's board for another's.
    """
    if cache_key is None:
        return _build_props(games, stat_label, window)
    return _build_props_cached(games, stat_label, window, cache_key)


def _build_props(games, stat_label="Points", window="l10"):
    """(rows, unrated) — every qualifying player ranked for this stat."""
    cfg = STATS.get(stat_label, STATS["Points"])
    key, def_key = cfg["key"], cfg["def_key"]

    # slate baselines: pace, and positional defense for this stat
    totals = [g.get("away_avg_total") for g in games if g.get("away_avg_total")]
    totals += [g.get("home_avg_total") for g in games if g.get("home_avg_total")]
    slate_pace = (sum(totals) / len(totals)) if totals else None

    def_pool = {}
    if def_key:
        for g in games:
            for side in ("away", "home"):
                for pos, d in (g.get(f"{side}_pos_def_allowed") or {}).items():
                    if d.get(def_key) is not None:
                        def_pool.setdefault(pos, []).append(d[def_key])
    league_def = {p: sum(v) / len(v) for p, v in def_pool.items() if v}

    rows, unrated = [], []
    for g in games:
        game_pace = None
        if g.get("away_avg_total") and g.get("home_avg_total"):
            game_pace = (g["away_avg_total"] + g["home_avg_total"]) / 2

        for side, opp_side in (("away", "home"), ("home", "away")):
            opp_def = g.get(f"{opp_side}_pos_def_allowed") or {}
            opp_name = g.get(opp_side, "?")
            for p in g.get(f"{side}_players") or []:
                name = p.get("name")
                if not name:
                    continue
                base = {"player": name, "pos": p.get("pos") or "?",
                        "team": g.get(side, "?"), "opp": opp_name}
                # AVAILABILITY FIRST. Checked before any season-total
                # threshold, because those all pass for a player who
                # stopped playing a month ago — see the note by
                # STALE_DAYS. Cheapest check and the one that matters
                # most, so it goes first.
                ok, why, days = availability(p)
                if not ok:
                    unrated.append({**base, "reason": why})
                    continue

                gp = p.get("gp") or 0
                mpg = p.get("min") or 0

                if gp < MIN_GP:
                    unrated.append({**base, "reason": f"only {gp} games played"})
                    continue
                if mpg and mpg < MIN_MPG:
                    unrated.append({**base, "reason": f"{mpg:.0f} min/game \u2014 below the {MIN_MPG:.0f} floor"})
                    continue

                log = p.get("log") or []
                vals = [gl.get(key) for gl in log if gl.get(key) is not None]
                if key == "pra" and not vals:
                    vals = [((gl.get("pts") or 0) + (gl.get("reb") or 0)
                             + (gl.get("ast") or 0)) for gl in log]
                if len(vals) < MIN_LOG:
                    unrated.append({**base,
                                    "reason": f"only {len(vals)} games of log history"})
                    continue

                l15, l10 = vals[-15:], vals[-10:]
                line = _line_for(l15)
                if line is None:
                    unrated.append({**base, "reason": "no line derivable"})
                    continue

                # ---- CONSISTENCY (35%) ----
                # Clear-rate says how often he beat the number; floor-rate
                # says how rarely he collapsed. Both matter, and the
                # floor is what separates a safe prop from a coin flip.
                r15 = _clear_rate(l15, line)
                r10 = _clear_rate(l10, line)
                f15 = _floor_rate(l15, line)
                consistency = None
                if r15 is not None and r10 is not None:
                    clear_part = _scale(r15 * 0.6 + r10 * 0.4, 30.0, 85.0)
                    floor_part = _scale(f15, 40.0, 95.0) if f15 is not None else None
                    if floor_part is None:
                        consistency = clear_part
                    else:
                        consistency = clear_part * 0.5 + floor_part * 0.5

                # ---- FORM (25%) ----
                season_v = p.get(cfg["season"])
                recent_v = p.get(cfg[window]) or p.get(cfg["l10"])
                form = None
                if season_v and recent_v:
                    form = _scale((recent_v - season_v) / season_v * 100.0, -25.0, 25.0)

                # ---- MATCHUP (25%) ----
                matchup, matchup_note = None, "no positional data for this stat"
                pos1 = (p.get("pos") or "").upper()[:1]
                if def_key and pos1 in opp_def and league_def.get(pos1):
                    allowed = opp_def[pos1].get(def_key)
                    lg = league_def[pos1]
                    if allowed is not None and lg:
                        soft = (allowed - lg) / lg * 100.0
                        matchup = _scale(soft, -20.0, 20.0)
                        matchup_note = (f"{opp_name} allows {allowed:.1f} to {pos1} "
                                        f"vs {lg:.1f} slate avg")

                # ---- PACE (15%) ----
                pace, pace_note = None, "pace unavailable"
                if game_pace and slate_pace:
                    diff = (game_pace - slate_pace) / slate_pace * 100.0
                    pace = _scale(diff, -12.0, 12.0)
                    pace_note = f"game total {game_pace:.0f} vs slate {slate_pace:.0f}"

                parts = [(consistency, W_CONSISTENCY), (form, W_FORM),
                         (matchup, W_MATCHUP), (pace, W_PACE)]
                live = [(v, w) for v, w in parts if v is not None]
                if not live:
                    unrated.append({**base, "reason": "no scoreable components"})
                    continue
                total_w = sum(w for _v, w in live)
                score = sum(v * w for v, w in live) / total_w

                rows.append({
                    **base,
                    "stat": stat_label,
                    "line": line,
                    "score": round(score, 1),
                    "l15_rate": round(r15, 0) if r15 is not None else None,
                    "l10_rate": round(r10, 0) if r10 is not None else None,
                    "l15_txt": f'{sum(1 for v in l15 if v > line)}/{len(l15)}',
                    "floor_txt": (f'{sum(1 for v in l15 if v >= line * 0.8)}/{len(l15)}'
                                  if line else "\u2014"),
                    "l10_txt": f'{sum(1 for v in l10 if v > line)}/{len(l10)}',
                    "form": round(form, 0) if form is not None else None,
                    "matchup": round(matchup, 0) if matchup is not None else None,
                    "pace": round(pace, 0) if pace is not None else None,
                    "why": " \u00b7 ".join([matchup_note, pace_note]),
                    "id": p.get("pid") or p.get("id"),
                })

    rows.sort(key=lambda r: -r["score"])
    return rows, unrated


# ------------------------------------------------------------
# LIKELY STARTERS
# ------------------------------------------------------------
# The WNBA feed publishes no starter flag, and unlike MLB there's no
# confirmed lineup posted hours before tip. So this is derived, and the
# derivation has to be honest about what it is: a very strong inference,
# not an announcement.
#
# RECENT minutes, not season minutes. That distinction is the whole
# point. A player promoted into the starting five two weeks ago still
# carries a low season average and would be ranked as a bench player by
# any season-total measure — the same class of mistake that had absent
# players clearing every filter. Recent minutes describe the role she
# holds now.
#
# Only AVAILABLE players are considered. A starter who has been out three
# weeks is not tonight's starter, and leaving her in would push the woman
# who actually replaced her down to sixth.
STARTER_LOOKBACK = 5     # games
STARTERS_PER_TEAM = 5


def _recent_minutes(player, lookback=STARTER_LOOKBACK):
    """Mean minutes over her last `lookback` appearances, or None."""
    log = player.get("log") or []
    mins = [g.get("min") for g in log[-lookback:] if g.get("min") is not None]
    if not mins:
        return None
    return sum(mins) / len(mins)


def likely_starters(players, today=None):
    """Set of pids most likely to start for this team tonight.

    Returns an EMPTY SET when minutes can't be read for anyone, so callers
    treat it as "unknown" and show everyone rather than hiding a whole
    roster behind a failed inference.
    """
    ranked = []
    for p in players or []:
        ok, _why, _days = availability(p, today=today)
        if not ok:
            continue
        mins = _recent_minutes(p)
        if mins is None:
            continue
        pid = p.get("pid") or p.get("id")
        if pid is not None:
            ranked.append((mins, pid))
    if not ranked:
        return set()
    ranked.sort(reverse=True)
    return {pid for _m, pid in ranked[:STARTERS_PER_TEAM]}
