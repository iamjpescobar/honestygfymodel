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

MIN_GP = 8
MIN_MPG = 15.0
MIN_LOG = 10

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


def build_props(games, stat_label="Points", window="l10"):
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
