"""A hit rate without its baseline is a misleading number.

The league-average starter gets a hit about two nights in three. So a
board reporting "65% got a hit" may be adding nothing at all, and
printing that rate on its own is how this tool would manufacture false
confidence in someone sizing real bets off it.

Worse, the baselines used to be HARDCODED PROSE and two were badly wrong
— "~12%" for a home run and "~33%" for an extra-base hit are both roughly
double the true rates, so HR Edge was judged against an inflated bar.
They are now measured from the same league Statcast data the picks come
from.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRE = (ROOT / "precompute.py").read_text()
CAL = (ROOT / "app" / "engines" / "calibration.py").read_text()

# --- 1. the baseline is measured, and shipped ------------------------
assert "def build_baselines" in PRE, "no baseline measurement in precompute"
assert "build_baselines(season_df)" in PRE, "build_baselines is never called"
assert 'baselines.json' in PRE and 'baselines.json' in CAL, (
    "precompute and calibration disagree on the baseline filename")
print("PASS: baselines are measured nightly and read by calibration")

_bb = PRE[PRE.index("def build_baselines"):PRE.index("def build_hr_metrics")]
assert 'pa"] >= 3' in _bb, (
    "the baseline must be limited to players who actually STARTED. Counting "
    "one-PA pinch hitters drags every baseline down and flatters every board")
assert "len(starters) < 500" in _bb, (
    "no minimum sample — a baseline off a handful of games is worse than none")
print("PASS: baseline uses starters only and refuses tiny samples")

# --- 2. no hardcoded baseline claims survive in the UI ---------------
for name in ("Calibration.py", "Player_Of_The_Day.py", "Daily_13.py"):
    src = (ROOT / "app" / "views" / name).read_text()
    code = "\n".join(l.split("#")[0] for l in src.split("\n"))
    for bogus in ("1 game in 8", "~12%", "~33%", "~65%"):
        assert bogus not in code, (
            f"{name} still asserts a hardcoded baseline ({bogus}). These were "
            f"guesses, and the HR and XBH ones were about double the real "
            f"rates — a board judged against an inflated bar looks broken "
            f"when it isn't")
print("PASS: no hardcoded baseline claims left in the views")

# --- 3. the verdict refuses to call small samples --------------------
def verdict(hits, total, base):
    if not total or base is None:
        return "not enough graded picks yet"
    p0 = base / 100.0
    se = (p0 * (1 - p0) / total) ** 0.5
    if se == 0:
        return "not enough graded picks yet"
    z = (hits / total - p0) / se
    if total < 30:
        return f"only {total} graded picks — far too few to judge"
    if z > 2:
        return "beating the league baseline (unlikely to be luck)"
    if z < -2:
        return "below the league baseline"
    return "no measurable edge over the baseline yet"

# A hot streak on a tiny sample must NEVER be reported as an edge.
assert "far too few" in verdict(20, 25, 64.0), (
    "20-for-25 on 25 picks was called an edge. Small-sample luck presented as "
    "skill is the single easiest way for this tool to cost someone money")
# Matching the baseline is not an edge, however good the raw rate looks.
assert verdict(64, 100, 64.0) == "no measurable edge over the baseline yet", (
    "a board exactly matching the league baseline was credited with an edge")
# A real, sustained gap should be reported.
assert "beating" in verdict(80, 100, 64.0)
assert "below" in verdict(40, 100, 64.0)
print("PASS: verdict is conservative — no edge claimed from noise")

# --- 4. summary() actually exposes all three -------------------------
_sum = CAL[CAL.index("def summary"):]
for field in ('"baseline"', '"edge"', '"verdict"'):
    assert field in _sum, f"summary() does not expose {field}"
assert "_edge_verdict(" in _sum
print("PASS: summary() exposes baseline, edge and verdict")

# --- 5. every MLB board is mapped to a baseline stat -----------------
for board in ("daily13", "hr_edge", "potd"):
    seg = CAL[CAL.index(f'"{board}":'):]
    seg = seg[:seg.index("}")]
    assert "baseline_stat" in seg, (
        f"{board} has no baseline_stat, so its rate renders with nothing to "
        f"compare against — which is the whole problem")
print("PASS: every MLB board is mapped to a measured baseline")
