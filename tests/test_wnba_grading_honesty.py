"""The two WNBA graders must agree, and neither may invent a stat.

There are two implementations of the same parse:

  calibration_pipeline._wnba_line   — SOURCE OF TRUTH for published
                                      history, runs in the nightly job
  app/engines/calibration.py        — the app's own live grader

They have drifted before, and the file comments record what it cost: the
pipeline kept re-poisoning the record the app read back. So this pins
BOTH to the same behaviour on the same inputs.

The specific thing being guarded: a component ESPN didn't return must not
become a zero. `(pts or 0) + (reb or 0) + (ast or 0)` turns an unread
rebound into a real one, and the resulting PRA looks measured and gets
graded as measured — understated, against a pick that may have hit.

Both graders already treat a None outcome as "dnp" and drop it from the
win/loss record, which is the honest outcome: better to not score a pick
than to score it against a number we couldn't read.

No network. The ESPN payload is constructed inline so the parse can be
exercised directly.
"""
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))


def espn_payload(labels, stats, date_str="2026-08-01"):
    """Minimal shape of ESPN's gamelog response."""
    return {
        "names": labels,
        "events": {"1": {"gameDate": f"{date_str}T23:00Z", "stats": stats}},
    }


# ----------------------------------------------------------------------
# Both graders fetch over the network, so requests.get is replaced with a
# stub that returns the payload under test. Nothing here touches ESPN.
# ----------------------------------------------------------------------
def stub_requests(payload):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    mod = types.ModuleType("requests")
    mod.get = lambda *a, **k: _Resp()
    return mod


CASES = [
    # label,                  labels,                stats,             expect_pra
    ("all three present",     ["PTS", "REB", "AST"], ["20", "8", "5"],  33.0),
    ("REB missing from row",  ["PTS", "AST"],        ["20", "5"],       None),
    ("AST missing from row",  ["PTS", "REB"],        ["20", "8"],       None),
    ("REB unparseable ('--')", ["PTS", "REB", "AST"], ["20", "--", "5"], None),
    ("genuine zeros are real", ["PTS", "REB", "AST"], ["20", "0", "0"], 20.0),
]

failures = []

for _case_i, (label, labels, stats, expect) in enumerate(CASES):
    payload = espn_payload(labels, stats)
    # The app grader is @st.cache_data-decorated and caches on its args,
    # so each case needs a distinct player id or every iteration after
    # the first would read back the first case's answer.
    pid = 12345 + _case_i

    # --- pipeline grader -------------------------------------------------
    sys.modules["requests"] = stub_requests(payload)
    for m in [k for k in sys.modules if k.startswith("calibration_pipeline")]:
        del sys.modules[m]
    import calibration_pipeline as cp
    got_pipeline = cp._wnba_line(pid, "2026-08-01")
    pra_pipeline = (got_pipeline or {}).get("pra")

    # --- app grader ------------------------------------------------------
    sys.modules["requests"] = stub_requests(payload)
    for m in [k for k in sys.modules if k.startswith("engines.calibration")]:
        del sys.modules[m]
    import engines.calibration as cal
    raw = cal._wnba_day_json(pid, "2026-08-01")
    got_app = json.loads(raw) if raw else None
    pra_app = (got_app or {}).get("pra")

    ok_pipeline = pra_pipeline == expect
    ok_app = pra_app == expect
    agree = pra_pipeline == pra_app

    status = "PASS" if (ok_pipeline and ok_app and agree) else "FAIL"
    print(f"{status}: {label:26} pipeline={pra_pipeline!r:8} app={pra_app!r:8} "
          f"expected={expect!r}")

    if not agree:
        failures.append(f"{label}: the two graders DISAGREE "
                        f"(pipeline={pra_pipeline!r}, app={pra_app!r})")
    if not ok_pipeline:
        failures.append(f"{label}: pipeline PRA {pra_pipeline!r}, expected {expect!r}")
    if not ok_app:
        failures.append(f"{label}: app PRA {pra_app!r}, expected {expect!r}")

    # A component that could not be read must never be reported as 0.
    for name, got in (("pipeline", got_pipeline), ("app", got_app)):
        if expect is None and got:
            if got.get("reb") == 0 and "REB" not in labels:
                failures.append(f"{label}: {name} reported an unread REB as 0")
            if got.get("ast") == 0 and "AST" not in labels:
                failures.append(f"{label}: {name} reported an unread AST as 0")

# ----------------------------------------------------------------------
# THE DATE MATCH — the half of this parse that was never covered.
#
# Every case above uses T23:00Z, which is 7 PM ET: the one tip time on
# the WNBA schedule where the UTC date and the ET slate date are the same
# calendar day. gameDate is UTC and picks are logged under the ET date,
# so an 8 PM tip is 00:00Z TOMORROW and a 10 PM West Coast tip is 02:00Z
# TOMORROW. Both used to fall through to "no matching event", grade as
# DNP three days later, and drop out of the hit-rate denominator without
# reporting anything.
#
# Real tip times, all belonging to the 2026-08-01 ET slate.
# ----------------------------------------------------------------------
TIP_TIMES = [
    ("12:00 PM ET matinee", "2026-08-01T16:00Z"),
    ("3:00 PM ET",          "2026-08-01T19:00Z"),
    ("7:00 PM ET",          "2026-08-01T23:00Z"),
    ("8:00 PM ET",          "2026-08-02T00:00Z"),
    ("10:00 PM ET west",    "2026-08-02T02:00Z"),
]

for _tip_i, (when, stamp) in enumerate(TIP_TIMES):
    payload = {"names": ["PTS", "REB", "AST"],
               "events": {"1": {"gameDate": stamp, "stats": ["20", "8", "5"]}}}
    pid = 90000 + _tip_i

    sys.modules["requests"] = stub_requests(payload)
    for m in [k for k in sys.modules if k.startswith("calibration_pipeline")]:
        del sys.modules[m]
    import calibration_pipeline as cp
    pipe = cp._wnba_line(pid, "2026-08-01")

    sys.modules["requests"] = stub_requests(payload)
    for m in [k for k in sys.modules if k.startswith("engines.calibration")]:
        del sys.modules[m]
    import engines.calibration as cal
    _raw = cal._wnba_day_json(pid, "2026-08-01")
    app = json.loads(_raw) if _raw else None

    ok = (pipe or {}).get("pts") == 20.0 and (app or {}).get("pts") == 20.0
    print(f"{'PASS' if ok else 'FAIL'}: {when:22} pipeline="
          f"{'read' if pipe else 'MISSED':6} app={'read' if app else 'MISSED'}")
    if not ok:
        failures.append(
            f"{when}: the line was not read (pipeline={pipe!r}, app={app!r}). "
            f"A pick on this slate grades as DNP and leaves the record "
            f"without ever reporting a failure.")

# ----------------------------------------------------------------------
# THE REAL PAYLOAD SHAPE.
#
# Every fixture above is a simplification written from the NBA gamelog's
# shape, and it hid two bugs that a nightly run then exposed on 45 picks:
#
#   1. ESPN sends headers twice — `labels` short (PTS/REB/AST/3PT) and
#      `names` long (POINTS/TOTALREBOUNDS/...). The parser read
#      `names or labels`, took the long array, and looked up "PTS" in it.
#   2. The top-level `events` map is METADATA. Its "stats" key is an
#      empty list; the numbers live under seasonTypes -> categories ->
#      events, keyed by eventId.
#
# So this case is the payload as ESPN actually returns it, at an 8 PM ET
# tip (00:00Z the next day) to keep the timezone fix under test at the
# same time.
# ----------------------------------------------------------------------
REAL_LABELS = ["MIN", "FG", "FG%", "3PT", "3P%", "FT", "FT%",
               "REB", "AST", "BLK", "STL", "PF", "TO", "PTS"]
REAL_NAMES = ["MINUTES", "FIELDGOALSMADE-FIELDGOALSATTEMPTED", "FIELDGOALPCT",
              "THREEPOINTFIELDGOALSMADE-THREEPOINTFIELDGOALSATTEMPTED",
              "THREEPOINTFIELDGOALPCT", "FREETHROWSMADE-FREETHROWSATTEMPTED",
              "FREETHROWPCT", "TOTALREBOUNDS", "ASSISTS", "BLOCKS", "STEALS",
              "FOULS", "TURNOVERS", "POINTS"]
REAL_ROW = ["31", "8-15", "53.3", "2-5", "40.0", "4-4", "100.0",
            "9", "6", "1", "2", "3", "2", "22"]
EXPECT = {"pts": 22.0, "reb": 9.0, "ast": 6.0, "pra": 37.0, "tpm": 2.0}


def real_payload(with_short_labels=True):
    p = {
        "names": REAL_NAMES,
        "seasonTypes": [{"categories": [{"events": [
            {"eventId": "401800", "stats": REAL_ROW}]}]}],
        # Metadata only — note the empty stats list, exactly as served.
        "events": {"401800": {"gameDate": "2026-08-02T00:00Z", "stats": []}},
    }
    if with_short_labels:
        p["labels"] = REAL_LABELS
    return p


for _real_i, _short in enumerate((True, False)):
    payload = real_payload(_short)
    pid = 70000 + _real_i
    who = "labels + names" if _short else "long names only"

    sys.modules["requests"] = stub_requests(payload)
    for m in [k for k in sys.modules if k.startswith("calibration_pipeline")]:
        del sys.modules[m]
    import calibration_pipeline as cp
    pipe = cp._wnba_line(pid, "2026-08-01")

    sys.modules["requests"] = stub_requests(payload)
    for m in [k for k in sys.modules if k.startswith("engines.calibration")]:
        del sys.modules[m]
    import engines.calibration as cal
    _raw = cal._wnba_day_json(pid, "2026-08-01")
    app = json.loads(_raw) if _raw else None

    ok = pipe == EXPECT and app == EXPECT
    print(f"{'PASS' if ok else 'FAIL'}: real ESPN shape ({who})")
    if not ok:
        failures.append(f"real ESPN shape ({who}): pipeline={pipe!r} "
                        f"app={app!r}, expected {EXPECT!r}")

# A game on a genuinely different day must still NOT match, or the fix
# would grade picks against the wrong night.
payload = {"names": ["PTS", "REB", "AST"],
           "events": {"1": {"gameDate": "2026-07-30T23:00Z",
                            "stats": ["20", "8", "5"]}}}
sys.modules["requests"] = stub_requests(payload)
for m in [k for k in sys.modules if k.startswith("calibration_pipeline")]:
    del sys.modules[m]
import calibration_pipeline as cp
if cp._wnba_line(99999, "2026-08-01") is not None:
    failures.append("a game two days earlier matched the slate date — the "
                    "grader would score picks against the wrong night")
else:
    print("PASS: a different night still does not match")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    print("=" * 68)
    print("\nA graded outcome built from a stat that was never read is a "
          "fabricated result in the one number that is supposed to prove "
          "the model.")
    sys.exit(1)

print("\nPASS: neither grader fabricates a PRA component, and they agree.")
