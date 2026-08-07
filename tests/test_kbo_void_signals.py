"""The source's own void signals must reach the board, on EVERY date.

WHY THIS TEST EXISTS

On 2026-08-07 mykbostats listed every KBO game through 08-09 as
Canceled during a heat wave. The app would have shown all fifteen as
SCHEDULED, because parse_week's status block sat behind
`if gdate < today_str:` — a cancellation was only ever read for games
already in the past, which is the one time it no longer matters.

On a betting site that is the worst direction to be wrong in: the board
says a game is on when the source says it is off. It is the void
problem itself, not a cosmetic status. NPB never had it — npb.jp's
`<div class="cancel">` check has no date gate — so KBO was the odd one
out, which is rule 21 in its quiet form.

Separately, `fetch_homepage_conditions()` parsed the site's own
"Chance of Heat Cancellation" warning and NOTHING CALLED IT. That
warning is the league's actual judgement published in advance, and it
is the one thing our own Open-Meteo forecast cannot reproduce, because
HEAT_CANCEL_C is still unverified against any published KBO rule.

So this pins three separations that are easy to collapse and expensive
to get wrong:

  1. a cancellation is read on every date
  2. "Chance of Heat Cancellation" (a warning, game still on) is NEVER
     mistaken for "Canceled Extreme Heat" (a decision, game off)
  3. a reason the site did not give is left absent, not guessed

All strings below were measured on the live schedule page: the decided
ones on 2026-08-07, the at-risk ones on 2026-08-06.

Plain script, like everything in tests/ — exits non-zero on failure.
No network.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kbo_precompute as kp  # noqa: E402

failures = []


def check(label, ok):
    if not ok:
        failures.append(label)


# ---- 1. the two patterns must not overlap ---------------------------
# A warning and a decision share the word "cancel". If POSTPONED_PAT
# ever matches the warning, an at-risk game gets marked off — wrong in
# the opposite direction, and worse, because it looks decided.
WARNINGS = ("Chance of Heat Cancellation", "Chance of Rainout",
            "Forecast Uncertain")
DECIDED = ("Canceled Extreme Heat", "Canceled", "Postponed Rain")

for w in WARNINGS:
    check(f"warning {w!r} is not read as a cancellation",
          not kp.POSTPONED_PAT.search(w))
    check(f"warning {w!r} is recognised as a risk",
          bool(kp.VOID_RISK_PAT.search(w)))
for d in DECIDED:
    check(f"decided {d!r} IS read as a cancellation",
          bool(kp.POSTPONED_PAT.search(d)))
    check(f"decided {d!r} is not also a forward risk",
          not kp.VOID_RISK_PAT.search(d))

# ---- 2. the reason, only when the site gives one --------------------
m = kp.CANCEL_REASON_PAT.search("Kia Tigers LG Twins Canceled Extreme Heat")
check("reason extracted verbatim", m and m.group(1).strip() == "Extreme Heat")
check("a bare Canceled yields no reason",
      not kp.CANCEL_REASON_PAT.search("Kia Tigers LG Twins Canceled"))

# The whole phrase is kept, not just the first word. "Extreme" alone
# would read as a different event.
check("multi-word reason survives whole",
      kp.CANCEL_REASON_PAT.search("Canceled Extreme Heat").group(1)
      == "Extreme Heat")

# ---- 3. the date gate is gone ---------------------------------------
_src = (ROOT / "kbo_precompute.py").read_text(encoding="utf-8")
_after = _src[_src.index("def parse_week("):]
_gate = _after.index("if gdate < today_str:")
_cancel = _after.index('if POSTPONED_PAT.search(text):')
check("the cancellation check runs BEFORE the past-date gate",
      _cancel < _gate)

# FINAL stays past-only: a future game has no score to parse. Losing
# that would send the score regex at every upcoming fixture.
check("FINAL_PAT is still inside the past-date branch",
      _after.index("FINAL_PAT.search(text)") > _gate)

# A called game must never also be graded as final — it has no result.
check("a postponed game cannot become final",
      'FINAL_PAT.search(text) and g["status"] != "postponed"' in _src)

# ---- 4. both signals reach the shipped row --------------------------
for key in ("void_reason", "void_risk"):
    check(f"{key} ships on the slate entry",
          f'"{key}": g.get("{key}")' in _src)

_view = (ROOT / "app" / "views" / "KBO.py").read_text(encoding="utf-8")
for key in ("void_reason", "void_risk"):
    check(f"the board renders {key}", f'g.get("{key}")' in _view)

# Quoted, never translated onto our own scale: the view must not invent
# wording the source did not use.
check("the board does not re-word the source",
      not re.search(r'"(RAIN|HEAT) RISK"', _view))

# ---- 5. NPB parity, stated rather than assumed ----------------------
# npb.jp is checked with no date gate, so NPB already behaves correctly
# here. It has NOT been checked for a forward-looking warning of its
# own; until someone looks, KBO shows a signal NPB does not, and that
# asymmetry is recorded in HANDOFF.md rather than left for a reader to
# discover on the page.
_npb = (ROOT / "npb_precompute.py").read_text(encoding="utf-8")
check("npb reads its cancellation with no date gate",
      '<div class="cancel">' in _npb)

if failures:
    print("FAIL:", "; ".join(failures))
    sys.exit(1)
print("PASS: void signals read on every date; warning and decision stay apart")
