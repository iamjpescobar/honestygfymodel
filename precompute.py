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
    "pitch_type", "stand",
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

        keep = [c for c in ENGINE_COLS + ID_COLS if c in df.columns]
        df = df[keep].copy()
        for c in df.select_dtypes(include="float64").columns:
            df[c] = df[c].astype("float32")
        chunks.append(df)
        print(f"  chunk {s}..{e}: {len(df):,} pitches")

    if not chunks:
        raise SystemExit("No Statcast data fetched — aborting without writing anything.")
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
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Manifest:", json.dumps(manifest, indent=2))

    print("Packaging archive...")
    with tarfile.open(ARCHIVE, "w:gz") as tar:
        tar.add(OUT_ROOT / "data", arcname="data")
    print(f"Wrote {ARCHIVE} ({ARCHIVE.stat().st_size / 1024**2:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())