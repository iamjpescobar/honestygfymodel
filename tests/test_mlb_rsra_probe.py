"""The MLB probe counts what it found — one extractor, not two.

WHY THIS EXISTS

Run 85312622391 printed:

    standings regularSeason  200 | 30 entries | 30 w/stats | 0 w/runs

Thirty entries. Thirty carrying `runsScored`. **Zero counted.**

The verdict then ranked shapes by `w/runs`, picked `teams/stats hitting`
with its ONE league-aggregate row, and reported *"PARTIAL: returned 1
club with runs, not 30 — tier 2 stays dark"* — declaring tier 2
unbuildable off a payload that had all thirty clubs sitting in it.

THE CAUSE: TWO PLACES EXTRACTED ENTRIES AND ONLY ONE LEARNED THE NEW
SHAPE. When standings was added, `_diagnose` was taught that its records
nest under `records[].teamRecords[]`. `main()` kept its own private copy
— `payload.get("teams") or payload.get("stats")` — which is empty for
standings. So the diagnostic saw thirty and the counter saw none, in the
same row of the same line of output.

That is the third time this repo has been bitten by the same idea in a
different costume: a computed thing and a rendered thing disagreeing
because they were derived separately. Here it was worse than a missing
feature — it produced a CONFIDENT NEGATIVE about an endpoint that works.

A probe that under-reports is not a safe failure. "Tier 2 is not
buildable" is exactly the kind of finding that gets written into HANDOFF
and closes an avenue for months.

WHAT THIS PINS

`_entries()` is the single extractor, and both the diagnostic and the
runs counter go through it. No `payload.get("teams")` anywhere else in
the file.

Runs offline against payloads matching each API's documented shape —
no network, no key.
"""
import importlib.util
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
_spec = importlib.util.spec_from_file_location(
    "mlb_rsra_probe", os.path.join(ROOT, "mlb_rsra_probe.py"))
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)

failures = []


def check(label, ok):
    if ok:
        print(f"PASS: {label}")
    else:
        failures.append(label)


def standings(n_div=6, per_div=5, runs=True):
    """A payload shaped like /api/v1/standings."""
    recs = []
    for d in range(n_div):
        team_records = []
        for i in range(per_div):
            tr = {"team": {"name": f"Club {d}-{i}"}, "gamesPlayed": 118}
            if runs:
                tr["runsScored"] = 500 + i
                tr["runsAllowed"] = 480 + i
            team_records.append(tr)
        recs.append({"division": {"id": 200 + d}, "teamRecords": team_records})
    return {"copyright": "x", "records": recs}


TEAMS_STATS = {"stats": [{"splits": [{"stat": {"runs": 591,
                                               "gamesPlayed": 119}}]}]}
HYDRATE = {"copyright": "x", "teams": [{"id": i} for i in range(30)]}


# ----------------------------------------------------------------------
# 1. THE REGRESSION. Diagnostic and counter must agree.
# ----------------------------------------------------------------------
p = standings()
_top, n_entries, n_stats = mp._diagnose(p)
entries = mp._entries(p)
w_runs = sum(1 for e in entries if mp._walk_for_runs(e))

check(f"the diagnostic unwraps divisions into clubs (got {n_entries})",
      n_entries == 30)
check(f"the COUNTER sees the same 30, not 0 (got {w_runs})", w_runs == 30)
check("diagnostic and counter agree — this is the whole bug",
      n_entries == len(entries) == w_runs == n_stats)

# 6 is the number the old code would have reported if it counted the
# outer list. Pinned by name because 6-of-30 reads like a partial
# failure rather than a parsing mistake.
check("divisions are never mistaken for clubs (6 != 30)",
      len(mp._entries(p)) != len(p["records"]))

# ----------------------------------------------------------------------
# 2. ONE EXTRACTOR. Asserted on the source, because a second private
#    copy is invisible from behaviour until a shape changes — which is
#    exactly how this shipped.
# ----------------------------------------------------------------------
src = open(os.path.join(ROOT, "mlb_rsra_probe.py"), encoding="utf-8").read()
code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
body = code.split("def _entries", 1)[-1]
after = body.split("def _entries", 1)[-1]
# The only `payload.get("teams")` in runnable code may be the one inside
# _entries itself.
occurrences = len(re.findall(r'payload\.get\("teams"\)', code))
check(f"only ONE place extracts entries (found {occurrences})",
      occurrences == 1)
check("main() goes through _entries()", "_entries(payload)" in code)

# ----------------------------------------------------------------------
# 3. THE OTHER SHAPES STILL WORK. A fix that broke teams/stats would
#    trade one silent wrong answer for another.
# ----------------------------------------------------------------------
check("teams/stats still yields its one league-aggregate row",
      len(mp._entries(TEAMS_STATS)) == 1)
check("teams/stats runs are still found",
      mp._walk_for_runs(mp._entries(TEAMS_STATS)[0]) == (591, 119))
check("the hydrate shape still yields 30 entries with no stats",
      len(mp._entries(HYDRATE)) == 30
      and sum(1 for e in mp._entries(HYDRATE) if mp._walk_for_runs(e)) == 0)

# ----------------------------------------------------------------------
# 4. THE FIELD NAME. Standings spells it runsScored; teams/stats spells
#    it runs. Looking for only one traverses a perfect payload and calls
#    it empty.
# ----------------------------------------------------------------------
check("runsScored is recognised as runs",
      mp._walk_for_runs({"runsScored": 540, "gamesPlayed": 117}) == (540, 117))
check("plain `runs` still is too",
      mp._walk_for_runs({"runs": 591, "gamesPlayed": 119}) == (591, 119))

# ----------------------------------------------------------------------
# 5. AN EMPTY OR MALFORMED PAYLOAD IS ZERO, NOT AN EXCEPTION. A probe
#    that crashes tells you less than one that reports nothing.
# ----------------------------------------------------------------------
for bad in (None, [], "nope", {}, {"records": "nope"}, {"records": [None]}):
    if mp._entries(bad) != []:
        failures.append(f"malformed payload {bad!r} did not yield []")
        break
else:
    check("malformed payloads yield no entries rather than raising", True)

check("a standings payload with no runs counts entries but no runs",
      len(mp._entries(standings(runs=False))) == 30
      and sum(1 for e in mp._entries(standings(runs=False))
              if mp._walk_for_runs(e)) == 0)

if failures:
    print()
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(1)

print("\nThirty found, zero counted. A probe that under-reports is not a "
      "safe failure.")
