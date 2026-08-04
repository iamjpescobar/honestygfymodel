#!/usr/bin/env python3
"""
Nightly calibration — grades yesterday's picks and persists the record.

WHY THIS RUNS IN THE PIPELINE, NOT THE APP
The app writes to a container filesystem that is rebuilt on every
deploy, and the deploy hook fires up to three times a day. Anything
the app records is therefore temporary by construction. The pipeline,
by contrast, publishes a data archive the app downloads — so a
calibration file placed inside that archive survives every redeploy
and reaches every user identically.

THE HANDOFF
  1. The app records each board's picks for the day (cheap, local,
     disposable) and ALSO writes them into the archive directory it
     already unpacks, so the next pipeline run can see them.
  2. This script reads whatever picks exist, grades any from a past
     date against real box scores, merges them into the durable
     record, and writes it back into the archive being built.
  3. The app reads the durable record for display and never needs to
     write anything permanent.

If picks for a day never made it across (the app was idle, or a deploy
landed mid-slate), that day is simply absent — the record shows what it
actually observed rather than inventing coverage.

Sources: MLB's official stats API for baseball outcomes, ESPN's public
gamelog for WNBA — the same sources the app itself grades against.
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")

# Where the pipeline stages files that get packed into the archive.
BUILD_DATA = Path("build_data") / "data"
RECORD_PATH = BUILD_DATA / "calibration.json"

# Where a previously published record would have been unpacked, if the
# workflow restored it. Both are checked so the record accumulates
# across runs instead of resetting.
EXISTING_PATHS = [
    Path("app") / "data" / "calibration.json",
    Path("data") / "calibration.json",
    RECORD_PATH,
]

MLB_URL = "https://statsapi.mlb.com/api/v1/people/{pid}/stats"
ESPN_URL = ("https://site.api.espn.com/apis/common/v3/sports/basketball/wnba/"
            "athletes/{pid}/gamelog")

BOARDS = {
    "daily13": {"sport": "mlb", "stat": "hits", "threshold": 1},
    "hr_edge": {"sport": "mlb", "stat": "homeRuns", "threshold": 1},
    "potd": {"sport": "mlb", "stat": "xbh", "threshold": 1},
    # Pitcher strikeouts. sport "mlb_pitching" routes to a different
    # Stats API stat GROUP — asking for group=hitting on a pitcher
    # returns his at-bats, not his Ks. threshold None because each pick
    # carries its own projected line to clear.
    "k_board": {"sport": "mlb_pitching", "stat": "strikeOuts", "threshold": None},
    "wnba_props": {"sport": "wnba", "stat": "pts", "threshold": None},
    "wnba_defense": {"sport": "wnba", "stat": "pts", "threshold": None},
}

def has_id(value) -> bool:
    """True when `value` is a usable player id.

    NOT a truthiness check. Every id filter in the calibration path used
    to read `if r.get("id")`, which silently discards the id 0 — and 0 is
    a perfectly ordinary integer, indistinguishable from a real id
    everywhere except in a boolean test. Nothing in the record would show
    the pick had been dropped; it would simply never appear, and the
    board's denominator would be quietly short.

    MLB and ESPN do not currently issue an id of 0, so this has never
    fired. That is exactly what makes it worth removing: a filter that is
    wrong but never triggers is one upstream change away from silently
    eating picks, and the symptom (a board a little thinner than it
    should be) looks like nothing at all.

    An empty or whitespace-only string is still rejected — that is a
    missing id rather than a real one, and str(0) is "0", so the integer
    survives.
    """
    return value is not None and str(value).strip() != ""

    # Standalone copy: this script runs on a bare CI runner with no
    # app/ on sys.path, so it cannot import the twin in
    # app/engines/calibration.py. Keep the two identical — the graders
    # disagreeing is what poisoned the record before.


MAX_GRADE_DAYS = 21     # don't chase results older than this
RETENTION_DAYS = 120    # keep roughly a season of history

# When a pick has NO box-score line, that means one of two things and
# the API can't tell us which: the official log hasn't posted yet, or
# the player genuinely didn't play (scratched, benched, sent down).
#
# Treating "no line" as not-ready-yet is right for a few hours and wrong
# forever after. It left days permanently open: a benched player never
# gets a line, so `all(result is not None)` never became True, the day
# was re-fetched on every run for MAX_GRADE_DAYS, and then aged out of
# the grading window still ungraded — its real hits and misses sitting
# in the file, counted by summarize() while the day itself never closed.
#
# MLB and ESPN both publish official logs within hours of a final. Three
# days is far past any plausible delay, so past that point "no line"
# means the player did not play, and we finalize it as a genuine DNP.
# DNPs are reported separately and excluded from the hit-rate
# denominator, so this never flatters or penalises the model — it just
# stops the day hanging open forever.
FINALIZE_AFTER_DAYS = 3


def _load_existing():
    """Merge every record we can find, newest value winning per day."""
    merged = {}
    for p in EXISTING_PATHS:
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        for board, days in (data or {}).items():
            if not isinstance(days, dict):
                continue
            dest = merged.setdefault(board, {})
            for day, entry in days.items():
                prev = dest.get(day)
                # prefer the version that has more graded picks
                if prev is None or _graded_count(entry) >= _graded_count(prev):
                    dest[day] = entry
    return merged


def _graded_count(entry):
    return sum(1 for p in (entry or {}).get("picks", [])
               if p.get("result") in ("hit", "miss"))


def _mlb_line(pid, date_str):
    season = int(date_str[:4])
    try:
        resp = requests.get(MLB_URL.format(pid=pid),
                            params={"stats": "gameLog", "group": "hitting",
                                    "season": season},
                            timeout=15)
        resp.raise_for_status()
        stats = resp.json().get("stats") or []
        splits = (stats[0].get("splits") if stats else []) or []
    except Exception:
        return None
    for sp in splits:
        if sp.get("date") == date_str:
            stat = sp.get("stat", {}) or {}
            try:
                doubles = int(stat.get("doubles", 0))
                triples = int(stat.get("triples", 0))
                hrs = int(stat.get("homeRuns", 0))
                return {"hits": int(stat.get("hits", 0)), "homeRuns": hrs,
                        "xbh": doubles + triples + hrs}
            except Exception:
                return None
    return None


def _mlb_pitching_line(pid, date_str):
    """That pitcher's line for one date, or None if he didn't appear.

    Separate from _mlb_line because the Stats API splits hitting and
    pitching into different stat GROUPS — asking for group=hitting on a
    pitcher returns his (meaningless) at-bats, not his strikeouts. The
    Strikeout Board projects Ks for every probable starter and nothing
    ever checked those projections against what actually happened, so
    the board had no accountability at all.
    """
    season = int(date_str[:4])
    try:
        resp = requests.get(MLB_URL.format(pid=pid),
                            params={"stats": "gameLog", "group": "pitching",
                                    "season": season},
                            timeout=15)
        resp.raise_for_status()
        stats = resp.json().get("stats") or []
        splits = (stats[0].get("splits") if stats else []) or []
    except Exception:
        return None
    for sp in splits:
        if sp.get("date") == date_str:
            stat = sp.get("stat", {}) or {}
            try:
                return {"strikeOuts": int(stat.get("strikeOuts", 0))}
            except Exception:
                return None
    return None


# ----------------------------------------------------------------------
# ESPN gives gameDate in UTC. The picks are logged under the ET slate
# date. Those are the same calendar day only for tips before 8 PM ET.
#
#   7:00 PM ET  -> 23:00Z  same day     matched
#   8:00 PM ET  -> 00:00Z  NEXT day     never matched
#   10:00 PM ET -> 02:00Z  NEXT day     never matched
#
# The old comparison took gameDate[:10] raw, so every evening game — most
# of the WNBA schedule, and all of the West Coast slate — fell through to
# "no event matching the date" and the pick was closed as a DNP three
# days later. DNPs are excluded from the hit-rate denominator, so this
# removed picks from the record without ever reporting a failure.
#
# The fixture in tests/test_wnba_grading_honesty.py used T23:00Z, which
# is 7 PM ET — the one tip time on the schedule where the two dates
# agree. The parse was covered; the date match never was.
#
# MUST STAY BYTE-IDENTICAL between calibration_pipeline.py and
# app/engines/calibration.py. The two graders disagreed once before and
# it poisoned the record.
# ----------------------------------------------------------------------
def _espn_slate_date(raw) -> str:
    """ESPN's UTC gameDate as the ET calendar date a pick was logged under."""
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        # Unparseable: fall back to the old raw prefix rather than
        # matching nothing, so a shape change can never do WORSE than
        # the behaviour this replaced.
        return s[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EASTERN).strftime("%Y-%m-%d")


# ----------------------------------------------------------------------
# WNBA GRADING DIAGNOSTICS
#
# _wnba_line returns None for four completely different reasons — the
# request failed, the gamelog holds no event on that date, the event
# carries no stats, or PTS didn't parse — and grade() treats all four
# identically: leave the pick open, then close it as "dnp" once
# FINALIZE_AFTER_DAYS has passed. DNPs are excluded from the hit-rate
# denominator, so a grader that never reads a single line does not show
# up as a failure anywhere. The board reports "tracked" and measures
# nothing, and the picks quietly age out three days at a time.
#
# That is exactly the state the record is in: 45 WNBA picks logged
# across three days, every result still None, none ever graded. So this
# records WHICH of the four happened, and main() prints the tally. One
# nightly run then names the cause instead of another day of silence.
#
# Counting only — the parse below is unchanged, and must stay
# byte-identical to app/engines/calibration._wnba_day_json (see
# tests/test_wnba_grading_honesty.py, which pins both to the same
# behaviour on the same inputs). The app grader gets no diagnostics
# because nobody reads a Render log looking for them; this one runs in
# CI, where the log is the whole point.
# ----------------------------------------------------------------------
_WNBA_DIAG = {"reasons": {}, "samples": [], "ok": 0}


def _wnba_diag(reason, detail=None):
    """Record why a line couldn't be read, and return None as before."""
    _WNBA_DIAG["reasons"][reason] = _WNBA_DIAG["reasons"].get(reason, 0) + 1
    if detail and len(_WNBA_DIAG["samples"]) < 3:
        _WNBA_DIAG["samples"].append(f"{reason} -> {detail}")
    return None


def report_wnba_diagnostics():
    """Print the tally. Called from main() after grading."""
    failed = sum(_WNBA_DIAG["reasons"].values())
    total = failed + _WNBA_DIAG["ok"]
    if not total:
        return
    print(f"\n[verify-wnba] read {_WNBA_DIAG['ok']}/{total} box-score lines.")
    for reason, n in sorted(_WNBA_DIAG["reasons"].items(), key=lambda x: -x[1]):
        print(f"[verify-wnba]   {n:4d}  {reason}")
    for sample in _WNBA_DIAG["samples"]:
        print(f"[verify-wnba]   sample: {sample}")
    if failed and not _WNBA_DIAG["ok"]:
        # Loud on purpose. This is the case that looks like nothing.
        print(f"[verify-wnba] NOT ONE line was read this run. Every WNBA pick "
              f"stays ungraded and closes as DNP after {FINALIZE_AFTER_DAYS} "
              f"days, which removes it from the record without ever "
              f"reporting a failure. The reason above is the bug.")
    print("")


def _wnba_line(pid, date_str):
    try:
        resp = requests.get(ESPN_URL.format(pid=pid), timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        # getattr, not resp.status_code: `resp` may not exist (the
        # request itself failed), and the test stub in
        # tests/test_wnba_grading_honesty.py deliberately implements only
        # raise_for_status() and json(). Reaching for an attribute it
        # doesn't have would break the one test pinning this parse.
        _status = getattr(locals().get("resp"), "status_code", "?")
        return _wnba_diag(f"request failed ({type(exc).__name__}, HTTP {_status})",
                          f"pid={pid} {str(exc)[:160]}")
    if not isinstance(data, dict):
        return _wnba_diag("gamelog response was not an object",
                          f"pid={pid} type={type(data).__name__}")
    names = [str(n).upper() for n in (data.get("names") or data.get("labels") or [])]
    want = date_str
    _seen = []
    for _ev_id, ev in (data.get("events") or {}).items():
        _gd = _espn_slate_date(ev.get("gameDate"))
        _seen.append(_gd)
        if _gd != want:
            continue
        stats = ev.get("stats") or []
        if not stats or not names:
            return _wnba_diag(
                "matched the date but the event had no stats or no labels",
                f"pid={pid} labels={names[:10]} stats={list(stats)[:10]}")
        row = {}
        raw = {}
        for i, label in enumerate(names):
            if i >= len(stats):
                break
            # Keep the RAW value alongside the parsed float. Combo
            # labels like 3PT/FG/FT are "made-attempted" strings that
            # float() cannot handle, and the `continue` below drops
            # them from `row` entirely.
            raw[label] = stats[i]
            try:
                row[label] = float(stats[i])
            except (TypeError, ValueError):
                continue
        pts = row.get("PTS")
        if pts is None:
            # The labels are the diagnostic here: if PTS isn't among them
            # the response shape has changed, and if it is, the value
            # didn't survive float().
            return _wnba_diag("event found but PTS did not parse",
                              f"pid={pid} labels={names[:12]} "
                              f"raw={dict(list(raw.items())[:6])}")
        # NO `or 0` ON REB/AST — see the matching note in
        # app/engines/calibration.py.
        #
        # This read `row.get("REB") or 0`, which reported an unparsed
        # rebound total as a measured zero AND folded it into PRA. This
        # file is the SOURCE OF TRUTH for published history, so a
        # fabricated component here propagates into the record the app
        # reads back and into every accuracy number shown on the
        # Calibration page.
        #
        # grade() below already sets result="dnp" when `value is None`,
        # which drops the pick from the win/loss record instead of
        # scoring it against a total we couldn't actually measure. The
        # two graders must stay identical — they disagreed once before
        # and it poisoned the record.
        reb, ast = row.get("REB"), row.get("AST")
        # THREES ARRIVE AS A MADE-ATTEMPTED STRING ("5-11"), NOT A NUMBER.
        # float() therefore fails on the 3PT label and the `continue`
        # above silently drops it, so `tpm` was missing from every line
        # this parser produced. grade() reads `line.get("tpm")`, got
        # None, and closed every 3PM pick as a DNP — the market could
        # never accumulate a record no matter how many picks were logged.
        #
        # wnba_precompute.py already solved this with _made_att: split on
        # the dash, take the made half. Same rule here, and it must stay
        # BYTE-IDENTICAL between this file and its twin — the two graders
        # disagreed once before and it poisoned the record.
        tpm = None
        _tpt = raw.get("3PT")
        if _tpt is not None:
            _parts = str(_tpt).split("-")
            if len(_parts) == 2:
                try:
                    tpm = float(_parts[0])
                except (TypeError, ValueError):
                    tpm = None
        pra = (pts + reb + ast
               if reb is not None and ast is not None else None)
        _WNBA_DIAG["ok"] += 1
        return {"pts": pts, "reb": reb, "ast": ast, "pra": pra, "tpm": tpm}
    # No event on that date. The sample below is the highest-value line
    # in the whole report: the top-level keys tell you whether this is
    # even a gamelog (an error page or a rate-limit body has neither
    # "events" nor "names"), and the dates tell you whether the player's
    # log is real but the date format or timezone doesn't line up.
    return _wnba_diag(
        "no event matching the date" if _seen else "gamelog contained no events",
        f"pid={pid} want={want} saw={_seen[:6]} events={len(_seen)} "
        f"labels={names[:8]} top_keys={sorted(data.keys())[:8]}")


def grade(record):
    """Fill in outcomes for past-dated picks. Returns count graded."""
    today = datetime.now(EASTERN).strftime("%Y-%m-%d")
    cutoff = (datetime.now(EASTERN) - timedelta(days=MAX_GRADE_DAYS)).strftime("%Y-%m-%d")
    # Dates strictly older than this have had ample time for official
    # logs to post, so a missing line is a real DNP rather than a
    # not-ready-yet. See FINALIZE_AFTER_DAYS.
    finalize_before = (datetime.now(EASTERN)
                       - timedelta(days=FINALIZE_AFTER_DAYS)).strftime("%Y-%m-%d")
    graded = 0

    for board, days in record.items():
        cfg = BOARDS.get(board)
        if not cfg:
            continue
        for date_str, entry in sorted(days.items()):
            # never grade an in-progress or future slate
            if date_str >= today or date_str < cutoff:
                continue
            for pick in entry.get("picks", []):
                if pick.get("result") in ("hit", "miss", "dnp"):
                    continue
                pid = pick.get("id")
                if not has_id(pid):
                    pick["result"] = "dnp"
                    continue
                if cfg["sport"] == "wnba":
                    line = _wnba_line(pid, date_str)
                elif cfg["sport"] == "mlb_pitching":
                    line = _mlb_pitching_line(pid, date_str)
                else:
                    line = _mlb_line(pid, date_str)
                time.sleep(0.12)   # be polite to the public APIs
                if line is None:
                    # NO BOX-SCORE LINE YET — leave this pick UNGRADED.
                    #
                    # This used to set result="dnp", which combined with
                    # the entry["graded"] = all(result is not None) line
                    # below to freeze the whole day permanently: the
                    # `if pick.get("result") in ("hit","miss","dnp")`
                    # skip at the top of this loop then meant no later
                    # run ever revisited it. A single slow-posting game
                    # log — or one timed-out request in this sequential
                    # loop — buried the entire day's picks as DNPs that
                    # could never be recovered. That is the cause of the
                    # ungraded days.
                    #
                    # app/engines/calibration.py was already fixed for
                    # exactly this; the pipeline (which is the SOURCE OF
                    # TRUTH for published history) never got the fix, so
                    # it kept re-poisoning the record the app reads back.
                    #
                    # None here means "not ready yet" far more often than
                    # it means "didn't play" — but only for the first few
                    # days. Past FINALIZE_AFTER_DAYS the logs have long
                    # since posted, so a still-missing line is a real
                    # DNP and we close it rather than leaving the day
                    # open forever. See the constant for the full why.
                    if date_str < finalize_before:
                        pick["result"] = "dnp"
                    continue
                stat_key = pick.get("stat") or cfg["stat"]
                target = pick.get("line")
                if target is None:
                    target = cfg["threshold"]
                value = line.get(stat_key)
                if value is None or target is None:
                    pick["result"] = "dnp"
                    continue
                cleared = (value > target if isinstance(target, float) and target % 1
                           else value >= target)
                pick["result"] = "hit" if cleared else "miss"
                graded += 1
            entry["graded"] = all(
                p.get("result") is not None for p in entry.get("picks", []))
    return graded


def reopen_stuck(record, days_back: int = FINALIZE_AFTER_DAYS) -> int:
    """Reopen picks that were closed as "dnp" before their box score had
    a fair chance to post.

    SCOPE MATTERS HERE. This used to reopen every "dnp" in the last 10
    days on every run. Now that grade() deliberately finalizes a missing
    line as a genuine DNP after FINALIZE_AFTER_DAYS, a 10-day window
    would reopen those same legitimate DNPs on the very next run, grade()
    would re-close them, and the two would fight forever — one HTTP
    request plus a 0.12s sleep per pick per run, permanently. The WNBA
    boards were the worst case: their pipeline threshold is None, so
    every pick without an explicit line closes as DNP immediately.

    So the window is exactly the pending window. Inside it, a "dnp" is
    suspect (that's where the old freeze bug wrote them, and where a
    log may simply not have posted yet) and gets another look. Outside
    it, a "dnp" is grade()'s considered verdict and is left alone.

    Deliberately conservative either way: real "hit"/"miss" results are
    never touched, so a genuine miss can't be laundered into a win.
    """
    today = datetime.now(EASTERN).strftime("%Y-%m-%d")
    cutoff = (datetime.now(EASTERN) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    reopened = 0
    for board, days in record.items():
        if board not in BOARDS:
            continue
        for date_str, entry in days.items():
            if date_str >= today or date_str < cutoff:
                continue
            touched = False
            for pick in entry.get("picks", []):
                if has_id(pick.get("id")) and pick.get("result") == "dnp":
                    pick["result"] = None
                    reopened += 1
                    touched = True
            if touched or entry.get("graded"):
                entry["graded"] = False
    return reopened


def prune(record):
    """Drop days older than the retention window."""
    keep_after = (datetime.now(EASTERN) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    for board in list(record.keys()):
        for day in list(record[board].keys()):
            if day < keep_after:
                del record[board][day]
        if not record[board]:
            del record[board]
    return record


def summarize(record):
    out = {}
    for board in BOARDS:
        hits = misses = dnp = 0
        for _day, entry in (record.get(board) or {}).items():
            for p in entry.get("picks", []):
                if p.get("result") == "hit":
                    hits += 1
                elif p.get("result") == "miss":
                    misses += 1
                elif p.get("result") == "dnp":
                    dnp += 1
        total = hits + misses
        out[board] = {"hits": hits, "total": total, "dnp": dnp,
                      "rate": round(hits / total * 100, 1) if total else None}
    return out


def main():
    record = _load_existing()
    if not record:
        print("Calibration: no picks recorded yet — writing an empty record "
              "so the app has something valid to read.")
    reopened = reopen_stuck(record)
    if reopened:
        print(f"Calibration: reopened {reopened} pick(s) stranded as DNP by the "
              f"freeze bug — re-grading them against box scores that have "
              f"since posted.")
    graded = grade(record)
    # Printed BEFORE the per-board summary below, because the summary is
    # what makes this invisible: a board with zero graded picks prints
    # "nothing graded yet", which reads as "no picks yet" rather than
    # "the grader failed on all of them".
    report_wnba_diagnostics()
    record = prune(record)

    RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECORD_PATH.write_text(json.dumps(record, indent=2))

    # ALSO write back to the repo-committed copy, and commit it in the
    # workflow. Without this, grades evaporate every night: RECORD_PATH
    # lives under build_data/, which is rebuilt from scratch on each CI
    # runner and only ever leaves as a release asset. _load_existing()
    # reads local paths only, so tomorrow's run would start from
    # data/calibration.json — which calibration_picks.py fills with
    # UNGRADED picks — and every result graded tonight would be gone.
    #
    # Writing both makes the loop closed and durable:
    #   slate-picks.yml  -> commits today's picks to data/calibration.json
    #   nightly pipeline -> grades them, writes back here AND to the
    #                       archive the app reads
    # The repo copy is the persistent record; the archive is the app's
    # read-only view of it.
    REPO_RECORD = Path(__file__).resolve().parent / "data" / "calibration.json"
    REPO_RECORD.parent.mkdir(parents=True, exist_ok=True)
    REPO_RECORD.write_text(json.dumps(record, indent=2))

    summary = summarize(record)
    print(f"Calibration: graded {graded} pick(s) this run.")
    for board, s in summary.items():
        if s["total"]:
            print(f"  {board}: {s['hits']}/{s['total']} ({s['rate']}%)"
                  + (f", {s['dnp']} DNP" if s["dnp"] else ""))
        else:
            print(f"  {board}: nothing graded yet")
    print(f"Calibration: record written to {RECORD_PATH} and {REPO_RECORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
