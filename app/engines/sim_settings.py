"""
Simulator settings, ONE ENTRY PER SPORT (10-26). Izzy: "NHL simulator be
crashing on me ... maybe all of them need their own settings, I think all
of them are sharing settings and logic".

They were: every simulator page copied the same block (a run cached with
st.cache_data, max 4 runs kept, the whole game in one numpy pass). That
block suits a light simulator and breaks a heavy one.

MEASURED 10-26 (one game each, peak memory of one run, size of the kept
result):
    NHL 50,000 games, 36 skaters, period by period:
        +147 MB while it runs, 31 MB kept
    MLB 50,000 games, plate appearance by plate appearance:
        +81 MB while it runs, 25 MB kept (the page runs 25,000)
    NBA 50,000: +14 MB, 4 MB kept     NFL 50,000: +26 MB, 5 MB kept
On top of that, st.cache_data hands back a fresh COPY of the kept result
on every click (it is pickled), and four runs were kept per page. On the
NHL page alone that was 4 x 31 MB kept + a 31 MB copy per click + a
147 MB run + the parlay's own runs (50,000-game chunks) — enough to push
the server over its memory and drop the page.

What each sport now gets, sized from those numbers:
  games      how many games the page plays (the same as before: the
             accuracy is kept; only how the work is cut up changed)
  chunk      the run is made in pieces this big and joined, so the
             memory a run needs is one piece's, not the whole run's
  keep       how many games' runs stay cached (st.cache_resource: one
             shared copy, no copy per click)
  sgp        games behind a same-game parlay, and sgp_chunk its pieces
Result, NHL 50,000 games: peak 141 MB in one pass -> 62 MB in pieces
(tracemalloc, tests/test_sim_settings.py), kept once instead of copied.
Splitting a run into pieces changes which random numbers are drawn, not
what the simulator does: the joined run has the same distribution
(tests/test_sim_settings.py checks the means against one big run).

Pure apart from numpy.
"""
import numpy as np

SIMS = {
    "nhl": {"games": 50_000, "chunk": 10_000, "keep": 2, "sgp": 200_000, "sgp_chunk": 10_000},
    "nba": {"games": 50_000, "chunk": 25_000, "keep": 2, "sgp": 500_000, "sgp_chunk": 100_000},
    "nfl": {"games": 50_000, "chunk": 25_000, "keep": 2, "sgp": 200_000, "sgp_chunk": 50_000},
    "mlb": {"games": 25_000, "chunk": 5_000, "keep": 2, "sgp": 50_000, "sgp_chunk": 5_000},
}


def settings(sport):
    return dict(SIMS[sport])


def merge(parts):
    """Join chunk results: arrays whose first axis is that chunk's game
    count are concatenated; dicts merge key by key; anything else (a
    number, a label) is taken from the first chunk."""
    first = parts[0]
    if isinstance(first, dict):
        return {k: merge([p[k] for p in parts]) for k in first}
    if isinstance(first, np.ndarray) and first.ndim >= 1:
        return np.concatenate(parts, axis=0)
    return first


def run(sport, fn, *args, seed=7, games=None, chunk=None, **kw):
    """fn(*args, n=..., seed=..., **kw) played `games` times in pieces of
    `chunk` (the sport's settings by default), joined."""
    s = SIMS[sport]
    games = games or s["games"]
    chunk = chunk or s["chunk"]
    parts, done, k = [], 0, 0
    while done < games:
        m = min(chunk, games - done)
        parts.append(fn(*args, n=m, seed=int(seed) + 7919 * k, **kw))
        done += m
        k += 1
    return parts[0] if len(parts) == 1 else merge(parts)
