"""
The arithmetic every game model and prop model on the site shares.

WHY ONE MODULE
--------------
MLB, NHL and NFL each turn "how many will this side score" into "how
often does this side win" and "what is that worth as a line". If each
sport carried its own copy of that conversion, the three would drift —
one would round differently, one would forget ties — and the Results page
would be comparing three different definitions of the same number. So
the conversion lives here, once, and the sport engines only decide WHAT
goes in.

NO CONSTANTS CHOSEN BY EYE (rule 1)
----------------------------------
Nothing in this file is a tuned number. Every function takes its
parameters as arguments, and every parameter a caller passes is either
exact arithmetic or something the nightly MEASURED from real finals:

    shrink_k     fitted by walk-forward log loss    (fit_shrinkage)
    dispersion   method of moments on residuals     (nb_dispersion)
    prior        beta-binomial / gamma-Poisson ML   (fit_beta_prior,
                                                     fit_gamma_prior)

The one modelling assumption a caller makes is the DISTRIBUTION (negative
binomial runs, Poisson goals, normal football margins). Each sport states
it on its page and the nightly validation checks whether it held.

Pure: no streamlit, no requests, no numpy. The fetchers in CI and the
pages on Render both import it, and the tests run it with nothing
installed.
"""
from math import exp, lgamma, log, sqrt, erf

# Score distributions are summed out to this many units. MLB's single-
# game record is 30 runs and the NHL's is 16 goals; a team expectation
# that put real mass past 40 would be an input error, and the guard in
# score_pmf says so rather than silently truncating it.
MAX_SCORE = 40

_GOLD = (5 ** 0.5 - 1) / 2


# ----------------------------------------------------------------------
# Distributions
# ----------------------------------------------------------------------
def poisson_pmf(mu, max_k=MAX_SCORE):
    """[P(0) .. P(max_k)] for a Poisson with mean mu."""
    if mu is None or mu < 0:
        return None
    if mu == 0:
        return [1.0] + [0.0] * max_k
    out, p = [], exp(-mu)
    for k in range(max_k + 1):
        out.append(p)
        p = p * mu / (k + 1)
    return out


def nb_pmf(mu, r, max_k=MAX_SCORE):
    """Negative binomial with mean mu and size r (variance mu + mu^2/r).

    r = None or inf means no over-dispersion, which IS a Poisson — so a
    sport whose measured dispersion comes back unbounded falls through to
    Poisson instead of dividing by infinity.
    """
    if mu is None or mu < 0:
        return None
    if r is None or r <= 0 or r == float("inf") or r > 1e6:
        return poisson_pmf(mu, max_k)
    if mu == 0:
        return [1.0] + [0.0] * max_k
    p = r / (r + mu)                 # success probability
    out = []
    for k in range(max_k + 1):
        lp = (lgamma(k + r) - lgamma(r) - lgamma(k + 1)
              + r * log(p) + k * log(1 - p))
        out.append(exp(lp))
    return out


def score_pmf(mu, dispersion=None, max_k=MAX_SCORE):
    """The score distribution a game model uses for one side."""
    pmf = nb_pmf(mu, dispersion, max_k)
    if pmf is None:
        return None
    tail = 1.0 - sum(pmf)
    if tail > 1e-3:
        # More than a tenth of a percent past MAX_SCORE: the expectation
        # is wrong, not the sport.
        return None
    return pmf


def outcome_probs(pmf_home, pmf_away):
    """(P(home ahead), P(level), P(away ahead)) at the end of regulation."""
    ph = pt = pa = 0.0
    cum_a = 0.0
    cdf_a = []
    for p in pmf_away:
        cum_a += p
        cdf_a.append(cum_a)
    for h, p_h in enumerate(pmf_home):
        if p_h == 0.0:
            continue
        if h == 0:
            below = 0.0
        else:
            below = cdf_a[min(h - 1, len(cdf_a) - 1)]
        at = pmf_away[h] if h < len(pmf_away) else 0.0
        ph += p_h * below
        pt += p_h * at
        pa += p_h * max(0.0, 1.0 - below - at)
    s = ph + pt + pa
    return (ph / s, pt / s, pa / s) if s else (None, None, None)


def win_prob(mu_home, mu_away, dispersion=None, home_wins_tie=0.5):
    """P(home wins), with a level score resolved at the measured rate.

    home_wins_tie is how often the home side wins a game that is level
    after regulation (extra innings, overtime/shootout). It is MEASURED
    by each sport's nightly from real finals; 0.5 is only the default
    for a caller that has not measured it, and the page says which.
    """
    ph = score_pmf(mu_home, dispersion)
    pa = score_pmf(mu_away, dispersion)
    if ph is None or pa is None:
        return None
    h, t, _a = outcome_probs(ph, pa)
    if h is None:
        return None
    return h + t * home_wins_tie


def total_over_prob(mu_home, mu_away, line, dispersion=None):
    """P(combined score > line). A whole-number line pushes, so the push
    mass is excluded from both sides (returns the over share of the
    decided outcomes)."""
    ph = score_pmf(mu_home, dispersion)
    pa = score_pmf(mu_away, dispersion)
    if ph is None or pa is None or line is None:
        return None
    tot = convolve(ph, pa)
    over = sum(p for k, p in enumerate(tot) if k > line)
    push = tot[int(line)] if float(line).is_integer() and int(line) < len(tot) else 0.0
    under = 1.0 - over - push
    return over / (over + under) if (over + under) > 0 else None


def over_prob_pmf(pmf, line):
    """P(X > line) among DECIDED outcomes for one count distribution — a
    team total, a skater's shots, a pitcher's strikeouts. A whole-number
    line pushes, and the push mass is excluded from both sides, exactly
    as total_over_prob does for a game total."""
    if pmf is None or line is None:
        return None
    over = sum(p for k, p in enumerate(pmf) if k > line)
    push = pmf[int(line)] if float(line).is_integer() and 0 <= int(line) < len(pmf) else 0.0
    under = max(0.0, 1.0 - over - push)
    return over / (over + under) if (over + under) > 0 else None


def margin_cover_prob(mu_home, mu_away, home_spread, dispersion=None, home_wins_tie=0.5):
    """P(home covers `home_spread`) for a count sport (run line, puck line,
    alt spreads), among decided outcomes.

    The home side covers when (home - away) + home_spread > 0. A game
    level after regulation goes to extras (MLB) or OT/shootout (NHL),
    which in both sports ends with a ONE-goal/run winner as far as the
    margin is concerned: sudden-death OT and the shootout's single
    awarded goal are exact; a multi-run top of the 10th under the
    automatic runner is the one case this treats as a one-run game, and
    the run-line calibration in the nightly's market check is what holds
    that to account. The level mass is split at the MEASURED rate the
    home side wins those games (tie_home_win), never assumed 50/50 when
    measured.
    """
    ph = score_pmf(mu_home, dispersion)
    pa = score_pmf(mu_away, dispersion)
    if ph is None or pa is None or home_spread is None:
        return None
    # normalised over the mass actually summed, exactly as outcome_probs
    # does, so -0.5 reproduces win_prob to the last digit
    sh, sa = sum(ph), sum(pa)
    ph = [x / sh for x in ph]
    pa = [x / sa for x in pa]
    cover = push = 0.0
    for h, p_h in enumerate(ph):
        if p_h == 0.0:
            continue
        for a, p_a in enumerate(pa):
            p = p_h * p_a
            if p == 0.0:
                continue
            m = h - a
            if m == 0:
                # resolved in extras: home by one, or away by one
                for mm_, w in ((1, home_wins_tie), (-1, 1.0 - home_wins_tie)):
                    v = mm_ + home_spread
                    if v > 0:
                        cover += p * w
                    elif v == 0:
                        push += p * w
                continue
            v = m + home_spread
            if v > 0:
                cover += p
            elif v == 0:
                push += p
    decided = 1.0 - push
    return cover / decided if decided > 0 else None


def convolve(a, b):
    out = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x == 0.0:
            continue
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def normal_cdf(x, mean=0.0, sd=1.0):
    if sd is None or sd <= 0:
        return None
    return 0.5 * (1.0 + erf((x - mean) / (sd * sqrt(2.0))))


def prob_at_least(pmf, k):
    """P(X >= k) from a pmf list."""
    if pmf is None:
        return None
    if k <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - sum(pmf[:k])))


# ----------------------------------------------------------------------
# Odds
# ----------------------------------------------------------------------
def fair_american(p):
    """Fair (no-vig) American odds for a probability, as an int.

    The price at which a bet at probability p breaks even — the line the
    model would set. Rounded to a whole number because that is how books
    print it; returns None at the edges where no finite price exists.
    """
    if p is None or not (0.0 < p < 1.0):
        return None
    if p >= 0.5:
        return -int(round(100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))


def fmt_american(v):
    if v is None:
        return "—"
    return f"+{v}" if v > 0 else str(v)


def implied_prob(american):
    """Break-even probability of an American price (vig included)."""
    try:
        a = float(american)
    except (TypeError, ValueError):
        return None
    if a == 0 or -100 < a < 100:
        return None
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def no_vig_pair(home_american, away_american):
    """(home, away) market probabilities with the bookmaker's margin
    removed by normalising — the fairest single reading of what the
    market thinks, and what the model is compared against."""
    ph, pa = implied_prob(home_american), implied_prob(away_american)
    if ph is None or pa is None or (ph + pa) <= 0:
        return None, None
    s = ph + pa
    return ph / s, pa / s


# ----------------------------------------------------------------------
# Fitting — every parameter a caller passes in comes from one of these
# ----------------------------------------------------------------------
def golden_max(f, lo, hi, iters=80):
    """argmax of a unimodal f on [lo, hi]."""
    c, d = hi - _GOLD * (hi - lo), lo + _GOLD * (hi - lo)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if fc > fd:
            hi, d, fd = d, c, fc
            c = hi - _GOLD * (hi - lo)
            fc = f(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + _GOLD * (hi - lo)
            fd = f(d)
    return (lo + hi) / 2.0


def shrunk_rate(total, games, league_rate, k):
    """A team's per-game rate pulled toward the league by k games of
    league-average evidence. k is FITTED (fit_shrinkage), never chosen:
    in April it decides how much a 12-game sample should move a team off
    average, which is exactly the question that cannot be eyeballed."""
    if league_rate is None:
        return None
    if not games:
        return league_rate
    return (total + k * league_rate) / (games + k)


def log_loss(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * log(p) + (1 - y) * log(1 - p))


def nb_dispersion(pairs):
    """Method-of-moments NB size r from (expected, actual) pairs.

    Var(X) = mu + mu^2 / r  =>  r = sum(mu^2) / sum((x - mu)^2 - mu).
    Measured on the RESIDUALS of the model's own predictions, so it is
    the spread left over after team strength is accounted for — not the
    raw league spread, which would double count the gap between teams.
    Returns None (Poisson) when the data shows no excess variance.
    """
    num = sum(mu * mu for mu, _x in pairs)
    den = sum((x - mu) ** 2 - mu for mu, x in pairs)
    if not pairs or den <= 0:
        return None
    return num / den


def fit_beta_prior(obs, mean=None):
    """Beta-binomial prior strength for (successes, trials) pairs by
    maximum likelihood. Returns (mean, strength) or (None, None).

    rate = (x + mean*strength) / (n + strength). Same method the NFL
    anytime-TD estimator uses (nfl_precompute.td_opportunity_prior);
    golden-section on log(strength) because method of moments needs a
    minimum-sample cutoff, and that cutoff would be chosen by eye.
    """
    obs = [(min(x, n), n) for x, n in obs if n and n > 0]
    if not obs:
        return None, None
    total_n = sum(n for _x, n in obs)
    mu = mean if mean is not None else sum(x for x, _n in obs) / total_n
    if not (0.0 < mu < 1.0):
        return None, None

    def _lbeta(a, b):
        return lgamma(a) + lgamma(b) - lgamma(a + b)

    def ll(log_s):
        s = exp(log_s)
        a, b = mu * s, (1.0 - mu) * s
        base = _lbeta(a, b)
        return sum(_lbeta(x + a, n - x + b) - base for x, n in obs)

    log_s = golden_max(ll, 0.0, 9.0)
    return mu, exp(log_s)


def fit_gamma_prior(obs, mean=None):
    """Gamma-Poisson (negative binomial) prior for (count, exposure)
    pairs — e.g. (shots, games). Returns (mean_rate, strength) where
    strength is in EXPOSURE units: rate = (count + mean*s) / (n + s).
    """
    obs = [(x, n) for x, n in obs if n and n > 0 and x is not None and x >= 0]
    if not obs:
        return None, None
    total_n = sum(n for _x, n in obs)
    mu = mean if mean is not None else sum(x for x, _n in obs) / total_n
    if mu <= 0:
        return None, None

    def ll(log_s):
        s = exp(log_s)
        a = mu * s                    # gamma shape; rate parameter = s
        tot = 0.0
        for x, n in obs:
            tot += (lgamma(x + a) - lgamma(a)
                    + a * log(s / (s + n)) + x * log(n / (s + n)))
        return tot

    log_s = golden_max(ll, -2.0, 9.0)
    return mu, exp(log_s)


def calibration_bins(preds, edges=(0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001)):
    """[(band, n, mean predicted, actual rate)] — the curve every model
    on this site is held to. A model whose 70% band wins 52% of the time
    is not a 70% model, whatever its Brier score says."""
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sub = [(p, y) for p, y in preds if lo <= p < hi]
        if not sub:
            continue
        out.append({
            "band": f"{int(lo * 100)}-{min(int(hi * 100), 100) - 1}%",
            "n": len(sub),
            "predicted": round(sum(p for p, _ in sub) / len(sub), 3),
            "actual": round(sum(y for _, y in sub) / len(sub), 3),
        })
    return out


def score_predictions(preds):
    """{n, brier, log_loss} for [(p, y)] — None-safe."""
    preds = [(p, y) for p, y in preds if p is not None]
    if not preds:
        return {"n": 0, "brier": None, "log_loss": None}
    n = len(preds)
    return {
        "n": n,
        "brier": round(sum((p - y) ** 2 for p, y in preds) / n, 4),
        "log_loss": round(sum(log_loss(p, y) for p, y in preds) / n, 4),
    }


# How many standard errors an improvement must clear before the site
# calls it real. 2 is the conventional ~95% bar — a statistical
# convention, not a tuned number, and it is printed beside every verdict.
SIGNIFICANCE_Z = 2.0


def paired_verdict(model_losses, base_losses):
    """Is the model's loss lower than the baseline's on the SAME games by
    more than noise? Paired, because both are scored on identical games:

        d_i = base_loss_i - model_loss_i      (positive = model better)
        z   = mean(d) / (sd(d) / sqrt(n))

    verdict: "beats" (z >= SIGNIFICANCE_Z), "thin" (better on average but
    within noise), "fails" (not better). This is what the trust badges on
    the model pages show.
    """
    d = [b - m for m, b in zip(model_losses, base_losses)
         if m is not None and b is not None]
    n = len(d)
    if n < 2:
        return {"n": n, "verdict": None}
    mean = sum(d) / n
    var = sum((x - mean) ** 2 for x in d) / (n - 1)
    se = (var / n) ** 0.5
    z = mean / se if se > 0 else (float("inf") if mean > 0 else 0.0)
    verdict = "beats" if z >= SIGNIFICANCE_Z else ("thin" if mean > 0 else "fails")
    return {"n": n, "diff": round(mean, 5), "se": round(se, 5),
            "z": round(z, 2) if z != float("inf") else 99.0, "verdict": verdict}


# ----------------------------------------------------------------------
# Last season as evidence — how much it is worth, MEASURED (10-04)
# ----------------------------------------------------------------------
def prior_season_rate(x_prior, n_prior, x_cur, n_cur, mean, strength, weight):
    """A rate from this season's evidence plus last season's at `weight`
    per unit, pulled toward the league `mean` by `strength` units:

        rate = (x_cur + w * x_prior + mean * s) / (n_cur + w * n_prior + s)

    weight 0 is "last season tells us nothing", 1 is "a PA last year is
    worth a PA this year". It is FITTED (fit_prior_weight), never chosen."""
    num = (x_cur or 0) + weight * (x_prior or 0) + mean * strength
    den = (n_cur or 0) + weight * (n_prior or 0) + strength
    return num / den if den > 0 else mean


def fit_prior_weight(groups, kind="binomial"):
    """The weight of last season's evidence, by maximum likelihood of
    THIS season's outcomes predicted from LAST season's alone (plus the
    league prior).

    groups: [(pairs, mean, strength)], pairs [((x_prior, n_prior),
    (x_cur, n_cur))] — e.g. one group per plate-appearance outcome, all
    sharing one weight. kind: "binomial" (x of n trials) or "poisson"
    (x events over n exposure).

    Returns {"weight", "n_players", "loglik_gain"} — the gain is this
    season's log likelihood at the fitted weight minus at weight 0 (league
    prior only), so a weight that buys nothing says so. None if no pairs.
    """
    usable = [(p, m, s) for p, m, s in groups if p and m is not None and s is not None]
    if not usable:
        return None

    def ll(w):
        tot = 0.0
        for pairs, mean, s in usable:
            for (x0, n0), (x1, n1) in pairs:
                if not n1:
                    continue
                r = prior_season_rate(x0, n0, 0, 0, mean, s, w)
                r = min(max(r, 1e-9), 1 - 1e-9) if kind == "binomial" else max(r, 1e-9)
                if kind == "binomial":
                    tot += x1 * log(r) + (n1 - x1) * log(1 - r)
                else:
                    tot += x1 * log(r * n1) - r * n1
        return tot

    w = golden_max(ll, 0.0, 1.0, iters=40)
    if w < 1e-3:
        w = 0.0
    elif w > 1 - 1e-3:
        w = 1.0
    n_players = len({id(pr) for pairs, _m, _s in usable for pr in pairs})
    return {"weight": round(w, 4), "n_players": n_players,
            "loglik_gain": round(ll(w) - ll(0.0), 2)}
