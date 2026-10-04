"""
MLB batter props — hits, total bases, home runs, strikeouts — built one
plate appearance at a time.

THE MODEL
---------
Every plate appearance ends in one of seven outcomes:

    1B  2B  3B  HR  BB (walk, HBP, IBB, catcher's interference)  K  OUT

For tonight's matchup each outcome's probability is the batter's rate
combined with the pitcher's allowed rate by the ODDS-RATIO method
(Tango's log5, generalised to several outcomes):

    p_i  proportional to  batter_i * pitcher_i / league_i

which has no parameter in it: an average pitcher leaves the batter
exactly himself, and a pitcher who allows twice the league's home-run
rate doubles the batter's odds of one.

  - BATTER and PITCHER rates are each shrunk toward the league by a
    beta-binomial prior per outcome, FITTED by maximum likelihood over
    every batter (or pitcher) in the season (model_math.fit_beta_prior).
    A 40-PA call-up is mostly league; a 600-PA regular is mostly himself.
  - HOW MANY PLATE APPEARANCES comes from his lineup slot and the
    measured distribution of team PA per game: slot i bats
    floor((T - i) / 9) + 1 times in a game where his team sends T men
    to the plate. Exact arithmetic over a measured histogram.
  - HOW MANY OF THOSE ARE AGAINST THE STARTER: team PA number 9j + i is
    against the starter when the starter has not yet left — his
    batters-faced per start, from his own starts mixed with the league's
    starters by a gamma-Poisson strength fitted the same way.
  - The rest are against the BULLPEN, taken as a league-average pitcher.
    Tonight's specific relievers are not known before the game, and
    pretending otherwise would be inventing a number.

Then the count distributions (hits, total bases, HR, K) are summed
exactly over those PAs and mixed over the PA scenarios.

WHAT IT LEAVES OUT, STATED ON THE PAGE
--------------------------------------
Park, weather, platoon split, and the specific bullpen. Each is a real
effect; none is in the number. A probability that silently leaves out
the park is the same as one that silently includes a made-up park
factor — so the omission is printed under the table.

Pure — no streamlit, no requests. The nightly (precompute.build_prop_model)
measures the inputs and validates walk-forward; the Game Card projects.
"""
import json
from collections import Counter
from pathlib import Path

from engines import model_math as mm

OUTCOMES = ("1B", "2B", "3B", "HR", "BB", "K", "OUT")
TB = {"1B": 1, "2B": 2, "3B": 3, "HR": 4}

_EVENT_MAP = {
    "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR",
    "walk": "BB", "intent_walk": "BB", "hit_by_pitch": "BB",
    "catcher_interf": "BB",
    "strikeout": "K", "strikeout_double_play": "K",
}
# Not a plate appearance with an outcome — dropped, not counted as an out.
_IGNORE = {"truncated_pa", ""}

# The markets on the page: (key, label, stat, at_least). Every one is
# scored walk-forward by the nightly against the batter's own hit rate;
# any OTHER line is priced off the same distribution by the any-line tool
# (and inherits its stat's test, which the tool says).
MARKETS = (
    ("h1", "Hits O0.5", "h", 1),
    ("h2", "Hits O1.5", "h", 2),
    ("h3", "Hits O2.5", "h", 3),
    ("tb1", "TB O0.5", "tb", 1),
    ("tb2", "TB O1.5", "tb", 2),
    ("tb3", "TB O2.5", "tb", 3),
    ("tb4", "TB O3.5", "tb", 4),
    ("hr1", "HR O0.5", "hr", 1),
    ("k1", "K O0.5", "k", 1),
    ("k2", "K O1.5", "k", 2),
    ("bb1", "Walks+HBP O0.5", "bb", 1),
    ("s1", "Singles O0.5", "s", 1),
    ("d1", "Doubles O0.5", "d", 1),
    ("rbi1", "RBI O0.5", "rbi", 1),
    ("rbi2", "RBI O1.5", "rbi", 2),
)
# Stat groups for the page: (stat, label, lines shown in the table).
STATS = (
    ("h", "Hits", (0.5, 1.5, 2.5)),
    ("tb", "Total bases", (0.5, 1.5, 2.5, 3.5)),
    ("hr", "Home runs", (0.5,)),
    ("k", "Strikeouts", (0.5, 1.5)),
    ("bb", "Walks (incl. hit-by-pitch)", (0.5,)),
    ("s", "Singles", (0.5,)),
    ("d", "Doubles", (0.5,)),
    ("rbi", "RBI", (0.5, 1.5)),
)
# RBI is measured as the runs that scored on his plate appearance
# (Statcast's post_bat_score - bat_score on the PA-ending pitch). Official
# RBI leaves out runs that score on an error or a double play, so this
# reads slightly HIGH — said under the table (rule 9).
RBI_NOTE = ("RBI = runs that scored on his plate appearance; the official stat leaves out "
            "runs on errors and double plays, so this reads a touch high.")
MAX_RBI = 4

# Pitcher props for tonight's starter against the lineup he faces:
# (key, label, stat, at_least).
PITCHER_MARKETS = (
    ("pk4", "K O3.5", "k", 4),
    ("pk5", "K O4.5", "k", 5),
    ("pk6", "K O5.5", "k", 6),
    ("pk7", "K O6.5", "k", 7),
    ("ph5", "Hits allowed O4.5", "h", 5),
    ("ph6", "Hits allowed O5.5", "h", 6),
    ("pbb2", "Walks+HBP allowed O1.5", "bb", 2),
    ("phr1", "HR allowed O0.5", "hr", 1),
)
PITCHER_STATS = (
    ("k", "Strikeouts", (3.5, 4.5, 5.5, 6.5)),
    ("h", "Hits allowed", (4.5, 5.5)),
    ("bb", "Walks allowed (incl. HBP)", (1.5,)),
    ("hr", "HR allowed", (0.5,)),
)


def classify(event):
    """Statcast `events` -> one of OUTCOMES, or None for a non-PA row."""
    if event is None:
        return None
    e = str(event).strip().lower()
    if e in _IGNORE or e == "nan":
        return None
    return _EVENT_MAP.get(e, "OUT")


def outcome_counts(df):
    """{outcome: count, "PA": n} from a player's Statcast frame — one
    row per completed plate appearance (terminal-event rows, deduped on
    game_pk + at_bat_number so a frame that ever carries a PA twice
    cannot double it)."""
    out = Counter()
    if df is None or len(df) == 0 or "events" not in df.columns:
        return {"PA": 0}
    sub = df[df["events"].notna()]
    if "game_pk" in sub.columns and "at_bat_number" in sub.columns:
        sub = sub.drop_duplicates(subset=["game_pk", "at_bat_number"])
    for e in sub["events"]:
        o = classify(e)
        if o:
            out[o] += 1
    d = {o: int(out.get(o, 0)) for o in OUTCOMES}
    d["PA"] = sum(d.values())
    return d


def with_prior(counts, prior_counts, weight):
    """This season's outcome counts plus LAST season's at the fitted
    weight (prop_model.json "prior_weight"; model_math.fit_prior_weight).
    Either may be missing; neither is ever invented."""
    if not prior_counts or not weight:
        return counts
    out = {o: (counts or {}).get(o, 0) + weight * prior_counts.get(o, 0) for o in OUTCOMES}
    out["PA"] = sum(out[o] for o in OUTCOMES)
    out["PA_this_season"] = (counts or {}).get("PA", 0)
    out["PA_last_season"] = prior_counts.get("PA", 0)
    return out


def player_counts(model, pid, counts, kind="batter"):
    """counts with last season folded in, for a batter or a pitcher."""
    pw = (model or {}).get("prior_weight") or {}
    pri = ((model or {}).get(f"prior_{kind}s") or {}).get(str(pid))
    return with_prior(counts, pri, pw.get(kind) or 0.0)


def shrunk_rates(counts, priors):
    """Posterior per-PA rates, normalised to sum to 1.

    priors: {outcome: [mean, strength]} as fitted by the nightly. A
    missing prior leaves that outcome at the league mean, never zero.
    """
    if not priors:
        return None
    n = (counts or {}).get("PA", 0)
    raw = {}
    for o in OUTCOMES:
        mean, s = (priors.get(o) or [None, None])
        if mean is None:
            return None
        x = (counts or {}).get(o, 0)
        raw[o] = (x + mean * s) / (n + s)
    tot = sum(raw.values())
    return {o: v / tot for o, v in raw.items()}


def combine(batter, pitcher, league):
    """Odds-ratio combination, normalised."""
    if not batter or not league:
        return None
    if not pitcher:
        return dict(batter)
    raw = {o: batter[o] * pitcher[o] / league[o] if league[o] else 0.0 for o in OUTCOMES}
    tot = sum(raw.values())
    return {o: v / tot for o, v in raw.items()} if tot else None


def slot_pa(slot, team_pa):
    """Plate appearances slot `slot` gets when his team sends team_pa."""
    if team_pa < slot:
        return 0
    return (team_pa - slot) // 9 + 1


def pa_vs_starter(slot, n_pa, starter_bf):
    """How many of those n_pa come while the starter is still in."""
    return sum(1 for j in range(n_pa) if 9 * j + slot <= starter_bf)


def scenario_mass(slot, team_pa_hist, bf_dist):
    """{(n_pa, n_vs_sp): probability} — the PA scenarios for one slot.

    team_pa_hist: {T: count} measured; bf_dist: {bf: prob} for tonight's
    starter. Collapsing to (n_pa, n_sp) pairs first keeps the exact sum
    to a handful of terms.
    """
    # T and the starter's BF are treated as independent, and the PAs he
    # gets against the starter are min(n, m) where m counts the trips
    # through the order the starter lasts — so the two distributions can
    # be collapsed separately first (a few values each) instead of
    # crossing ~40 T values with ~30 BF values for every batter.
    tot_t = sum(team_pa_hist.values())
    n_dist = Counter()
    for t, ct in team_pa_hist.items():
        n_dist[slot_pa(slot, int(t))] += ct / tot_t
    m_dist = Counter()
    if bf_dist:
        for bf, pb in bf_dist.items():
            m_dist[slot_pa(slot, int(bf))] += pb
    else:
        m_dist[0] = 1.0
    out = Counter()
    for n, pn in n_dist.items():
        for m, pm_ in m_dist.items():
            out[(n, min(n, m))] += pn * pm_
    return dict(out)


def _steps(probs, rbi_given=None):
    """One plate appearance's distribution for every stat the page prices.

    rbi_given: {outcome: [P(0 RBI), P(1), ...]} for this lineup slot,
    MEASURED by the nightly (league-wide, by slot and outcome). None ->
    no RBI distribution (an older prop file), and the RBI markets are
    left out rather than guessed."""
    ph = sum(probs[o] for o in TB)
    tb = [0.0] * 5
    for o, p in probs.items():
        tb[TB.get(o, 0)] += p
    st = {"h": [1 - ph, ph], "tb": tb, "hr": [1 - probs["HR"], probs["HR"]],
          "k": [1 - probs["K"], probs["K"]], "bb": [1 - probs["BB"], probs["BB"]],
          "s": [1 - probs["1B"], probs["1B"]], "d": [1 - probs["2B"], probs["2B"]]}
    if rbi_given:
        r = [0.0] * (MAX_RBI + 1)
        for o, p in probs.items():
            dist = rbi_given.get(o)
            if not dist:
                r[0] += p
                continue
            for k, q in enumerate(dist[:MAX_RBI + 1]):
                r[k] += p * q
        st["rbi"] = r
    return st


def _count_pmfs(p_sp, p_pen, n_sp, n_pen, rbi_given=None):
    """Exact pmfs of every stat over n_sp + n_pen PAs."""
    out = None
    for probs, n in ((p_sp, n_sp), (p_pen, n_pen)):
        if n <= 0:
            continue
        steps = _steps(probs, rbi_given)
        if out is None:
            out = {k: [1.0] for k in steps}
        for _ in range(n):
            for k, step in steps.items():
                out[k] = mm.convolve(out[k], step)
    if out is None:
        keys = ("h", "tb", "hr", "k", "bb", "s", "d") + (("rbi",) if rbi_given else ())
        out = {k: [1.0] for k in keys}
    return out


def _mix(acc, pmfs, w):
    for k, pmf in pmfs.items():
        cur = acc.setdefault(k, [])
        if len(cur) < len(pmf):
            cur.extend([0.0] * (len(pmf) - len(cur)))
        for i, p in enumerate(pmf):
            cur[i] += w * p


def _trim(pmf, eps=1e-7):
    out = list(pmf)
    while len(out) > 1 and out[-1] < eps:
        out.pop()
    return [round(x, 7) for x in out]


def rbi_table(model, slot):
    """{outcome: [P(r RBI)]} for a lineup slot, or None."""
    t = (model or {}).get("rbi_given") or {}
    return t.get(str(slot)) or t.get("all")


def project_batter(slot, b_counts, p_counts, model, bf_dist=None):
    """{"exp_pa", "probs": {market: p}, "fair": {market: american},
        "pmfs": {stat: [P(0), P(1), ...]}, "pa": batter PA on record} or None.

    model: the nightly's prop_model.json dict (league rates, priors,
    team PA histogram). p_counts None means the starter is unknown or
    has no record — then every PA is scored against a league-average
    pitcher, and the caller says so.
    """
    if not model or not slot:
        return None
    league = model.get("league_rates")
    b = shrunk_rates(b_counts, model.get("batter_priors"))
    p = shrunk_rates(p_counts, model.get("pitcher_priors")) if p_counts and p_counts.get("PA") else None
    hist = {int(k): v for k, v in (model.get("team_pa_hist") or {}).items()}
    if not league or not b or not hist:
        return None
    p_sp = combine(b, p, league)
    p_pen = dict(b)
    rbi_given = rbi_table(model, int(slot))
    scen = scenario_mass(int(slot), hist, bf_dist if p else None)
    mix = {}
    exp_pa = 0.0
    tot_w = 0.0
    for (n, n_sp), w in scen.items():
        exp_pa += n * w
        tot_w += w
        _mix(mix, _count_pmfs(p_sp, p_pen, n_sp, n - n_sp, rbi_given), w)
    if tot_w:
        mix = {k: [x / tot_w for x in v] for k, v in mix.items()}
    probs = {}
    for key, _label, stat, at_least in MARKETS:
        if stat in mix:
            probs[key] = round(mm.prob_at_least(mix[stat], at_least) or 0.0, 4)
    return {
        "exp_pa": round(exp_pa, 2),
        "probs": probs,
        "fair": {k: mm.fair_american(v) for k, v in probs.items()},
        "pmfs": {k: _trim(v) for k, v in mix.items()},
        "pa": int((b_counts or {}).get("PA", 0)),
        "vs_starter": p is not None,
    }


def project_pitcher(order_counts, p_counts, model, bf_dist):
    """Tonight's starter against the lineup he faces.

    order_counts: nine entries in batting order, each a batter's outcome
    counts (None = no record -> that slot is the league prior, and the
    caller says how many). bf_dist: his batters-faced distribution
    (starter_bf_dist). Plate appearance j goes to slot ((j - 1) mod 9) + 1
    and ends in an outcome from the odds-ratio combination of that
    batter and this pitcher — the same per-PA model as the batter props,
    seen from the mound.

    Returns {"exp_bf", "probs": {market: p}, "pmfs": {stat: pmf}} or None.

    How long he lasts is his own BF distribution, taken as independent of
    how the game goes. In reality a starter getting hit is pulled
    earlier, so hits allowed run slightly wider than this; the nightly's
    walk-forward against his own rate is the check.
    """
    if not model or not bf_dist or not order_counts:
        return None
    league = model.get("league_rates")
    pri_b, pri_p = model.get("batter_priors"), model.get("pitcher_priors")
    pr = shrunk_rates(p_counts, pri_p) if p_counts and p_counts.get("PA") else None
    if not league or not pr:
        return None
    per_slot = []
    for i in range(9):
        bc = order_counts[i] if i < len(order_counts) else None
        b = shrunk_rates(bc or {"PA": 0}, pri_b)
        if not b:
            return None
        per_slot.append(_steps(combine(b, pr, league)))
    max_bf = max(int(k) for k in bf_dist)
    cur = {k: [1.0] for k in per_slot[0]}
    mix = {}
    exp_bf = 0.0
    tot_w = 0.0
    for j in range(1, max_bf + 1):
        steps = per_slot[(j - 1) % 9]
        cur = {k: mm.convolve(cur[k], steps[k]) for k in cur}
        w = bf_dist.get(j, 0.0) or bf_dist.get(str(j), 0.0)
        if w:
            _mix(mix, cur, w)
            exp_bf += j * w
            tot_w += w
    if not tot_w:
        return None
    mix = {k: [x / tot_w for x in v] for k, v in mix.items()}
    probs = {key: round(mm.prob_at_least(mix[stat], n) or 0.0, 4)
             for key, _l, stat, n in PITCHER_MARKETS}
    return {"exp_bf": round(exp_bf / tot_w, 1), "probs": probs,
            "pmfs": {k: _trim(v) for k, v in mix.items()},
            "exp": {k: round(sum(i * p for i, p in enumerate(v)), 2) for k, v in mix.items()}}


def starter_bf_dist(bf_list, model, prior_bf=None):
    """{bf: prob} for a starter — his own starts (last season's counted at
    the FITTED prior_weight["bf"]) mixed with the league's by the fitted
    strength (in starts). No starts -> the league's."""
    league = {int(k): v for k, v in (model.get("league_bf_hist") or {}).items()}
    s = model.get("bf_strength_starts")
    ltot = sum(league.values())
    if not league or not ltot:
        return None
    own = Counter(int(b) for b in (bf_list or []))
    w_bf = ((model.get("prior_weight") or {}).get("bf") or 0.0)
    if prior_bf and w_bf:
        for b in prior_bf:
            own[int(b)] += w_bf
    n = sum(own.values())
    w_own = n / (n + s) if (s and n) else 0.0
    out = Counter()
    for bf, c in league.items():
        out[bf] += (1 - w_own) * c / ltot
    for bf, c in own.items():
        out[bf] += w_own * c / n
    return dict(out)


# ----------------------------------------------------------------------
# File access (reader side)
# ----------------------------------------------------------------------
_memo = {}


def load_prop_model():
    """data/statcast/prop_model.json from the nightly archive, or None."""
    base = Path(__file__).resolve().parents[1] / "data"
    for p in (base / "statcast" / "prop_model.json", base / "prop_model.json"):
        if p.exists():
            try:
                st = p.stat()
                key = (str(p), st.st_mtime_ns, st.st_size)
                if key not in _memo:
                    _memo.clear()
                    _memo[key] = json.loads(p.read_text())
                return _memo[key]
            except Exception:
                return None
    return None


def market_verdicts(model, pitcher=False):
    """{market_key: 'beats' | 'thin' | 'fails' | None} — the paired
    significance verdict vs the player's own frequency; a prop model from
    before verdicts existed falls back to the plain beat/fail boolean."""
    v = (model or {}).get("pitcher_validation" if pitcher else "validation") or {}
    out = {}
    for k, *_ in (PITCHER_MARKETS if pitcher else MARKETS):
        x = v.get(k) or {}
        verdict = (x.get("verdict") or {}).get("verdict")
        if verdict is None and "beats_baseline" in x:
            verdict = "beats" if x["beats_baseline"] else "fails"
        out[k] = verdict
    return out
