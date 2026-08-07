"""The slate coverage counter tells the truth, identically for both leagues.

WHY THIS EXISTS

The counter was added on 2026-08-07 to answer a question no log could
answer: did the schedule-card venue/time fix actually reach the page?
On its FIRST production run it printed

    KBO: slate 2026-08-07 coverage — venue 0/5, first pitch 0/5,
                                     a named starter 5/5

Two things were wrong with that line and only one of them was in the
scraper.

  * `venue 0/5` was CORRECT. Every game on the 2026-08-07 slate was
    called for extreme heat, and a called card carries no clock — the
    probe dumped `Kia Tigers LG Twins Canceled Extreme Heat` with no
    <time> element. The fix under test was working. But a bare zero
    reads as a broken scraper, so the line now says how many games were
    called off and why that makes zero the right answer.

  * `a named starter 5/5` was a LIE, and it was mine. KBO writes
    `g.get("away_starter") or "TBD"`, so the field is never falsy; the
    KBO copy of the counter tested truthiness while the NPB copy tested
    against "TBD". Two copies of the same idea, disagreeing inside a
    single run, on a slate where the homepage had reported `0 of 15`
    starters. A counter that lies is worse than no counter, because a
    counter is trusted.

Hence one engine, imported by both pipelines (rule 21), and this test.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
from engines.intl_slate import coverage_line  # noqa: E402

failures = []


def check(label, ok):
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def game(**kw):
    g = {"stadium": "TBD", "time_kst": "TBD", "time_jst": "TBD",
         "away_starter": "TBD", "home_starter": "TBD",
         "status": "scheduled"}
    g.update(kw)
    return g


# ---- 1. "TBD" is missing, not present -------------------------------
# This is the whole bug. Both pipelines write "TBD" rather than leaving
# a key absent, so a truthiness test counts every game as complete.
line = coverage_line("KBO", "2026-08-07", [game()] * 5, "time_kst")
check("an all-TBD slate reports zero venues", "venue 0/5" in line)
check("an all-TBD slate reports zero first pitches",
      "first pitch 0/5" in line)
check('an all-TBD slate reports zero named starters — the 2026-08-07 bug',
      "a named starter 0/5" in line)

# Empty string and None are missing too — a source can hand back either.
line = coverage_line("KBO", "d", [game(stadium=""), game(stadium=None)],
                     "time_kst")
check("empty string and None count as missing", "venue 0/2" in line)


# ---- 2. real values are counted -------------------------------------
full = game(stadium="Daejeon", time_kst="18:30", away_starter="Oh Won-seok")
line = coverage_line("KBO", "2026-08-08", [full] * 5, "time_kst")
check("a real venue is counted", "venue 5/5" in line)
check("a real first pitch is counted", "first pitch 5/5" in line)
check("one named starter is enough for that game",
      "a named starter 5/5" in line)


# ---- 3. a called-off slate explains its own zeros --------------------
off = coverage_line("KBO", "2026-08-07",
                    [game(status="postponed")] * 5, "time_kst")
check("a called-off slate says so", "5 of 5 called off" in off)
check("a called-off slate says why zero is expected",
      "no clock" in off)
# KBO's source word is "Canceled"; NPB's is "postponed". Both must land.
canc = coverage_line("KBO", "d", [game(status="canceled")], "time_kst")
check('"canceled" counts as called off, not just "postponed"',
      "1 of 1 called off" in canc)
# A healthy slate must NOT carry the excuse — it would read as an alibi
# for a real zero later.
check("a played slate carries no called-off note",
      "called off" not in coverage_line("KBO", "d", [full], "time_kst"))


# ---- 4. an empty slate is not a zero-coverage slate ------------------
# 0/0 would read as total failure. An off-day is not a defect.
check("an empty slate reports an off-day, not 0/0",
      "empty slate" in coverage_line("NPB", "d", [], "time_jst")
      and "0/0" not in coverage_line("NPB", "d", [], "time_jst"))


# ---- 5. the two leagues share ONE implementation --------------------
# Rule 21, and the specific failure above: duplicated counters drifted
# apart and disagreed inside a single run.
kbo = open(os.path.join(ROOT, "kbo_precompute.py"), encoding="utf-8").read()
npb = open(os.path.join(ROOT, "npb_precompute.py"), encoding="utf-8").read()
for name, src in (("kbo_precompute", kbo), ("npb_precompute", npb)):
    check(f"{name} imports the shared counter",
          "from engines.intl_slate import coverage_line" in src)
    # Assert the PROPERTY — no second implementation — not a spelling.
    check(f"{name} does not hand-roll its own counter",
          not re.search(r'f?"\{?\w*\}?:?\s*slate .*coverage', src))

# Same field set for both, differing only in the timezone key, which is
# the one thing that legitimately differs.
k = coverage_line("KBO", "d", [full], "time_kst")
n = coverage_line("NPB", "d", [game(stadium="Tokyo Dome", time_jst="18:00",
                                    home_starter="Yamamoto")], "time_jst")
check("both leagues emit the same shape",
      k.replace("KBO", "X") == n.replace("NPB", "X"))

print("FAILING:" + (" " + ", ".join(failures) if failures else " none"))
sys.exit(1 if failures else 0)
