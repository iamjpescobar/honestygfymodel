"""The morning lineup is a projection, and it has to say which parts.

WHAT IS BEING GUARDED

MLB posts a real lineup 1-3 hours before first pitch. Slate breakdowns
get recorded before that, so every morning lineup on this site is the
projected one — last game's real nine, IL-filtered. Measured on the HR
research log for 2026-08-12..16, ~80% of a team's bats repeat game to
game: about two of those nine are wrong by first pitch.

engines/lineup_lock attaches how often each bat has actually started.
The ways that can go wrong are all silent, so each gets a check:

  1. it BUILDS instead of reads, and takes a page down like the Boards
     column did on 2026-08-16
  2. a missing window reads as "never plays" — MISSING IS NOT ZERO,
     standing rule 6, relearned in four other places already
  3. an unmeasured platoon split reports 0-for-0 as 0%
  4. the number ships without ever being checked against an outcome,
     which is standing rule 1
  5. it fires on a CONFIRMED lineup, where there is nothing to project
     and a "lock" label would be nonsense next to a posted order
"""
import ast
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import lineup_lock as ll          # noqa: E402

# ---------------------------------------------------------------------
# A fixture with the shape production has: one everyday bat, one platoon
# bat the team has only seen one hand of, one bat who never started.
# ---------------------------------------------------------------------
FIXTURE = {
    "window_games": 14,
    "window_is_measured": False,
    "generated_at_et": "2026-08-17T06:00:00-04:00",
    "teams": {
        "Test Team": {
            "games": 12,
            "players": {
                "111": {"starts": 12, "games": 12, "rate": 1.0,
                        "vs": {"R": {"starts": 9, "games": 9, "rate": 1.0},
                               "L": {"starts": 3, "games": 3, "rate": 1.0}}},
                "222": {"starts": 6, "games": 12, "rate": 0.5,
                        # only ever measured against RHP in this window
                        "vs": {"R": {"starts": 6, "games": 9, "rate": 0.667}}},
                "333": {"starts": 9, "games": 12, "rate": 0.75,
                        "vs": {"R": {"starts": 8, "games": 9, "rate": 0.889},
                               "L": {"starts": 1, "games": 3, "rate": 0.333}}},
            },
        }
    },
}

_tmp = Path(tempfile.mkdtemp()) / "lineup_lock.json"
_tmp.write_text(json.dumps(FIXTURE))
ll._PUBLISHED = _tmp
ll._REPO = _tmp
ll.clear_cache()

# --- 1. THE ENGINE CANNOT BUILD --------------------------------------
#
# Not "does not today" — cannot. The Boards column called board
# builders during a render on 2026-08-16 and the Game Card sat blank
# with no error, because the builders cache with show_spinner=False.
# Asserted against the source so a future edit cannot quietly add one.
src = (ROOT / "app" / "engines" / "lineup_lock.py").read_text(encoding="utf-8")
tree = ast.parse(src)
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        for a in node.names:
            imported.add(a.name)
    elif isinstance(node, ast.Import):
        for a in node.names:
            imported.add(a.name.split(".")[0])
FORBIDDEN = {"requests", "statsapi", "pybaseball", "urllib", "http"}
assert not (imported & FORBIDDEN), (
    f"engines/lineup_lock imports {imported & FORBIDDEN} — this module is a "
    f"READER. Anything that fetches belongs in lineup_lock_precompute.py; a "
    f"page that builds during a render is the 2026-08-16 outage.")
assert "roster" not in imported and "statcast_engine" not in imported, (
    "engines/lineup_lock pulled in a fetching engine — same rule as above")
print("PASS: the engine has no build path")

# --- 2. MISSING IS NOT ZERO ------------------------------------------
#
# Two different unknowns that must not collapse into each other:
# a team with no window at all (nightly never ran, or an expansion of
# the file) and a player who really did not start.
rate, starts, games, basis = ll.start_rate("No Such Team", "111")
assert rate is None, (
    f"a team with no window returned {rate} instead of None — an unpublished "
    f"file would render as 'every bat is a 0% start', which is a confident "
    f"wrong answer where there should be no answer")
assert ll.tier_of(None) == ll.TIER_UNKNOWN

rate, starts, games, basis = ll.start_rate("Test Team", "999")
assert rate == 0.0 and games == 12, (
    "a rostered bat who did not start in a measured window should read 0 of "
    "12 — that IS measured, and it is the one case where zero is honest")
# attach() reaches the same guard by a DIFFERENT route (_lookup with an
# unresolved team), and a control that broke only that route stayed green
# while this file tested start_rate alone. Both entry points, every time.
_unknown = [{"id": "111", "name": "Nobody"}]
ll.attach(_unknown, "No Such Team", vs_hand="R")
assert _unknown[0]["lock_rate"] is None and _unknown[0]["lock_tier"] == ll.TIER_UNKNOWN, (
    f"attach on an unpublished team produced {_unknown[0]['lock_rate']} — the "
    f"missing-is-not-zero guard is not covering the path attach uses")
print("PASS: no window is None, a measured zero is 0.0 (both entry points)")


# --- 2b. THE PARSED COPY NOTICES A NEW FILE --------------------------
#
# load() memoises on (path, mtime, size) instead of re-parsing 110 KB on
# every lookup — attaching one lineup was 19 ms before that and is 0.05
# ms after. The risk a memo carries is the opposite one: the nightly
# writes a fresh file and the page serves yesterday's for the life of
# the process.
#
# Deliberately does NOT call clear_cache() — clearing by hand is what
# hid this gap the first time, because the test told the memo to forget
# instead of checking that it noticed.
import os                                        # noqa: E402
import time as _time                             # noqa: E402

_before = ll.load()["teams"]["Test Team"]["players"]["111"]["starts"]
_bumped = dict(FIXTURE)
_bumped["teams"] = {"Test Team": {"games": 12, "players": {
    "111": {"starts": 7, "games": 12, "rate": 0.583, "vs": {}}}}}
_time.sleep(0.01)
_tmp.write_text(json.dumps(_bumped))
os.utime(_tmp, None)
_after = ll.load()["teams"]["Test Team"]["players"]["111"]["starts"]
assert _before == 12 and _after == 7, (
    f"the memo served a stale copy after the file changed ({_before} -> "
    f"{_after}); a nightly rebuild would never reach the page")
_tmp.write_text(json.dumps(FIXTURE))
ll.clear_cache()
print("PASS: the parsed copy re-reads when the file changes")

# --- 3. AN UNMEASURED SPLIT FALLS BACK AND SAYS SO -------------------
#
# Player 222 has never faced a lefty in the window. Reporting his vsL
# rate as 0% would call a healthy platoon regular a bench bat on the
# exact morning a lefty is on the mound.
rate, starts, games, basis = ll.start_rate("Test Team", "222", vs_hand="L")
assert basis == "window" and rate == 0.5, (
    f"vsL with no lefties faced returned rate={rate} basis={basis}; it must "
    f"fall back to the overall rate and label the basis, not invent a split")
rate, starts, games, basis = ll.start_rate("Test Team", "222", vs_hand="R")
assert basis == "vsR" and games == 9, "a real split must be used when it exists"
print("PASS: an unmeasured platoon split falls back and labels its basis")

# --- 4. THE NUMBER IS LABELLED UNTIL THE PROBE HAS RUN ---------------
#
# Standing rule 1. The window is 14 because someone picked 14;
# lineup_lock_probe.py is what turns that into a measurement.
assert ll.measured() is False, "fixture has window_is_measured False"
batters = [{"id": "111", "name": "Everyday"}, {"id": "222", "name": "Platoon"},
           {"id": "999", "name": "Benchguy"}]
ll.attach(batters, "Test Team", vs_hand="L")
cap = ll.caption(batters)
assert "provisional" in cap, (
    f"caption does not say the number is unchecked: {cap!r}")
assert "not yet checked against outcomes" in cap
print("PASS: unmeasured window is labelled provisional on screen")

# --- 5. THE CAPTION NAMES THE SOFT BATS ------------------------------
#
# A single confidence percentage over nine rows hides WHICH two are
# soft, and which two is the entire useful part when you are talking
# through a slate on camera.
locks, in_q, named = ll.summarize(batters)
assert locks == 1, f"expected 1 lock, got {locks}"
assert in_q == 2 and set(named) == {"Platoon", "Benchguy"}, (
    f"in_question={in_q} named={named} — the soft bats must be named")
assert "Platoon" in cap and "Benchguy" in cap
print(f"PASS: caption names the soft bats -> {cap}")

# --- 6. NOTHING RENDERS WHEN THERE IS NO DATA ------------------------
#
# A column of dashes reads as "these bats have no history"; silence
# reads as "not published yet". Those are opposite meanings.
_empty = Path(tempfile.mkdtemp()) / "lineup_lock.json"
_empty.write_text("{}")
ll._PUBLISHED = _empty
ll._REPO = _empty
ll.clear_cache()
assert ll.available() is False
assert ll.caption(batters) is None, "caption must be silent with no data"
ll._PUBLISHED = _tmp
ll._REPO = _tmp
ll.clear_cache()
print("PASS: no published file renders nothing, not an empty column")

# --- 7. THE GAME CARD ONLY PROJECTS WHEN NOTHING IS POSTED -----------
#
# Once MLB has posted the order there is nothing left to project, and a
# "lock" label beside a confirmed lineup would be actively misleading.
# The attach lives inside the else-branch of the confirmed check;
# asserted structurally rather than by reading the source, because the
# indentation is the whole guarantee.
gc = ast.parse((ROOT / "app" / "views" / "GameCard.py").read_text(encoding="utf-8"))
resolver = next(n for n in ast.walk(gc)
                if isinstance(n, ast.FunctionDef)
                and n.name == "_resolve_lineup_batters")
calls_in_else = []
for node in ast.walk(resolver):
    if isinstance(node, ast.If):
        for sub in node.orelse:
            for inner in ast.walk(sub):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr in ("attach", "caption")):
                    calls_in_else.append(inner.func.attr)
assert "attach" in calls_in_else and "caption" in calls_in_else, (
    "the lock attach/caption is not inside the unconfirmed branch of "
    "_resolve_lineup_batters — it would label a CONFIRMED lineup as a "
    "projection, which is a wrong label on a right number (rule 9)")
print("PASS: the projection only runs when MLB has posted nothing")

# --- 8. THE BUILDER WRITES WHERE THE ENGINE READS --------------------
#
# The failure this repo already had once: four tables built, published,
# downloaded and never opened, because the writer and the reader pointed
# at different directories and every test monkeypatched the constant.
# Compared as the two files' own literals.
pre = (ROOT / "lineup_lock_precompute.py").read_text(encoding="utf-8")
assert 'OUT_PATH = Path(__file__).resolve().parent / "data" / "mlb" / "lineup_lock.json"' in pre, (
    "the builder's OUT_PATH moved — it must stay data/mlb/lineup_lock.json, "
    "which is what the engine's _REPO resolves")
assert '"data" / "mlb" / "lineup_lock.json"' in src, (
    "engines/lineup_lock no longer resolves data/mlb/lineup_lock.json — the "
    "builder would write a file nothing ever opens")
print("PASS: builder and reader name the same file")

# --- 9. THE PROBE MEASURES THE FORECAST, NOT THE PAST -----------------
#
# The leak that would make this column look perfect: computing the rate
# over a window that INCLUDES the game being predicted.
probe = (ROOT / "lineup_lock_probe.py").read_text(encoding="utf-8")
assert "history[max(0, upto - window):upto]" in probe, (
    "the probe's window no longer stops strictly before the game under "
    "test — including tonight in the history that predicts tonight reports "
    "a perfect column and means nothing")
assert "naive" in probe and "started last game" in probe, (
    "the probe dropped the naive baseline. Without 'he started last game', "
    "any plausible method clears a bar nobody checked — the same trap as the "
    "HR Edge 11.9% baseline")
print("PASS: the probe excludes the test game and keeps a naive baseline")
