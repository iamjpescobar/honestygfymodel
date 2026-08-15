"""Does the model beat a DUMB list? Reads the research log, no new logging.

    python benchmark_probe.py

THE QUESTION THIS ANSWERS, AND WHY THE RESULTS PAGE CANNOT
----------------------------------------------------------
The Results page grades HR Edge against 11.9% — the share of all league
starters who homer on a given night. Over 18 days the board is 19/89 =
21.3%, which is p=0.003 against that baseline.

**But 11.9% is the wrong opponent, and it flatters the board.** The
board does not pick random starters; it picks sluggers. A list built by
sorting tonight's starters on season ISO and taking five would also beat
11.9%, with no model in it at all.

So 21.3% proves the board picks power hitters. It does NOT prove the
ranking — four axes, a platoon term, a context layer — adds anything
beyond that.

This probe runs the honest comparison: the model's top five against
naive top fives drawn from the SAME pool on the SAME nights, graded with
the same outcomes.

    If the model beats the naive lists  -> the machinery earns its keep
    If it ties them                     -> it is an elaborate way to say
                                           "bet the guys who hit homers"
    If it loses                         -> the ranking is subtracting

WHY IT NEEDS NO NIGHTLY STEP
----------------------------
hr_research_log already records EVERY rated bat with its full stat line
and its graded result. Every naive list is reconstructable from what is
already on disk, and the answer improves on its own as the log fills.
Adding a second logger would have meant a second thing to keep in sync.

READ THE SAMPLE COLUMN FIRST. At ten picks an arm this says nothing;
these are 5 picks a night, so a month is ~150.
"""
import json
import sys
from collections import Counter
from math import erf, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "data" / "hr_research"
TOP_N = 5

# Each naive list is something a person could build in a spreadsheet in
# five minutes with no model. That is the point — they are the bar the
# machinery has to clear, not strawmen.
NAIVE = [
    ("ISO", "season isolated power"),
    ("HR/FB", "home runs per fly ball"),
    ("SLG", "slugging"),
    ("Brl/PA", "barrels per plate appearance"),
    ("HH %", "hard-hit rate"),
]
# The model's own numbers, for comparison against each other.
MODEL = [("edge", "HR Edge (score + tonight)"),
         ("hr_score", "HR Score (skill only)"),
         ("hr_threat", "HRThreat")]


def _rows():
    out = []
    for p in sorted(LOG_DIR.glob("*.ndjson")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return [r for r in out if r.get("graded") == "played"]


def _pick(rows, key):
    """Top N by `key` on each date. Bats missing the key are skipped —
    never defaulted to 0, which would rank an unmeasured hitter last
    rather than leaving him out."""
    hits = tot = 0
    for date in sorted({r["date"] for r in rows}):
        day = [r for r in rows if r["date"] == date and r.get(key) is not None]
        day.sort(key=lambda r: r[key], reverse=True)
        for r in day[:TOP_N]:
            tot += 1
            hits += 1 if r.get("hr") else 0
    return hits, tot


def _p(hits, n, base):
    if not n:
        return 1.0
    sd = sqrt(n * base * (1 - base)) or 1e-9
    z = (hits - n * base) / sd
    return 0.5 * (1 - erf(z / sqrt(2)))


def main() -> int:
    rows = _rows()
    if not rows:
        print(f"No graded rows in {LOG_DIR}. The log grades on the nightly "
              f"run; check for 'hr_research: graded N bat(s)'.")
        return 1
    dates = sorted({r["date"] for r in rows})
    base = sum(1 for r in rows if r.get("hr")) / len(rows)

    print(f"{len(rows):,} graded bats over {len(dates)} night(s): "
          f"{dates[0]} to {dates[-1]}")
    print(f"Rate across EVERY rated bat: {base * 100:.1f}% "
          f"— this is the honest floor, not the 11.9% league figure, "
          f"because it is measured on the same pool the lists draw from.\n")

    print("=" * 68)
    print(f"{'list':<34}{'record':>10}{'rate':>8}{'vs pool':>10}")
    print("=" * 68)
    results = []
    for key, label in MODEL + NAIVE:
        h, n = _pick(rows, key)
        if not n:
            continue
        results.append((h / n, label, h, n))
        tag = "MODEL" if (key, label) in MODEL else "naive"
        print(f"{tag} {label:<28}{h:>4}/{n:<5}{h / n * 100:>7.1f}%"
              f"{(h / n - base) * 100:>+9.1f}")

    results.sort(reverse=True)
    best_model = max((r for r in results if "HR Edge" in r[1]), default=None)
    best_naive = max((r for r in results
                      if r[1] in [d for _k, d in NAIVE]), default=None)

    print(f"""
HOW TO READ IT
==============
The rightmost column is each list against the pool it was drawn from —
not against the league. A list that cannot beat the pool of bats the
board already rated is not selecting anything.

THE COMPARISON THAT MATTERS is HR Edge against the best naive list. The
league baseline on the Results page is a much easier opponent: it
includes every slap hitter in the majors, and any power-sorted list
clears it.
""")
    if best_model and best_naive:
        m, _l, mh, mn = best_model
        b, bl, bh, bn = best_naive
        print(f"  HR Edge      {mh}/{mn}  {m * 100:.1f}%")
        print(f"  best naive   {bh}/{bn}  {b * 100:.1f}%   ({bl})")
        print(f"  difference   {(m - b) * 100:+.1f} points")
        if mn < 100:
            print(f"\n  ** {mn} picks. This is not an answer yet — at five a "
                  f"night a month is ~150, and the gap above is well inside "
                  f"noise at this size. Re-run in a few weeks. **")
        else:
            print(f"\n  p={_p(mh, mn, b):.4f} against the naive list as the "
                  f"baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
