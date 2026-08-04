"""Every way the WNBA grader can fail must name itself in the log.

_wnba_line returns None for four unrelated reasons, and grade() cannot
tell them apart: it leaves the pick open, then closes it as "dnp" once
FINALIZE_AFTER_DAYS passes. DNPs are excluded from the hit-rate
denominator, so a grader that reads NOTHING produces no error, no empty
column and no banner — just a board that says "nothing graded yet"
forever while its picks age out three days at a time. That is the state
the record is actually in: 45 WNBA picks logged, zero ever graded.

So the fix is not a guess at which failure it is. It's making the run
say which. This pins that: each failure mode must produce its own
distinct reason string, and a run that reads nothing at all must say so
loudly rather than blending into the summary.

No network — requests.get is stubbed, same technique as
test_wnba_grading_honesty.py, whose cases pin the PARSE. This pins the
REPORTING around it.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

failures = []


def stub_requests(payload=None, raise_exc=None, status=200):
    class _Resp:
        status_code = status

        def raise_for_status(self):
            if raise_exc:
                raise raise_exc

        def json(self):
            return payload

    mod = types.ModuleType("requests")
    mod.get = lambda *a, **k: _Resp()
    return mod


def fresh_pipeline(**stub_kwargs):
    """Re-import with a stubbed requests, so _WNBA_DIAG starts empty."""
    sys.modules["requests"] = stub_requests(**stub_kwargs)
    for m in [k for k in sys.modules if k.startswith("calibration_pipeline")]:
        del sys.modules[m]
    import calibration_pipeline as cp
    return cp


def gamelog(labels, stats, date_str="2026-08-01"):
    return {"names": labels,
            "events": {"1": {"gameDate": f"{date_str}T23:00Z", "stats": stats}}}


CASES = [
    # name,               stub kwargs,                                   expected reason fragment
    ("request blew up",   dict(raise_exc=RuntimeError("403 Forbidden"), status=403),
     "request failed"),
    ("not a gamelog",     dict(payload=["unexpected"]),
     "not an object"),
    ("no events at all",  dict(payload={"names": ["PTS"], "events": {}}),
     "no events"),
    ("wrong date",        dict(payload=gamelog(["PTS"], ["20"], "2026-07-30")),
     "no event matching the date"),
    ("event has no stats", dict(payload=gamelog(["PTS", "REB", "AST"], [])),
     "carried no stat row"),
    # Headers that map to nothing usable is a DIFFERENT bug from a
    # missing stat row — this is the shape that broke grading for a week
    # (long-form names read as if they were the short ones).
    ("no PTS in headers", dict(payload=gamelog(["REB", "AST"], ["8", "5"])),
     "no usable column headers"),
    ("PTS present but junk", dict(payload=gamelog(["PTS", "REB"], ["--", "8"])),
     "PTS did not parse"),
]

seen_reasons = set()
for name, kwargs, fragment in CASES:
    cp = fresh_pipeline(**kwargs)
    got = cp._wnba_line(4398966, "2026-08-01")
    reasons = list(cp._WNBA_DIAG["reasons"])

    if got is not None:
        failures.append(f"{name}: returned {got!r} instead of None — the "
                        f"parse must be unchanged by the instrumentation")
    elif not reasons:
        failures.append(f"{name}: failed silently, no reason recorded — this "
                        f"is the exact invisibility the report exists to end")
    elif fragment not in reasons[0]:
        failures.append(f"{name}: reason {reasons[0]!r} does not name the "
                        f"failure (expected something containing {fragment!r})")
    else:
        seen_reasons.add(reasons[0])
        print(f"PASS: {name:20} -> {reasons[0]}")

if len(seen_reasons) < len(CASES) and not failures:
    failures.append(f"only {len(seen_reasons)} distinct reasons for "
                    f"{len(CASES)} failure modes — two different bugs would "
                    f"report as the same thing and the log stops being useful")
elif not failures:
    print(f"PASS: all {len(CASES)} failure modes report distinct reasons")

# ----------------------------------------------------------------------
# A successful read must be counted, so the report can say "0 of 45"
# rather than only listing failures.
# ----------------------------------------------------------------------
cp = fresh_pipeline(payload=gamelog(["PTS", "REB", "AST"], ["20", "8", "5"]))
line = cp._wnba_line(4398966, "2026-08-01")
if (line or {}).get("pra") != 33.0:
    failures.append(f"a good payload no longer parses: {line!r}")
elif cp._WNBA_DIAG["ok"] != 1 or cp._WNBA_DIAG["reasons"]:
    failures.append(f"successful read not counted: ok={cp._WNBA_DIAG['ok']}, "
                    f"reasons={cp._WNBA_DIAG['reasons']}")
else:
    print("PASS: a successful read is counted and records no reason")

# ----------------------------------------------------------------------
# The all-failed case must be LOUD. It is the one that currently looks
# like nothing at all in the nightly log.
# ----------------------------------------------------------------------
import io                                                    # noqa: E402
import contextlib                                            # noqa: E402

cp = fresh_pipeline(raise_exc=RuntimeError("403 Forbidden"), status=403)
for _pid in (1, 2, 3):
    cp._wnba_line(_pid, "2026-08-01")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cp.report_wnba_diagnostics()
out = buf.getvalue()

if "[verify-wnba]" not in out:
    failures.append("the report prints nothing under the [verify-wnba] tag, "
                    "so it can't be found in a nightly log")
elif "read 0/3" not in out:
    failures.append(f"the report does not state how many lines were read:\n{out}")
elif "NOT ONE" not in out:
    failures.append(f"a run that graded nothing did not say so loudly:\n{out}")
else:
    print("PASS: a run that reads nothing says so, with the count and reason")

# And the quiet case stays quiet — no noise on a healthy run.
cp = fresh_pipeline(payload=gamelog(["PTS", "REB", "AST"], ["20", "8", "5"]))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cp.report_wnba_diagnostics()
if buf.getvalue().strip():
    failures.append("the report prints on a run that graded no WNBA picks at "
                    "all — noise trains you to skip the log")
else:
    print("PASS: no WNBA picks this run means no report")

# ----------------------------------------------------------------------
if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nWNBA grading diagnostics: every failure mode is nameable.")
