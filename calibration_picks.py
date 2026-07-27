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
daily13, potd, and hr_edge.

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
import os
import sys
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
            for r in rows if isinstance(r, dict) and r.get("id")]


def _rows_potd():
    """Today's Player of the Day, or [] if there isn't a real one."""
    from engines.player_of_the_day import get_mlb_player_of_the_day
    result = get_mlb_player_of_the_day()
    # The engine returns (pick, note)-shaped or dict-shaped data across
    # versions; accept either rather than assuming.
    pick = result[0] if isinstance(result, tuple) else result
    if not isinstance(pick, dict) or not pick.get("id"):
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
            for r in rows if r.get("id")]


BUILDERS = {"daily13": _rows_daily13, "potd": _rows_potd,
            "hr_edge": _rows_hr_edge}


def main() -> int:
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    record = _load()
    wrote = 0

    for board, build in BUILDERS.items():
        existing = record.get(board, {}).get(date_str)
        if existing and existing.get("picks"):
            print(f"{board}: already logged for {date_str} "
                  f"({len(existing['picks'])} picks) - leaving alone.")
            continue
        try:
            rows = build()
        except Exception as exc:
            # One board failing must not cost the other. A missing board
            # is a gap; a crash here would be a whole lost day.
            print(f"{board}: could not build ({type(exc).__name__}: {exc})")
            continue
        if not rows:
            # Almost always "lineups aren't posted yet" — a real timing
            # fact, not an error. A later run picks it up.
            print(f"{board}: no board yet for {date_str} "
                  f"(lineups likely not posted) - will retry.")
            continue
        record.setdefault(board, {})[date_str] = {
            "picks": [{"id": r["id"], "name": r.get("name"),
                       "team": r.get("team"), "stat": None, "line": None,
                       "result": None} for r in rows],
            "graded": False,
            # Marks picks recorded by CI rather than by a page view, so
            # a mixed record stays interpretable later.
            "source": "ci",
        }
        wrote += len(rows)
        print(f"{board}: logged {len(rows)} pick(s) for {date_str}.")

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
