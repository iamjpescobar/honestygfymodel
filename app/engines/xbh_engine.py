"""
XBH Score — extra-base-hit skill, and the matchup that supports it.

The Player of the Day picks one bat per slate to record an EXTRA-BASE
HIT (double, triple, or home run). That target sits between "any hit"
and "home run", and it needs its own model rather than a borrowed one:

  - HR models over-weight loft. A home run needs roughly 25-35 degrees
    of launch angle; a double works from about 10 degrees up, and a
    scorched line drive into the gap counts the same on the ticket.
  - Hit models over-weight contact. A bloop single is a win for xBA
    and worth nothing here.

SKILL (from real Baseball Savant percentiles, live)
  xSLG              35%  the most direct XBH indicator there is —
                         slugging is driven almost entirely by
                         extra-base hits
  Barrel%           25%  barrels are the launch-angle-plus-velocity
                         combination that produces doubles and homers
  Hard-Hit%         20%  the floor under every extra-base hit
  Exit Velocity     10%  raw force, which turns catchable flies into
                         wall-scrapers
  K% (penalty)      10%  strikeouts are plate appearances with zero
                         chance of an extra-base hit. Two bats with
                         the same barrel rate are NOT equivalent if
                         one strikes out 35% of the time and the
                         other 18% — the second simply gets more
                         chances. Applied as a penalty against the
                         league-average percentile, capped, so it
                         shades the ranking without letting contact
                         skill outrank power.

MATCHUP (added on top, each capped and printed on the page)
  Edge layer       ±40  the same BvP / zone-fit / bullpen model the
                        Game Card ranks with — reused rather than
                        rebuilt so both pages agree
  Pitcher XBH      ±10  what this starter actually allows: SLG and
                        ISO against, which is the pitcher-side mirror
                        of the skill above
  Park             ±6   XBH park factor, NOT home-run park factor.
                        Deep-gap parks suppress homers while helping
                        doubles and triples, so using an HR factor
                        here would actively mislead.
  Wind             ±3   real but deliberately small: wind blowing in
                        kills fly balls, and a line drive into the
                        gap barely notices. Only MLB's official
                        field-relative string is trusted.

Nothing here is a probability. League-wide a hitter records an
extra-base hit in roughly one game in three, so a pick sustaining a
rate meaningfully above that is doing real work — and the calibration
tracker grades exactly that, on extra-base hits, not on hits.
"""

# ---- skill weights (sum to 1.0 including the K penalty slot) ----
W_XSLG = 0.35
W_BARREL = 0.25
W_HARDHIT = 0.20
W_EV = 0.10
W_K = 0.10

# ---- matchup caps ----
PITCHER_XBH_CAP = 10
PARK_CAP = 6
WIND_CAP = 3

# League-average percentile: a batter at the 50th percentile in K%
# neither gains nor loses. Above it (strikes out more than average)
# costs, below it gains.
K_NEUTRAL = 50.0

# Parks that suppress home runs but play NEUTRAL-to-good for doubles
# and triples: deep gaps, big outfields, high walls that turn would-be
# homers into off-the-wall two-baggers. Using a home-run park factor
# for an XBH play would penalize these unfairly, so they get a floor.
DEEP_GAP_PARKS = {
    "Detroit Tigers",        # Comerica — cavernous gaps
    "Kansas City Royals",    # Kauffman — huge outfield, triples park
    "Boston Red Sox",        # Fenway — the Monster makes doubles
    "Colorado Rockies",      # Coors — everything plays big
    "Pittsburgh Pirates",    # PNC — deep left-center
    "San Francisco Giants",  # Oracle — Triples Alley
    "Oakland Athletics",
    "Athletics",
    "Miami Marlins",         # loanDepot — deep center
    "Cleveland Guardians",
}


def _pct(savant_df, pid, col):
    """Percentile lookup that tolerates a missing column or player."""
    from engines.savant_leaderboard import get_percentile
    try:
        return get_percentile(savant_df, pid, col)
    except Exception:
        return None


def xbh_skill(pid, savant_df):
    """(score, parts) — 0-100 extra-base-hit skill, or (None, {}) when
    Savant has no real sample for this batter. Never guesses."""
    xslg = _pct(savant_df, pid, "xslg")
    brl = _pct(savant_df, pid, "brl_percent")
    hh = _pct(savant_df, pid, "hard_hit_percent")
    ev = _pct(savant_df, pid, "exit_velocity")
    kp = _pct(savant_df, pid, "k_percent")

    core = [(xslg, W_XSLG), (brl, W_BARREL), (hh, W_HARDHIT), (ev, W_EV)]
    live = [(v, w) for v, w in core if v is not None]
    if not live:
        return None, {}

    # renormalize over whatever is present so a missing column doesn't
    # silently deflate the score
    total_w = sum(w for _v, w in live)
    base = sum(v * w for v, w in live) / total_w

    parts = {"xSLG": xslg, "Barrel%": brl, "HardHit%": hh, "ExitVelo": ev}

    # K penalty: percentile is "how much he strikes out" (high = more),
    # so above-average K costs and below-average helps. Scaled by its
    # weight and capped at +/- 10 points of the final score.
    k_adj = 0.0
    if kp is not None:
        k_adj = max(-10.0, min(10.0, (K_NEUTRAL - float(kp)) * W_K * 2))
        parts["K%"] = kp

    score = max(0.0, min(100.0, base + k_adj))
    parts["_k_adj"] = round(k_adj, 1)
    parts["_base"] = round(base, 1)
    return round(score, 1), parts


def pitcher_xbh_adj(splits):
    """(adj, note) — how much extra-base damage this starter allows.

    SLG and ISO against are the pitcher-side mirror of the batter skill
    above: ISO in particular is literally extra bases per at-bat, which
    is exactly the thing being bet on. Neutral when the splits engine
    reports an error or an empty sample rather than assuming average.
    """
    if not splits or splits.get("_error"):
        return 0, None
    slg = splits.get("SLG")
    iso = splits.get("ISO")
    parts = []
    # .420 SLG and .160 ISO are roughly league-average against; every
    # .040 of SLG or .030 of ISO above that is worth a point.
    if isinstance(slg, (int, float)) and slg > 0:
        parts.append((float(slg) - 0.420) / 0.040)
    if isinstance(iso, (int, float)) and iso > 0:
        parts.append((float(iso) - 0.160) / 0.030)
    if not parts:
        return 0, None
    raw = sum(parts) / len(parts)
    adj = int(max(-PITCHER_XBH_CAP, min(PITCHER_XBH_CAP, round(raw))))
    bits = []
    if isinstance(slg, (int, float)) and slg > 0:
        bits.append(f"SLG {slg:.3f}")
    if isinstance(iso, (int, float)) and iso > 0:
        bits.append(f"ISO {iso:.3f}")
    return adj, ("allows " + ", ".join(bits)) if bits else None


def park_xbh_adj(home_team, park_factor, verified):
    """(adj, note) — park effect on EXTRA-BASE hits, not home runs.

    A raw home-run park factor is the wrong instrument here: Comerica,
    Kauffman, and Oracle all suppress homers while playing fine or
    better for doubles and triples. Those parks get a floor of zero so
    a deep outfield never reads as a negative on an XBH play.
    """
    if not verified or park_factor is None:
        return 0, None
    try:
        pf = float(park_factor)
    except (TypeError, ValueError):
        return 0, None
    adj = int(max(-PARK_CAP, min(PARK_CAP, round((pf - 100) * 0.3))))
    note = f"park factor {pf:g}"
    if home_team in DEEP_GAP_PARKS and adj < 0:
        adj = 0
        note = f"park factor {pf:g} (HR-suppressing but deep gaps — neutral for XBH)"
    return adj, note


def wind_xbh_adj(wind_str):
    """(adj, note) — capped at +/-3 because wind moves fly balls far
    more than it moves line drives into the gap, and only MLB's
    official field-relative wind can honestly claim a direction."""
    if not wind_str:
        return 0, None
    import re
    w = str(wind_str).lower()
    m = re.search(r"(\d+)\s*mph", w)
    mph = int(m.group(1)) if m else 0
    if mph < 8:
        return 0, None
    if "out to" in w:
        adj = min(WIND_CAP, 2 if mph < 15 else 3)
        return adj, f"wind out {mph} mph (+{adj})"
    if "in from" in w:
        adj = -min(WIND_CAP, 2 if mph < 15 else 3)
        return adj, f"wind in {mph} mph ({adj})"
    return 0, None
