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
from datetime import datetime, timedelta
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
    "wnba_props": {"sport": "wnba", "stat": "pts", "threshold": None},
    "wnba_defense": {"sport": "wnba", "stat": "pts", "threshold": None},
}

MAX_GRADE_DAYS = 21     # don't chase results older than this
RETENTION_DAYS = 120    # keep roughly a season of history


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


def _wnba_line(pid, date_str):
    try:
        resp = requests.get(ESPN_URL.format(pid=pid), timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    names = [str(n).upper() for n in (data.get("names") or data.get("labels") or [])]
    want = date_str.replace("-", "")
    for _ev_id, ev in (data.get("events") or {}).items():
        if str(ev.get("gameDate") or "")[:10].replace("-", "") != want:
            continue
        stats = ev.get("stats") or []
        if not stats or not names:
            return None
        row = {}
        for i, label in enumerate(names):
            if i >= len(stats):
                break
            try:
                row[label] = float(stats[i])
            except (TypeError, ValueError):
                continue
        pts = row.get("PTS")
        if pts is None:
            return None
        reb, ast = row.get("REB") or 0, row.get("AST") or 0
        return {"pts": pts, "reb": reb, "ast": ast, "pra": pts + reb + ast}
    return None


def grade(record):
    """Fill in outcomes for past-dated picks. Returns count graded."""
    today = datetime.now(EASTERN).strftime("%Y-%m-%d")
    cutoff = (datetime.now(EASTERN) - timedelta(days=MAX_GRADE_DAYS)).strftime("%Y-%m-%d")
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
                if not pid:
                    pick["result"] = "dnp"
                    continue
                line = (_wnba_line(pid, date_str) if cfg["sport"] == "wnba"
                        else _mlb_line(pid, date_str))
                time.sleep(0.12)   # be polite to the public APIs
                if line is None:
                    # didn't play, or no log available — not a miss
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
    graded = grade(record)
    record = prune(record)

    RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECORD_PATH.write_text(json.dumps(record, indent=2))

    summary = summarize(record)
    print(f"Calibration: graded {graded} pick(s) this run.")
    for board, s in summary.items():
        if s["total"]:
            print(f"  {board}: {s['hits']}/{s['total']} ({s['rate']}%)"
                  + (f", {s['dnp']} DNP" if s["dnp"] else ""))
        else:
            print(f"  {board}: nothing graded yet")
    print(f"Calibration: record written to {RECORD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
