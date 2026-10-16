"""
MLB game logs with the postseason (10-16) — engines/mlb_gamelog and the
graders / trend windows that read it.

Plain script — exits non-zero on failure. Payloads in the Stats API's
gameLog shape ({"stats": [{"splits": [{"date", "game": {"gamePk"},
"stat"}]}]}) — rule 5. No network: a fake getter keyed on gameType.

Negative controls, confirmed red by exit code when written (rule 4):
  - splits() without the postseason read
    -> "a postseason pick is graded, not closed as did-not-play" fails
  - splits() without the de-duplication
    -> "one row per game when both reads return it" fails
  - splits() trying only gameType P
    -> "falls back to F,D,L,W when P returns nothing" fails
  - reopen_postseason without the ps_regraded stamp
    -> "a genuine DNP is never reopened twice" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import mlb_gamelog as gl  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def log(*games):
    return {"stats": [{"splits": [{"date": d, "game": {"gamePk": pk},
                                   "stat": {"hits": h, "homeRuns": hr, "doubles": 0,
                                            "triples": 0, "strikeOuts": k}}
                                  for d, pk, h, hr, k in games]}]}


REG = log(("2026-09-27", 1, 2, 1, 0), ("2026-09-26", 2, 0, 0, 1))
POST = log(("2026-10-14", 9, 1, 1, 7), ("2026-10-12", 8, 0, 0, 5))


def getter(post_by=("P",), fail_post=False, fail_reg=False):
    calls = []

    def get(url, params):
        gt = params.get("gameType")
        calls.append(gt)
        if gt is None:
            if fail_reg:
                raise RuntimeError("down")
            return REG
        if fail_post:
            raise RuntimeError("down")
        return POST if gt in post_by else {"stats": []}
    return get, calls


get, calls = getter()
sp = gl.splits(get, "u", "hitting", 2026)
check("regular season + postseason, in date order",
      [s["date"] for s in sp] == ["2026-09-26", "2026-09-27", "2026-10-12", "2026-10-14"])
check("postseason rows are marked", [s["_post"] for s in sp] == [False, False, True, True])
check("asks for the postseason once when P answers", calls == [None, "P"])

get, calls = getter(post_by=("F,D,L,W",))
sp = gl.splits(get, "u", "hitting", 2026)
check("falls back to F,D,L,W when P returns nothing",
      calls == [None, "P", "F,D,L,W"] and sum(s["_post"] for s in sp) == 2)

get, _ = getter(fail_post=True)
check("a failed postseason read keeps the regular season",
      [s["date"] for s in gl.splits(get, "u", "hitting", 2026)] == ["2026-09-26", "2026-09-27"])
get, _ = getter(fail_reg=True)
try:
    gl.splits(get, "u", "hitting", 2026)
    raised = False
except RuntimeError:
    raised = True
check("a failed regular read still raises (unknown is not did-not-play)", raised)


def dup_get(url, params):
    return REG if params.get("gameType") is None else log(("2026-09-27", 1, 2, 1, 0))


check("one row per game when both reads return it",
      len(gl.splits(dup_get, "u", "hitting", 2026)) == 2)

# --- the nightly grader --------------------------------------------------------
import calibration_pipeline as cp  # noqa: E402

orig = cp._gamelog.requests_getter
cp._gamelog.requests_getter = lambda timeout=15: getter()[0]
try:
    line = cp._mlb_line(123, "2026-10-14")
    check("a postseason pick is graded, not closed as did-not-play",
          isinstance(line, dict) and line["homeRuns"] == 1 and line["hits"] == 1)
    check("a date he really did not play is still did-not-play",
          cp._mlb_line(123, "2026-10-13") is cp.DID_NOT_PLAY)
    k = cp._mlb_pitching_line(456, "2026-10-12")
    check("a postseason start is graded for the Strikeout Board", k == {"strikeOuts": 5})
finally:
    cp._gamelog.requests_getter = orig

# --- the one-time reopen of postseason DNPs ------------------------------------
rec = {"daily13": {"2026-09-20": {"graded": True, "picks": [{"id": 1, "result": "dnp"}]},
                   "2026-10-05": {"graded": True, "picks": [{"id": 2, "result": "dnp"},
                                                            {"id": 3, "result": "hit"}]}},
       "wnba_props": {"2026-10-05": {"graded": True, "picks": [{"id": 4, "result": "dnp"}]}}}
n1 = cp.reopen_postseason(rec)
check("postseason DNPs on MLB boards are reopened once",
      n1 == 1 and rec["daily13"]["2026-10-05"]["picks"][0]["result"] is None
      and not rec["daily13"]["2026-10-05"]["graded"])
check("regular-season DNPs, hits and other sports are left alone",
      rec["daily13"]["2026-09-20"]["picks"][0]["result"] == "dnp"
      and rec["daily13"]["2026-10-05"]["picks"][1]["result"] == "hit"
      and rec["wnba_props"]["2026-10-05"]["picks"][0]["result"] == "dnp")
rec["daily13"]["2026-10-05"]["picks"][0]["result"] = "dnp"       # a genuine DNP
check("a genuine DNP is never reopened twice", cp.reopen_postseason(rec) == 0)

# --- every MLB game-log reader uses it ----------------------------------------
for path in ("calibration_pipeline.py", "app/engines/calibration.py",
             "app/engines/batter_trends.py", "app/engines/pitcher_trends.py"):
    src = (ROOT / path).read_text(encoding="utf-8")
    check(f"{path} reads logs through mlb_gamelog", "splits(" in src and "gamelog" in src)
check("trend windows label postseason games",
      all('(PS)' in (ROOT / p).read_text(encoding="utf-8")
          for p in ("app/engines/batter_trends.py", "app/engines/pitcher_trends.py")))
check("the nightly prints whether Statcast carries postseason pitches",
      "Statcast postseason pitches" in (ROOT / "precompute.py").read_text(encoding="utf-8"))

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall postseason game-log checks passed")
