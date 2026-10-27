"""
NHL nightly speed (10-27): the NHL step spent ~8 of its ~9 minutes FITTING
(ice time, PP weighting, shot factors) — millions of passes through
nhl_model.probs, each rebuilding a negative binomial from scratch and the
chances of every market, though each fit reads one family.

Two changes, both required to give THE SAME NUMBERS (not close — equal):
  - model_math.nb_pmf keeps lgamma(k + r) - lgamma(r) - lgamma(k + 1) per
    (size, length): the shots size is one number all night
  - nhl_model.probs(only=...) builds only the asked family's distributions;
    the fits pass their family

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - the nb table keyed on the size alone (not the length) -> "a shorter and a
    longer pmf at the same size are both right" fails
  - only= building points from goals alone -> "only= gives the same numbers"
    fails
"""
import random
import sys
from math import exp, lgamma, log
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import model_math as mm  # noqa: E402
from engines import nhl_model as hm  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def nb_ref(mu, r, max_k):
    """The formula as it was written before 10-27."""
    p = r / (r + mu)
    return [exp(lgamma(k + r) - lgamma(r) - lgamma(k + 1) + r * log(p) + k * log(1 - p))
            for k in range(max_k + 1)]


rng = random.Random(5)
bad = 0
for _ in range(5000):
    mu, r = rng.uniform(0.01, 9), rng.choice([2.5, 8.0, rng.uniform(0.3, 60)])
    if mm.nb_pmf(mu, r, 20) != nb_ref(mu, r, 20):
        bad += 1
check("negative binomial: equal to the old formula, float for float (5,000 draws)", bad == 0)
check("a shorter and a longer pmf at the same size are both right",
      mm.nb_pmf(2.0, 7.5, 5) == nb_ref(2.0, 7.5, 5)
      and mm.nb_pmf(2.0, 7.5, 30) == nb_ref(2.0, 7.5, 30))
check("poisson fall-through unchanged", mm.nb_pmf(2.0, None, 10) == mm.poisson_pmf(2.0, 10))

bad = 0
for _ in range(3000):
    r = {"sog": rng.uniform(0.3, 4.5), "g": rng.uniform(0.02, 0.6), "a": rng.uniform(0.02, 0.8)}
    kw = dict(shot_ratio=rng.uniform(.8, 1.2), goal_ratio=rng.uniform(.8, 1.2),
              sog_disp=rng.choice([None, 9.3]), toi_sog=rng.uniform(.8, 1.2),
              toi_pts=rng.uniform(.8, 1.2), att_sog=rng.uniform(.8, 1.2),
              chance_g=rng.uniform(.8, 1.2))
    full = hm.probs(r, **kw)
    for only in (("sog",), ("g", "a", "pts"), ("g",)):
        part = hm.probs(r, **kw, only=only)
        want = {k: full[k] for k, _l, st, _n in hm.MARKETS if st in only}
        if part != want:
            bad += 1
check("only= gives the same numbers for the family asked, and nothing else", bad == 0)

src = (ROOT / "app" / "engines" / "nhl_model.py").read_text()
check("the ice-time / PP fits and the shot fits pass their family",
      "only=stats)" in src and "only=SHOT_FAMS[fam])" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
