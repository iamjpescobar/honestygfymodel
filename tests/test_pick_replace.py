"""A single-market board must REPLACE its picks, not freeze at 1 PM.

WHAT HAPPENED ON 2026-08-12. hr_edge graded four picks on a fifteen-game
slate — two confirmed lineups at 1 PM against a 2-per-game cap. By
evening the real board had Cal Raleigh and Shohei Ohtani above every one
of them. The record was measuring lunchtime.

THE CAUSE. Idempotency is per (board, date, MARKET):

    logged_markets = {p.get("stat") for p in existing["picks"]}
    fresh = [r for r in rows if r.get("stat") not in logged_markets]

hr_edge, daily13 and potd carry stat=None on every pick. After the 1 PM
run logged_markets == {None}; at 5 and 7 PM every row also had
stat=None, so `fresh` was empty and the day was left alone. The rule was
written for the WNBA boards, which have five real markets. It froze the
MLB ones, and nothing said so — the log line read "every market already
logged", which was true and completely misleading.

The multi-market behaviour must survive the fix, so it is pinned here
too.
"""
import json, sys, types, tempfile
from pathlib import Path

sys.modules.setdefault("pybaseball", types.ModuleType("pybaseball"))
sys.path.insert(0, ".")


def run(record, board, rows, date="2026-08-12"):
    """The write path from calibration_picks.main(), in isolation.

    Mirrors the source rather than importing it — main() fetches a slate
    over the network and builds every board. Case 4 below asserts this
    copy has not drifted from the real one.
    """
    existing = record.get(board, {}).get(date) or {}
    logged_markets = {p.get("stat") for p in existing.get("picks", [])}
    _single_market = {r.get("stat") for r in rows} == {None}
    if (_single_market and existing.get("picks")
            and len(rows) >= len(existing["picks"])):
        entry = record[board][date]
        entry["picks"] = [{"id": r["id"], "name": r.get("name"),
                           "stat": r.get("stat"), "result": None} for r in rows]
        entry["graded"] = False
        return "replaced"
    fresh = [r for r in rows if r.get("stat") not in logged_markets]
    if not fresh:
        return "frozen"
    entry = record.setdefault(board, {}).setdefault(
        date, {"picks": [], "graded": False, "source": "ci"})
    entry["picks"].extend({"id": r["id"], "name": r.get("name"),
                           "stat": r.get("stat"), "result": None} for r in fresh)
    entry["graded"] = False
    return "appended"


def bats(*names):
    return [{"id": str(i), "name": n, "stat": None} for i, n in enumerate(names)]


# --- 1. THE 1 PM BOARD MUST NOT SURVIVE THE EVENING ------------------
rec = {}
assert run(rec, "hr_edge", bats("Alonso", "Schwarber")) == "appended"
assert run(rec, "hr_edge", bats("Raleigh", "Ohtani", "Alonso",
                                "Schwarber", "Riley")) == "replaced"
names = [p["name"] for p in rec["hr_edge"]["2026-08-12"]["picks"]]
assert names == ["Raleigh", "Ohtani", "Alonso", "Schwarber", "Riley"], names
print(f"PASS: the evening board replaced the 1 PM one ({names[0]} now #1)")

# --- 2. REPLACING REOPENS THE DAY ------------------------------------
#
# grade() skips a day already marked graded. Replace the picks without
# clearing the flag and the new list is never graded at all — worse than
# the freeze, because it looks complete.
rec["hr_edge"]["2026-08-12"]["graded"] = True
# Five, not three: a thinner board is refused by case 6's guard, so a
# three-pick fixture here would have been testing the refusal instead of
# the reopen — green for the wrong reason.
run(rec, "hr_edge", bats("Raleigh", "Ohtani", "Judge", "Soto", "Betts"))
assert rec["hr_edge"]["2026-08-12"]["graded"] is False
print("PASS: a replacement reopens the day for grading")

# --- 3. NO DUPLICATES ------------------------------------------------
#
# The old path APPENDED. Replacing with an overlapping board must not
# leave two Alonsos.
rec2 = {}
run(rec2, "hr_edge", bats("Alonso", "Schwarber"))
run(rec2, "hr_edge", bats("Alonso", "Schwarber", "Riley"))
got = [p["name"] for p in rec2["hr_edge"]["2026-08-12"]["picks"]]
assert got == ["Alonso", "Schwarber", "Riley"], got
assert len(got) == len(set(got)), got
print("PASS: an overlapping later board does not duplicate picks")

# --- 4. MULTI-MARKET BOARDS STILL APPEND PER MARKET -------------------
#
# The behaviour the per-market rule was written for, and the reason the
# fix is scoped to boards whose markets are all None. A WNBA board that
# has Points at 5 PM and Rebounds at 7 must keep both.
rec3 = {}
pts = [{"id": "1", "name": "A", "stat": "Points"}]
reb = [{"id": "2", "name": "B", "stat": "Rebounds"}]
assert run(rec3, "wnba_props", pts) == "appended"
assert run(rec3, "wnba_props", reb) == "appended"
assert run(rec3, "wnba_props", pts) == "frozen", (
    "a market already logged was logged again")
stats = sorted(p["stat"] for p in rec3["wnba_props"]["2026-08-12"]["picks"])
assert stats == ["Points", "Rebounds"], stats
print("PASS: multi-market boards still append per market and skip repeats")

# --- 5. THE COPY ABOVE MATCHES THE REAL WRITE PATH -------------------
src = open("calibration_picks.py", encoding="utf-8").read()
assert '_single_market = {r.get("stat") for r in rows} == {None}' in src, (
    "calibration_picks no longer detects single-market boards — the "
    "replace path is gone and hr_edge will freeze at 1 PM again")
assert 'entry["graded"] = False' in src
print("PASS: calibration_picks still contains the replace path")


# --- 6. A DEGRADED LATER RUN MUST NOT CLOBBER A GOOD ONE -------------
#
# The risk plain replacement introduced, and the reason the guard is
# `len(rows) >= len(existing)`. If the 7 PM build hiccups and sees two
# games where the 5 PM one saw fifteen, the day must keep the fuller
# list. tests/test_calibration_picks.py caught this the moment the
# unguarded version landed — retry safety is what three daily runs are
# FOR, and replacement quietly traded it away.
rec4 = {}
run(rec4, "hr_edge", bats("Raleigh", "Ohtani", "Alonso", "Schwarber", "Riley"))
assert run(rec4, "hr_edge", bats("Alonso", "Schwarber")) == "frozen", (
    "a two-pick board overwrote a five-pick one")
kept = [p["name"] for p in rec4["hr_edge"]["2026-08-12"]["picks"]]
assert kept[0] == "Raleigh" and len(kept) == 5, kept
print("PASS: a thinner later board is refused; the fuller one survives")

# ...and an equal-sized one still wins, because it rests on more
# confirmed lineups.
assert run(rec4, "hr_edge", bats("A", "B", "C", "D", "E")) == "replaced"
print("PASS: an equal-sized later board still wins the tie")
