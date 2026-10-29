"""
Game-model shrink search widened and a nightly "this-season form" check
(10-29) — engines/game_model K_MAX / form_check.

The NHL goals fit sat on the old search edge (k = 400): a fit pinned to its
edge may want more than it was allowed. The check scores the fitted setting
against k = 20 (current form) walk-forward on this season's games.

Plain script — exits non-zero on failure. Synthetic finals. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - K_MAX back at 400 -> "a season with no team differences fits past the old
    edge" fails
  - form_check scoring both settings with the same k -> "the check compares
    two different settings" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import game_model as gm  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def season(spread, n_days=120, seed=1):
    rng = random.Random(seed)
    teams = [str(i) for i in range(16)]
    att = {t: 3.0 * (1 + rng.gauss(0, spread)) for t in teams}
    out = []
    for d in range(n_days):
        rng.shuffle(teams)
        for i in range(0, 16, 2):
            h, a = teams[i], teams[i + 1]
            hs = sum(1 for _ in range(60) if rng.random() < att[h] / 60)
            as_ = sum(1 for _ in range(60) if rng.random() < att[a] / 60)
            out.append({"date": f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}", "home": h, "away": a,
                        "hs": hs, "as": as_, "extra": False})
    return out


flat = gm.fit(season(0.0))
check("a season with no team differences fits past the old edge",
      flat["shrink_k"] > 400)
real = gm.fit(season(0.25, seed=2))
check("a season with real differences still fits well inside it", real["shrink_k"] < 100)
fc = gm.form_check(season(0.25, seed=2), real)
check("the check compares two different settings, on every game after the first day",
      fc["fitted_k"] != fc["form_k"] and fc["n"] > 800 and fc["verdict"]["verdict"] is not None)
check("too few games: no check", gm.form_check(season(0.2)[:10], real) is None)
src_m = (ROOT / "app" / "engines" / "nhl_model.py").read_text()
src_p = (ROOT / "nhl_precompute.py").read_text()
check("the NHL nightly ships and prints it",
      '"form_check": goal.get("form_check")' in src_m
      and "NHL goal ratings vs this-season form" in src_p)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
