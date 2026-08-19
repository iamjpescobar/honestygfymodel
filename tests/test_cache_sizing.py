"""Caches sized to one slate's working set, not to a stale number.

THE FAILURE MODE. A Streamlit cache that is smaller than the working
set does not fail — it EVICTS, silently, and every eviction turns a
dict lookup into a parquet read or a network round-trip. Nothing
errors, nothing warns; the page just gets slower the longer you use
it, which is exactly the shape of problem that survives testing and
shows up on a recording.

WHAT HAPPENED THE FIRST TIME. `get_batter_iso_vs_hand` sat at
max_entries=64, which was right when pen_context was its only caller:
one blended read per batter for the bullpen's hand mix. The platoon
term against the STARTER (added 2026-08-13) calls it TWICE per batter,
once per hand. A full slate is ~300 batters, so ~600 lookups against
64 slots — near-total thrash, and every miss reads that batter's whole
parquet.

WHAT HAPPENED THE SECOND TIME, AND WHY THIS FILE WAS REWRITTEN.
`weak_spots_json` sat at 16 for exactly the same reason and this test
did not see it, because it only checked the four batter caches named
inside it. It tested the callers I knew about instead of the rule.
Measured on a 30-starter slate: revisiting eight already-seen starters
cost 291 ms of recomputation against 1.6 ms warm.

So the rule is enforced against the GLOB now. Every `@st.cache_data`
in app/engines whose first parameter is a player id has to hold at
least the players one slate can put through it. A new engine, or a new
cache in an old engine, is covered the day it is written.

THE RULE: when a function gains a caller, re-size its cache. Nobody
remembers, so this test does it.
"""
import ast
import pathlib

SLATE_BATTERS = 300     # a full MLB slate, both lineups
SLATE_ARMS = 150        # every probable plus both bullpens

# First-parameter names that mean "this cache is keyed per player".
_BATTER_KEYS = {"batter_id"}
_PITCHER_KEYS = {"pitcher_id"}
_GENERIC_KEYS = {"pid", "player_id"}

# --- THE ONE EXEMPTION, AND THE CONDITION THAT KILLS IT --------------
#
# _k_vs_team_json is asked only about tonight's PROBABLES — the
# Strikeout Board loops the slate's starters and nothing else reaches
# it. That is ~30 arms, so 64 is real headroom rather than a leftover
# number.
#
# An exemption granted on "one caller, and it only asks about
# starters" rots the moment a second caller appears. So the exemption
# carries that condition as an assertion below: if this function is
# ever called from outside its own module, the exemption lapses and
# the full floor applies.
STARTERS_ONLY = {"k_projection.py:_k_vs_team_json": 60}

ENGINES = pathlib.Path("app/engines")


def cached_functions():
    """Every st.cache_data-decorated function under app/engines.

    Parsed from the AST rather than matched with a regex: a decorator
    can be wrapped, reordered or reformatted, and a regex that misses
    one reports a clean pass on an unchecked cache."""
    out = []
    for path in sorted(ENGINES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if "cache_data" not in ast.unparse(dec):
                    continue
                entries = None
                if isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if kw.arg == "max_entries":
                            entries = ast.literal_eval(kw.value)
                args = [a.arg for a in node.args.args]
                out.append((path.name, node.name, entries, args))
    return out


CACHES = cached_functions()
assert len(CACHES) >= 50, (
    f"only found {len(CACHES)} cached functions — the AST walk is not "
    f"seeing the decorators, so every check below is vacuous")
print(f"PASS: found {len(CACHES)} cached functions under app/engines")


# --- 1. EVERY PER-PLAYER CACHE HOLDS A SLATE -------------------------
#
# Classified by the FIRST parameter's name, which is what the cache is
# keyed on. A cache keyed per player and sized for one card is the
# defect this file exists for.
undersized = []
for fname, func, entries, args in CACHES:
    if not args:
        continue
    key = args[0]
    if key in _BATTER_KEYS:
        floor = SLATE_BATTERS
    elif key in _PITCHER_KEYS or key in _GENERIC_KEYS:
        floor = SLATE_ARMS
    else:
        continue
    exempt = STARTERS_ONLY.get(f"{fname}:{func}")
    if exempt is not None:
        floor = exempt
    if entries is None:
        undersized.append(f"{fname}:{func} is per-player and UNBOUNDED")
    elif entries < floor:
        undersized.append(
            f"{fname}:{func} holds {entries}, under the {floor} one slate "
            f"needs (keyed on `{key}`)")

assert not undersized, (
    "per-player caches too small for one slate — each miss is a parquet "
    "read or a network call:\n  " + "\n  ".join(undersized))
print(f"PASS: every per-player cache holds a slate "
      f"({SLATE_BATTERS} bats / {SLATE_ARMS} arms)")


# --- 1b. A COLLECTION IN THE KEY MULTIPLIES THE WORKING SET ----------
#
# Rule 1 above assumes ONE cache entry per player. That is true only
# when the player id is effectively the whole key. When the key also
# carries a COLLECTION — get_batter_vs_pitch_types takes
# `pitch_types: tuple` — the entry count is players times distinct
# collections, because the collection varies per OPPOSING PITCHER, not
# per player.
#
# get_batter_vs_pitch_types sat at 384 and passed rule 1 cleanly, which
# is the same failure this file's docstring describes twice: the check
# was calibrated to the callers someone had in mind rather than to the
# shape of the key. Counted on one game card — starter's top 3 across
# the lineup, three pitch families per batter opened, plus every
# reliever picked in the bullpen browser against all ~13 opposing bats —
# a single game can spend ~85 entries and five games blows the cache.
#
# Detected from the ANNOTATION, so a new cache keyed on a tuple of
# anything is covered the day it is written, with no name list to keep
# current.
_COLLECTION_ANNOTATIONS = {"tuple", "list", "set", "frozenset"}
# How many distinct collections one player is realistically asked about
# in a session: tonight's starter, the three pitch families, and a
# handful of relievers opened in the bullpen browser.
COLLECTIONS_PER_PLAYER = 6

multiplied = []
for path in sorted(ENGINES.glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any("cache_data" in ast.unparse(d) for d in node.decorator_list):
            continue
        args = node.args.args
        if not args:
            continue
        key = args[0].arg
        if key in _BATTER_KEYS:
            base = SLATE_BATTERS
        elif key in _PITCHER_KEYS or key in _GENERIC_KEYS:
            base = SLATE_ARMS
        else:
            continue
        has_collection = any(
            a.annotation is not None
            and ast.unparse(a.annotation) in _COLLECTION_ANNOTATIONS
            for a in args[1:])
        if not has_collection:
            continue
        entries = None
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                for kw in dec.keywords:
                    if kw.arg == "max_entries":
                        entries = ast.literal_eval(kw.value)
        floor = base * COLLECTIONS_PER_PLAYER
        if entries is None or entries < floor:
            multiplied.append(
                f"{path.name}:{node.name} holds {entries}, but its key "
                f"carries a collection so the working set is "
                f"{base} x {COLLECTIONS_PER_PLAYER} = {floor}")

assert not multiplied, (
    "caches keyed on a collection are sized as if keyed on the player "
    "alone — each eviction re-slices a parquet and recomputes every "
    "metric on it:\n  " + "\n  ".join(multiplied))
print(f"PASS: collection-keyed caches sized for players x "
      f"{COLLECTIONS_PER_PLAYER} collections")


# --- 2. THE EXEMPTION'S CONDITION STILL HOLDS ------------------------
#
# The moment an exempt cache is called from another module, the reason
# it was exempt ("starters only, one caller") is no longer true.
for entry in STARTERS_ONLY:
    fname, func = entry.split(":")
    own = (ENGINES / fname).resolve()
    callers = []
    for path in sorted(pathlib.Path("app").rglob("*.py")):
        if path.resolve() == own:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == func):
                callers.append(f"{path}:{node.lineno}")
    assert not callers, (
        f"{entry} is exempted from the slate floor because only its own "
        f"module calls it, and only about tonight's probables. It now has "
        f"outside callers ({', '.join(callers)}), so the exemption is void "
        f"— size it for {SLATE_ARMS} arms or re-justify it here.")
print("PASS: exempted caches still have no outside callers")


# --- 3. THE UNDERLYING FRAME CACHES ARE NOT THE SMALLEST -------------
#
# _get_batter_df / _get_pitcher_df are what a miss in any of the above
# falls through to. If they are smaller than their callers, raising the
# callers just moves the thrash one level down.
by_name = {f"{f}:{n}": e for f, n, e, _a in CACHES}
assert by_name["statcast_engine.py:_get_batter_df"] >= SLATE_BATTERS, (
    "_get_batter_df is under one slate's batters — the layer everything "
    "else falls through to is the bottleneck")
assert by_name["statcast_engine.py:_get_pitcher_df"] >= SLATE_ARMS, (
    "_get_pitcher_df is under one slate's arms")
print("PASS: the frame caches hold at least one slate each")


# --- 4. THE NAMED FOUR, IN ADDITION TO THE GLOB ----------------------
#
# Section 1 classifies by parameter name, so renaming a parameter would
# quietly drop a cache out of it without failing anything. These four
# have measured floors and are checked by name as well.
for func, need in (("get_batter_iso_vs_hand", SLATE_BATTERS * 2),
                   ("get_batter_profile_windowed", SLATE_BATTERS * 2),
                   ("get_batter_vs_pitch_types", 128),
                   ("weak_spots_json", SLATE_ARMS)):
    key = next((k for k in by_name if k.endswith(f":{func}")), None)
    assert key is not None, f"{func} is no longer cached, or it moved"
    assert by_name[key] >= need, (
        f"{func} caches {by_name[key]} entries, under the {need} it needs")
print("PASS: the four named caches are each at their measured floor")
