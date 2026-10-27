"""
The offered projection's own level, learned from the graded record (10-27).

Since 10-26 every DraftKings line the site priced keeps the projection the
site OFFERED beside what the player did (engines/book_grade: graded rows
end [letter, our projection, what he did]). The first night read NBA
points x1.06, rebounds x1.17, assists x1.11, NHL assists x1.23 (actual /
ours). The team-minutes fix (10-27) explains about +6% on every NBA stat;
rebounds and assists ran more than that, and one night is not a verdict.

So the level is LEARNED and TESTED, per stat, every night:
  factor  = 1 + (sum actual / sum ours - 1) x n / (n + N0)
            from the player-game-stat rows graded so far (each once)
  test    walk-forward by date: each night's projections scaled by the
          factor from the nights BEFORE it, against the box score —
          squared error of the projection, paired with the unscaled one
  used    only when the test BEATS on MIN_TEST+ lines; otherwise the
          factor is 1 and the page numbers are the model's alone.
A model change resets the record: `since` (the caller's) drops the nights
graded before it — NBA learns from 10-27 on, because the team-minutes fix
that day already moved every NBA projection up about 6%, and learning from
the nights before would correct that twice.
A factor never goes outside CLIP. Base stats only; combos (PRA etc.) are
re-summed from them by the caller.

Pure — no streamlit, no requests.
"""
from engines import model_math as mm

N0 = 150           # lines of evidence before the factor moves halfway to the data
MIN_TEST = 150     # graded lines in the walk-forward test before it can be used
CLIP = (0.85, 1.20)


def _rows(graded, stat, since=None):
    """[(date, ours, actual)] for one stat, once per player-game, from
    `since` on (a model change resets what the level can learn from)."""
    seen, out = set(), []
    for r in graded or []:
        if len(r) < 13 or r[3] != stat or r[11] is None or r[12] is None:
            continue
        if since and str(r[0]) < since:
            continue
        k = (r[1], r[2])
        if k in seen:
            continue
        seen.add(k)
        out.append((str(r[0]), float(r[11]), float(r[12])))
    out.sort()
    return out


def factor(rows):
    if not rows:
        return 1.0
    so = sum(o for _d, o, _a in rows)
    sa = sum(a for _d, _o, a in rows)
    if so <= 0:
        return 1.0
    n = len(rows)
    f = 1.0 + (sa / so - 1.0) * n / (n + N0)
    return min(CLIP[1], max(CLIP[0], f))


def fit(graded, stats, since=None):
    """{stat: {"factor", "n", "test": verdict, "n_test", "used": factor or 1.0}}."""
    out = {}
    for st in stats:
        rows = _rows(graded, st, since)
        dates = sorted({d for d, _o, _a in rows})
        with_f, without = [], []
        for d in dates[1:]:
            f = factor([x for x in rows if x[0] < d])
            for _d, o, a in (x for x in rows if x[0] == d):
                with_f.append((a - o * f) ** 2)
                without.append((a - o) ** 2)
        v = mm.paired_verdict(with_f, without) if len(with_f) >= 2 else {"verdict": None}
        f_all = factor(rows)
        ok = v.get("verdict") == "beats" and len(with_f) >= MIN_TEST
        out[st] = {"factor": round(f_all, 4), "n": len(rows), "test": v,
                   "n_test": len(with_f), "used": round(f_all, 4) if ok else 1.0}
    return out


def line(league, fitted):
    return (f"  [verify] OFFERED LEVEL {league}: " + "; ".join(
        f"{st} x{x['factor']} on {x['n']} lines (test {x['test'].get('verdict')} "
        f"z={x['test'].get('z')}, n={x['n_test']}) -> "
        + ("USED" if x["used"] != 1.0 else "not used") for st, x in fitted.items()))
