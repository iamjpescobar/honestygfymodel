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
                "threshold": 1, "question": "got a hit",
                # Which measured league rate this board must BEAT to be
                # worth anything. Without it, "65% got a hit" reads as a
                # strong result when the league-average starter does
                # roughly the same — see build_baselines in precompute.py.
                "baseline_stat": "hits"},
    "hr_edge": {"sport": "mlb", "label": "HR Edge (top 5)", "stat": "homeRuns",
                "threshold": 1, "question": "hit a home run",
                "baseline_stat": "homeRuns"},
    # Player of the Day is an EXTRA-BASE HIT play, so it's graded on
    # doubles + triples + home runs. Grading it on hits or homers alone
    # would score it against a goal it isn't trying to achieve.
    "potd": {"sport": "mlb", "label": "Player of the Day", "stat": "xbh",
             "threshold": 1, "question": "recorded an extra-base hit",
             "baseline_stat": "xbh"},
    # No baseline_stat: this board is graded against ITS OWN published
    # projection, not a league rate. "Did he beat the number we printed"
    # has no league-average equivalent, and inventing one would be worse
    # than showing none.
    "k_board": {"sport": "mlb_pitching", "label": "Strikeout Board (top 5)",
                "stat": "strikeOuts", "threshold": None,
                "question": "cleared this board's projected strikeouts"},
    # WNBA boards grade against a per-pick LINE rather than a fixed
    # threshold — "did he clear the number this board implied".
    #
    # threshold is None, matching calibration_pipeline.BOARDS exactly.
    # It used to be 15 here and None there, so the same pick graded
    # differently depending on which file evaluated it — and the
    # pipeline is the source of truth for published history, so the
    # app was the one showing the wrong answer.
    #
    # None rather than 15 on purpose. A pick that arrives without a line
    # is a pick this board never actually published a number for, and
    # scoring it against an invented 15 would grade a claim the site
    # never made. It closes as DNP instead, which is excluded from the
    # hit-rate denominator and so neither flatters nor penalises the
    # model. Same standard as everything else here: no placeholders.
    "wnba_props": {"sport": "wnba", "label": "WNBA Props", "stat": "pts",
                   "threshold": None, "question": "cleared its line"},
    "wnba_defense": {"sport": "wnba", "label": "WNBA Defense Matchup (top 5)",
                     "stat": "pts", "threshold": None,
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


def _repo_path():
    """The record CI commits back to the REPOSITORY.

    This is the file .github/workflows/slate-picks.yml writes at 1, 5 and
    7 PM ET, and it is a different file from _published_path() — that one
    only changes when the nightly archive is rebuilt at 6 AM ET.

    Nothing in the app read this until now, and the consequence was
    invisible rather than loud: today's picks were logged by CI, committed,
    and then not seen by the site until the NEXT morning's archive carried
    them back. The only way today's board appeared on the site at all was
    log_picks() firing as a side effect of somebody opening that board's
    page — which is the exact "no visitor, no picks" failure
    calibration_picks.py was written to eliminate on the CI side.

    Render checks out the whole repository, so this resolves in production;
    app/ is the service root, not the checkout root.
    """
    return Path(__file__).resolve().parents[2] / "data" / "calibration.json"


def _load():
    """Published record (durable) merged with local picks (today's), then
    backfilled from the CI-committed repo record.

    Per day, the version with more graded picks wins — so a day the
    pipeline has already graded is never overwritten by a local copy
    that only has the picks.

    The repo record is applied LAST and FILL-ONLY: it supplies (board, day)
    entries the first two sources don't have at all, and never replaces one
    they do. That is deliberate rather than lazy. Its job here is today's
    board, which by definition nothing else holds yet; graded history is
    owned by the pipeline, and letting a third file overwrite an already
    graded day would reintroduce exactly the "which record wins" ambiguity
    the _LOG_PATH split was created to end. It also keeps hand-entered odds
    safe, since those live only in the local log.
    """
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

    try:
        repo = json.loads(_repo_path().read_text())
    except Exception:
        repo = None
    for board, days in (repo or {}).items():
        if not isinstance(days, dict):
            continue
        dest = merged.setdefault(board, {})
        for day, entry in days.items():
            dest.setdefault(day, entry)

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
                    # The pipeline already has this day graded as well or
                    # better — EXCEPT if we hold odds it doesn't.
                    #
                    # Odds are entered by hand here and the pipeline never
                    # writes them, so dropping the day on grade-count
                    # alone silently threw every price away the moment it
                    # was typed: set_odds returned True, the number
                    # vanished, and the profit columns stayed empty with
                    # no error anywhere.
                    _pub_odds = {str(x.get("id")): x.get("odds")
                                 for x in (pub.get("picks") or [])}
                    _has_new_odds = any(
                        x.get("odds") is not None
                        and _pub_odds.get(str(x.get("id"))) != x.get("odds")
                        for x in (entry.get("picks") or [])
                    )
                    if not _has_new_odds:
                        continue
                local_only.setdefault(board, {})[day] = entry

        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG_PATH.write_text(json.dumps(local_only, indent=2))
        return True
    except Exception:
        return False


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
    # FIRST WRITER WINS PER MARKET, NOT PER DAY.
    #
    # This used to bail out the moment a date had any picks at all. On a
    # single-market board that is exactly right, and it stays right —
    # MLB picks carry stat=None, so the first write claims None and
    # every later write for that day is still refused.
    #
    # But WNBA Props publishes five markets (points, rebounds, assists,
    # PRA, threes) under one board key, and each is logged by a separate
    # call. Under the old rule whichever market happened to be built
    # first claimed the day and the other four were dropped in silence.
    # Four of five markets therefore had NO record at all, however many
    # nights ran — the board looked tracked while 80% of what it
    # published went unmeasured.
    #
    # Keying on (board, date, stat) keeps the honest part of the old
    # rule — a later, better-informed version of a market you already
    # recorded is not the pick that was made, so it is still refused —
    # while letting a market nobody has logged yet be added to the same
    # day.
    entry = data[board].get(date_str)
    if entry is None:
        entry = {"picks": [], "graded": False}
        data[board][date_str] = entry

    logged_markets = {p.get("stat") for p in entry.get("picks", [])}
    fresh = [r for r in rows
             if has_id(r.get("id")) and r.get("stat") not in logged_markets]
    if not fresh:
        return True

    entry.setdefault("picks", []).extend(
        {"id": r.get("id"), "name": r.get("name"),
         "team": r.get("team"),
         # optional per-pick grading target; falls back to the
         # board default when absent
         "stat": r.get("stat"), "line": r.get("line"),
         # American odds for this pick, e.g. -180 or +320.
         # Optional and usually absent at log time: nothing
         # here has a sportsbook feed, so this is filled in by
         # the user on the Calibration page with the price they
         # ACTUALLY got. That is better data than a scraped
         # consensus would be, and it is the only thing that
         # turns a hit rate into a profit figure.
         "odds": r.get("odds"),
         "result": None}
        for r in fresh)

    # Adding a market reopens the day. grade_pending() skips any entry
    # already flagged graded, so without this a market logged after an
    # earlier grading pass would sit ungraded forever.
    entry["graded"] = False
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
        reb = row.get("REB")
        ast = row.get("AST")
        if pts is None:
            return json.dumps(None)
        # PRA IS None UNLESS ALL THREE COMPONENTS PARSED.
        #
        # This was `(pts or 0) + (reb or 0) + (ast or 0)`, which turns a
        # component ESPN didn't return — a label missing from `names`, a
        # value that failed the float() above and hit the `continue` —
        # into a real zero. The sum then looks like a measured PRA and is
        # graded as one, understated, against a pick that may well have
        # hit. A rebound we couldn't read is not zero rebounds.
        #
        # grade_pending() already treats a None outcome as "dnp" and
        # leaves it out of the win/loss record, so returning None here
        # excludes the pick instead of scoring it wrong. Calibration is
        # the number that proves the model — it is the last place in this
        # app that should be averaging in a fabricated result.
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
        return json.dumps({
            "pts": pts, "reb": reb, "ast": ast, "pra": pra, "tpm": tpm,
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
                if not has_id(pick.get("id")):
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
                if value is None or target is None:
                    # We DID get the player's line for that day, and the
                    # graded stat simply isn't in it — that's a real DNP
                    # for this stat, safe to finalize.
                    #
                    # `target is None` is the same guard
                    # calibration_pipeline.grade() has always had, and
                    # this function was missing. On a board whose
                    # threshold is None (every board that grades against
                    # its own published number), a pick that arrived
                    # without a line reached the comparison below and
                    # evaluated `value >= None` — TypeError, not a bad
                    # grade. It never fired only because the WNBA
                    # thresholds here were a hardcoded 15 that the
                    # pipeline didn't share; removing that invented
                    # number exposes the missing guard.
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
                if has_id(pick.get("id")) and pick.get("result") == "dnp":
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
        rate = round(hits / total * 100, 1) if total else None

        # BASELINE COMPARISON — the number that decides whether any of
        # this is worth anything.
        #
        # A hit rate on its own is not evidence of skill. The
        # league-average starter gets a hit about two nights in three, so
        # a board reporting "65% got a hit" may be doing nothing at all.
        # Reporting the rate without the baseline beside it is how a tool
        # like this manufactures false confidence, and people bet real
        # money on that.
        # Profit across every graded pick that carries a price. Separate
        # from the hit rate on purpose — they answer different questions,
        # and the hit rate is the one that misleads.
        _all_picks = [pk for entry in days.values() for pk in entry.get("picks", [])]
        profit = _profit_summary(_all_picks)

        base = _baseline_for(cfg.get("baseline_stat"))
        edge = round(rate - base, 1) if (rate is not None and base is not None) else None
        out[board] = {
            "label": cfg["label"], "question": cfg["question"],
            "hits": hits, "total": total, "dnp": dnp,
            "rate": rate,
            "days": dates,
            "baseline": base,
            "edge": edge,
            # Is the gap real, or is the sample just small? See
            # _edge_verdict — with a few dozen picks the honest answer is
            # almost always "too early to tell", and saying so is the
            # whole point.
            "verdict": _edge_verdict(hits, total, base),
            "profit": profit,
        }
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _baselines():
    """League baselines measured by precompute.build_baselines.

    Returns {} when the nightly hasn't shipped them yet — callers then
    show no comparison rather than inventing one.
    """
    try:
        path = _DATA_DIR / "statcast" / "baselines.json"
        return json.loads(path.read_text()) or {}
    except Exception:
        return {}


def _baseline_for(stat):
    if not stat:
        return None
    v = _baselines().get(stat)
    return float(v) if isinstance(v, (int, float)) else None


def set_odds(board: str, date_str: str, pid, odds, stat=None) -> bool:
    """Attach the price you actually got to one already-logged pick.

    Written separately from log_picks because odds are not known when a
    pick is made — the board is built in the morning and priced when you
    bet it. Nothing here has a sportsbook feed, and inventing a consensus
    price would defeat the purpose: what matters for YOUR profit is the
    number YOU took.

    Editing odds never touches `result`. A graded pick keeps its grade;
    only the price changes, so back-filling prices on old picks is safe
    and does not reopen anything.
    """
    data = _load()
    entry = (data.get(board) or {}).get(date_str)
    if not entry:
        return False
    hit = False
    for pk in entry.get("picks", []):
        if str(pk.get("id")) != str(pid):
            continue
        # MATCH ON THE MARKET TOO, once a `stat` is supplied.
        #
        # A day used to hold one market per board, so a player id was a
        # unique handle. It no longer is: the same player can carry a
        # points pick AND a rebounds pick on the same night, at
        # completely different prices. Matching on id alone wrote one
        # price onto both, quietly inventing a number for the market
        # that was never priced and corrupting its ROI.
        #
        # stat stays optional so existing single-market callers keep
        # working unchanged.
        if stat is not None and pk.get("stat") != stat:
            continue
        try:
            pk["odds"] = int(odds) if odds not in (None, "", 0) else None
        except (TypeError, ValueError):
            return False
        hit = True
    return _save(data) if hit else False


def american_to_decimal(odds):
    """American odds -> decimal payout multiplier. None if unusable.

    -180 means risk 180 to win 100, so a winning unit returns 1.556.
    +320 means risk 100 to win 320, so it returns 4.20.
    """
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return 1.0 + (100.0 / abs(o) if o < 0 else o / 100.0)


def implied_pct(odds):
    """What the BOOK thinks the chance is, from its price, as a percent.

    Includes the vig, so these sum to more than 100% across a market.
    That's fine for the purpose here: the book's price is the bar a pick
    has to clear, vig included, because the vig is a cost you actually
    pay.
    """
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return round((abs(o) / (abs(o) + 100) if o < 0 else 100 / (o + 100)) * 100, 1)


def breakeven_pct(odds):
    """The hit rate a price REQUIRES just to break even, as a percent.

    This is the number that decides whether a board is worth betting, and
    it is the one nobody looks at. A 65% hit rate sounds excellent and
    loses money all season at -200, which needs 66.7%. Reporting a rate
    without its break-even is how a tool like this quietly costs someone
    money while showing them a good-looking number.
    """
    dec = american_to_decimal(odds)
    if dec is None or dec <= 1:
        return None
    return round(100.0 / dec, 1)


def _profit_summary(picks):
    """Units won/lost across graded picks that carry a price.

    Flat 1 unit risked per pick — the only assumption here, and stated
    plainly rather than buried, because we do not know what anyone
    actually staked.

    Picks with no odds are EXCLUDED rather than assumed to be even money.
    Assuming a price would manufacture a profit figure out of nothing,
    which is worse than reporting that fewer picks have prices attached.
    DNPs are excluded too: a scratched player is a returned stake, not a
    loss.
    """
    staked = 0.0
    returned = 0.0
    priced = 0
    wins = 0
    be_sum = 0.0
    for p in picks:
        res = p.get("result")
        if res not in ("hit", "miss"):
            continue
        dec = american_to_decimal(p.get("odds"))
        if dec is None:
            continue
        priced += 1
        staked += 1.0
        be = breakeven_pct(p.get("odds"))
        if be is not None:
            be_sum += be
        if res == "hit":
            returned += dec
            wins += 1
    if not priced:
        return {"priced": 0}
    profit = returned - staked
    return {
        "priced": priced,
        "wins": wins,
        "units": round(profit, 2),
        "roi": round(profit / staked * 100, 1),
        "hit_rate": round(wins / priced * 100, 1),
        # Average price faced, expressed as the rate needed to break even.
        # Beat this and the board made money; sit under it and it didn't,
        # however good the raw hit rate looks.
        "breakeven": round(be_sum / priced, 1),
    }


def _edge_verdict(hits, total, base):
    """Plain-language read on whether a board is beating its baseline.

    Deliberately conservative. With 15 or 40 picks the honest answer is
    "not enough data yet", and this says so instead of dressing up noise
    as an edge — a board looking good on 20 picks is the single easiest
    way for this tool to cost someone money.

    Uses a normal approximation to the binomial: if the observed rate is
    within two standard errors of the baseline, it is not distinguishable
    from chance, and we say exactly that.
    """
    if not total or base is None:
        return "not enough graded picks yet"
    p0 = base / 100.0
    se = (p0 * (1 - p0) / total) ** 0.5
    if se == 0:
        return "not enough graded picks yet"
    z = (hits / total - p0) / se
    # Sample so small that even a large gap proves nothing.
    if total < 30:
        return f"only {total} graded picks — far too few to judge"
    if z > 2:
        return "beating the league baseline (unlikely to be luck)"
    if z < -2:
        return "below the league baseline"
    return "no measurable edge over the baseline yet"
