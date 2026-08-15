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
from functools import lru_cache as _lru_cache

from engines import hr_floors
from engines import form as form_engine


def _recent_for(b):
    """The hitter's recent window, or None when it can't be read.

    One fetch, shared by both Form outputs below. It used to be pulled
    twice — once for the score and once for the note — which was two
    identical windowed Statcast reads per hitter on every board paint.
    """
    try:
        from engines.statcast_engine import get_batter_profile_windowed
        return get_batter_profile_windowed(b.get("id"),
                                           window=form_engine.FORM_WINDOW,
                                           unit=form_engine.FORM_UNIT)
    except Exception:
        return None


def _form_deltas_for(b):
    """{column header: real delta} — see engines/form."""
    return form_engine.form_deltas(b.get("profile"), _recent_for(b))


def _form_pct_for(b, hr_df, pid):
    """(percentile, direction) — measured nightly, read here.

    Not computed at render time: it is a RANK against the league, and a
    rank needs the whole league. build_hr_metrics has it; a view does
    not.
    """
    return (get_hr_metric(hr_df, pid, "form_pct"),
            get_hr_metric(hr_df, pid, "form_dir"))


def _form_note_for(b):
    return form_engine.form_note(b.get("profile"), _recent_for(b))

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


@_lru_cache(maxsize=1)
def _league_hrfb() -> float:
    """League HR/FB percent from the nightly build, else the fallback.

    Cached: this is called from inside the per-batter loop, and it was
    opening and re-parsing baselines.json once per hitter — several
    hundred disk reads to answer the same question on every board paint.
    The file changes once a night; a process-lifetime cache is the
    correct scope, and Render restarts the process on every deploy.
    """
    return (_load_baselines().get("hrPerFlyBall")
            or _LEAGUE_HRFB_FALLBACK)


@_lru_cache(maxsize=1)
def _load_baselines() -> dict:
    """The nightly baselines file, or {} — parsed once per process.

    Two callers now (the HR/FB anchor and the qualification floors) and
    both sit inside per-batter loops, so this exists so the file is
    opened once rather than once per hitter per caller. {} on any
    failure: a missing archive means every consumer falls back to its
    own literal, which is the behaviour that kept the site up when the
    data reader was pointed at the wrong directory.
    """
    try:
        import json as _j
        from pathlib import Path as _P
        _p = (_P(__file__).resolve().parent.parent
              / "data" / "statcast" / "baselines.json")
        return _j.loads(_p.read_text()) or {}
    except Exception:
        return {}


_HRFB_WEIGHT = 0.15

# ------------------------------------------------------------
# AXIS WEIGHTS for hr_score. Calibration constants: a considered
# starting point, NOT fitted against outcomes. Argue with them HERE —
# never special-case a weight at a call site, which is how an app ends
# up with five definitions of the same score.
#
# THE RULE THAT SHAPES THEM: no measured column may appear in more than
# one axis.
#
# The previous version broke that rule and said the opposite. INTENT was
# fed hr_intent_pct, and HRIntent is the mean of bat speed, HR window %
# and pull air % — the last two being exactly the two columns the LAUNCH
# axis already carried. Stated weights were power .45 / launch .30 /
# intent .15. What the arithmetic actually produced:
#
#     Brl/PA   37.5% | EV90 12.5% | HR window 22.2%
#     pull air 22.2% | bat speed 5.6%
#
# So launch plane carried 44% of the score against power's 50%, and bat
# speed — the one input in that axis measuring the SWING rather than the
# result of a swing — carried a twentieth. It was the same failure the
# docstring below describes in the version before it, where Barrel%,
# Hard-Hit% and EV were averaged as three axes while measuring one
# thing. Sitting in the fix for it.
#
# Four axes now, each column used exactly once. Correlation between
# axes remains — every batted-ball stat correlates with every other —
# but nothing is literally entered twice, and the weights say what the
# arithmetic does.
_W_POWER = 0.40         # Brl/PA, EV90            — how hard
_W_CONVERGE = 0.30      # FB95%, Clears Anywhere% — hard AND in the air
_W_LAUNCH = 0.22        # HR window %, pull air % — trajectory
_W_PROCESS = 0.08       # bat speed               — the swing itself

# Within-axis splits.
_S_BRL_PA, _S_EV90 = 0.70, 0.30
_S_FB95, _S_CLEARS = 0.60, 0.40
_S_WINDOW, _S_PULLAIR = 0.50, 0.50

# COVERAGE FLOOR. Renormalising over live axes stops a missing axis from
# reading as a zero — but with no floor it also meant a bat measured on
# ONE axis received a full 0-100 score indistinguishable from a bat
# measured on four, with nothing on the board to tell them apart. A
# score has to rest on most of its own definition.
_MIN_LIVE_WEIGHT = 0.60

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

    Four axes, and NO COLUMN APPEARS IN TWO OF THEM. See the weight
    block above for the version that broke that rule and the arithmetic
    showing what it really weighted.

      POWER (40%)     Brl/PA (70%), EV90 (30%). How hard.
                      Brl/PA rather than Brl% because it folds in
                      contact rate and plate discipline — a bat that
                      barrels 15% of its contact while striking out a
                      third of the time produces far fewer home runs
                      than the per-BBE rate implies. EV90 rather than
                      Max EV because Max is a sample of one that never
                      regresses.

      CONVERGENCE     FB95 % (60%), Clears Anywhere % (40%). Hard
      (30%)           contact ACTUALLY PUT IN THE AIR, and contact on a
                      trajectory the league's own outcomes say leaves
                      any park. This is not power and it is not launch:
                      a bat can sit in the top decile of both and still
                      rarely combine them in one swing, and the
                      combination is the home run. FB95 was already
                      computed, ranked and displayed by the nightly and
                      was read by nothing that scored anything — the
                      one column here whose own comment says it is the
                      intersection that predicts home runs.

      LAUNCH (22%)    HR Window % (launch angle 20-40) and pulled-fly-
                      ball rate, evenly. Deliberately velocity-free:
                      does his swing plane put the ball where home runs
                      live, independent of how hard he hits it. Home
                      runs are overwhelmingly PULLED in the air.

      PROCESS (8%)    Bat speed, alone. Every other axis is downstream
                      of results, so they all sag together when a good
                      power hitter goes cold; this one asks whether the
                      swing is still a home-run swing. It is ALONE here
                      because it is the only input in the table that is
                      not a measurement of a batted ball — the previous
                      version put window and pull-air in beside it and
                      called the axis independent.

      CONVERSION      xHR minus actual HR, PER SCOREABLE BATTED BALL,
      (adjustment)    as a bounded +/-8 adjustment rather than a weight.
                      A hitter well under his xHR has been putting
                      home-run trajectories in play and not being paid
                      for them, and that gap tends to close. It's a
                      correction to the skill estimate, not a skill of
                      its own, so it shouldn't carry weight in the base.
                      It reads xhr_gap_RATE_pct: the old xhr_gap_pct
                      ranked a raw count of home runs, which put playing
                      time inside a correction that has nothing to do
                      with playing time.

    COVERAGE FLOOR. Renormalising over live axes protects a bat with one
    axis missing. It does NOT protect the reader from a bat with only
    one axis PRESENT, which used to receive a full 0-100 score off a
    single measurement. A score now has to rest on at least
    _MIN_LIVE_WEIGHT of its own definition, and must include POWER;
    below that it falls back to the Savant path or returns None.

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
    fb95 = get_hr_metric(hr_df, player_id, "fb95_pct_pct")
    clears = get_hr_metric(hr_df, player_id, "clears_anywhere_pct_pct")
    window = get_hr_metric(hr_df, player_id, "hr_window_pct_pct")
    pull_air = get_hr_metric(hr_df, player_id, "pull_air_pct_pct")
    bat_speed = get_hr_metric(hr_df, player_id, "bat_speed_pct")
    xhr_gap = get_hr_metric(hr_df, player_id, "xhr_gap_rate_pct")

    def _blend(*pairs):
        """Weighted mean over whichever components are measurable."""
        live = [(v, w) for v, w in pairs if v is not None]
        if not live:
            return None
        return sum(v * w for v, w in live) / sum(w for _, w in live)

    power = _blend((brl_pa, _S_BRL_PA), (ev90, _S_EV90))
    converge = _blend((fb95, _S_FB95), (clears, _S_CLEARS))
    launch = _blend((window, _S_WINDOW), (pull_air, _S_PULLAIR))
    process = bat_speed

    axes = [(power, _W_POWER), (converge, _W_CONVERGE),
            (launch, _W_LAUNCH), (process, _W_PROCESS)]
    live = [(v, w) for v, w in axes if v is not None]
    live_w = sum(w for _, w in live)

    # THE NIGHTLY TABLE IS THE PREFERRED PATH, NOT THE ONLY ONE.
    #
    # When hr_metrics.parquet is absent — a fresh deploy before the first
    # nightly, or an archive that predates it — none of the axes above
    # resolve and the Savant percentile average is a complete, valid
    # score on its own. That path must survive: this reader has already
    # silently pointed at the wrong directory once, and the symptom was
    # every board quietly falling back rather than going blank, which is
    # the behaviour that kept the site up while the bug was found.
    #
    # The coverage floor therefore governs the NEW path only. A bat the
    # table knows but barely measures falls back to Savant if Savant has
    # him, and scores nothing if neither source does.
    if live_w < _MIN_LIVE_WEIGHT or power is None:
        if savant_base is None:
            return None
        base = savant_base
    else:
        # Renormalise over measurable axes so a missing one doesn't read
        # as a zero for that axis.
        base = sum(v * w for v, w in live) / live_w

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
    # Tonight's qualification thresholds, resolved once. See
    # engines/hr_floors for why these are measured percentiles rather
    # than the numbers as typed.
    _thresholds = hr_floors.resolve(_load_baselines())
    for b in batter_profiles:
        pid = b.get("id")
        _met, _total, _missed = hr_floors.evaluate(b.get("profile") or {},
                                                   _thresholds)
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
            # Slate-wide HR metrics off the nightly league table. Free
            # here: hr_df is already loaded above for hr_score and the
            # lookups are O(1) on an indexed frame, so the board gets
            # these without a single extra Statcast pull.
            #
            # The REGRESSED rates, not the raw ones. This board ranks
            # hitters against each other, and an unregressed rate off 40
            # batted balls sorts above a bat with ten times the evidence
            # — noise at the top of the board is exactly what the
            # shrinkage in build_hr_metrics exists to prevent. The raw
            # figures stay on the Game Card, where you're reading one
            # hitter rather than ordering four hundred.
            "hr_threat": get_hr_metric(hr_df, pid, "hr_threat"),
            "clears_anywhere": get_hr_metric(hr_df, pid, "clears_anywhere_pct"),
            "fb95": get_hr_metric(hr_df, pid, "fb95_pct"),
            # THE DENOMINATOR, carried so a board can show it.
            #
            # The inclusion floor is 50 PA and the scale core is 150, so
            # a part-timer and a everyday bat sit in the same ranked list
            # in identical type with nothing between them. The regression
            # in build_hr_metrics protects the NUMBER; it does nothing
            # for the reader. Same argument that put the G column on the
            # pitcher splits table, where the comment about a table
            # having "no sample column to contradict it" was written.
            # AVERAGE exit velocity, beside EV90. Two different
            # questions: how hard is his contact, versus how hard is his
            # BEST contact. The board showed only the second.
            "avg_ev": (b.get("profile") or {}).get("AvgEV"),
            # FORM — his recent numbers against HIS OWN, in his own
            # units. Not an index: this used to be a 0-100 score with 50
            # at his baseline, which was a real deviation wearing the
            # costume of the league percentiles sitting beside it. What
            # spreads onto the row now is the subtraction itself —
            # "+1.8 mph", "+6.9 pts" — a stat a subscriber can check
            # against Savant. See engines/form for why there is no
            # single blended Form number.
            **_form_deltas_for(b),
            "form_note": _form_note_for(b),
            # FORM as a league percentile plus a direction. See
            # engines/form: 64 means hotter than 64% of qualified
            # hitters tonight, which is a count rather than a score.
            "form_pct": get_hr_metric(hr_df, pid, "form_pct"),
            "form_dir": get_hr_metric(hr_df, pid, "form_dir"),
            # Volume and distance, from the nightly.
            "hr_count": get_hr_metric(hr_df, pid, "hr"),
            "near_hr": get_hr_metric(hr_df, pid, "near_hr"),
            "l5_pa_per_game": get_hr_metric(hr_df, pid, "l5_pa_per_game"),
            "avg_dist": get_hr_metric(hr_df, pid, "avg_dist"),
            "dist_300": get_hr_metric(hr_df, pid, "dist_300"),
            "dist_350": get_hr_metric(hr_df, pid, "dist_350"),
            "hr_pa": get_hr_metric(hr_df, pid, "pa"),
            "hr_bbe": get_hr_metric(hr_df, pid, "bbe"),
            # QUALIFICATION FLOORS AS A TIER, NOT A FILTER.
            #
            # hr_floors_probe measured the proposed nine-floor AND gate
            # against 373 hitters at 150+ PA: 21 clear all nine. About a
            # third of qualifying hitters are in any night's confirmed
            # lineups, so a hard gate leaves roughly seven bats and
            # cannot fill a top-15 board. Thirty-three more miss by
            # exactly one, and deleting the hitter at 10.9% barrel with
            # everything else elite is a cliff nobody wants.
            #
            # So nothing is filtered. The count rides along and the
            # board shows it, which is the same choice the sample column
            # above makes: put the qualification in front of the reader
            # rather than acting on it for them.
            "floors_met": _met, "floors_total": _total, "floors_missed": _missed,
        })
    return out
