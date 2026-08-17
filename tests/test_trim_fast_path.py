"""_trim_and_downcast skips work only when there is no work to do.

WHY THIS EXISTS. `_read_local_parquet` carried a comment saying the
trim "costs nothing when the file is already trimmed". Measured, on a
frame shaped like one the nightly writes:

    pd.read_parquet                     3.9 ms
    _trim_and_downcast on that frame    1.3 ms    <- pure waste
    the _conforms check                 0.1 ms

`df[keep].copy()` copies the whole frame whether or not anything needs
changing, and a cold board pass reads ~300 batters. The fast path
returns the frame untouched when it already matches.

THE RISK A FAST PATH CARRIES is that it is not actually equivalent —
it skips a conversion the callers depend on and the numbers change
somewhere far away. So the test that matters is not "is it faster", it
is "is the output the same object shape, dtypes and values as the slow
path produced". Every check below compares the two paths directly
rather than asserting what either one does on its own.
"""
import sys
import pandas as pd

sys.path.insert(0, "app")
from engines import statcast_engine as se        # noqa: E402


def raw_frame():
    """A frame shaped like a LIVE Statcast pull: full-width, float64,
    plain object strings, columns in the wrong order."""
    return pd.DataFrame({
        "spin_axis": [1, 2, 3],                    # not in _KEEP_COLS
        "launch_speed": [98.4, 88.1, 105.0],       # float64
        "type": ["X", "S", "X"],                   # -> category
        "events": ["single", None, "home_run"],    # -> category
        "game_date": pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-03"]),
        "stand": ["L", "R", "L"],                  # -> category
        "zone": [5, 9, 1],
    })


slow = se._trim_and_downcast(raw_frame())

# --- 1. THE SLOW PATH STILL DOES ITS JOB -----------------------------
#
# If this stopped being true the comparison below would be comparing
# two wrongs and agreeing.
assert "spin_axis" not in slow.columns, "un-kept column survived the trim"
assert str(slow["launch_speed"].dtype) == "float32", "float64 not downcast"
assert str(slow["type"].dtype) == "category", "category col not converted"
print("PASS: the slow path trims, downcasts and categorises")

# --- 2. ITS OUTPUT IS CONFORMANT, SO THE FAST PATH RECOGNISES IT -----
#
# This is the load-bearing link. _trim_and_downcast's own output is
# exactly what a nightly parquet looks like on read, so if _conforms
# rejected it the fast path would never fire in production and the
# whole change would be a no-op that still measured green.
assert se._conforms(slow), (
    "_conforms rejects the slow path's OWN output — the fast path would "
    "never fire on a nightly file, so nothing is saved")
print("PASS: _conforms accepts what the slow path produces")

# --- 3. THE TWO PATHS AGREE, VALUE FOR VALUE -------------------------
again = se._trim_and_downcast(slow)
pd.testing.assert_frame_equal(again, slow)
assert again is slow, (
    "the fast path copied instead of returning the frame — that copy is "
    "the entire cost this change removes")
print("PASS: re-trimming a conformant frame is identity, values equal")

# --- 4. NON-CONFORMANT INPUT STILL TAKES THE SLOW PATH ---------------
#
# One check per condition _conforms tests, because a fast path that
# fires too eagerly is worse than no fast path: it would let a
# full-width or float64 frame into the cache silently.
extra = slow.copy()
extra["spin_axis"] = 0
assert not se._conforms(extra), "an un-kept column was called conformant"

wide = slow.copy()
wide["launch_speed"] = wide["launch_speed"].astype("float64")
assert not se._conforms(wide), "a float64 column was called conformant"

plain = slow.copy()
plain["type"] = plain["type"].astype(str)
assert not se._conforms(plain), "an object string column was called conformant"

reordered = slow[list(slow.columns)[::-1]]
assert not se._conforms(reordered), "reversed column order was called conformant"

for bad in (extra, wide, plain, reordered):
    fixed = se._trim_and_downcast(bad)
    assert se._conforms(fixed), "slow path did not repair a bad frame"
    assert fixed is not bad, "slow path returned its input"
print("PASS: each non-conformant shape still takes the slow path")

# --- 5. EMPTY AND NONE ARE UNCHANGED ---------------------------------
assert se._trim_and_downcast(None).empty
assert se._trim_and_downcast(pd.DataFrame()).empty
print("PASS: None and empty still return an empty frame")

# --- 6. THE FAST PATH ACTUALLY FIRES ON THE NIGHTLY'S FILES ----------
#
# Everything above proves the shortcut is equivalent. This proves it is
# REACHED — which is a separate question, and the one that decides
# whether any of this saves a millisecond in production.
#
# _conforms compares the frame's column order against
# [c for c in _KEEP_COLS if c in df.columns]. precompute.py writes each
# player file in ENGINE_COLS + ID_COLS order. If those two orders ever
# diverge — a column appended to one list rather than inserted in step
# with the other — the check fails on every real file, the fast path
# stops firing, and NOTHING BREAKS: the site just quietly goes back to
# copying every frame it reads. A silent return to the old cost is
# precisely the kind of thing this repo keeps rediscovering late, so it
# is pinned here.
#
# Compared as the two modules' OWN literals, per the standing rule that
# cross-module agreement cannot be tested through a fixture that
# replaces one of them.
import ast                                        # noqa: E402


def literal(path, name):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path} — it was renamed or moved")


engine_cols = literal("precompute.py", "ENGINE_COLS")
id_cols = literal("precompute.py", "ID_COLS")
keep_cols = literal("app/engines/statcast_engine.py", "_KEEP_COLS")

# A batter's file drops its own id column and keeps the opponent's.
for own, opponent in (("batter", "pitcher"), ("pitcher", "batter")):
    written = [c for c in engine_cols + id_cols if c != own]
    expected = [c for c in keep_cols if c in set(written)]
    assert written == expected, (
        f"precompute writes {own} files in an order _conforms will reject, so "
        f"the fast path would never fire on a real nightly file.\n"
        f"  written : {written}\n"
        f"  expected: {expected}\n"
        f"Keep ENGINE_COLS and _KEEP_COLS in the same order, or drop the "
        f"order check from _conforms and accept the copy.")
print("PASS: the nightly's column order matches what _conforms accepts")
