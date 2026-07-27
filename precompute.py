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

import numpy as np
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


def _mask(series) -> pd.Series:
    """Force a boolean mask to plain numpy bool with NA treated as False.

    Statcast columns arrive with nullable dtypes (Int8/Float64) and real
    missing values — launch_speed_angle is NaN on every row that isn't a
    batted ball, which is most of them. A comparison against a nullable
    column yields a NULLABLE boolean carrying pd.NA, and pd.NA survives
    `&`, so the result can't be cast: "ValueError: cannot convert NA to
    integer". That killed the nightly run at the barrel mask.

    NA here always means "this row is not that kind of event", which is
    exactly False, so collapsing it is correct rather than merely
    convenient.
    """
    return pd.Series(series, copy=False).fillna(False).astype(bool)


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

    bbe = season_df[_mask(season_df["type"] == "X")].copy()
    ev = pd.to_numeric(bbe["launch_speed"], errors="coerce")
    la = pd.to_numeric(bbe["launch_angle"], errors="coerce")
    ok = _mask(ev.between(XHR_MIN_EV, XHR_MAX_EV) & la.between(XHR_MIN_LA, XHR_MAX_LA))
    bbe, ev, la = bbe[ok], ev[ok], la[ok]
    if bbe.empty:
        print("  xHR table skipped — no batted balls in the tracked region.")
        return False

    grid = pd.DataFrame({
        "ev_bin": (ev // EV_BIN * EV_BIN).astype("float32"),
        "la_bin": (la // LA_BIN * LA_BIN).astype("float32"),
        "is_hr": _mask(bbe["events"].astype(str) == "home_run").astype("int8"),
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


# ------------------------------------------------------------
# LEAGUE-WIDE HR METRICS
# ------------------------------------------------------------
# Computes the HR metric layer for EVERY batter in one vectorised pass
# and ships it as a lookup table, exactly like the Savant percentile
# leaderboard the app already uses.
#
# Why here and not in the app: _compute_batted_ball_metrics works on
# ONE player's dataframe. Calling it per batter to rank a slate would
# mean hundreds of per-player Statcast pulls on every page load. The
# nightly bulk pull already holds every batted ball in the league, so
# doing it once here costs a single groupby and the app gets an O(1)
# dictionary lookup instead.
#
# Everything is converted to a 0-100 LEAGUE PERCENTILE before shipping,
# so it lands on the same scale as the Savant percentiles hr_score
# already blends, and no downstream weight has to know the raw units.
HRM_MIN_PA = 50          # below this a rate is noise, not a signal
HRM_MIN_BBE = 30


def build_hr_metrics(season_df: pd.DataFrame) -> bool:
    need = {"batter", "launch_speed", "launch_angle", "events", "type"}
    if not need.issubset(season_df.columns):
        print("  HR metrics skipped — missing required columns.")
        return False

    df = season_df.copy()
    ev = pd.to_numeric(df["launch_speed"], errors="coerce")
    la = pd.to_numeric(df["launch_angle"], errors="coerce")
    # Every mask below goes through _mask(): these columns are nullable
    # and mostly missing, and an NA leaking into a mask breaks the
    # integer cast further down.
    is_bbe = _mask(df["type"] == "X")
    is_pa = _mask(df["events"].notna())

    # Barrel: Statcast's own launch_speed_angle == 6. NaN on every
    # non-batted-ball row, which is the majority of the file.
    is_barrel = _mask(pd.to_numeric(df.get("launch_speed_angle"), errors="coerce") == 6)
    # HR window: launch angle 20-40. See _HR_LA_MIN in statcast_engine —
    # NOT the 8-32 sweet-spot band, which starts at a line drive.
    in_window = _mask(is_bbe & la.between(20.0, 40.0))
    # Pulled fly ball, using the identical spray-angle convention as
    # statcast_engine._spray_angle so the two never disagree.
    if {"hc_x", "hc_y", "stand"}.issubset(df.columns):
        ang = np.degrees(np.arctan2(
            pd.to_numeric(df["hc_x"], errors="coerce") - 125.42,
            198.27 - pd.to_numeric(df["hc_y"], errors="coerce")))
        pulled = _mask((_mask(df["stand"] == "R") & _mask(ang < 0)) |
                       (_mask(df["stand"] == "L") & _mask(ang > 0)))
        is_pull_air = _mask(is_bbe & _mask(df.get("bb_type") == "fly_ball") & pulled)
    else:
        is_pull_air = pd.Series(False, index=df.index)

    work = pd.DataFrame({
        "batter": df["batter"],
        "pa": is_pa.astype("int32"),
        "bbe": is_bbe.astype("int32"),
        "barrel": (is_bbe & is_barrel).astype("int32"),
        "window": in_window.astype("int32"),
        "pullair": is_pull_air.astype("int32"),
        "hr": _mask(df["events"].astype(str) == "home_run").astype("int32"),
        "ev": ev.where(is_bbe),
        "bat_speed": pd.to_numeric(df.get("bat_speed"), errors="coerce"),
    })
    g = work.groupby("batter", observed=True)
    out = g[["pa", "bbe", "barrel", "window", "pullair", "hr"]].sum()
    out["ev90"] = g["ev"].quantile(0.90)
    out["max_ev"] = g["ev"].max()
    out["bat_speed"] = g["bat_speed"].mean()
    out = out[(out["pa"] >= HRM_MIN_PA) & (out["bbe"] >= HRM_MIN_BBE)]
    if out.empty:
        print("  HR metrics skipped — no batter cleared the sample floor.")
        return False

    out["brl_per_pa"] = out["barrel"] / out["pa"] * 100
    out["hr_window_pct"] = out["window"] / out["bbe"] * 100
    out["pull_air_pct"] = out["pullair"] / out["bbe"] * 100

    # HR Intent — same three process inputs and the same league anchors
    # as statcast_engine, averaged over whatever is measurable.
    intent = [
        (out["bat_speed"] / 71.0 * 50.0).clip(upper=100),
        (out["hr_window_pct"] / 30.0 * 50.0).clip(upper=100),
        (out["pull_air_pct"] / 18.0 * 50.0).clip(upper=100),
    ]
    stacked = pd.concat(intent, axis=1)
    out["hr_intent"] = stacked.mean(axis=1, skipna=True)

    # xHR from the same empirical grid, so the app and the build agree.
    xhr_path = DATA_DIR / "xhr_table.parquet"
    if xhr_path.exists():
        tbl = pd.read_parquet(xhr_path)
        key = pd.DataFrame({
            "batter": df["batter"],
            "ev_bin": (ev // 2.0 * 2.0),
            "la_bin": (la // 2.0 * 2.0),
        })[is_bbe.values]
        merged = key.merge(tbl, on=["ev_bin", "la_bin"], how="left")
        merged["hr_prob"] = merged["hr_prob"].fillna(0.0)
        out["xhr"] = merged.groupby("batter", observed=True)["hr_prob"].sum()
        out["xhr"] = out["xhr"].fillna(0.0)
        # THE regression signal: trajectories that deserved to leave and
        # didn't. Positive = owed home runs.
        out["xhr_gap"] = out["xhr"] - out["hr"]
    else:
        out["xhr"] = np.nan
        out["xhr_gap"] = np.nan

    # Rank to 0-100 league percentiles, matching the Savant scale.
    for col in ("brl_per_pa", "hr_window_pct", "pull_air_pct",
                "ev90", "hr_intent", "xhr_gap"):
        out[col + "_pct"] = out[col].rank(pct=True) * 100.0

    out = out.reset_index()
    out["batter"] = out["batter"].astype("int64")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DATA_DIR / "hr_metrics.parquet", index=False)
    print(f"  HR metrics: {len(out):,} qualified batters "
          f"(>= {HRM_MIN_PA} PA, {HRM_MIN_BBE} BBE)")
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

    print("Building league-wide HR metrics...")
    hrm_ok = build_hr_metrics(season_df)

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
        "hr_metrics_included": hrm_ok,
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