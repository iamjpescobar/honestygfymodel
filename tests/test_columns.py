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
