"""
Calibration — did the picks actually hit?

This is the honesty backstop for every score on the site. Impressions
lie: on a 15-game slate roughly 25 home runs happen, so any list of
high-barrel bats in good parks will "look right" some nights. The only
way to know whether HR Edge, the Daily 13, or anyone else's picks
beat a coin flip is to write down the picks BEFORE the games and
grade them AFTER.

How it works:
  - log_picks(board, date, rows) writes that day's top picks to a
    local JSON file, once per board per day (re-running is idempotent
    — it overwrites the same day's entry rather than duplicating).
  - grade_pending() looks up every logged pick from a past date and
    fills in what actually happened, from MLB's official box-score
    game logs (the same source the trend charts use).
  - summary() reports hit rate by board over the tracked period.

What's graded per board:
  daily13       -> did the batter get >= 1 hit that day
  hr_edge       -> did the batter hit >= 1 home run that day
  potd          -> did the batter record >= 1 extra-base hit
  wnba_props    -> did the player clear the line the board implied
  wnba_defense  -> same, for the defense-matchup top picks

MLB outcomes come from MLB's official stats API; WNBA outcomes from
ESPN's public gamelog endpoint — the same source the WNBA pipeline
already uses, so both halves of the site grade against the data they
were built from.

STORAGE ARCHITECTURE
The app's own filesystem is rebuilt on every deploy, so nothing it
writes is durable. The record therefore lives in the nightly data
archive: the app logs today's picks locally, the pipeline's
calibration step (calibration_pipeline.py) grades them against real
box scores and republishes the merged record inside the next archive,
and the app reads that published record back. Grading in the app
remains available for same-session feedback, but the pipeline is the
source of truth for history.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st

EASTERN = ZoneInfo("America/New_York")
# The app writes picks HERE — inside the same data directory the
# nightly archive unpacks into. That placement is the handoff: the
# pipeline's calibration step reads these picks, grades them against
# real box scores, and republishes the merged record in the next
# archive. The app's own writes are still ephemeral (the container is
# rebuilt on deploy), but they only need to survive until the next
# pipeline run, and the durable record always comes back from the
# archive.
_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# The app's OWN pick log. This MUST NOT be the same file as the
# published record below.
#
# It used to be: _LOG_PATH and _published_path() both resolved to
# app/data/calibration.json, the identical file. Two consequences,
# both bad. (1) _load() read the same file twice and its "merge
# published history with today's local picks" logic was a no-op.
# (2) fetch_data.py extracts the nightly archive straight over
# app/data/, so every deploy overwrote the app's logged picks with the
# archive copy — and the deploy hook fires up to three times a day.
# Picks logged during a slate were destroyed before anything could
# grade them.
_LOG_PATH = _DATA_DIR / "calibration_local.json"
_URL = "https://statsapi.mlb.com/api/v1/people/{pid}/stats"

# Days after which a pick with no box-score line is treated as a real
# DNP rather than a log that hasn't posted yet. MUST match
# calibration_pipeline.FINALIZE_AFTER_DAYS: the pipeline owns published
# history, and if the two grade the same pick differently the merge in
# _load() would flip results depending on which record won. See the long
# note on the constant in calibration_pipeline.py.
FINALIZE_AFTER_DAYS = 3

BOARDS = {
    "daily13": {"sport": "mlb", "label": "Daily 13", "stat": "hits",
                "threshold": 1, "question": "got a hit"},
    "hr_edge": {"sport": "mlb", "label": "HR Edge (top 5)", "stat": "homeRuns",
                "threshold": 1, "question": "hit a home run"},
    # Player of the Day is a HOME RUN play, so it's graded on home
    # runs. Grading it on hits would score it against a goal it isn't
    # trying to achieve — a 0-for-4 with two hard-hit flyouts is a
    # normal night for a power pick, not a model failure.
    # Player of the Day is an EXTRA-BASE HIT play, so it's graded on
    # doubles + triples + home runs. Grading it on hits or homers alone
    # would score it against a goal it isn't trying to achieve.
    "potd": {"sport": "mlb", "label": "Player of the Day", "stat": "xbh",
             "threshold": 1, "question": "recorded an extra-base hit"},
    # WNBA boards grade against a per-pick LINE rather than a fixed
    # threshold — "did he clear the number this board implied" — so the
    # threshold here is a default the pick can override.
    "wnba_props": {"sport": "wnba", "label": "WNBA Props", "stat": "pts",
                   "threshold": 15, "question": "cleared its line"},
    "wnba_defense": {"sport": "wnba", "label": "WNBA Defense Matchup (top 5)",
                     "stat": "pts", "threshold": 15,
                     "question": "cleared its line"},
}


def _published_path():
    """The pipeline's record, as unpacked from the nightly archive.

    precompute.py packs build_data/data as "data", and fetch_data.py
    extracts that into app/, so the pipeline's
    build_data/data/calibration.json arrives here as
    app/data/calibration.json. The app treats this as READ-ONLY and
    keeps its own picks in calibration_local.json alongside it — see
    the _LOG_PATH note above for why sharing one file broke both the
    merge and the picks themselves. _load() merges the two, with the
    more-graded entry winning per day: published history is restored,
    and today's local picks sit alongside it without either clobbering
    the other."""
    return _DATA_DIR / "calibration.json"


def _load():
    """Published record (durable) merged with local picks (today's).

    Per day, the version with more graded picks wins — so a day the
    pipeline has already graded is never overwritten by a local copy
    that only has the picks."""
    merged = {}
    for path in (_published_path(), _LOG_PATH):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        for board, days in (data or {}).items():
            if not isinstance(days, dict):
                continue
            dest = merged.setdefault(board, {})
            for day, entry in days.items():
                prev = dest.get(day)
                if prev is None or _graded_n(entry) >= _graded_n(prev):
                    dest[day] = entry
    return merged


def _graded_n(entry):
    return sum(1 for p in (entry or {}).get("picks", [])
               if p.get("result") in ("hit", "miss"))


def _save(data):
    """Write to the LOCAL pick log only. The published record is
    read-only from the app's perspective — the pipeline owns it.

    `data` is whatever _load() returned, which is the published record
    MERGED with local picks. Writing it back verbatim copied the entire
    published history into calibration_local.json — every day the
    pipeline had ever graded. Two problems. The local file grew without
    bound, and because _load() breaks ties with `>=` and reads local
    second, a local copy carrying the same graded count as the published
    one would win the merge: the app's disposable file shadowing the
    pipeline's source of truth.

    So subtract the published record before writing. Only days the
    published record does not already hold, or holds with FEWER grades,
    stay in the local log — which is exactly what "the app's own picks,
    until the pipeline picks them up" means.
    """
    try:
        published = {}
        try:
            published = json.loads(_published_path().read_text()) or {}
        except Exception:
            published = {}

        local_only = {}
        for board, days in (data or {}).items():
            if not isinstance(days, dict):
                continue
            pub_days = (published.get(board) or {}) if isinstance(published, dict) else {}
            for day, entry in days.items():
                pub = pub_days.get(day)
                if pub is not None and _graded_n(pub) >= _graded_n(entry):
                    continue  # the pipeline already has this day, as good or better
                local_only.setdefault(board, {})[day] = entry

        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG_PATH.write_text(json.dumps(local_only, indent=2))
        return True
    except Exception:
        return False


def log_picks(board: str, rows, date_str: str = None) -> bool:
    """Record today's picks for later grading. rows: [{"id","name",
    "team"}...]. Idempotent per (board, date)."""
    if board not in BOARDS or not rows:
        return False
    date_str = date_str or datetime.now(EASTERN).strftime("%Y-%m-%d")
    data = _load()
    data.setdefault(board, {})

    # ACTUALLY idempotent now. The docstring above always claimed this,
    # but the write below was unconditional: every render of a board
    # replaced that date's entry wholesale, resetting every "result" to
    # None and "graded" to False.
    #
    # Two consequences. Re-opening a page after grading wiped the grades
    # for that day. And with calibration_picks.py logging the same boards
    # from CI, whichever wrote last won — so the record could be the
    # model's real board or a thinner pre-lineup version depending on
    # when someone happened to load the page.
    #
    # First writer for a date wins. That is the honest rule: picks are
    # meant to be locked in BEFORE the games, so a later, better-informed
    # version of the same board is not the pick that was made.
    existing = data[board].get(date_str)
    if existing and existing.get("picks"):
        return True

    data[board][date_str] = {
        "picks": [{"id": r.get("id"), "name": r.get("name"),
                   "team": r.get("team"),
                   # optional per-pick grading target; falls back to the
                   # board default when absent
                   "stat": r.get("stat"), "line": r.get("line"),
                   "result": None}
                  for r in rows if r.get("id")],
        "graded": False,
    }
    return _save(data)


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def _player_day_json(pid: int, date_str: str, season: int) -> str:
    """That player's official box-score line for one date."""
    try:
        resp = requests.get(
            _URL.format(pid=pid),
            params={"stats": "gameLog", "group": "hitting", "season": season},
            timeout=10,
        )
        resp.raise_for_status()
        stats = resp.json().get("stats") or []
        splits = (stats[0].get("splits") if stats else []) or []
    except Exception:
        return json.dumps(None)
    for sp in splits:
        if sp.get("date") == date_str:
            stat = sp.get("stat", {}) or {}
            try:
                doubles = int(stat.get("doubles", 0))
                triples = int(stat.get("triples", 0))
                hrs = int(stat.get("homeRuns", 0))
                return json.dumps({
                    "hits": int(stat.get("hits", 0)),
                    "homeRuns": hrs,
                    # extra-base hits: what the Player of the Day pick
                    # is actually trying to produce
                    "xbh": doubles + triples + hrs,
                })
            except Exception:
                return json.dumps(None)
    return json.dumps(None)


_ESPN_LOG = ("https://site.api.espn.com/apis/common/v3/sports/basketball/wnba/"
             "athletes/{pid}/gamelog")


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def _wnba_day_json(pid, date_str: str) -> str:
    """That player's real box-score line for one date, from ESPN's
    public gamelog endpoint — the same source the WNBA pipeline uses.
    Returns None when he didn't play that day."""
    try:
        resp = requests.get(_ESPN_LOG.format(pid=pid), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return json.dumps(None)

    # ESPN returns a labels array plus per-event stat rows; map by label
    names = [str(n).upper() for n in (data.get("names") or data.get("labels") or [])]
    events = (data.get("events") or {})
    want = date_str.replace("-", "")
    for ev_id, ev in events.items():
        ev_date = str(ev.get("gameDate") or "")[:10].replace("-", "")
        if ev_date != want:
            continue
        stats = ev.get("stats") or []
        if not stats or not names:
            return json.dumps(None)
        row = {}
        for i, label in enumerate(names):
            if i >= len(stats):
                break
            try:
                row[label] = float(stats[i])
            except (TypeError, ValueError):
                continue
        pts = row.get("PTS")
        reb = row.get("REB")
        ast = row.get("AST")
        if pts is None:
            return json.dumps(None)
        return json.dumps({
            "pts": pts, "reb": reb, "ast": ast,
            "pra": (pts or 0) + (reb or 0) + (ast or 0),
        })
    return json.dumps(None)


def grade_pending(max_days: int = 14) -> int:
    """Fill in outcomes for logged picks from past dates. Returns the
    number of newly graded picks. Only grades dates strictly before
    today, so an in-progress slate is never scored."""
    data = _load()
    today = datetime.now(EASTERN).strftime("%Y-%m-%d")
    cutoff = (datetime.now(EASTERN) - timedelta(days=max_days)).strftime("%Y-%m-%d")
    finalize_before = (datetime.now(EASTERN)
                       - timedelta(days=FINALIZE_AFTER_DAYS)).strftime("%Y-%m-%d")
    graded_n = 0
    for board, days in data.items():
        cfg = BOARDS.get(board)
        if not cfg:
            continue
        for date_str, entry in days.items():
            if entry.get("graded") or date_str >= today or date_str < cutoff:
                continue
            season = int(date_str[:4])
            all_done = True
            for pick in entry.get("picks", []):
                if pick.get("result") is not None:
                    continue
                if not pick.get("id"):
                    # no player id to look up — nothing we can ever grade
                    # here, so don't let it hold the day open forever.
                    pick["result"] = "dnp"
                    continue
                try:
                    if cfg.get("sport") == "wnba":
                        box = json.loads(_wnba_day_json(pick["id"], date_str))
                    else:
                        box = json.loads(_player_day_json(int(pick["id"]), date_str, season))
                except Exception:
                    box = None
                if box is None:
                    # No box-score line yet. Official logs for a
                    # completed slate can post hours late, so a None here
                    # usually means "not ready yet", NOT "the player
                    # didn't play". Leave the pick UNGRADED and keep the
                    # day open so the next run retries it. Previously
                    # this marked the pick "dnp" and set the whole day
                    # graded=True, which froze it before the box scores
                    # ever posted — the original cause of ungraded days.
                    #
                    # But "not ready yet" expires. Past
                    # FINALIZE_AFTER_DAYS the logs have long since
                    # posted, so a still-missing line is a genuine DNP;
                    # close it, or a single benched player keeps the day
                    # open forever. Kept in lockstep with
                    # calibration_pipeline.FINALIZE_AFTER_DAYS — the
                    # pipeline is the source of truth for published
                    # history and the two must not disagree.
                    if date_str < finalize_before:
                        pick["result"] = "dnp"
                        graded_n += 1
                    else:
                        all_done = False
                    continue
                stat_key = pick.get("stat") or cfg["stat"]
                target = pick.get("line")
                if target is None:
                    target = cfg["threshold"]
                value = box.get(stat_key)
                if value is None:
                    # We DID get the player's line for that day, and the
                    # graded stat simply isn't in it — that's a real DNP
                    # for this stat, safe to finalize.
                    pick["result"] = "dnp"
                    graded_n += 1
                else:
                    # a "line" of 15.5 means the pick needed MORE
                    # than 15.5; an integer threshold means >=
                    cleared = (value > target if isinstance(target, float)
                               and target % 1 else value >= target)
                    pick["result"] = "hit" if cleared else "miss"
                    graded_n += 1
            entry["graded"] = all_done
    if graded_n:
        _save(data)
    return graded_n


def reopen_recent_days(days_back: int = FINALIZE_AFTER_DAYS) -> int:
    """One-time recovery for days frozen by the old grading bug, which
    marked a day graded=True (and its picks "dnp") before the official
    box scores had posted, so they were never revisited.

    Reopens every day within the last `days_back` days (but strictly
    before today) by clearing its graded flag and resetting any pick
    that was left "dnp" back to ungraded, so the next grade_pending()
    re-checks them against box scores that have since posted. Real
    hit/miss results are left untouched — only stuck DNPs are cleared,
    so a genuine miss is never turned into a win. Returns the number of
    picks reopened. Call grade_pending() right after.

    The window defaults to FINALIZE_AFTER_DAYS, not an arbitrary 5.
    grade_pending() now deliberately closes a missing line as a real DNP
    once that many days have passed, so reopening anything older would
    just undo a considered verdict and hand it straight back to be
    re-closed — a loop, one HTTP request per pick per run. Inside the
    window a DNP is still suspect; outside it, it stands.
    """
    data = _load()
    today = datetime.now(EASTERN).strftime("%Y-%m-%d")
    cutoff = (datetime.now(EASTERN) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    reopened = 0
    for board, days in data.items():
        if board not in BOARDS:
            continue
        for date_str, entry in days.items():
            if date_str >= today or date_str < cutoff:
                continue
            touched = False
            for pick in entry.get("picks", []):
                # Only reset picks that have an id to look up and were
                # left as "dnp" — those are the ones the bug stranded.
                if pick.get("id") and pick.get("result") == "dnp":
                    pick["result"] = None
                    reopened += 1
                    touched = True
            if touched or entry.get("graded"):
                entry["graded"] = False
    if reopened:
        _save(data)
    return reopened


def summary():
    """Per-board record over everything graded so far.

    Reads whatever _load() returns, which is the pipeline-published
    record merged with any picks this container has logged today. The
    pipeline is the source of truth for GRADED history; the app only
    ever adds today's ungraded picks on top."""
    data = _load()
    out = {}
    for board, cfg in BOARDS.items():
        days = data.get(board, {})
        hits = misses = dnp = 0
        dates = []
        for date_str, entry in sorted(days.items()):
            day_hits = sum(1 for p in entry.get("picks", []) if p.get("result") == "hit")
            day_miss = sum(1 for p in entry.get("picks", []) if p.get("result") == "miss")
            day_dnp = sum(1 for p in entry.get("picks", []) if p.get("result") == "dnp")
            if day_hits or day_miss:
                dates.append({"date": date_str, "hits": day_hits,
                              "total": day_hits + day_miss})
            hits += day_hits
            misses += day_miss
            dnp += day_dnp
        total = hits + misses
        out[board] = {
            "label": cfg["label"], "question": cfg["question"],
            "hits": hits, "total": total, "dnp": dnp,
            "rate": round(hits / total * 100, 1) if total else None,
            "days": dates,
        }
    return out
