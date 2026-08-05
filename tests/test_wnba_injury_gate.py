"""The roster's reported injury status must reach availability().

wnba_precompute carries ESPN's roster injury note onto every slate row
(injury_status / injury_date), but for a while only the Status COLUMN in
app/views/WNBA.py read it. availability() — which every board that
actually PICKS a player goes through — never looked at it. The visible
symptom was one table row reading "Status: Out" next to "Role: START";
the expensive one was Props / Defense / Player of the Day ranking a
player the team had already reported out.

These pin both halves: that a reported out is honoured, and that the
honouring is narrow enough not to empty a board on uncertainty, a stale
note, or a status string ESPN invents next season.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from engines.wnba_props import (          # noqa: E402
    INJURY_TRUST_DAYS,
    _injury_flag,
    _norm_status,
    availability,
)

TODAY = date(2026, 8, 5)


def _log(days_ago, minutes=30.0):
    d = TODAY - timedelta(days=days_ago)
    return {"date": d.isoformat(), "min": minutes}


def player(**over):
    # Healthy baseline: played yesterday, full shift. Every case below
    # differs from this by exactly the field under test, so anything
    # that fails is failing for the reason named.
    base = {"pid": 1, "name": "Test Player", "log": [_log(3), _log(1)]}
    base.update(over)
    return base


# --- the fix itself ---------------------------------------------------
ok, why, _days = availability(player(), today=TODAY)
assert ok, why
print("PASS: healthy baseline is available (control)")

ok, why, _d = availability(player(injury_status="Out"), today=TODAY)
assert not ok, "a reported Out must rule a player out"
assert "injury report" in why, why
print("PASS: reported 'Out' rules her out even though she played yesterday")

# This is the exact contradiction that was visible on the WNBA page:
# Status column said Out, Role column said START.
ok, _why, _d = availability(
    player(injury_status="Injured Reserve"), today=TODAY)
assert not ok
ok, _why, _d = availability(player(injury_status="Suspension"), today=TODAY)
assert not ok
print("PASS: injured reserve and suspension count as out")


# --- narrow on purpose ------------------------------------------------
# Uncertainty is not absence. A questionable player is usually playing,
# and dropping her from a board on a maybe is the same class of error in
# the other direction.
for soft in ("Day-To-Day", "Questionable", "Doubtful", "Probable",
             "Game Time Decision", "Active", "Available"):
    ok, why, _d = availability(player(injury_status=soft), today=TODAY)
    assert ok, f"{soft!r} must not rule anyone out (got: {why})"
print("PASS: day-to-day / questionable / doubtful / probable stay available")

# A status nobody has seen before must not silently empty a board.
ok, _why, _d = availability(
    player(injury_status="Reconditioning"), today=TODAY)
assert ok, "an unrecognised status must fall through, not rule out"
ok, _why, _d = availability(player(injury_status=None), today=TODAY)
assert ok
ok, _why, _d = availability(player(injury_status={"unexpected": "shape"}),
                            today=TODAY)
assert ok, "a non-string status must not crash or rule out"
print("PASS: unknown, missing and malformed statuses fall through")


# --- the note can be wrong, and the log can prove it ------------------
# Notes are not always cleared when a player returns. An appearance
# dated after the note settles it — that is harder evidence than a
# report.
back = player(injury_status="Out",
              injury_date=(TODAY - timedelta(days=6)).isoformat(),
              log=[_log(9), _log(2)])
ok, why, _d = availability(back, today=TODAY)
assert ok, f"she has played since the note was filed (got: {why})"
print("PASS: a game played AFTER the injury date discards the note")

# With nothing to contradict it, an ancient note stops being evidence
# about tonight.
stale = player(injury_status="Out",
               injury_date=(TODAY - timedelta(days=INJURY_TRUST_DAYS + 5)).isoformat(),
               log=[_log(1)])
ok, why, _d = availability(stale, today=TODAY)
assert ok, f"a note older than INJURY_TRUST_DAYS must not decide (got: {why})"

fresh = player(injury_status="Out",
               injury_date=(TODAY - timedelta(days=1)).isoformat(),
               log=[_log(1)])
ok, _why, _d = availability(fresh, today=TODAY)
assert not ok, "a note filed yesterday is exactly the case to honour"
print(f"PASS: notes expire after {INJURY_TRUST_DAYS} days, fresh ones hold")

# An undated note is the roster's current statement with nothing to
# weigh against it. Failing open here would reinstate the whole bug.
ok, _why, _d = availability(player(injury_status="Out"), today=TODAY)
assert not ok
print("PASS: an undated note is trusted rather than ignored")


# --- ESPN's per-game report still outranks the roster note ------------
# today_out is about THIS game; the roster note is about the player in
# general. When ESPN has published tonight's injury report, it wins in
# both directions.
ok, why, _d = availability(
    player(injury_status="Out", today_out=False), today=TODAY)
assert ok, f"tonight's ESPN report says she is playing (got: {why})"

ok, why, _d = availability(
    player(injury_status="Day-To-Day", today_out=True,
           today_status="Out"), today=TODAY)
assert not ok and "ESPN" in why, why
print("PASS: today_out still outranks the roster note, both directions")


# --- the log inference is untouched -----------------------------------
ok, why, days = availability(player(log=[_log(30)]), today=TODAY)
assert not ok and days == 30, (ok, why, days)
ok, why, _d = availability(player(log=[_log(1, minutes=2.0)]), today=TODAY)
assert not ok and "min" in why, why
ok, _why, _d = availability(player(log=[{"date": "not-a-date", "min": 30.0}]),
                            today=TODAY)
assert ok, "unparseable dates must still fail OPEN"
print("PASS: existing staleness / short-shift / fail-open behaviour intact")

# ...but an undated log plus a reported out is positive evidence.
ok, _why, _d = availability(
    player(injury_status="Out", log=[{"date": "not-a-date", "min": 30.0}]),
    today=TODAY)
assert not ok, "a reported out applies even when no date parses"
print("PASS: reported out applies even when the log has no usable dates")


# --- helpers ----------------------------------------------------------
assert _norm_status("Day-To-Day") == "daytoday"
assert _norm_status("  OUT ") == "out"
assert _norm_status(None) == ""
assert _norm_status({"name": "Out"}) == ""
out, why = _injury_flag({}, today=TODAY)
assert out is False and why is None, "silence must not read as available"
print("PASS: _norm_status and _injury_flag boundaries")


# --- and the field has to survive the pipeline -------------------------
# availability() reading injury_status is useless if the slate stops
# carrying it. Pinned here as well as in test_wnba_roster_status.py
# because this is the consumer that would fail silently: no error, just
# every board quietly forgetting about injuries again.
build = (Path(__file__).resolve().parents[1] / "wnba_precompute.py").read_text()
assert 'row["injury_status"]' in build, (
    "slate rows must carry injury_status — availability() reads it")
assert 'row["injury_date"]' in build, (
    "slate rows must carry injury_date — the staleness check reads it")
print("PASS: the slate still carries injury_status and injury_date")

print("\nOK: reported injuries reach every board, and only when reported")
