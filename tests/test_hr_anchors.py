"""League anchors are measured nightly, not typed into two files.

WHAT WENT WRONG. Every composite on the HR side maps "league average"
to 50, and the numbers defining league average were literals — 71.0 bat
speed, 30.0 HR window, 18.0 pull air in BOTH precompute.py and
statcast_engine.py, plus 6.0 Brl/PA and 4.0 clears-anywhere in the
engine alone.

Two failure modes, one already realised:

  * DUPLICATION. Two copies of the same constant in two files means a
    board built in CI and a player page rendered live can disagree about
    what average is, with nothing to reveal it.
  * STALENESS. The clears-anywhere anchor was set to 4.0 before a single
    nightly had run. The real contour turned out roughly eight times
    tighter, so every hitter alike scored near zero on that component
    and a real signal became noise. The same thing happened to the
    hardcoded 11.5 league HR/FB, measured at 17.1 the moment anyone
    looked.

An anchor of zero or NaN is worse than a stale one — it divides the
entire league to infinity — so the fallback path matters as much as the
happy one and is tested here too.
"""
import json
import sys
import types
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter", "statcast_pitcher", "playerid_lookup", "statcast"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb

sys.path.insert(0, ".")
sys.path.insert(0, "app")

failures = []
tmp = Path(tempfile.mkdtemp())

import engines.statcast_engine as se
se._DATA_DIR = tmp
from engines.statcast_engine import _hr_anchors, _ANCHOR_FALLBACK

# --- 1. no file at all -> the documented fallbacks --------------------
a = _hr_anchors()
if a != _ANCHOR_FALLBACK:
    failures.append(f"with no baselines.json the anchors should be the "
                    f"fallbacks, got {a}")
else:
    print("PASS: an archive with no anchors falls back, doesn't crash")

# --- 2. measured values win -------------------------------------------
(tmp / "baselines.json").write_text(json.dumps({
    "hits": 62.0,
    "hr_anchors": {"bat_speed": 72.4, "brl_per_pa": 5.1,
                   "clears_anywhere_pct": 0.42},
}))
a = _hr_anchors()
if a["bat_speed"] != 72.4 or a["brl_per_pa"] != 5.1:
    failures.append(f"measured anchors did not override the literals: {a}")
elif a["hr_window_pct"] != _ANCHOR_FALLBACK["hr_window_pct"]:
    failures.append("a key absent from the file should keep its fallback, "
                    "not vanish")
else:
    print("PASS: measured anchors override, per key, and absent keys keep "
          "their fallback")

# --- 3. THE ONE THAT MATTERS: a zero or NaN anchor ---------------------
# Division by an anchor of 0 sends the whole league to infinity, and a
# NaN sends it to NaN. Either would render as a board full of garbage
# rather than an error anyone would notice.
for bad in (0, 0.0, -1, None, "n/a"):
    (tmp / "baselines.json").write_text(json.dumps({
        "hr_anchors": {"brl_per_pa": bad}}))
    a = _hr_anchors()
    if a["brl_per_pa"] != _ANCHOR_FALLBACK["brl_per_pa"]:
        failures.append(f"an anchor of {bad!r} was accepted — every score "
                        f"built on it would be inf or NaN")
        break
else:
    print("PASS: zero, negative, null and non-numeric anchors are refused")

# --- 4. corrupt file ---------------------------------------------------
(tmp / "baselines.json").write_text("{not json")
if _hr_anchors() != _ANCHOR_FALLBACK:
    failures.append("a corrupt baselines.json did not fall back cleanly")
else:
    print("PASS: a corrupt baselines.json falls back instead of raising")

# --- 5. the build writes what the app reads ---------------------------
# The whole point is one source of truth. If build_hr_metrics stops
# writing the key the engine looks for, the app silently reverts to
# literals and nobody finds out.
src = Path("precompute.py").read_text()
if '"hr_anchors"' not in src:
    failures.append("precompute no longer writes hr_anchors — the app would "
                    "silently fall back to typed constants")
else:
    print("PASS: the build writes the key the app reads")

for name in _ANCHOR_FALLBACK:
    if f'"{name}"' not in src:
        failures.append(f"the build never measures {name}, but the engine "
                        f"expects it")
if not failures:
    print(f"PASS: all {len(_ANCHOR_FALLBACK)} anchors the engine reads are "
          f"measured by the build")

# --- 6. no literal anchors left in the engine -------------------------
eng = Path("app/engines/statcast_engine.py").read_text()
body = eng.split("_ANCHOR_FALLBACK", 2)[-1]
for stale in ("= 71.0", "= 30.0", "= 18.0", "= 6.0", "= 4.0"):
    if f"_ANCHOR {stale}" in body or f"ANCHOR {stale}" in body:
        failures.append(f"a literal anchor ({stale.strip()}) is still bound "
                        f"in the engine outside the fallback table")
if not failures:
    print("PASS: the engine holds anchors in one place only")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nLeague average is measured every night, in one place.")
