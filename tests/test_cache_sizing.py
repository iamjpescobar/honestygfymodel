"""Caches sized to one slate's working set, not to a stale number.

THE FAILURE MODE. A Streamlit cache that is smaller than the working set
does not fail — it EVICTS, silently, and every eviction turns a dict
lookup into a parquet read. Nothing errors, nothing warns; the page just
gets slower the longer you use it, which is exactly the shape of problem
that survives testing and shows up on a recording.

WHAT HAPPENED. `get_batter_iso_vs_hand` sat at max_entries=64, which was
right when pen_context was its only caller: one blended read per batter
for the bullpen's hand mix. The platoon term against the STARTER (added
2026-08-13) calls it TWICE per batter, once per hand. A full slate is
~300 batters, so ~600 lookups against 64 slots — near-total thrash, and
every miss reads that batter's whole parquet.

THE RULE: when a function gains a caller, its cache has to be re-sized.
Nobody remembers, so this test does it.
"""
import re

SLATE_BATTERS = 300     # a full MLB slate, both lineups
s = open("app/engines/statcast_engine.py", encoding="utf-8").read()


def max_entries(fn):
    m = re.search(rf"max_entries=(\d+)[^)]*\)\n(?:#[^\n]*\n)*def {fn}\b", s)
    assert m, f"{fn} is not cached, or the decorator moved"
    return int(m.group(1))


# --- 1. THE ONE THE PLATOON TERM BROKE -------------------------------
#
# Two calls per batter — one per hand — so the working set is twice the
# slate, not once.
iso = max_entries("get_batter_iso_vs_hand")
assert iso >= SLATE_BATTERS * 2, (
    f"get_batter_iso_vs_hand holds {iso} but the platoon term needs "
    f"{SLATE_BATTERS * 2} for one slate (two hands per batter). Below "
    f"that it thrashes and every miss is a parquet read.")
print(f"PASS: iso_vs_hand holds {iso} — covers {SLATE_BATTERS} batters x 2 hands")

# --- 2. TWO WINDOWS PER BATTER ---------------------------------------
#
# The lineup table reads season for the stats and l15 for Form, so one
# pass over a slate is ~600 entries before anyone looks at a card twice.
prof = max_entries("get_batter_profile_windowed")
assert prof >= SLATE_BATTERS * 2, (
    f"get_batter_profile_windowed holds {prof}, under the {SLATE_BATTERS * 2} "
    f"one slate needs (season + l15 per batter)")
print(f"PASS: profile_windowed holds {prof} — covers season + l15 for a slate")

# --- 3. THE UNDERLYING FRAME CACHE IS NOT THE SMALLEST ---------------
#
# _get_batter_df is what a miss above falls through to. If it is smaller
# than its callers, raising them just moves the thrash one level down.
df = max_entries("_get_batter_df")
assert df >= SLATE_BATTERS, (
    f"_get_batter_df holds {df}, under one slate's {SLATE_BATTERS} batters — "
    f"the layer everything else falls through to is the bottleneck")
print(f"PASS: _get_batter_df holds {df}, at least one slate")

# --- 4. NO PER-BATTER CACHE IS LEFT AT A TOKEN SIZE ------------------
#
# The regression guard. 64 looked deliberate and had simply been left
# behind when the caller count doubled; a bare number gives no hint that
# it is now wrong.
for fn in ("get_batter_iso_vs_hand", "get_batter_profile_windowed",
           "get_batter_vs_pitch_types", "_get_batter_df"):
    n = max_entries(fn)
    assert n >= 128, (
        f"{fn} caches only {n} entries — too small for any real slate, "
        f"and a cache that small costs a file read on nearly every call")
print("PASS: no per-batter cache left at a token size")
