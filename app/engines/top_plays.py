"""
Batter ranking scores for the Top Plays panel and the Matchup table.

Built on REAL, LIVE MLB-computed percentile rankings from
baseballsavant.mlb.com (see engines/savant_leaderboard.py), matched by
MLBAM player_id — not name-string matching, not FanGraphs, not this
app's own percentile approximation. This replaced an earlier version
that depended on FanGraphs, which commonly blocks requests from
cloud/dev hosts; Baseball Savant does not have that problem and is
MLB's own first-party data besides.

IMPORTANT — these are still heuristic composite scores (0-100), built
by averaging real percentiles together. They are NOT calibrated
predictive probabilities: nothing here has been backtested against
actual outcomes and graded for accuracy the way a real prediction
model would be. Don't relabel these as "probability" or add a % sign
implying that kind of calibration — every number that FEEDS these
scores is real and live, but the way they're combined is still this
app's own choice, not an official stat.
"""
from engines.savant_leaderboard import get_percentile, get_hr_metric, get_hr_metrics


# HR/FB scoring anchors — league-average HR/FB sits around 11.5%, so
# that maps to 50 on the same 0-100 scale the Savant percentiles use.
# Weight is deliberately light: HR/FB is the least stable power stat.
# HR/FB scoring anchor — MEASURED, not asserted.
#
# This was a hardcoded 11.5. Close to reality, but typed in rather than
# measured, so it silently went stale as the league moved and nothing in
# the app could tell. precompute.build_baselines now measures HR per FLY
# BALL across the whole league each night and ships it in baselines.json.
#
# The literal survives only as a fallback for a build that predates the
# measurement, so the score never breaks — it just uses the old anchor
# until the next nightly, and says so in the docstring rather than
# pretending the number is measured.
_LEAGUE_HRFB_FALLBACK = 11.5


def _league_hrfb() -> float:
    """League HR/FB percent from the nightly build, else the fallback."""
    try:
        import json as _j
        from pathlib import Path as _P
        _p = (_P(__file__).resolve().parent.parent
              / "data" / "statcast" / "baselines.json")
        v = (_j.loads(_p.read_text()) or {}).get("hrPerFlyBall")
        return float(v) if v else _LEAGUE_HRFB_FALLBACK
    except Exception:
        return _LEAGUE_HRFB_FALLBACK
_HRFB_WEIGHT = 0.15

# Axis weights for hr_score. These are a considered starting point, NOT
# fitted against outcomes — nothing here has been backtested yet. The
# structure (one power axis instead of three, plus genuinely independent
# launch and intent axes) is what matters; once calibration is producing
# real graded history these should be replaced by fitted weights.
_W_POWER = 0.45
_W_LAUNCH = 0.30
_W_INTENT = 0.15
# xHR gap enters as a bounded correction, not a weight — see hr_score.
_XHR_MAX_ADJ = 8.0


def hr_score(player_id, savant_df, hrfb_pct=None, hr_df=None):
    """
    Home-run skill, 0-100. Still a heuristic composite, not a calibrated
    probability — see the module docstring.

    STRUCTURE (this is the important part, not the weights):

    The previous version averaged Barrel%, Hard-Hit%, and Exit Velocity
    percentiles with equal weight. Those are three measurements of ONE
    underlying thing — how hard he hits the ball — so averaging them
    triple-counted raw power and left the score with no other axis at
    all. It got loud about obvious sluggers, which is exactly where the
    market is already efficient, and blind to everything else.

    Four axes now, each carrying information the others don't:

      POWER (45%)    Brl/PA primary, EV90 as a ceiling modifier.
                     Brl/PA rather than Brl% because it folds in contact
                     rate and plate discipline — a bat that barrels 15%
                     of its contact while striking out a third of the
                     time produces far fewer home runs than the per-BBE
                     rate implies. EV90 rather than Max EV because Max
                     is a sample of one that never regresses.
                     The whole correlated block is now ONE input.

      LAUNCH (30%)   HR Window % (launch angle 20-40) and pulled-fly-ball
                     rate. Deliberately velocity-free: this asks whether
                     his swing plane puts the ball where home runs live,
                     independent of how hard he hits it. Home runs are
                     overwhelmingly PULLED in the air, and neither of
                     these is measured anywhere in the power block.

      INTENT (15%)   Bat speed, window, and pull-air as process inputs.
                     Every other axis here is downstream of results, so
                     they all sag together when a good power hitter goes
                     cold. This one asks whether the swing is still a
                     home-run swing.

      CONVERSION     xHR minus actual HR, as a bounded +/-8 ADJUSTMENT
      (adjustment)   rather than a weight. A hitter well under his xHR
                     has been putting home-run trajectories in play and
                     not being paid for them, and that gap tends to
                     close. It's a correction to the skill estimate, not
                     a skill of its own, so it shouldn't carry weight in
                     the base.

    DEGRADES GRACEFULLY. hr_df comes from a nightly table that won't
    exist until the next pipeline run, and a batter under the sample
    floor won't be in it. Whenever it's missing, this falls back to the
    original Savant-percentile path so nothing breaks mid-season and no
    player silently scores 0. Weights are renormalised over whichever
    axes are actually measurable, so a partial read is scaled correctly
    rather than quietly penalised.

    HR/FB is retained but demoted. It measures conversion, which the xHR
    gap now measures better and with far less noise, so it only applies
    when the xHR gap is unavailable — otherwise the same idea would be
    counted twice.
    """
    # ---- fallback: original Savant-only path -------------------------
    brl = get_percentile(savant_df, player_id, "brl_percent")
    hh = get_percentile(savant_df, player_id, "hard_hit_percent")
    ev = get_percentile(savant_df, player_id, "exit_velocity")
    savant_parts = [x for x in (brl, hh, ev) if x is not None]
    savant_base = sum(savant_parts) / len(savant_parts) if savant_parts else None

    # ---- new axes ----------------------------------------------------
    brl_pa = get_hr_metric(hr_df, player_id, "brl_per_pa_pct")
    ev90 = get_hr_metric(hr_df, player_id, "ev90_pct")
    window = get_hr_metric(hr_df, player_id, "hr_window_pct_pct")
    pull_air = get_hr_metric(hr_df, player_id, "pull_air_pct_pct")
    intent = get_hr_metric(hr_df, player_id, "hr_intent_pct")
    xhr_gap = get_hr_metric(hr_df, player_id, "xhr_gap_pct")

    # POWER — one axis. Brl/PA leads; EV90 modifies the ceiling. Falls
    # back to the Savant power average when the nightly table is absent.
    power = None
    if brl_pa is not None and ev90 is not None:
        power = brl_pa * 0.75 + ev90 * 0.25
    elif brl_pa is not None:
        power = brl_pa
    elif savant_base is not None:
        power = savant_base

    launch_parts = [x for x in (window, pull_air) if x is not None]
    launch = sum(launch_parts) / len(launch_parts) if launch_parts else None

    axes = [(power, _W_POWER), (launch, _W_LAUNCH), (intent, _W_INTENT)]
    live = [(v, w) for v, w in axes if v is not None]
    if not live:
        return None
    # Renormalise over measurable axes so a missing one doesn't read as
    # a zero for that axis.
    total_w = sum(w for _, w in live)
    base = sum(v * w for v, w in live) / total_w

    # CONVERSION — bounded correction, never a weight.
    if xhr_gap is not None:
        base += (xhr_gap - 50.0) / 50.0 * _XHR_MAX_ADJ
    elif hrfb_pct is not None:
        # Only when the better conversion signal is unavailable.
        hrfb_scaled = max(0.0, min(100.0, hrfb_pct / _league_hrfb() * 50.0))
        base = base * (1 - _HRFB_WEIGHT) + hrfb_scaled * _HRFB_WEIGHT

    return round(max(0.0, min(100.0, base)))


def hit_score(player_id, savant_df):
    """
    Real MLB-computed percentile average of xBA (expected batting
    average) and Hard-Hit% — both pulled live from Baseball Savant.
    """
    xba = get_percentile(savant_df, player_id, "xba")
    hh = get_percentile(savant_df, player_id, "hard_hit_percent")
    parts = [p for p in [xba, hh] if p is not None]
    return round(sum(parts) / len(parts)) if parts else None


def k_score(player_id, savant_df):
    """
    Strikeout risk, 0-100, where HIGHER = MORE strikeout-prone.

    INVERTED from Savant's raw percentile ON PURPOSE. Baseball Savant
    orients EVERY percentile so that higher is better, including stats
    where a lower raw value is the good outcome — whiff%, chase%, K%.
    So whiff_percent = 100 means the batter whiffs LESS than the entire
    league, not more.

    This used to return the percentile straight through, justified by a
    comment reading "Aaron Judge (elite contact hitter) shows
    whiff_percent=10.0". The 10.0 was real; the premise was not. Judge
    is one of the highest-whiff hitters in baseball, and 10.0 is exactly
    what that looks like on a scale where 100 is best. Reading it as
    "low = whiffs less" flipped the whole stat.

    The visible symptom: Luis Arraez, the hardest man in the league to
    strike out, sits near the 100th percentile — and therefore went
    straight to the TOP of the Strikeout Targets board. The list was
    ranking the league's best contact hitters as its best strikeout
    plays, i.e. exactly backwards, every single day.

    100 - percentile puts it back on this app's convention. Still None
    (never 0) when Savant has no sample for the player.
    """
    pct = get_percentile(savant_df, player_id, "whiff_percent")
    if pct is None:
        return None
    return round(100.0 - float(pct))


def confidence_tier(sample_size: int) -> tuple:
    """
    Confidence label based purely on sample size — a real, honest
    statistical courtesy (small samples are noisy, full stop), not a
    marketing badge. Returns (label, sample_size) so callers can show
    both, e.g. "Low — n=89".
    Thresholds are this app's own choice, not an industry standard;
    documented here so they're easy to revisit.
    """
    if sample_size >= 300:
        return "High", sample_size
    if sample_size >= 100:
        return "Medium", sample_size
    return "Low", sample_size


def matchup_tier(slam_score: float) -> str:
    """
    Great/Good/Neutral/Weak bucket derived from SLAM. SLAM is now built
    on real xSLG/xwOBA normalized so ~50 = league average (a league-
    average xSLG of .400 and xwOBA of .310 both map to 50) — these
    thresholds are set relative to that real center point, not the old
    0-30ish arbitrary scale. Still a starting point, not a calibrated
    cutoff — revisit once there's real outcome data to check it against.
    """
    if slam_score >= 65:
        return "Great"
    if slam_score >= 55:
        return "Good"
    if slam_score >= 45:
        return "Neutral"
    return "Weak"


def rank_batters(batter_profiles: list, savant_df) -> list:
    """
    batter_profiles: list of {"name": str, "bats": str, "id": str, "profile": dict}
    "id" must be the batter's real MLBAM player ID (already tracked by
    this app's roster engine) — scores are matched on that, not name
    strings, since real IDs don't have the typo/formatting mismatches
    name matching does.

    Returns the same list with hr_score/hit_score/k_score attached.
    HR Score additionally folds in each batter's HR/FB from his
    profile (15% weight, 25-fly-ball floor) when it's available.
    A score is None (never a fabricated 0) when Baseball Savant simply
    doesn't have this player yet — too few plate appearances so far
    this season, most commonly.
    """
    out = []
    # Loaded ONCE for the whole slate. get_hr_metrics is cached and the
    # lookups are O(1), so the four new axes cost nothing per batter.
    hr_df = get_hr_metrics()
    for b in batter_profiles:
        pid = b.get("id")
        out.append({
            **b,
            # HR/FB comes from the batter's own windowed profile (the
            # same one the lineup table shows), so the layer respects
            # whatever window the view is on rather than always using
            # season data.
            "hr_score": hr_score(pid, savant_df,
                                 hrfb_pct=(b.get("profile") or {}).get("HR/FB"),
                                 hr_df=hr_df),
            "hit_score": hit_score(pid, savant_df),
            "k_score": k_score(pid, savant_df),
        })
    return out
