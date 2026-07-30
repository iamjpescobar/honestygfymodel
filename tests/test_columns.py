"""Guards the column contract between the engine and the nightly build.

_KEEP_COLS (app/engines/statcast_engine.py) and ENGINE_COLS + ID_COLS
(precompute.py) must describe the same set. When they drift, the symptom
is silent: _trim_and_downcast quietly drops the missing column, and any
function reading it hits its `not in df.columns` guard and returns None
forever. That is exactly how p_throws went missing and left the Game
Card's platoon split dead league-wide without a single error.
"""
import re, sys

def cols(path, *names):
    text = open(path).read()
    out = set()
    for n in names:
        m = re.search(n + r"\s*=\s*\[(.*?)\]", text, re.S)
        assert m, f"{n} not found in {path}"
        out |= set(re.findall(r'"([a-z_]+)"', m.group(1)))
    return out

engine = cols("app/engines/statcast_engine.py", "_KEEP_COLS")
build = cols("precompute.py", "ENGINE_COLS", "ID_COLS")

assert not (engine - build), f"engine reads columns the build never writes: {sorted(engine - build)}"
assert not (build - engine), f"build writes columns the engine discards: {sorted(build - engine)}"
print(f"PASS: engine and nightly build agree on all {len(engine)} columns")

# p_throws specifically: every handedness split in the app depends on it.
assert "p_throws" in engine and "p_throws" in build, "p_throws dropped again"
print("PASS: p_throws present in both — platoon splits can resolve")


# ----------------------------------------------------------------------
# The barrel column must be requested, and its absence must be fatal.
#
# Barrels come only from Statcast's launch_speed_angle == 6 bucket, and
# Brl/PA is the primary input to top_plays' POWER axis (45% of the score).
# If the column ever goes missing the failure is SILENT and looks like a
# real value: DataFrame.get returns None, pd.to_numeric(None) == 6
# evaluates to a scalar False rather than raising, and that broadcasts to
# every row — zero barrels league-wide, written to the parquet as 0.0.
# Nothing downstream can tell that apart from a genuine 0.0.
#
# precompute is read as TEXT rather than imported, same as above:
# importing it would pull in pybaseball.
# ----------------------------------------------------------------------
import numpy as np
import pandas as pd

_pre = open("precompute.py").read()

assert '"launch_speed_angle"' in _pre.split("ENGINE_COLS")[1].split("]")[0], (
    "launch_speed_angle dropped from ENGINE_COLS — barrels would be zero for "
    "every batter and HR Score's power axis would silently go dead")
print("PASS: launch_speed_angle is requested in ENGINE_COLS")

assert 'if "launch_speed_angle" not in out.columns:' in _pre, (
    "the hard abort for a missing launch_speed_angle is gone from "
    "fetch_season() — a pybaseball change would ship an archive with zero "
    "barrels league-wide instead of failing the build")
print("PASS: fetch_season() aborts when the barrel column is absent")

_start = _pre.index("def _mask")
_end = _pre.index("def ", _pre.index("return pd.Series(series"))
_ns = {"pd": pd, "np": np}
exec(compile(_pre[_start:_end], "precompute._mask", "exec"), _ns)
_mask = _ns["_mask"]

_missing = pd.to_numeric(pd.DataFrame({"a": [1, 2]}).get("launch_speed_angle"),
                         errors="coerce") == 6
assert np.isscalar(_missing) or isinstance(_missing, (bool, np.bool_)), (
    "precondition changed: a missing column no longer collapses to a scalar, "
    "so this test is no longer checking anything real")
try:
    _mask(_missing)
    raise AssertionError(
        "_mask() accepted a scalar. A missing source column would broadcast as "
        "all-False and ship zero barrels for the entire league as a real 0.0")
except TypeError:
    print("PASS: _mask() rejects a scalar from a missing column")

_real = _mask(pd.to_numeric(pd.Series([6, 3, pd.NA], dtype="Int8"),
                            errors="coerce") == 6)
assert list(_real) == [True, False, False], (
    f"real barrel mask broke: {list(_real)} — NA must collapse to False, since "
    f"launch_speed_angle is NaN on every row that isn't a batted ball")
print("PASS: real barrel mask still works, NA collapses to False")
