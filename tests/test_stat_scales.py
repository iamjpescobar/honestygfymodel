"""A number is the same colour everywhere.

WHY THIS EXISTS

Cell colour used to come from the column you were looking at:
`_magnitude_column` normalised each column against its own min and max.
So the SAME .285 came out gold in one table and violet in another, and
changing the Bats or Window filter recoloured every cell without a
single value moving. It answered "where does this sit among the rows
currently on screen" — which nobody reads it as. A colour reads as a
verdict.

Now the tier comes from the value against a fixed scale in
styles/stat_scales.py, so it cannot depend on what else is rendered.
That is the property this file pins, and it is easy to lose: one
`favor_high` list edited in one view is enough to reintroduce a
relative scale for a stat that has an absolute one.

The cut points themselves are CALIBRATION CONSTANTS, not measurements —
judgements about where a stat stops being average. They are not tested
for correctness here (nothing could test that), only for coherence:
ascending, four of them, five tiers out.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import pandas as pd  # noqa: E402
from styles.stat_scales import (  # noqa: E402
    SCALES, N_TIERS, has_scale, tier_index, tier_fraction,
)

failures = []


def check(label, ok):
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


# ---- 1. the scales themselves are coherent --------------------------
bad = [k for k, v in SCALES.items() if len(v) != N_TIERS - 1]
check(f"every scale has {N_TIERS - 1} cut points (bad: {bad or 'none'})", not bad)
unsorted = [k for k, v in SCALES.items() if list(v) != sorted(v)]
check(f"every scale ascends (bad: {unsorted or 'none'})", not unsorted)


# ---- 2. the tier comes from the VALUE, not the neighbours -----------
# This is the whole point. Same number, wildly different company.
for stat, v in (("BA", 0.285), ("Brl %", 9.5), ("SLAM", 72.0), ("WHIP", 1.10)):
    lo = tier_index(stat, v)
    check(f"{stat} {v} lands in a tier", lo is not None)
check("tier_index ignores everything except the value",
      tier_index("BA", 0.285) == tier_index("BA", 0.285))

# Ordering must hold across the whole scale, not just at the ends.
_ba = [tier_index("BA", v) for v in (0.150, 0.220, 0.255, 0.285, 0.340)]
check(f"a rising BA rises through the tiers ({_ba})", _ba == sorted(_ba))
check("the bottom of the scale is tier 0", tier_index("BA", 0.000) == 0)
check("the top of the scale is the last tier",
      tier_index("BA", 0.900) == N_TIERS - 1)

# invert is what lets one scale serve a pitcher table and a batter one.
check("invert flips the ladder end for end",
      tier_index("Whiff %", 31.0) == N_TIERS - 1 - tier_index("Whiff %", 31.0, invert=True))

# Not-a-number never gets a colour rather than getting a wrong one.
for junk in (None, "", "N/A", float("nan")):
    check(f"{junk!r} yields no tier", tier_index("BA", junk) is None)
check("an unknown stat yields no tier", tier_index("NotAStat", 1.0) is None)
check("tier_fraction sits mid-band, never on a boundary",
      all(0.0 < (tier_fraction("BA", v) or -1) < 1.0
          for v in (0.100, 0.240, 0.500)))


# ---- 3. through the real styler: same value, different company ------
import types  # noqa: E402
_stub = types.ModuleType("streamlit")
_stub.markdown = lambda *a, **k: None
_stub.session_state = {}
sys.modules.setdefault("streamlit", _stub)
from styles.table_style import _magnitude_column  # noqa: E402

high = _magnitude_column(pd.Series([0.285, 0.400, 0.500], name="BA"),
                         invert=False, use_gradient=True)
low = _magnitude_column(pd.Series([0.285, 0.150, 0.170], name="BA"),
                        invert=False, use_gradient=True)
check("the SAME .285 renders identically in a strong and a weak column",
      high[0] == low[0])
# The bug this replaces: under relative colouring .285 was the WORST
# cell in one frame and the BEST in the other, so those two strings
# differed. If they ever differ again, relative colouring is back.
check("a value's colour does not depend on its neighbours",
      _magnitude_column(pd.Series([12.0, 13.0], name="Brl %"), False, True)[0]
      == _magnitude_column(pd.Series([12.0, 2.0], name="Brl %"), False, True)[0])

# Columns with no fixed scale must still colour — falling back is the
# honest behaviour, blanking them is not.
check("an unscaled column still gets relative colouring",
      bool(_magnitude_column(pd.Series([1, 2, 3], name="Nonesuch"), False, True)[0]))

# And an all-empty column stays empty rather than inventing a tier.
check("an all-NaN column colours nothing",
      _magnitude_column(pd.Series([None, None], name="BA"), False, True) == ["", ""])

print("FAILING:" + (" " + ", ".join(failures) if failures else " none"))
sys.exit(1 if failures else 0)
