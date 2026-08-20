"""The pick record has to be written BEFORE first pitch, not after it.

TWO FAILURES THIS PINS, both of which were silent and both of which cost
a whole day of record rather than throwing anything.

1. THE FIRST RUN WAS AFTER THE SLATE STARTED.

   slate-picks used to fire at 17:00, 21:00 and 23:00 UTC — 1, 5 and
   7 PM ET. MLB posts confirmed lineups one to three hours before first
   pitch, so on a getaway day with a 12:35 PM ET start the lineups exist
   from roughly 9:35 AM and the first run was twenty-five minutes after
   the game began. Nothing ran in that four-hour window. The board for an
   early slate was, in practice, never recorded before it was played.

2. EVERY CRON SAT ON THE HOUR.

   GitHub queues scheduled workflows rather than guaranteeing them, and
   the top of the hour is the most contended minute there is — a run
   booked for "0 17" routinely starts 15-45 minutes late. So the job
   scheduled 25 minutes after first pitch was really running an hour
   after it. This is the half of the fix that costs nothing.

Neither is checkable from a green Actions tab, because both produce
successful runs. The only evidence is a thin pick record on days the
slate started early, which is exactly the shape of evidence nobody goes
looking for.
"""
import re
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures = []


def _crons(name):
    """[(minute, hour), ...] in schedule order, from a workflow file."""
    src = (ROOT / ".github" / "workflows" / name).read_text()
    return [(int(m), int(h))
            for m, h in re.findall(r'cron:\s*"(\d+)\s+(\d+)', src)]


picks = _crons("slate-picks.yml")

if not picks:
    failures.append("slate-picks.yml has no cron schedule at all")
else:
    # EDT, because that is when a baseball season happens. The DST hole
    # is documented in slate_guard._FIRST_BUILD_HOUR and is deliberately
    # not modelled here — under EST every run lands an hour earlier,
    # which is the safe direction.
    et = [((h - 4) % 24, m) for m, h in picks]

    # A 12:35 PM ET first pitch has confirmed lineups from about 9:35.
    # At least one run must land inside that window, or an early slate
    # gets recorded after it has already started.
    EARLIEST_FIRST_PITCH = time(12, 35)
    before_first_pitch = [t for t in et if time(*t) < EARLIEST_FIRST_PITCH]
    if len(before_first_pitch) < 2:
        failures.append(
            f"only {len(before_first_pitch)} slate-picks run(s) land before a "
            f"12:35 PM ET first pitch: {sorted(before_first_pitch)}. A getaway "
            f"day slate needs at least two — one to catch the early lineups "
            f"and one to pick up the stragglers — or the board is recorded "
            f"against games already in progress.")
    else:
        print(f"PASS: {len(before_first_pitch)} runs land before a 12:35 ET "
              f"first pitch")

    # Ordered earliest-first. tests/test_slate_guard.py reads cron[0] and
    # pins slate_guard._FIRST_BUILD_HOUR to it, so a schedule listed out
    # of order would pin the constant to the wrong run and Home would
    # call a working workflow broken for three hours every morning.
    if picks != sorted(picks, key=lambda c: (c[1], c[0])):
        failures.append(
            "slate-picks crons are not in earliest-first order. "
            "test_slate_guard pins _FIRST_BUILD_HOUR to cron[0]; out of "
            "order, that constant describes the wrong run.")
    else:
        print("PASS: slate-picks crons are listed earliest-first")

    # Off the hour, on purpose. See the module docstring.
    on_the_hour = [f"{h:02d}:{m:02d} UTC" for m, h in picks if m == 0]
    if on_the_hour:
        failures.append(
            f"slate-picks crons on the top of the hour: {on_the_hour}. That is "
            f"the most contended minute on GitHub's scheduler and routinely "
            f"costs 15-45 minutes of queue delay, which is enough to push a "
            f"pre-slate run past first pitch.")
    else:
        print("PASS: no slate-picks cron sits on the top of the hour")


# ----------------------------------------------------------------------
# The late refresh must PUBLISH whatever it successfully rebuilt.
#
# WNBA was added to this workflow because it has no other recovery path:
# its slate is built only inside nightly-data, downstream of the
# fifteen-minute Statcast pull, so when the nightly fails the site shows
# "no WNBA slate on disk" until the next one succeeds.
#
# The fetch step was added and the repack condition was extended — three
# times over, the same clause repeated — but the PUBLISH and DEPLOY steps
# still tested only NPB and KBO. So in the one scenario this exists for
# (nightly failed, KBO and NPB down or on a break, WNBA is what needs
# recovering) the job downloaded the archive, refetched WNBA, repacked
# it, verified it, skipped the upload, and went green.
# ----------------------------------------------------------------------
refresh = (ROOT / ".github" / "workflows" / "intl-late-refresh.yml").read_text()

# Every step that ships something must be gated on the SAME decision, and
# that decision has to be written once. Three hand-copied boolean
# expressions is how one of them drifted.
_shipping = ["Repack and verify", "Publish the refreshed archive",
             "Trigger Render deploy"]
for step in _shipping:
    _i = refresh.find(f"- name: {step}")
    if _i < 0:
        failures.append(f"intl-late-refresh has no {step!r} step")
        continue
    _block = refresh[_i:_i + 400]
    _cond = re.search(r"if:\s*(.+)", _block)
    if not _cond:
        failures.append(f"{step!r} has no `if:` guard at all")
    elif "steps.gate.outputs.publish" not in _cond.group(1):
        failures.append(
            f"{step!r} rolls its own publish condition "
            f"({_cond.group(1).strip()!r}) instead of the shared gate. Every "
            f"league that can be refreshed must reach every shipping step, "
            f"and hand-copied conditions are exactly how WNBA was refetched, "
            f"repacked, verified and then never uploaded.")
if not failures:
    print("PASS: every shipping step in the late refresh shares one gate")

# And the gate itself must actually consider all three leagues.
_gate_i = refresh.find("- name: Decide whether anything is worth publishing")
if _gate_i < 0:
    failures.append("intl-late-refresh has no shared publish gate step")
else:
    _gate = refresh[_gate_i:_gate_i + 900]
    for lg in ("NPB", "KBO", "WNBA"):
        if f"{lg}_OUTCOME" not in _gate:
            failures.append(
                f"the publish gate never reads {lg}'s outcome, so a run where "
                f"only {lg} refreshed would rebuild the archive and throw it "
                f"away")
    else:
        print("PASS: the publish gate considers NPB, KBO and WNBA")



# ----------------------------------------------------------------------
# A NOTIFICATION MUST NOT FAIL A JOB THAT DID ITS WORK.
#
# 2026-08-20: the Render deploy hook returned HTTP 500, `curl -fsS`
# exited 22, and the nightly went red — after the tests passed and the
# archive was built, verified and successfully uploaded to the release.
# Everything the job exists to produce existed. Only the notification
# failed.
#
# That red X is the "confident wrong diagnosis" this repo has a standing
# rule against: it sends whoever reads it to debug a data build that is
# fine, and it trains the eye to ignore red — which is how a REAL
# failure gets missed on some later night.
#
# Warning instead of failing is safe ONLY because this step is last and
# the release asset is already published: the data is reachable and a
# human can press Manual Deploy. Pinned so the step cannot drift back to
# job-fatal, or stop being last.
# ----------------------------------------------------------------------
# slate-picks is in this list since 2026-08-20. Render Auto-Deploy was
# turned off (it rebuilt the service on every data commit), so a push no
# longer ships anything and this job's own hook is the ONLY way the pick
# record reaches the live site. Without it the board records five times a
# day into a repo the site never re-reads — every step green, Home
# quietly stale.
for _wf in ("nightly-data.yml", "intl-late-refresh.yml", "slate-picks.yml"):
    _src = (ROOT / ".github" / "workflows" / _wf).read_text()
    _i = _src.find("- name: Trigger Render deploy")
    if _i < 0:
        failures.append(f"{_wf} has no Render deploy step")
        continue
    _step = _src[_i:]
    _nxt = _step.find("\n      - name:", 1)
    if _nxt > 0:
        _step = _step[:_nxt]

    if "for attempt in" not in _step:
        failures.append(
            f"{_wf}'s deploy hook has no retry loop — one transient 500 "
            f"reds the whole run after the archive already published")
    if "::warning::" not in _step:
        failures.append(
            f"{_wf}'s deploy hook fails the job instead of warning. The "
            f"archive is published by this point; a red X here says the "
            f"data build broke when it did not.")
    # The warning must say the work SURVIVED — otherwise "deploy hook
    # failed" reads as "the run lost its output", which is the confident
    # wrong diagnosis all over again. The archive jobs say "already
    # published"; slate-picks says "already committed". Either is fine,
    # nothing is not.
    _u = _step.upper()
    if "ALREADY PUBLISHED" not in _u and "ALREADY COMMITTED" not in _u:
        failures.append(
            f"{_wf}'s warning does not say the work is already saved, so "
            f"whoever reads it has to work out that nothing was lost")
    # The entire argument for warning rather than failing rests on this
    # step running AFTER the upload. If it ever moves ahead of it, a
    # swallowed failure means no archive and no red X either.
    # For the archive jobs the deploy must follow the release upload.
    # slate-picks publishes nothing to a release — its durable artifact is
    # the git commit — so the same rule applies against that instead.
    _i_pub = _src.find("release upload")
    if _i_pub < 0:
        _i_pub = _src.find("release create")
    if _i_pub < 0:
        _i_pub = _src.find("git commit")
    if 0 <= _i < _i_pub:
        failures.append(
            f"{_wf} triggers the deploy BEFORE the artifact it ships is "
            f"committed or published — a non-fatal hook is only safe last")
if not failures:
    print("PASS: deploy hooks retry, warn rather than fail, and run last")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1)
print("\nA board recorded after first pitch is a board that measured nothing.")
