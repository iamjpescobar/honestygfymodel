"""
Nightly Statcast precompute for Los Cappers.

Pulls REAL pitch-level Statcast data for the whole season to date —
the exact same Baseball Savant source the app uses live — in one bulk
league-wide pass, splits it per player, trims it to the exact columns
the app's engine uses, and packages everything as parquet files plus
a manifest recording precisely when the data was fetched.

No estimates, no filler: every row is a real recorded pitch. A player
with no data simply gets no file, and the app falls back to a live
pull for them.

Run by GitHub Actions nightly (see .github/workflows/nightly-data.yml).
Can also be run locally: python precompute.py
"""

import json
import sys
import tarfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from pybaseball import statcast

# Must match DEFAULT_START_DATE in app/engines/statcast_engine.py so the
# precomputed data covers the identical range as a live pull would.
SEASON_START = date(2026, 3, 1)

# ------------------------------------------------------------
# Column set — keep in sync with _KEEP_COLS in
# app/engines/statcast_engine.py. ID_COLS are needed here only to
# split the bulk data per player and are dropped before saving.
# ------------------------------------------------------------
ENGINE_COLS = [
    "game_date", "game_pk", "at_bat_number", "pitch_number",
    "type", "events", "description", "zone",
    # p_throws: pitcher handedness. Must be here too — if the nightly
    # parquets don't carry it, the engine can't recover it, and the
    # platoon split stays dead on the precomputed path even after
    # _KEEP_COLS is fixed.
    "pitch_type", "stand", "p_throws",
    "bb_type", "launch_speed", "launch_angle", "launch_speed_angle",
    "hc_x", "hc_y",
    "bat_speed", "release_speed",
    "estimated_slg_using_speedangle", "estimated_woba_using_speedangle",
    "balls", "strikes", "plate_x", "plate_z",
]
ID_COLS = ["batter", "pitcher"]
CATEGORY_COLS = ["type", "events", "description", "bb_type", "stand"]

OUT_ROOT = Path("build_data")
DATA_DIR = OUT_ROOT / "data" / "statcast"
ARCHIVE = Path("statcast_data.tar.gz")


def week_ranges(start: date, end: date):
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=6), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def fetch_season() -> pd.DataFrame:
    """Bulk-pulls the whole league's real pitch data in weekly chunks,
    trimming each chunk immediately to keep memory in check."""
    today = date.today()
    chunks = []
    # The expected-stat columns (xwOBA/xSLG) are the ones SLAM and the
    # lineup table's xwOBA/xSLG columns depend on. pybaseball's bulk
    # statcast() has, in some versions, returned a narrower column set
    # than the per-player endpoints and omitted these — which silently
    # shipped parquets without them, showing "None" xwOBA/xSLG and 0.0
    # SLAM for every batter. Track whether we ever actually see them so
    # the run can WARN loudly instead of failing silently.
    _expected_cols = {"estimated_woba_using_speedangle",
                      "estimated_slg_using_speedangle"}
    _saw_expected = False
    for start, stop in week_ranges(SEASON_START, today):
        s, e = start.strftime("%Y-%m-%d"), stop.strftime("%Y-%m-%d")
        df = None
        for attempt in (1, 2):
            try:
                df = statcast(start_dt=s, end_dt=e)
                break
            except Exception as exc:
                print(f"  chunk {s}..{e} attempt {attempt} failed: {exc}")
                time.sleep(15)
        if df is None or df.empty:
            print(f"  chunk {s}..{e}: no data")
            continue

        if _expected_cols.issubset(df.columns):
            _saw_expected = True

        keep = [c for c in ENGINE_COLS + ID_COLS if c in df.columns]
        df = df[keep].copy()
        for c in df.select_dtypes(include="float64").columns:
            df[c] = df[c].astype("float32")
        chunks.append(df)
        print(f"  chunk {s}..{e}: {len(df):,} pitches")

    if not chunks:
        raise SystemExit("No Statcast data fetched — aborting without writing anything.")

    if not _saw_expected:
        print("  *** WARNING: bulk statcast() never returned the expected-stat "
              "columns (estimated_woba/slg_using_speedangle). xwOBA/xSLG will be "
              "None and SLAM 0.0 for every batter. This is the cause of the "
              "'Season shows 0' bug — the bulk endpoint is omitting them. ***")
    return pd.concat(chunks, ignore_index=True)


def save_player_files(season_df: pd.DataFrame) -> dict:
    """Splits the bulk data per batter and per pitcher, matching exactly
    what statcast_batter()/statcast_pitcher() would return for each
    player (their rows from the same dataset), most-recent-first."""
    counts = {"batters": 0, "pitchers": 0}

    # Most-recent-first, matching Baseball Savant's ordering convention.
    season_df = season_df.sort_values(
        ["game_date", "at_bat_number", "pitch_number"],
        ascending=[False, False, False],
    )

    # Each player's file keeps the OPPONENT's id column ("pitcher" in a
    # batter's file, "batter" in a pitcher's file) — that single column is
    # what makes real BvP history computable straight from these files.
    for kind, id_col, keep_opp in (("batters", "batter", "pitcher"),
                                    ("pitchers", "pitcher", "batter")):
        out_dir = DATA_DIR / kind
        out_dir.mkdir(parents=True, exist_ok=True)
        for pid, group in season_df.groupby(id_col):
            if pd.isna(pid):
                continue
            drop_cols = [c for c in ID_COLS if c in group.columns and c != keep_opp]
            g = group.drop(columns=drop_cols).copy()
            for c in CATEGORY_COLS:
                if c in g.columns:
                    g[c] = g[c].astype("category")
            g.to_parquet(out_dir / f"{int(pid)}.parquet", index=False)
            counts[kind] += 1
        print(f"  wrote {counts[kind]:,} {kind} files")

    return counts


# ------------------------------------------------------------
# xHR LOOKUP TABLE
# ------------------------------------------------------------
# Expected home runs, built from THIS season's own league-wide batted
# balls rather than an imported constant or a hand-tuned formula.
#
# The method: bucket every batted ball in the league by exit velocity
# and launch angle, and record what share of the balls in each bucket
# actually became home runs. That empirical rate IS the home-run
# probability of a batted ball with that trajectory, measured rather
# than modelled. A player's xHR is then just the sum of those
# probabilities over his own batted balls.
#
# What that buys: xHR minus actual HR is a real luck gap. A hitter
# well under his xHR has been putting home-run trajectories in play and
# not being paid for them — bad park draws, dead air, warning-track
# outs — and that gap tends to close. That's the regression signal, and
# it's where mispriced bats live.
#
# It is deliberately PARK-NEUTRAL: the rate is pooled across all 30
# parks, so xHR answers "how often does this trajectory leave an average
# yard." Tonight's specific park belongs in the matchup layer, not baked
# into the hitter's own skill number, or the two would double-count.
#
# Buckets are 2 mph x 2 degrees, restricted to the region where home
# runs actually occur. Buckets with too few batted balls to support a
# rate are dropped rather than published as noise.
EV_BIN, LA_BIN = 2.0, 2.0
XHR_MIN_EV, XHR_MAX_EV = 80.0, 122.0
XHR_MIN_LA, XHR_MAX_LA = 8.0, 50.0
XHR_MIN_BUCKET_N = 15


def build_xhr_table(season_df: pd.DataFrame) -> bool:
    """Writes the empirical HR-probability grid used for xHR."""
    need = {"launch_speed", "launch_angle", "events", "type"}
    if not need.issubset(season_df.columns):
        print("  xHR table skipped — missing launch_speed/launch_angle/events.")
        return False

    bbe = season_df[season_df["type"] == "X"].copy()
    ev = pd.to_numeric(bbe["launch_speed"], errors="coerce")
    la = pd.to_numeric(bbe["launch_angle"], errors="coerce")
    ok = (ev.between(XHR_MIN_EV, XHR_MAX_EV) & la.between(XHR_MIN_LA, XHR_MAX_LA))
    bbe, ev, la = bbe[ok], ev[ok], la[ok]
    if bbe.empty:
        print("  xHR table skipped — no batted balls in the tracked region.")
        return False

    grid = pd.DataFrame({
        "ev_bin": (ev // EV_BIN * EV_BIN).astype("float32"),
        "la_bin": (la // LA_BIN * LA_BIN).astype("float32"),
        "is_hr": (bbe["events"].astype(str) == "home_run").astype("int8"),
    })
    agg = grid.groupby(["ev_bin", "la_bin"], observed=True)["is_hr"].agg(["sum", "count"])
    agg = agg[agg["count"] >= XHR_MIN_BUCKET_N]
    if agg.empty:
        print("  xHR table skipped — no bucket cleared the sample floor.")
        return False
    agg["hr_prob"] = (agg["sum"] / agg["count"]).astype("float32")

    out = agg.reset_index()[["ev_bin", "la_bin", "hr_prob"]]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DATA_DIR / "xhr_table.parquet", index=False)
    print(f"  xHR table: {len(out):,} buckets from {len(bbe):,} batted balls "
          f"({int(grid['is_hr'].sum()):,} home runs)")
    return True


def fetch_fangraphs() -> bool:
    """Fetches the real FanGraphs batting leaderboard (same call the app
    makes) from GitHub's servers — which FanGraphs does not block, unlike
    cloud hosts like Render — and ships it with the data package so the
    app can read it locally in production. Returns True on success."""
    try:
        from pybaseball import batting_stats
        fg = batting_stats(2026, qual=10)
        if fg is None or fg.empty:
            print("  FanGraphs returned no data — app will use its live/Statcast fallback.")
            return False
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fg.to_parquet(DATA_DIR / "fangraphs_batting.parquet", index=False)
        print(f"  FanGraphs leaderboard saved: {len(fg):,} qualified batters")
        return True
    except Exception as exc:
        print(f"  FanGraphs fetch failed ({exc}) — app will use its live/Statcast fallback.")
        return False


def main():
    print("Fetching real Statcast data (bulk, weekly chunks)...")
    season_df = fetch_season()
    print(f"Total pitches fetched: {len(season_df):,}")

    print("Splitting per player...")
    counts = save_player_files(season_df)

    print("Building xHR probability table...")
    xhr_ok = build_xhr_table(season_df)

    print("Fetching FanGraphs leaderboard...")
    fangraphs_ok = fetch_fangraphs()

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "season_start": SEASON_START.isoformat(),
        "through_date": date.today().isoformat(),
        "total_pitches": int(len(season_df)),
        "n_batters": counts["batters"],
        "n_pitchers": counts["pitchers"],
        "source": "Baseball Savant via pybaseball bulk statcast()",
        "fangraphs_included": fangraphs_ok,
        "xhr_table_included": xhr_ok,
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Manifest:", json.dumps(manifest, indent=2))

    # Calibration lives inside the archive so the record survives every
    # redeploy — see calibration_pipeline.py for the full rationale.
    print("Grading calibration picks...")
    try:
        import calibration_pipeline
        calibration_pipeline.main()
    except Exception as e:
        print(f"Calibration step failed ({e}) — continuing without it. "
              f"The archive will simply carry the previous record.")

    print("Packaging archive...")
    with tarfile.open(ARCHIVE, "w:gz") as tar:
        tar.add(OUT_ROOT / "data", arcname="data")
    print(f"Wrote {ARCHIVE} ({ARCHIVE.stat().st_size / 1024**2:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())