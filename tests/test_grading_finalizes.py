"""Ungraded days must eventually CLOSE, and closing must not churn.

Two bugs lived here. Grading treated a missing box-score line as "not
posted yet" forever, so a single benched player kept a day open
permanently — re-fetched on every run until it aged out of the window
still ungraded. And reopen_stuck reset every DNP in a 10-day window on
every run, so once grading did close one, the next run reopened it and
they fought indefinitely.

These tests assert the pending window works, the day finalizes after it,
the result is idempotent, and real hit/miss results are never touched.
"""
import copy
import sys
import types
from datetime import datetime, timedelta

sys.path.insert(0, ".")
import calibration_pipeline as cp

_REAL_DT = cp.datetime


def _at(day_offset, record):
    """Run reopen+grade as if `day_offset` days had passed."""
    class FakeDT(_REAL_DT):
        @classmethod
        def now(cls, tz=None):
            return _REAL_DT.now(tz) + timedelta(days=day_offset)

    rec = copy.deepcopy(record)
    cp.datetime = FakeDT
    try:
        cp.reopen_stuck(rec)
        cp.grade(rec)
    finally:
        cp.datetime = _REAL_DT
    return rec


def _tally(entry):
    out = {}
    for p in entry["picks"]:
        key = str(p.get("result"))
        out[key] = out.get(key, 0) + 1
    return out


# A day with real results plus one pick whose box score never arrives —
# i.e. a genuinely benched player, the exact case that hung days open.
_YESTERDAY = (_REAL_DT.now(cp.EASTERN) - timedelta(days=1)).strftime("%Y-%m-%d")
RECORD = {
    "daily13": {
        _YESTERDAY: {
            "picks": [
                {"id": 1, "name": "A", "result": "hit"},
                {"id": 2, "name": "B", "result": "miss"},
                {"id": 3, "name": "C", "result": None},   # never gets a line
            ],
            "graded": False,
        }
    }
}

# Nothing ever returns a line, and no real sleeping in tests.
cp._mlb_line = lambda pid, d: None
cp._wnba_line = lambda pid, d: None
cp.time.sleep = lambda s: None

# --- 1. Inside the pending window, stay open --------------------------
day0 = _at(0, RECORD)["daily13"][_YESTERDAY]
assert day0["graded"] is False, (
    "a day one day old must stay OPEN — official logs post hours late and "
    "closing early is what stranded picks as permanent DNPs")
assert _tally(day0)["None"] == 1, "the pending pick must stay ungraded, not be closed early"
print("PASS: a fresh day stays open while box scores may still post")

# --- 2. Past the window, close it ------------------------------------
late = _at(cp.FINALIZE_AFTER_DAYS + 2, RECORD)["daily13"][_YESTERDAY]
assert late["graded"] is True, (
    f"a day older than FINALIZE_AFTER_DAYS ({cp.FINALIZE_AFTER_DAYS}) must "
    f"CLOSE — otherwise one benched player holds it open forever and it "
    f"ages out of the grading window ungraded")
assert _tally(late).get("dnp") == 1, "the unplayable pick must finalize as a real DNP"
print("PASS: a stale missing line finalizes as DNP and the day closes")

# --- 3. Real results are never rewritten -----------------------------
t = _tally(late)
assert t.get("hit") == 1 and t.get("miss") == 1, (
    f"grading must never touch settled hit/miss results, got {t} — a miss "
    f"laundered into a hit would make the whole scorecard worthless")
print("PASS: settled hit/miss results survive finalization untouched")

# --- 4. Idempotent: no reopen/close loop -----------------------------
once = _at(cp.FINALIZE_AFTER_DAYS + 2, RECORD)
twice = _at(cp.FINALIZE_AFTER_DAYS + 2, once)
assert _tally(twice["daily13"][_YESTERDAY]) == _tally(once["daily13"][_YESTERDAY]), (
    "re-running grading changed the record — reopen_stuck is undoing "
    "grade()'s verdict, which means one HTTP request per pick per run forever")
assert twice["daily13"][_YESTERDAY]["graded"] is True
print("PASS: grading is idempotent — reopen_stuck no longer fights grade()")

# --- 5. The two graders must agree on the rule ------------------------
# The pipeline owns published history; the app grades the same picks for
# same-session feedback. If their finalize windows differ, the same pick
# gets different results depending on which record wins the merge.
st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
sys.path.insert(0, "app")
from engines import calibration as app_cal

assert app_cal.FINALIZE_AFTER_DAYS == cp.FINALIZE_AFTER_DAYS, (
    f"app ({app_cal.FINALIZE_AFTER_DAYS}) and pipeline "
    f"({cp.FINALIZE_AFTER_DAYS}) disagree on when a missing line becomes a "
    f"DNP — the same pick would grade differently on each side")
print("PASS: app and pipeline share one finalize rule")
