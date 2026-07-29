"""Guards the specific scope bug that has now shipped twice.

Streamlit views can't be imported headlessly, so a name that exists only
inside a function but is referenced from module-level code compiles fine,
passes every other test, and raises NameError the moment a user opens the
page. Two have shipped:

  - GameCard called _side_for() from a point above its definition
  - KBO referenced `pitchers` — a local inside the pitcher-tab function —
    from module scope: "NameError: name 'pitchers' is not defined"

A general module-level scope analyser was tried and abandoned: correctly
distinguishing a module-level `if/else` body from a function body, and
handling a function's own def line, produced ~140 false positives across
these views. A test that noisy is worse than no test, because it trains
you to ignore it.

So this checks the narrow, reliable thing instead: every helper the
projection code depends on must be DEFINED before it is USED, in the same
file, at a line number that precedes it.
"""
import re

CHECKS = {
    "app/views/KBO.py": [
        # (name defined, place it's used) — definition must come first.
        ("_kbo_pitchers, _ = _load_pitchers()", "_kbo_starter_era(g, \"home\", _kbo_pitchers)"),
        ("_LEAGUE_RS = _league_avg(", "            _LEAGUE_RS,"),
        ("def _kbo_starter_era(", "_kbo_starter_era(g, \"home\""),
    ],
    "app/views/NPB.py": [
        ("def _league_baselines(", "_LEAGUE_RS = _league_baselines(games)"),
        ("def _starter_era(", "_starter_era(g, \"home\")"),
        ("_LEAGUE_RS = _league_baselines(games)", "            _LEAGUE_RS,"),
    ],
}

for path, pairs in CHECKS.items():
    src = open(path).read()
    for definition, use in pairs:
        assert definition in src, f"{path}: missing definition {definition!r}"
        assert use in src, f"{path}: missing use {use!r}"
        assert src.index(definition) < src.index(use), (
            f"{path}: {definition!r} is used before it's defined — NameError on load")
    print(f"PASS: {path.split('/')[-1]} defines every projection helper before use")

# The exact regression: `pitchers` is a LOCAL in the pitcher-tab function.
kbo = open("app/views/KBO.py").read()
assert "for _sp in (pitchers or [])" not in kbo, (
    "module-level code referenced `pitchers`, a function-local — this is the "
    "NameError that shipped")
assert "_kbo_pitchers, _ = _load_pitchers()" in kbo, (
    "the league-ERA baseline must load pitchers itself; the loader is cached "
    "so calling it again is free")
print("PASS: KBO loads its own pitcher list rather than borrowing a local")

# And the earlier one, so it can't come back either.
gc = open("app/views/GameCard.py").read()
edge_block = gc[gc.index("_pen_adj, _pen_note = pen_context"):]
edge_block = edge_block[:edge_block.index("_r[\"iso_vs_hand\"]")]
assert "_side_for(_r)" not in edge_block, (
    "_side_for is defined further down; calling it here was a NameError")
print("PASS: GameCard's edge loop doesn't call the later-defined _side_for")
