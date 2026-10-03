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

# The markets on the page: (key, label, stat, at_least).
MARKETS = (
    ("h1", "Hits O0.5", "h", 1),
    ("h2", "Hits O1.5", "h", 2),
    ("tb2", "TB O1.5", "tb", 2),
    ("hr1", "HR O0.5", "hr", 1),
    ("k1", "K O0.5", "k", 1),
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


def _count_pmfs(p_sp, p_pen, n_sp, n_pen):
    """Exact pmfs of hits, TB, HR, K over n_sp + n_pen PAs."""
    h = [1.0]
    tb = [1.0]
    hr = [1.0]
    k = [1.0]
    for probs, n in ((p_sp, n_sp), (p_pen, n_pen)):
        if n <= 0:
            continue
        ph = sum(probs[o] for o in TB)
        step_h = [1 - ph, ph]
        step_tb = [0.0] * 5
        for o, p in probs.items():
            step_tb[TB.get(o, 0)] += p
        step_hr = [1 - probs["HR"], probs["HR"]]
        step_k = [1 - probs["K"], probs["K"]]
        for _ in range(n):
            h = mm.convolve(h, step_h)
            tb = mm.convolve(tb, step_tb)
            hr = mm.convolve(hr, step_hr)
            k = mm.convolve(k, step_k)
    return {"h": h, "tb": tb, "hr": hr, "k": k}


def project_batter(slot, b_counts, p_counts, model, bf_dist=None):
    """{"exp_pa", "probs": {market: p}, "fair": {market: american},
        "pa": batter PA on record} or None.

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
    scen = scenario_mass(int(slot), hist, bf_dist if p else None)
    totals = {m[0]: 0.0 for m in MARKETS}
    exp_pa = 0.0
    for (n, n_sp), w in scen.items():
        exp_pa += n * w
        pm = _count_pmfs(p_sp, p_pen, n_sp, n - n_sp)
        for key, _label, stat, at_least in MARKETS:
            totals[key] += w * (mm.prob_at_least(pm[stat], at_least) or 0.0)
    probs = {k: round(v, 4) for k, v in totals.items()}
    return {
        "exp_pa": round(exp_pa, 2),
        "probs": probs,
        "fair": {k: mm.fair_american(v) for k, v in probs.items()},
        "pa": int((b_counts or {}).get("PA", 0)),
        "vs_starter": p is not None,
    }


def starter_bf_dist(bf_list, model):
    """{bf: prob} for a starter — his own starts mixed with the league's
    by the fitted strength (in starts). No starts -> the league's."""
    league = {int(k): v for k, v in (model.get("league_bf_hist") or {}).items()}
    s = model.get("bf_strength_starts")
    ltot = sum(league.values())
    if not league or not ltot:
        return None
    own = Counter(int(b) for b in (bf_list or []))
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


def market_verdicts(model):
    """{market_key: 'beats' | 'thin' | 'fails' | None} — the paired
    significance verdict vs the batter's own frequency; a prop model from
    before verdicts existed falls back to the plain beat/fail boolean."""
    v = (model or {}).get("validation") or {}
    out = {}
    for k, *_ in MARKETS:
        x = v.get(k) or {}
        verdict = (x.get("verdict") or {}).get("verdict")
        if verdict is None and "beats_baseline" in x:
            verdict = "beats" if x["beats_baseline"] else "fails"
        out[k] = verdict
    return out
