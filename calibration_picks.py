"""
Log today's board picks WITHOUT anyone opening the site.

WHY THIS EXISTS
---------------
Calibration picks were only ever written from inside a Streamlit view —
Daily_13.py, Player_Of_The_Day.py, GameCard.py all call log_picks() as a
side effect of RENDERING. Two consequences, both fatal to the record:

  1. No visitor, no picks. On any day nobody loaded the board, nothing
     was recorded, so the day could never be graded. It didn't fail
     loudly; the day was simply absent.

  2. The app writes to its own container filesystem on Render, while
     calibration_pipeline.py grades on a fresh GitHub Actions runner.
     Different machines. The pipeline literally could not see them.

This script closes both. It runs in CI on a schedule, computes the same
boards from the same engines the site uses, and writes the picks into a
repo-committed file that the grading pipeline can actually read.

FIDELITY
--------
It calls the ENGINE functions (get_daily_13, get_mlb_player_of_the_day),
not a reimplementation. The views are display layers over these same
calls, so a pick logged here is the pick the site would have shown. If
the engines change, this follows automatically — there is no second copy
of the ranking logic to drift out of sync.

TIMING
------
MLB posts confirmed lineups 1-3 hours before first pitch (see
engines/roster.get_confirmed_lineup). The nightly 6 AM data job is far
too early — no lineup exists then. So this runs separately, several
times across the afternoon and evening, and is idempotent: the first run
that finds a real board records it, later runs leave it alone.

BOARDS LOGGED
-------------
daily13, potd, hr_edge, k_board, wnba_props, wnba_defense — see BUILDERS.

The last three grade against a per-pick LINE rather than a fixed
threshold, so their rows carry "stat" and "line" and main() must write
both through. See the note at the record.setdefault() call.

hr_edge was previously skipped: its picks were built inside
GameCard.py from ONE selected game against one opposing team, so the
record was "the top 5 bats from whichever game card was last open"
rather than the top 5 of the slate. engines/hr_edge_board.py now
computes it across every game, so it can be logged honestly. It is
restricted to CONFIRMED lineups — a pick made off a projected lineup
isn't the pick the site would have shown, and grading it would
measure a claim the model never made.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

EASTERN = ZoneInfo("America/New_York")
# Repo-committed, so the grading pipeline sees it on the next checkout.
# Deliberately NOT app/data/calibration_local.json — that one lives on
# the Render container and never reaches CI.
RECORD_PATH = ROOT / "data" / "calibration.json"


def _load() -> dict:
    if not RECORD_PATH.exists():
        return {}
    try:
        return json.loads(RECORD_PATH.read_text())
    except Exception as exc:
        # Never start from {} on a parse failure — that would silently
        # erase every graded day this file already holds.
        print(f"ERROR: {RECORD_PATH} is unreadable ({exc}). Refusing to "
              f"overwrite it.")
        raise


def _rows_daily13():
    """Today's Daily 13 board, or [] if it can't be built.

    get_daily_13() returns a (rows, meta) TUPLE, not a bare list — its
    docstring says so and I assumed a list anyway. Unpacking it as a list
    handed each element to r.get(), which failed with
    "AttributeError: 'list' object has no attribute 'get'" and cost the
    board every run.
    """
    from engines.daily_13 import get_daily_13
    result = get_daily_13()
    rows = result[0] if isinstance(result, tuple) else result
    rows = rows or []
    return [{"id": r.get("id"), "name": r.get("name"), "team": r.get("team")}
            for r in rows if isinstance(r, dict) and has_id(r.get("id"))]


def _rows_potd():
    """Today's Player of the Day, or [] if there isn't a real one."""
    from engines.player_of_the_day import get_mlb_player_of_the_day
    result = get_mlb_player_of_the_day()
    # The engine returns (pick, note)-shaped or dict-shaped data across
    # versions; accept either rather than assuming.
    pick = result[0] if isinstance(result, tuple) else result
    if not isinstance(pick, dict) or not has_id(pick.get("id")):
        return []
    return [{"id": pick.get("id"), "name": pick.get("name"),
             "team": pick.get("team")}]


def _rows_hr_edge():
    """Slate's top 5 by HR Edge, or [] if no confirmed lineups yet.

    Loggable now because engines/hr_edge_board.py computes the board
    across every game instead of inside a single game card.

    confirmed_only=True on purpose. A pick built off a projected lineup
    is not the pick the site would have shown, and grading it would
    measure a claim the model never made.
    """
    from engines.hr_edge_board import top_hr_edge
    rows, _meta = top_hr_edge(n=5, confirmed_only=True)
    return [{"id": r.get("id"), "name": r.get("name"), "team": r.get("team")}
            for r in rows if has_id(r.get("id"))]


from engines.slate_guard import load_slate  # noqa: E402


def _wnba_games():
    """Tonight's WNBA slate, or [] when what's on disk isn't tonight's.

    THE COMMENT THAT USED TO BE HERE SAID the file is current because
    slate-picks.yml runs fetch_data.py first. That is true only when the
    nightly published. fetch_data downloads the last SUCCESSFULLY
    published archive, so while the nightly was failing the fetch kept
    succeeding and kept returning a slate — just an older one.

    Nothing compared its date to today, so boards were built from games
    that had already been played and logged under TODAY's date. The
    grader then looked for box scores on a night those players did not
    play, found none, and closed 45 picks as DNP. The probe that caught
    it: a player on the Aug 3 board whose most recent ESPN game was
    Aug 2 at 7 PM ET.

    Publishing a board for a slate that already finished is worse than
    publishing nothing, so a stale slate now yields nothing and says so.
    """
    games, slate_date, ok = load_slate("wnba")
    if ok:
        return games
    if slate_date is None:
        print("wnba: no slate on disk (or it carries no slate_date_et) \u2014 "
              "no picks logged")
    else:
        print(f"wnba: slate on disk is for {slate_date}, not "
              f"{datetime.now(EASTERN).strftime('%Y-%m-%d')} \u2014 the nightly "
              f"archive has not published since. Those games are already "
              f"played; refusing to log picks for them.")
    return []


def _rows_wnba_props():
    """Tonight's top 10 WNBA prop picks, or [] if there's no slate.

    WHY THIS EXISTS. wnba_props was logged from ONE place — inside
    app/views/WNBA_Props.py, which only runs when a human opens that
    page. So the board was never calibrated: on any night nobody browsed
    it, the picks that board would have made vanished unrecorded, and the
    record showed no wnba_props entries at all. That is exactly the "no
    visitor, no picks" problem this whole file exists to solve for the
    MLB boards; WNBA just never got a builder.

    Deliberately mirrors the view's DEFAULTS (Points, L10 window, top 10)
    so what gets logged is what the board would actually have shown. A
    different stat or window here would grade a claim the site never
    made.

    Reads the nightly slate straight off disk, the same file the view
    reads, so this needs no Streamlit session.
    """
    games = _wnba_games()
    if not games:
        return []

    from engines.wnba_props import build_props, STATS
    # EVERY MARKET, not just Points.
    #
    # This used to build "Points" alone, which meant rebounds, assists,
    # PRA and threes were published nightly and never once scored. The
    # board reported a tracked record covering one fifth of what it
    # actually put in front of people.
    #
    # STATS is the view's own market list, so this follows automatically
    # if a market is ever added or dropped there — no second copy to
    # drift. "l10" and top-10 remain the view's defaults; changing
    # either here would grade a claim the site never made.
    out = []
    for stat_label, cfg in STATS.items():
        try:
            rows, _unrated = build_props(games, stat_label, "l10")
        except Exception as exc:
            # One market failing must not cost the other four.
            print(f"  wnba_props/{stat_label}: skipped "
                  f"({type(exc).__name__}: {exc})")
            continue
        out.extend({"id": r.get("id"), "name": r.get("player"),
                    "team": r.get("team"), "stat": cfg["key"],
                    "line": r.get("line")}
                   for r in (rows or [])[:10] if has_id(r.get("id")))
    return out


def _rows_wnba_defense():
    """Tonight's top 5 WNBA defense-matchup picks, or [].

    Same story as _rows_wnba_props: logged only from
    app/views/WNBA_Defense.py, so it calibrated only on nights someone
    happened to open that page. Mirrors the view's defaults (Points,
    L10, top 5) and its line field (`form`) so the logged pick is the
    pick the board would have shown.
    """
    games = _wnba_games()
    if not games:
        return []

    from engines.wnba_defense import build_board, _STATS
    # Same reasoning as _rows_wnba_props: log every market this board
    # can publish, not just the first one. _STATS is the board's own
    # list (Points / Rebounds / Assists — deliberately fewer than the
    # props board, since a defensive matchup rating only exists for
    # those three), so this tracks it without a second copy.
    out = []
    for stat_label, stat_key in _STATS.items():
        try:
            rows, _unrated = build_board(games, stat_label, "l10")
        except Exception as exc:
            print(f"  wnba_defense/{stat_label}: skipped "
                  f"({type(exc).__name__}: {exc})")
            continue
        out.extend({"id": r.get("id"), "name": r.get("player"),
                    "team": r.get("team"), "stat": stat_key,
                    "line": r.get("form")}
                   for r in (rows or [])[:5] if has_id(r.get("id")))
    return out


def _rows_k_board():
    """Tonight's top 5 strikeout projections, or [].

    The Strikeout Board projected Ks for every probable starter and
    NOTHING ever checked those projections against what actually
    happened — no logged picks, no grading, no record. A board that makes
    a number every day and is never scored is the easiest place for a
    model to be quietly wrong for months.

    Each pick carries its own projected line, so grading asks the honest
    question: did he clear the number this board published?
    """
    from engines.k_projection import get_slate_k_projections
    # UNPACK THE TUPLE. get_slate_k_projections returns (rows, warning),
    # exactly as views/Strikeout_Board.py reads it. This line used to
    # bind the whole tuple to `rows`, so the comprehension below iterated
    # [list, warning_str] and called .get() on a list — AttributeError on
    # every single run. main()'s per-board try/except caught it, printed
    # "k_board: could not build" into the Actions log, and moved on, which
    # is why this board has never logged one pick despite being wired
    # into BUILDERS and into both BOARDS configs.
    rows, _warning = get_slate_k_projections("season")
    rows = rows or []
    ranked = sorted((r for r in rows if has_id(r.get("pid")) and r.get("proj")),
                    key=lambda r: -(r.get("proj") or 0))[:5]
    return [{"id": r.get("pid"), "name": r.get("pitcher"), "team": r.get("team"),
             "stat": "strikeOuts", "line": r.get("proj")}
            for r in ranked]


# Shared with the app so the two never diverge on what counts as an id.
# sys.path already has app/ (see the top of this file), and CI installs
# streamlit because the board engines need it.
from engines.calibration import has_id  # noqa: E402

BUILDERS = {"daily13": _rows_daily13, "potd": _rows_potd,
            "k_board": _rows_k_board,
            "hr_edge": _rows_hr_edge, "wnba_props": _rows_wnba_props,
            "wnba_defense": _rows_wnba_defense}


def main() -> int:
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    record = _load()
    wrote = 0
    # PER-BOARD TIMING.
    #
    # Every print in this script was buffered and flushed at exit, so the
    # Actions log showed the whole run as one block and there was no way
    # to tell which board was slow — only that the six together took a
    # minute. flush=True plus an elapsed figure per board turns the log
    # into the profile, at the cost of nothing.
    timings = []

    for board, build in BUILDERS.items():
        # SKIP PER MARKET, NOT PER DAY — mirrors the same change in
        # app/engines/calibration.py's log_picks().
        #
        # The old check bailed out as soon as a date had any picks. On a
        # multi-market board that froze the day after the first market
        # landed: if only Points was up when the 17:00 run fired, the
        # 21:00 and 23:00 runs saw a non-empty day and left it alone, so
        # the other four markets were never recorded even though they
        # were available hours before tip-off. Idempotency is now per
        # (board, date, market), which keeps the retry behaviour these
        # three daily runs exist for.
        existing = record.get(board, {}).get(date_str) or {}
        logged_markets = {p.get("stat") for p in existing.get("picks", [])}
        _t0 = time.monotonic()
        try:
            rows = build()
        except Exception as exc:
            # One board failing must not cost the other. A missing board
            # is a gap; a crash here would be a whole lost day.
            print(f"{board}: could not build after {time.monotonic() - _t0:.1f}s "
                  f"({type(exc).__name__}: {exc})", flush=True)
            continue
        _elapsed = time.monotonic() - _t0
        timings.append((board, _elapsed))
        if not rows:
            # Almost always "lineups aren't posted yet" — a real timing
            # fact, not an error. A later run picks it up.
            print(f"{board}: no board yet for {date_str} in {_elapsed:.1f}s "
                  f"(lineups likely not posted) - will retry.", flush=True)
            continue
        # CARRY stat AND line THROUGH. These were hardcoded to None here,
        # which silently discarded the per-pick numbers every builder
        # above goes to the trouble of computing — k_board's projected
        # strikeouts, wnba_props' line, wnba_defense's form.
        #
        # For the MLB boards it didn't show: daily13/hr_edge/potd carry a
        # fixed threshold of 1 in BOARDS, so grade() had a target either
        # way. For every board whose threshold is None — which is exactly
        # the boards that grade against their OWN published number — the
        # target resolved to None and grade() closed each pick "dnp". Not
        # a wrong result: no result, permanently, by construction. The
        # WNBA boards logged 30 picks and graded zero of them.
        #
        # app/engines/calibration.py's log_picks() already wrote both
        # fields correctly. This is the CI path, and since every record
        # now carries source="ci", this was the only path that ran.
        fresh = [r for r in rows if r.get("stat") not in logged_markets]
        if not fresh:
            print(f"{board}: every market already logged for {date_str} "
                  f"({len(existing.get('picks', []))} picks) - leaving alone "
                  f"[built in {_elapsed:.1f}s].", flush=True)
            continue
        entry = record.setdefault(board, {}).setdefault(
            date_str, {"picks": [], "graded": False,
                       # Marks picks recorded by CI rather than by a page
                       # view, so a mixed record stays interpretable later.
                       "source": "ci"})
        entry.setdefault("picks", []).extend(
            {"id": r["id"], "name": r.get("name"),
             "team": r.get("team"), "stat": r.get("stat"),
             "line": r.get("line"),
             "result": None} for r in fresh)
        # A market added after an earlier grading pass must reopen the
        # day, or grade() will skip straight past it forever.
        entry["graded"] = False
        wrote += len(fresh)
        _added = sorted({str(r.get("stat")) for r in fresh})
        print(f"{board}: logged {len(fresh)} pick(s) for {date_str} "
              f"({', '.join(_added)}) in {_elapsed:.1f}s.", flush=True)

    if timings:
        _total = sum(t for _b, t in timings)
        print("\n--- build time by board (slowest first) ---", flush=True)
        for _b, _t in sorted(timings, key=lambda x: -x[1]):
            print(f"  {_t:7.1f}s  {_b}", flush=True)
        print(f"  {_total:7.1f}s  TOTAL\n", flush=True)

    if wrote:
        RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECORD_PATH.write_text(json.dumps(record, indent=2))
        print(f"Wrote {wrote} pick(s) to {RECORD_PATH}.")
    else:
        print("Nothing new to log.")
    # Always exit 0. An empty afternoon slate is normal, and a red X on
    # the Actions tab every day would train you to ignore it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
