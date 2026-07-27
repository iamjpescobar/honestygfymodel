"""Regression test for the calibration freeze bug, run against the real
pipeline module with the network calls stubbed out."""
import sys, json, types
from datetime import datetime, timedelta
sys.path.insert(0, ".")
import calibration_pipeline as cp

EASTERN = cp.EASTERN
y1 = (datetime.now(EASTERN) - timedelta(days=1)).strftime("%Y-%m-%d")
y2 = (datetime.now(EASTERN) - timedelta(days=2)).strftime("%Y-%m-%d")

# --- Test 1: box score not posted yet must NOT freeze the day ---
cp._mlb_line = lambda pid, d: None
cp.time.sleep = lambda *a: None
rec = {"hr_edge": {y1: {"picks": [{"id": 1, "name": "A", "result": None}], "graded": False}}}
cp.grade(rec)
e = rec["hr_edge"][y1]
assert e["picks"][0]["result"] is None, f"pick was frozen: {e['picks'][0]}"
assert e["graded"] is False, "day was marked graded with an unposted box score"
print("PASS: unposted box score leaves the day open for retry")

# --- Test 2: the retry on a later run actually grades it ---
cp._mlb_line = lambda pid, d: {"hits": 1, "homeRuns": 1, "xbh": 1}
n = cp.grade(rec)
assert rec["hr_edge"][y1]["picks"][0]["result"] == "hit", rec
assert rec["hr_edge"][y1]["graded"] is True
assert n == 1
print("PASS: retry grades the pick once the log posts")

# --- Test 3: already-poisoned days get recovered ---
rec2 = {"hr_edge": {y2: {"picks": [
    {"id": 1, "name": "A", "result": "dnp"},
    {"id": 2, "name": "B", "result": "miss"},
], "graded": True}}}
r = cp.reopen_stuck(rec2)
assert r == 1, r
assert rec2["hr_edge"][y2]["picks"][0]["result"] is None, "stuck dnp not reopened"
assert rec2["hr_edge"][y2]["picks"][1]["result"] == "miss", "a real miss was tampered with"
assert rec2["hr_edge"][y2]["graded"] is False
cp.grade(rec2)
assert rec2["hr_edge"][y2]["picks"][0]["result"] == "hit"
assert rec2["hr_edge"][y2]["picks"][1]["result"] == "miss", "real miss overwritten on regrade"
print("PASS: stranded DNPs recovered, real results untouched")

# --- Test 4: today's slate is never graded ---
today = datetime.now(EASTERN).strftime("%Y-%m-%d")
rec3 = {"hr_edge": {today: {"picks": [{"id": 1, "result": None}], "graded": False}}}
cp.grade(rec3)
assert rec3["hr_edge"][today]["picks"][0]["result"] is None
print("PASS: in-progress slate is never graded")
