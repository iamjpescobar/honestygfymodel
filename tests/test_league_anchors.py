"""Scoring anchors must be MEASURED, not typed in.

_LEAGUE_HRFB was a hardcoded 11.5 in two scoring engines. Close to
reality, but asserted rather than measured — so it went stale silently as
the league moved, and nothing in the app could tell. It was the last
number on the site that claimed to describe the league without ever
having looked at it.

Both engines now read the value precompute measures nightly, and keep the
literal only as a fallback for a build that predates the measurement.
"""
import json
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent

st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, str(ROOT / "app"))

from engines import slam_engine, top_plays  # noqa: E402

# --- 1. precompute must actually measure it --------------------------
PRE = (ROOT / "precompute.py").read_text()
assert '"hrPerFlyBall"' in PRE, (
    "precompute no longer ships hrPerFlyBall — both scoring engines fall "
    "back to a typed-in 11.5, which is the asserted number this replaced")
_bl = PRE[PRE.index("def build_baselines"):]
assert 'fly_ball' in _bl[:4000], (
    "HR/FB must use FLY BALLS as the denominator — that is the standard "
    "definition, and any other denominator makes the anchor mean something "
    "different from what every source reports")
assert "_fb_n >= 1000" in _bl, (
    "no minimum sample on the HR/FB measurement — a partial pull would "
    "ship a wild anchor that silently rescales every HR score")
print("PASS: precompute measures league HR/FB from fly balls, with a floor")

# --- 2. both engines read it, and agree ------------------------------
for mod in (slam_engine, top_plays):
    assert hasattr(mod, "_league_hrfb"), (
        f"{mod.__name__} no longer reads the measured anchor")
assert slam_engine._league_hrfb() == top_plays._league_hrfb(), (
    "the two scoring engines disagree on league HR/FB — the same batter "
    "would score differently on SLAM than on Top Plays")
print("PASS: both engines read the same anchor")

# --- 3. degraded paths never break scoring ---------------------------
_data = ROOT / "app" / "data" / "statcast"
_had = (_data / "baselines.json").exists()
if not _had:
    assert slam_engine._league_hrfb() == 11.5, (
        "with no baselines file the engines must fall back to the literal, "
        "not to zero — a zero anchor divides every HR/FB score by nothing")
    print("PASS: missing baselines file falls back safely")

_data.mkdir(parents=True, exist_ok=True)
_bak = (_data / "baselines.json").read_text() if _had else None
try:
    (_data / "baselines.json").write_text(json.dumps({"hrPerFlyBall": 13.42}))
    assert slam_engine._league_hrfb() == 13.42, "measured value not picked up"
    print("PASS: a measured value is used when present")

    (_data / "baselines.json").write_text(json.dumps({"hits": 62.0}))
    assert slam_engine._league_hrfb() == 11.5, (
        "a baselines file missing the key must fall back, not crash or "
        "score against None")
    print("PASS: a file without the key falls back rather than breaking")
finally:
    if _bak is not None:
        (_data / "baselines.json").write_text(_bak)
    else:
        (_data / "baselines.json").unlink(missing_ok=True)

# --- 4. no bare literal left at a use site ---------------------------
for name, mod_path in (("slam_engine", ROOT / "app" / "engines" / "slam_engine.py"),
                       ("top_plays", ROOT / "app" / "engines" / "top_plays.py")):
    code = "\n".join(l.split("#")[0] for l in mod_path.read_text().split("\n"))
    assert "/ _LEAGUE_HRFB " not in code and "/ _LEAGUE_HRFB\n" not in code, (
        f"{name} still divides by the raw constant instead of the measured "
        f"value — the fallback is for absence, not for normal use")
print("PASS: neither engine scores against the raw literal")
