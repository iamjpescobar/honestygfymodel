"""
Reopen WNBA days that a broken grader closed as DNP.

WHY THIS EXISTS

_wnba_line() never read a single box score. Two bugs stacked: the ET/UTC
date comparison missed every tip after 8 PM, and the parser read ESPN's
long-form `names` array while looking up short-form keys, then read
`stats` off the metadata map where it is always empty. Every WNBA pick
came back with no line, stayed open, and closed as "dnp" three days
later via FINALIZE_AFTER_DAYS.

Those DNPs are not facts about the games. They are the shape the failure
left behind, and they are worse than an empty record: DNPs are excluded
from the hit-rate denominator, so a day of them reports as "nothing to
measure" rather than "we failed to measure this." The games happened,
the box scores are still on ESPN, and the grader can now read them.

WHAT IT TOUCHES — deliberately narrow:

  * WNBA boards only.
  * Days inside MAX_GRADE_DAYS, since grade() will not chase older ones.
  * ONLY days where not one pick ever graded hit or miss.

That last rule is what makes this safe to run. A day the grader actually
scored is left alone, so a genuine DNP alongside real results is never
touched. A day of nothing but DNPs is indistinguishable from a grader
that read nothing — and once grading works, days like that stop
appearing, so this script stops having anything to do.

It does NOT decide any outcome. It clears results back to None and marks
the day ungraded; the next pipeline run re-derives every result from
ESPN. A player who genuinely sat comes back DNP again, honestly this
time.

Dry run by default. Pass --apply to write.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
RECORD = ROOT / "data" / "calibration.json"
EASTERN = ZoneInfo("America/New_York")

WNBA_BOARDS = ("wnba_props", "wnba_defense")
MAX_GRADE_DAYS = 21          # mirrors calibration_pipeline.MAX_GRADE_DAYS


def main(apply_changes: bool):
    record = json.loads(RECORD.read_text())
    cutoff = (datetime.now(EASTERN)
              - timedelta(days=MAX_GRADE_DAYS)).strftime("%Y-%m-%d")

    reopened, skipped, picks_recovered = [], [], 0

    for board in WNBA_BOARDS:
        for date_str, entry in sorted((record.get(board) or {}).items()):
            if date_str < cutoff:
                skipped.append((board, date_str, "older than the grading window"))
                continue

            picks = entry.get("picks") or []
            scored = [p for p in picks if p.get("result") in ("hit", "miss")]
            closed = [p for p in picks if p.get("result") == "dnp"]

            if scored:
                # The grader worked on this day. Leave it entirely alone —
                # a real DNP next to real results is a real DNP.
                skipped.append((board, date_str,
                                f"{len(scored)} pick(s) genuinely graded"))
                continue
            if not closed:
                skipped.append((board, date_str, "still open, nothing to reopen"))
                continue

            for p in picks:
                if p.get("result") == "dnp":
                    p["result"] = None
                    picks_recovered += 1
            entry["graded"] = False
            reopened.append((board, date_str, len(closed)))

    for board, date_str, n in reopened:
        print(f"REOPEN  {board:14} {date_str}  {n} pick(s) cleared of a "
              f"DNP no box score ever supported")
    for board, date_str, why in skipped:
        print(f"skip    {board:14} {date_str}  {why}")

    if not reopened:
        print("\nNothing to reopen.")
        return 0

    print(f"\n{picks_recovered} pick(s) across {len(reopened)} board-day(s) "
          f"would return to the record.")
    if not apply_changes:
        print("Dry run — nothing written. Re-run with --apply to commit, "
              "then run the nightly so the pipeline grades them.")
        return 0

    RECORD.write_text(json.dumps(record, indent=2))
    print(f"Written to {RECORD}.")
    print("Commit this, then run the nightly. The grader re-derives every "
          "result from ESPN — anyone who genuinely sat comes back DNP.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
