"""
Simulator settings per sport (10-26) — engines/sim_settings. Izzy: "NHL
simulator be crashing on me ... maybe all of them need their own
settings".

Measured before the change (one game each): NHL 50,000 games +147 MB
while it runs and 31 MB kept, MLB 50,000 +81 MB / 25 MB, NBA +14 / 4,
NFL +26 / 5; the pages kept 4 runs each through st.cache_data, which
hands back a fresh copy on every click.

Plain script — exits non-zero on failure. Synthetic games (the sims' own
test fixtures). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - merge() keeping only the first piece -> "the joined run has every game" fails
  - run() ignoring the chunk (one big pass) -> "a run in pieces needs a fraction
    of the memory" fails
  - every piece drawn with the same seed -> "pieces are different games" fails
"""
import sys
import tracemalloc
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nhl_sim as hs  # noqa: E402
from engines import sim_settings as ss  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


check("every sport has its own entry: games, chunk, keep, sgp, sgp_chunk",
      set(ss.SIMS) == {"nhl", "nba", "nfl", "mlb"}
      and all(set(v) == {"games", "chunk", "keep", "sgp", "sgp_chunk"} for v in ss.SIMS.values()))
check("the heavy ones are cut finer (NHL, MLB pieces smaller than NBA / NFL)",
      ss.SIMS["nhl"]["chunk"] < ss.SIMS["nba"]["chunk"]
      and ss.SIMS["mlb"]["chunk"] < ss.SIMS["nfl"]["chunk"]
      and all(v["keep"] <= 2 for v in ss.SIMS.values()))
check("settings() hands out a copy (one page cannot change another's)",
      ss.settings("nhl") is not ss.SIMS["nhl"])

# --- merge on a toy simulator -----------------------------------------------------------
def toy(n, seed=7, k=3):
    r = np.random.default_rng(seed)
    return {"home": r.poisson(3, n), "per": {"home": r.poisson(1, (n, 3))},
            "stats": {"a": {"g": r.poisson(0.4, n).astype(np.int16)}}, "label": "x"}


T = ss.run("nhl", toy, games=25_000, chunk=10_000, seed=1)
check("the joined run has every game, nested arrays too, labels kept",
      T["home"].shape == (25_000,) and T["per"]["home"].shape == (25_000, 3)
      and T["stats"]["a"]["g"].dtype == np.int16 and T["label"] == "x")
check("pieces are different games (each its own seed)",
      not np.array_equal(T["home"][:10_000], T["home"][10_000:20_000]))
check("one piece when the run fits in one", ss.run("nhl", toy, games=500, chunk=10_000)["home"].shape
      == (500,))

# --- the NHL simulator: same answers, a fraction of the memory ----------------------------
SK = [{"pid": f"{s}{i}", "side": s, "mu": {"sog": 2.6 - 0.1 * i, "g": 0.36 - 0.015 * i,
                                          "a": 0.46 - 0.02 * i}}
      for s in ("home", "away") for i in range(18)]
G = {"mu_home": 3.1, "mu_away": 2.9, "shots_home": 31, "shots_away": 29}


def peak(fn):
    tracemalloc.start()
    out = fn()
    p = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return out, p / 1e6


one, p_one = peak(lambda: hs.simulate(G, SK, None, 8.0, n=50_000, seed=3))
del one
cut, p_cut = peak(lambda: ss.run("nhl", hs.simulate, G, SK, None, 8.0, seed=3))
print(f"     NHL 50,000 games: one pass peak {p_one:.0f} MB, in pieces {p_cut:.0f} MB")
check("a run in pieces needs a fraction of the memory (under 60% of one pass)",
      p_cut < 0.6 * p_one)
big = hs.simulate(G, SK, None, 8.0, n=50_000, seed=11)
for key in ("home", "away"):
    se = np.sqrt(cut[key].var() / 50_000 + big[key].var() / 50_000)
    check(f"same answer: mean {key} goals within noise ({cut[key].mean():.3f} vs "
          f"{big[key].mean():.3f})", abs(cut[key].mean() - big[key].mean()) < 4 * se)
p0 = cut["stats"]["home0"]["pts"]
check("same answer: the top skater's point chance within noise",
      abs((p0 > 0.5).mean() - (big["stats"]["home0"]["pts"] > 0.5).mean()) < 0.012
      and p0.shape == (50_000,))

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall simulator settings checks passed")
