"""
Chances anchored to DraftKings (10-29) — engines/market_anchor, wired in
book_props_grade (fit + scorecard) and the Bet Finder (bet_finder.
anchor_chance).

Measured 10-29 on the graded record: NBA main-line chances had calibration
slope 0.31 and our disagreement with DraftKings' line was followed by the
box score at 0.08 per unit — most of it noise.

Plain script — exits non-zero on failure. Synthetic graded rows. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - b fitted on the SAME night it is scored on -> "a night is scored with the b
    from the nights before it" fails
  - the gate ignoring MIN_TEST -> "too few test lines: not used" fails
  - anchoring with one price only (book chance with the vig in) -> "no other
    side: the chance is left alone" fails
  - beats_book ignoring whether the anchor is used -> "past the THIN cap only
    when the anchor is used AND beat DraftKings' own" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import bet_finder as bf  # noqa: E402
from engines import market_anchor as ma  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


check("b = 0 is the book's chance, b = 1 ours", abs(ma.anchored(0.3, 0.5, 0.0) - 0.5) < 1e-9
      and abs(ma.anchored(0.3, 0.5, 1.0) - 0.3) < 1e-9)
check("in between, in between", 0.3 < ma.anchored(0.3, 0.5, 0.5) < 0.5)
check("a missing piece leaves the chance alone", ma.anchored(0.3, None, 0.5) == 0.3
      and ma.anchored(0.3, 0.5, None) == 0.3)


def record(signal, nights=8, per=120, seed=2):
    """book = truth + noise; ours = book + signal x (truth - book) + noise."""
    rng = random.Random(seed)
    out = []
    for d in range(nights):
        for i in range(per):
            t = rng.uniform(0.2, 0.8)
            bk = min(0.95, max(0.05, t + rng.gauss(0, 0.06)))
            ours = min(0.95, max(0.05, bk + signal * (t - bk) + rng.gauss(0, 0.15)))
            y = 1 if rng.random() < t else 0
            out.append([f"2026-11-{d + 1:02d}", "e", str(i), "pts", 20.5, ours, bk, y])
    return out


noise = ma.fit(record(0.0))["pts"]
check("our disagreement all noise: b near 0, used, beats the served chance",
      noise["b"] <= 0.15 and noise["used"] is not None
      and noise["vs_served"]["verdict"] == "beats")
few = ma.fit(record(0.0, nights=2, per=140, seed=5))["pts"]
check("too few test lines: not used (even when the test beats)",
      few["n_test"] == 140 and few["vs_served"]["verdict"] == "beats" and few["used"] is None)
one = [r for r in record(0.0) if r[0] == "2026-11-01"]
check("a single night has nothing before it to be tested on",
      ma.fit(one)["pts"]["n_test"] == 0 and ma.fit(one)["pts"]["used"] is None)

# walk-forward: night 1 (small) says b = 0, night 2 (big) rewards b = 1. Scored
# with night 1's b, night 2 is pulled to the book and LOSES to the served
# chance; a b that peeked at night 2 would equal the served chance instead.
wf = [["2026-11-01", "e", str(i), "pts", 1, 0.9 if i % 2 else 0.1, 0.5, 0 if i % 2 else 1]
      for i in range(50)]
wf += [["2026-11-02", "e", str(i), "pts", 1, 0.9 if i % 2 else 0.1, 0.5, 1 if i % 2 else 0]
       for i in range(300)]
f = ma.fit(wf)["pts"]
check("a night is scored with the b from the nights before it",
      f["n_test"] == 300 and f["vs_served"]["verdict"] == "fails"
      and f["vs_served"]["diff"] < -0.05)
check("since: nights before a model change are not learned from",
      ma.fit(record(0.0), since="2026-11-05")["pts"]["n"] == 4 * 120)

card = {"anchor": {"nba": {"pts": {"used": 0.2}, "pts*": {"used": None}}}}
check("the main-line b on DraftKings' line; the alternate fit off it",
      ma.b_for(card, "nba", "pts") == 0.2 and ma.b_for(card, "nba", "pts", main=False) is None
      and ma.b_for(None, "nba", "pts") is None)

card2 = {"anchor": {"nba": {"pts": {"used": 0.2, "vs_book": {"verdict": "beats"}},
                            "reb": {"used": 0.2, "vs_book": {"verdict": "thin"}},
                            "ast": {"used": None, "vs_book": {"verdict": "beats"}}}}}
check("past the THIN cap only when the anchor is used AND beat DraftKings' own",
      ma.beats_book(card2, "nba", "pts") and not ma.beats_book(card2, "nba", "reb")
      and not ma.beats_book(card2, "nba", "ast") and not ma.beats_book(None, "nba", "pts"))
check("the Bet Finder lifts the cap only for anchored calls that earned it",
      "_anc and _anchor_beats(sport, stat, _main)" in
      (ROOT / "app" / "views" / "Bet_Finder.py").read_text())
ch, a = bf.anchor_chance(0.30, -110, -110, 0.0)
check("both prices in: the chance moves to the book's de-vigged chance",
      a and abs(ch - 0.5) < 1e-6)
ch1, a1 = bf.anchor_chance(0.30, -110, None, 0.0)
check("no other side: the chance is left alone", ch1 == 0.30 and not a1)
check("no b: left alone", bf.anchor_chance(0.30, -110, -110, None) == (0.30, False))

src = (ROOT / "app" / "views" / "Bet_Finder.py").read_text()
grd = (ROOT / "book_props_grade.py").read_text()
check("the nightly fits it and ships it in the scorecard; the Bet Finder uses it",
      "anchor[lg] = ma.fit(rows, ma.SINCE.get(lg))" in grd and '"anchor": anchor' in grd
      and "bf.anchor_chance(ch, _yp, _os, _anchor_b(sport, stat, _main))" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
