"""Record EVERY rated bat on the slate, not just the five that publish.

WHY THIS EXISTS
---------------
calibration.json holds the top 5 of the HR board. The board rates on the
order of 270 bats a night and throws 265 of them away, so after sixteen
days the record contains roughly eighty graded HR picks and every one of
them comes from the extreme top of the distribution.

That record can answer "did the published picks beat the league rate."
It CANNOT answer the question the model actually rests on:

    does an 88 HR Edge hit more home runs than a 71?

You cannot validate a ranking by only ever recording its first five
rows. Every weight in top_plays and every floor anyone proposes is
currently an opinion, and will stay an opinion until the middle of the
distribution is on disk next to the top of it.

This file writes that. It publishes nothing, changes no board, and is
invisible on the site. It is a measuring instrument.

WHAT IT IS NOT
--------------
NOT a second pick record. It does not touch data/calibration.json, does
not feed the Results page, and must never be used to report a hit rate —
it contains every bat on the slate, most of which the site never
recommended, so a "record" built from it would be meaningless.

HOW IT RUNS
-----------
    python hr_research_log.py log     # evening, alongside calibration_picks
    python hr_research_log.py grade   # next morning, after the nightly pull

`log` is idempotent per (date, batter): run it three times an afternoon
the way calibration_picks runs, and the first run that finds a real
board records it.

`grade` reads app/data/statcast/batters/{id}.parquet — the files the
nightly already writes — so it needs no network and no MLB Stats API
calls. Grading 270 bats a night off the Stats API would be 270 HTTP
requests; this is a dataframe lookup against the same source the metrics
themselves come from.

STORAGE
-------
One NDJSON file per month, one line per bat-night, repo-committed so CI
and Codespaces see the same thing. Roughly 8,000 lines and a couple of
megabytes a month. If that becomes a problem the fix is parquet, not
logging less.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

EASTERN = ZoneInfo("America/New_York")
OUT_DIR = ROOT / "data" / "hr_research"
# WHERE THE BATTER PARQUETS ACTUALLY ARE, and there are two answers.
#
# precompute writes into build_data/ — a staging tree that gets packaged
# and published as the release asset. app/data/ only exists once
# fetch_data.py unpacks that asset, which happens on Render and in a
# Codespace and NEVER on the CI runner.
#
# This read app/data/ only, so on the nightly runner it found zero files,
# every lookup returned "cannot tell", and the coverage guard correctly
# refused to close the night. 270 rows sat ungraded for a day and the
# reason went into a log nobody read.
#
# Both roots, build_data first because that is where the freshest data
# lives at the moment grading runs.
BATTER_DIRS = (ROOT / "build_data" / "data" / "statcast" / "batters",
               ROOT / "app" / "data" / "statcast" / "batters")

# THE NINE FLOOR CANDIDATES, read straight off the profile the board
# already computed. Keys are the profile's own, not renamed — a rename
# here is a second name for one number, which is how two parts of this
# repo end up disagreeing about what a stat is.
# SHORT WINDOWS, LOGGED ALONGSIDE THE SEASON ONES.
#
# Everything in PROFILE_KEYS below is a SEASON figure, regressed toward
# the league mean. That is the conservative choice and it is defensible
# — season is stable, regression protects thin samples — but it is a
# CHOICE, and the log cannot currently tell whether it is the right one.
#
# Competing products rate almost entirely on short windows: exit
# velocity over the last 5 games, hard-hit and pull-air over 14, form
# over 7. For "does he homer TONIGHT", recent batted-ball shape may
# genuinely carry more signal than stable skill. Nobody here knows.
#
# The question is only answerable if both are on disk from the same
# night against the same outcome. Recording season alone means that in
# three weeks we can answer "does an 88 beat a 71" and still not answer
# "does L15 pull-air beat season pull-air" — and every night logged
# without these is a night that cannot answer it later.
#
# l15 and l5 because recency_windows already supports exactly those.
WINDOWED_KEYS = ("Brl %", "Brl/PA", "HH %", "FB %", "EV90", "AvgEV",
                 "PullAir %", "Blast %", "ISO", "HRWindow %")
WINDOWS = ("l15", "l5")

PROFILE_KEYS = ("Brl %", "Brl/PA", "HH %", "FB %", "EV90", "MaxEV",
                # AvgEV, not just EV90. The floor set names AvgEV, and
                # without it the qualification tier cannot be
                # reconstructed from a stored row — which is the whole
                # reason these nine are captured. It was omitted because
                # the column did not exist when this list was written.
                "AvgEV",
                "ClearsAnywhere %", "Blast %", "PullAir %", "PullBrl %",
                "ISO", "SLG", "BA", "HRIntent", "HRThreat", "HR/FB",
                "SweetSpot %", "LD %", "GB %", "BBE", "PA")

# What the edge layer contributed, kept SEPARATE from the skill score.
# Without these you cannot tell whether a miss came from rating the
# hitter wrong or from rating the park, the pen and the arsenal wrong,
# and those want opposite fixes.
EDGE_KEYS = ("edge",
             # THE UNCLAMPED VALUE. `edge` is an integer clamped to
             # 0-100, so every bat that pinned at the ceiling is stored
             # as the same number and the log cannot reconstruct the
             # order the board actually showed. The clamp erasing
             # separation at the top is precisely what edge_raw was
             # added to fix; recording only the clamped one puts the bug
             # back inside the measurement.
             "edge_raw",
             "hr_score", "bvp_adj", "zone_adj", "pen_adj",
             "ctx_adj", "pitch_adj", "slot_adj", "hr_threat",
             "clears_anywhere", "fb95", "hr_pa", "hr_bbe",
             # HOW MANY QUALIFICATION FLOORS. Derivable from the nine
             # metrics in principle, but only against the thresholds in
             # force ON THAT NIGHT — and those are measured nightly and
             # move. Storing the count records what the board actually
             # said rather than what today's thresholds would say about
             # a bat from three weeks ago.
             "floors_met", "floors_total")


def _month_path(month: str) -> Path:
    """month is 'YYYY-MM'. A date is accepted and truncated."""
    return OUT_DIR / f"{month[:7]}.ndjson"


def _read_month(month: str) -> list:
    """EVERY row in that month's file, not one date's.

    Named for the month on purpose. It was `_read(date_str)`, which read
    like a day's rows and returned thirty of them — the test asserting
    "tonight is ungraded" picked up last night's graded rows and failed
    against code that was working. A function whose name implies a
    narrower scope than it has will be misused, including by the person
    who wrote it twenty minutes earlier.
    """
    path = _month_path(month)
    if not path.exists():
        return []
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception as exc:
            # One corrupt line must not cost the month. Say which.
            print(f"WARNING: {path.name} line {i} unreadable ({exc}) — skipped")
    return rows


def _write_month(month: str, rows: list) -> None:
    path = _month_path(month)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, separators=(",", ":"))
                              for r in rows) + "\n", encoding="utf-8")


def log(date_str: str) -> int:
    """Record every rated bat on tonight's slate."""
    from engines.hr_edge_board import get_hr_edge_board
    from engines.statcast_engine import get_batter_profile_windowed

    # confirmed_only=True, deliberately, and for the SAME reason
    # calibration_picks uses it: a bat in a projected lineup may not
    # play, and a row whose outcome is "he was never in the game" is
    # noise in a file whose whole purpose is measuring the score.
    rows, meta = get_hr_edge_board(confirmed_only=True)
    if not rows:
        print(f"hr_research: no confirmed board for {date_str} "
              f"({meta.get('games', 0)} games, lineups likely not posted) "
              f"— will retry.")
        return 0

    existing = _read_month(date_str)
    already = {(r.get("date"), r.get("id")) for r in existing}

    fresh = []
    for r in rows:
        pid = r.get("id")
        if pid is None or (date_str, pid) in already:
            continue
        # Cache hit — the board just computed this same profile for this
        # same batter, so this is a dict lookup, not a second pull.
        prof = get_batter_profile_windowed(pid, window="season", unit="bbe") or {}
        rec = {
            "date": date_str, "id": pid, "name": r.get("name"),
            "team": r.get("team"), "opponent": r.get("opponent"),
            "pitcher": r.get("pitcher"), "park": r.get("park"),
            "bats": r.get("bats"),
            # THE GAME KEY, and its absence made a whole class of
            # question unanswerable. Without it the log cannot tell
            # which bats shared a park, a starter, a wind and a
            # bullpen — so it could never measure same-game correlation
            # or evaluate the 2-per-game cap, which is the reason the
            # cap exists. 103 rows were logged on 2026-08-12 with this
            # missing.
            "game_pk": r.get("game_pk"),
            # Filled by grade(). None means UNGRADED, not zero — the
            # distinction this repo has had to relearn three times.
            "hr": None, "graded": None,
        }
        for k in EDGE_KEYS:
            rec[k] = r.get(k)
        for k in PROFILE_KEYS:
            rec[k] = prof.get(k)

        # The same metrics over short windows, prefixed by window so a
        # column name always says which one it is. Cached per
        # (batter, window, unit), so the second and third calls for a
        # batter the board already profiled are dict lookups.
        for win in WINDOWS:
            wp = get_batter_profile_windowed(pid, window=win, unit="bbe") or {}
            for k in WINDOWED_KEYS:
                rec[f"{win}_{k}"] = wp.get(k)
        fresh.append(rec)

    if not fresh:
        print(f"hr_research: all {len(rows)} rated bats already logged for "
              f"{date_str} — leaving alone.")
        return 0

    _write_month(date_str, existing + fresh)
    print(f"hr_research: logged {len(fresh)} rated bat(s) for {date_str} "
          f"({meta.get('games', 0)} games, {meta.get('rated', 0)} rated).")
    return len(fresh)


def _homered(pid, date_str):
    """(hr, played) for one batter on one date, from the nightly files.

    Returns (None, None) when the file is absent — that is "cannot tell",
    and it must not be recorded as a zero.
    """
    import pandas as pd
    path = next((d / f"{int(pid)}.parquet" for d in BATTER_DIRS
                 if (d / f"{int(pid)}.parquet").exists()), None)
    if path is None:
        return None, None
    try:
        df = pd.read_parquet(path, columns=["game_date", "events"])
    except Exception:
        return None, None
    day = df[df["game_date"].astype(str).str[:10] == date_str]
    if day.empty:
        return None, False              # did not appear that night
    return int((day["events"].astype(str) == "home_run").sum()), True


def grade(today: str) -> int:
    """Fill in results for every past date the nightly pull now covers."""
    import pandas as pd  # noqa: F401  (imported for the reader in _homered)

    months = sorted(OUT_DIR.glob("*.ndjson")) if OUT_DIR.exists() else []
    if not months:
        print("hr_research: nothing logged yet.")
        return 0

    filled = 0
    for path in months:
        rows = _read_month(path.stem)
        by_date = {}
        for r in rows:
            by_date.setdefault(r.get("date"), []).append(r)

        for date_str, day_rows in sorted(by_date.items()):
            if date_str >= today:
                continue                       # tonight hasn't happened
            pending = [r for r in day_rows if r.get("graded") is None]
            if not pending:
                continue

            results = {}
            for r in pending:
                results[r["id"]] = _homered(r["id"], date_str)

            # THE COVERAGE CHECK, and it is the whole reason this is safe
            # to run every morning.
            #
            # "No rows on that date" is ambiguous: either the hitter did
            # not play, or the nightly pull has not reached that date yet.
            # A real slate always has most of its bats appearing, so if
            # almost nobody does, the pull is behind — and closing 270
            # bats as DNP would silently write a night of zeros. That is
            # exactly how 45 WNBA picks were once closed as DNP against
            # games that had already been played.
            appeared = sum(1 for _hr, played in results.values() if played)
            if appeared < len(pending) * 0.5:
                # SAY WHICH REASON. "No rows for this batter" and "no file
                # for this batter" are indistinguishable inside _homered,
                # and they mean completely different things: the first is
                # a pull that has not caught up, the second is a path that
                # is wrong. Reporting them as one cost a full day of
                # grading — the guard held, and nobody could tell why.
                _nofile = sum(1 for _hr, played in results.values()
                              if played is None)
                _roots = [str(d) for d in BATTER_DIRS if d.exists()]
                print(f"hr_research: {date_str} — only {appeared} of "
                      f"{len(pending)} bats appear in the batter files; "
                      f"{_nofile} had NO FILE AT ALL. Leaving the night "
                      f"ungraded.")
                _why = _roots or ["NONE — the path is wrong, not the pull"]
                print(f"  batter dirs present: {_why}")
                continue

            for r in pending:
                hr, played = results[r["id"]]
                if played is None:
                    continue                   # no file at all, still unknown
                r["hr"] = hr if played else 0
                r["graded"] = "played" if played else "dnp"
                filled += 1

            print(f"hr_research: graded {len(pending)} bat(s) for {date_str} "
                  f"— {sum(1 for r in pending if r.get('hr'))} homered.")

        if rows:
            # Keyed off the FILE, not off rows[0]["date"]. Same month by
            # construction, but deriving the destination from the data
            # you are writing is how a month's rows land in another
            # month's file the first time an assumption breaks.
            _write_month(path.stem, rows)

    print(f"hr_research: filled {filled} result(s).")
    return filled


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    today = datetime.now(EASTERN).strftime("%Y-%m-%d")
    if mode == "log":
        log(today)
    elif mode == "grade":
        grade(today)
    else:
        print(__doc__)
        print("usage: python hr_research_log.py [log|grade]")
        return 2
    # Always 0. An afternoon with no confirmed lineups is normal, and a
    # red X on the Actions tab every day trains you to ignore it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
