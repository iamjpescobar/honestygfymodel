"""
CHANCES ANCHORED TO DRAFTKINGS (10-29).

Measured on the graded record (Site vs DraftKings): on NBA main lines our
over chances averaged 0.397 where overs hit 0.503 and DraftKings priced
0.495; a logistic fit gave our chance a calibration slope of 0.31 (1 =
right-sized), and where our projection disagreed with DraftKings' line the
box score followed us by 0.08 per unit (threes 0.91, assists 0.40, points
0.10, rebounds 0.02) — most of the gap between us and the book was noise.

So wherever DraftKings has a price, the chance is

    p = logistic( logit(book) + b x (logit(ours) - logit(book)) )

  book  DraftKings' own chance (de-vigged, both sides)
  b     how much of our disagreement with DraftKings is REAL, per league and
        market (main line "stat", alternate lines "stat*"): b = 0 is the
        book's chance, b = 1 is ours unchanged. LEARNED every night from the
        graded record and TESTED walk-forward by date: each night's lines
        scored with the b from the nights before it, against the chance the
        site served (squared error, paired). USED only when that test beats
        on MIN_TEST+ lines; otherwise the served chance stands (and the
        market's THIN cap, book_grade.market_status, still applies).

The record keeps storing the model's own chance — the anchor is learned
from it, so it is never learned from its own output.

Pure — no streamlit, no requests.
"""
import math

GRID = tuple(i / 20 for i in range(21))     # b from 0 to 1 in steps of 0.05
MIN_TEST = 150


def _logit(p):
    p = min(max(float(p), 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def anchored(ours, book, b):
    """The anchored chance, or `ours` when either piece is missing."""
    if ours is None or book is None or b is None:
        return ours
    x = _logit(book) + b * (_logit(ours) - _logit(book))
    return 1.0 / (1.0 + math.exp(-x))


def best_b(rows):
    """The b on GRID with the lowest squared error over rows [(ours, book, y)]
    (ties -> the smaller b, the more anchored), or None without rows."""
    if not rows:
        return None
    best = None
    for b in GRID:
        e = sum((anchored(o, k, b) - y) ** 2 for o, k, y in rows)
        if best is None or e < best[0] - 1e-12:
            best = (e, b)
    return best[1]


SINCE = {"nba": "2026-10-27"}   # the NBA team-minutes fix (10-27) moved every chance


def fit(graded, since=None):
    """{market: {"b", "n", "n_test", "vs_served", "vs_book", "used"}} from
    graded rows [date, eid, pid, market, line, ours, book, y, ...], from the
    night `since` on (a model change resets what the anchor learns from)."""
    from engines import model_math as mm
    by = {}
    for r in graded or []:
        if len(r) < 8 or r[5] is None or r[6] is None or r[7] is None:
            continue
        if since and str(r[0]) < since:
            continue
        by.setdefault(r[3], []).append((str(r[0]), float(r[5]), float(r[6]), int(r[7])))
    out = {}
    for key, rows in sorted(by.items()):
        rows.sort()
        dates = sorted({d for d, *_ in rows})
        anc, srv, bk = [], [], []
        for d in dates[1:]:
            b = best_b([(o, k, y) for dd, o, k, y in rows if dd < d])
            for _d, o, k, y in (x for x in rows if x[0] == d):
                anc.append((anchored(o, k, b) - y) ** 2)
                srv.append((o - y) ** 2)
                bk.append((k - y) ** 2)
        b_all = best_b([(o, k, y) for _d, o, k, y in rows])
        v_srv = mm.paired_verdict(anc, srv) if len(anc) >= 2 else {"verdict": None}
        v_bk = mm.paired_verdict(anc, bk) if len(anc) >= 2 else {"verdict": None}
        ok = v_srv.get("verdict") == "beats" and len(anc) >= MIN_TEST
        out[key] = {"b": b_all, "n": len(rows), "n_test": len(anc), "vs_served": v_srv,
                    "vs_book": v_bk, "used": b_all if ok else None}
    return out


def b_for(card, league, stat, main=True):
    """The b in use for one market (None = serve the model's own chance):
    the main-line fit on DraftKings' main line, the alternate-line fit
    ("stat*") off it."""
    fits = (((card or {}).get("anchor") or {}).get(league) or {})
    x = fits.get(stat if main else stat + "*")
    return (x or {}).get("used")


def line(league, fitted):
    return (f"  [verify] DRAFTKINGS ANCHOR {league}: " + "; ".join(
        f"{k} b={x['b']} (keeps {100 * (x['b'] or 0):.0f}% of our disagreement; test vs served "
        f"{(x['vs_served'] or {}).get('verdict')} z={(x['vs_served'] or {}).get('z')}, vs book "
        f"{(x['vs_book'] or {}).get('verdict')} z={(x['vs_book'] or {}).get('z')}, "
        f"n={x['n_test']}) -> {'USED' if x['used'] is not None else 'not used'}"
        for k, x in fitted.items()))
