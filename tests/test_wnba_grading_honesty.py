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
