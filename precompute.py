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
    # Park attribution for the HR park-factor build. Must match
    # _KEEP_COLS or tests/test_columns.py fails.
    "home_team",
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

    out = pd.concat(chunks, ignore_index=True)

    # HARD ABORT if the barrel column is gone. This one cannot be a
    # warning, because unlike the expected stats above it fails SILENTLY
    # AS A PLAUSIBLE VALUE rather than as None. The barrel masks below
    # read df.get("launch_speed_angle"), DataFrame.get returns None for a
    # missing column, and pd.to_numeric(None, errors="coerce") == 6 does
    # not raise — it evaluates to a scalar False that broadcasts to every
    # row. Result: zero barrels for the entire league, written out as a
    # real 0.0. Nothing downstream can detect it, and Brl/PA is the
    # primary input to top_plays' POWER axis (45% of the score), so the
    # board would keep publishing confident rankings driven by an
    # all-zeros column. Publishing nothing is strictly better.
    if "launch_speed_angle" not in out.columns:
        raise SystemExit(
            "ABORTING: bulk statcast() did not return 'launch_speed_angle'.\n"
            "  Barrels come from Statcast's own launch_speed_angle == 6 bucket.\n"
            "  Without it every batter would be written with ZERO barrels — a\n"
            "  plausible-looking value that silently drives HR Score's POWER\n"
            "  axis to nothing. Refusing to build an archive.\n"
            "  Check for a pybaseball release that changed the bulk column set;\n"
            "  requirements.txt pins the version known to return it."
        )
    return out


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

    Raises on a SCALAR input. df.get("missing_col") returns None, and
    pd.to_numeric(None, errors="coerce") == 6 quietly evaluates to a
    scalar numpy False rather than raising. Passed through here it would
    broadcast to every row and read as "no row qualifies" — zero barrels
    league-wide, written out as a real 0.0. A comparison that was supposed
    to be per-row collapsing to one value is always a bug, never a
    legitimate mask, so it stops here instead of reaching the parquet.
    """
    if np.isscalar(series) or isinstance(series, (bool, np.bool_)):
        raise TypeError(
            f"_mask() got scalar {series!r} instead of a per-row Series. This "
            f"means a source column was MISSING: DataFrame.get returned None "
            f"and the comparison collapsed to a single value. Broadcasting it "
            f"would silently mark every row False."
        )
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


def build_baselines(season_df: pd.DataFrame) -> bool:
    """Measure what a RANDOM starting hitter does, league-wide.

    WHY THIS EXISTS. A board that reports "65% got a hit" tells you
    nothing on its own, because the league-average starter also gets a
    hit most nights. Without the baseline beside it, a number that merely
    matches chance reads as a winning model — which is the most expensive
    kind of false confidence a tool like this can create.

    Every rate here is MEASURED from the same league-wide pitch data the
    picks are built from. Nothing is asserted, assumed, or copied from a
    reference site: if the number moves, it moved because the league
    moved.

    Definition, kept deliberately strict: a "player-game" is one batter
    in one game with at least one plate appearance that reached a
    terminal event. That's the same population the boards pick from, so
    the comparison is like-for-like. It is NOT every batter on the roster
    and not pinch-hit cameos with a single PA — including those would
    depress the baseline and flatter every board.
    """
    need = {"batter", "game_pk", "events"}
    if not need.issubset(season_df.columns):
        print("  Baselines skipped — missing required columns.")
        return False

    df = season_df[season_df["events"].notna()].copy()
    if df.empty:
        print("  Baselines skipped — no terminal events in the pull.")
        return False

    ev = df["events"].astype(str)
    df["_hit"] = ev.isin(["single", "double", "triple", "home_run"])
    df["_hr"] = ev.eq("home_run")
    df["_xbh"] = ev.isin(["double", "triple", "home_run"])

    g = df.groupby(["batter", "game_pk"]).agg(
        pa=("events", "size"), hit=("_hit", "max"),
        hr=("_hr", "max"), xbh=("_xbh", "max"))

    # 3+ PA ≈ someone who actually started. A 1-PA pinch hitter is not
    # the population any board picks from, and counting them would drag
    # every baseline down and make the boards look better than they are.
    starters = g[g["pa"] >= 3]
    if len(starters) < 500:
        print(f"  Baselines skipped — only {len(starters)} player-games.")
        return False

    out = {
        "hits": round(float(starters["hit"].mean()) * 100, 1),
        "homeRuns": round(float(starters["hr"].mean()) * 100, 1),
        "xbh": round(float(starters["xbh"].mean()) * 100, 1),
        "player_games": int(len(starters)),
        "min_pa": 3,
        "note": ("Share of league player-games (3+ PA) with at least one of "
                 "each outcome, measured from this season's own Statcast "
                 "pitch data."),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "baselines.json").write_text(json.dumps(out, indent=2))
    print(f"  Baselines: hit {out['hits']}% · HR {out['homeRuns']}% · "
          f"XBH {out['xbh']}% over {out['player_games']:,} player-games")
    return True


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

    # ------------------------------------------------------------
    # SAMPLE-SIZE REGRESSION
    #
    # A raw rate off 55 plate appearances is not comparable to one off
    # 450, but percentile ranking treats them as if it were. A hitter who
    # happened to barrel four of his first fifty balls posts a Brl/PA in
    # the top percentile and outranks bats with ten times the evidence —
    # noise sorted as signal, landing at the top of a board.
    #
    # Every rate is pulled toward the league mean in proportion to how
    # thin its sample is:
    #
    #     regressed = (observed + k * league_rate) / (n + k)
    #
    # k is the "regression constant": the number of additional
    # league-average opportunities added to every hitter. At n = k a
    # rate sits halfway between the player and the league; as n grows the
    # player's own evidence takes over. This is the standard treatment
    # and it changes the ORDER of the board, not just the numbers —
    # thin-sample outliers fall back toward the middle where they belong,
    # and hitters with real track records rise.
    #
    # The constants below are set near the sample sizes at which these
    # rates are generally considered to stabilize. They are a considered
    # starting point, NOT fitted against outcomes — like the HR Score
    # weights, they should be refit once calibration has graded history.
    # Being explicit about that is the point: a wrong-but-labelled
    # constant is fixable, a hidden one is not.
    K_BRL_PA = 170      # plate appearances
    K_WINDOW = 110      # batted balls
    K_PULL_AIR = 110    # batted balls

    def _regress(made, opp, k):
        """Rate per 100, pulled toward the league mean by sample size."""
        league = made.sum() / opp.sum()          # real league rate, measured
        return (made + k * league) / (opp + k) * 100

    out["brl_per_pa"] = _regress(out["barrel"], out["pa"], K_BRL_PA)
    out["hr_window_pct"] = _regress(out["window"], out["bbe"], K_WINDOW)
    out["pull_air_pct"] = _regress(out["pullair"], out["bbe"], K_PULL_AIR)

    # Raw, unregressed rates kept alongside for DISPLAY. The regressed
    # values are what get ranked; the raw ones are what a hitter actually
    # did, and hiding them would be its own kind of dishonesty.
    out["brl_per_pa_raw"] = out["barrel"] / out["pa"] * 100
    out["hr_window_pct_raw"] = out["window"] / out["bbe"] * 100
    out["pull_air_pct_raw"] = out["pullair"] / out["bbe"] * 100

    # HR Intent — same three process inputs and the same league anchors
    # as statcast_engine, averaged over whatever is measurable.
    # Built on the REGRESSED rates on purpose. Intent feeds a ranked
    # percentile like everything else, so a thin-sample hitter would
    # otherwise import exactly the noise the regression above removes.
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


# ------------------------------------------------------------
# HR PARK FACTORS, BY BATTER HANDEDNESS
# ------------------------------------------------------------
# Measured from this season's own batted balls, not imported.
#
# WHY NOT engines/park_factors.py: that table is the OVERALL, wOBA-based
# park factor — "how much offense in general" — and its own docstring
# says so. Home runs don't follow overall offense, and the two hands
# don't follow each other.
#
# Fenway is the clearest case. It rates ~102 for offense, which reads
# mildly friendly. But the Green Monster is 310 feet away and 37 feet
# TALL, so for a right-handed pull hitter it converts home runs into
# doubles — great for offense, actively bad for homers — while right
# field is deep. Yankee Stadium is the mirror image: 314 to the
# right-field pole hands left-handed pull power a boost righties never
# see. One number per park cannot express either.
#
# Method: HR per batted ball, per (park, batter hand), indexed against
# the league rate for that hand. 100 = neutral, 120 = 20% more home runs
# than average for that hand. Indexing WITHIN hand matters — lefties and
# righties don't homer at the same base rate, and comparing across them
# would smuggle that difference in as a park effect.
#
# This is a raw venue rate, not a park factor in the strict sabermetric
# sense (no home/road split to control for which hitters play there
# most). Coors will read high partly because Rockies hitters bat there
# and are built for it. Treated as a bounded adjustment rather than a
# multiplier, that bias is acceptable; it would not be if this were
# multiplied into a projection.
PARK_MIN_BBE = 300        # per park-hand cell; below this it's noise


def build_park_hr_factors(season_df: pd.DataFrame) -> bool:
    need = {"home_team", "stand", "events", "type"}
    if not need.issubset(season_df.columns):
        print("  Park HR factors skipped — missing home_team/stand.")
        return False

    bbe = season_df[_mask(season_df["type"] == "X")]
    if bbe.empty:
        print("  Park HR factors skipped — no batted balls.")
        return False

    work = pd.DataFrame({
        "park": bbe["home_team"].astype(str),
        "hand": bbe["stand"].astype(str),
        "hr": _mask(bbe["events"].astype(str) == "home_run").astype("int32"),
    })
    work = work[work["hand"].isin(["R", "L"])]

    g = work.groupby(["park", "hand"], observed=True)["hr"].agg(["sum", "count"])
    g = g[g["count"] >= PARK_MIN_BBE]
    if g.empty:
        print("  Park HR factors skipped — no park-hand cell cleared the floor.")
        return False
    g["hr_rate"] = g["sum"] / g["count"]

    # League baseline PER HAND, so the index isolates the park.
    league = work.groupby("hand", observed=True)["hr"].mean()
    g = g.reset_index()
    g["league_rate"] = g["hand"].map(league)
    g["hr_index"] = (g["hr_rate"] / g["league_rate"] * 100).round(1)

    out = g[["park", "hand", "hr_index", "count"]]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DATA_DIR / "park_hr_factors.parquet", index=False)
    spread = out.groupby("park")["hr_index"].apply(lambda x: x.max() - x.min())
    widest = spread.idxmax() if len(spread) else None
    print(f"  Park HR factors: {len(out)} park-hand cells"
          + (f"; widest L/R split at {widest} ({spread.max():.0f} pts)" if widest else ""))
    return True


# ------------------------------------------------------------
# LEAGUE HR RATE BY PITCH TYPE
# ------------------------------------------------------------
# The one input in the pitch matchup that is effectively exact: tens of
# thousands of batted balls per pitch type across the league. Measured
# from this season's own data, so it tracks whatever the league is
# actually doing rather than an imported constant.
#
# This exists so the matchup NEVER has to use a pitcher's own HR rate per
# pitch type — a starter throws ~250 sliders and allows two homers on
# them, and a two-event rate is a coin flip wearing a decimal point.
PITCH_TYPE_MIN_BBE = 500


def build_pitch_type_hr(season_df: pd.DataFrame) -> bool:
    need = {"pitch_type", "events", "type"}
    if not need.issubset(season_df.columns):
        print("  Pitch-type HR rates skipped — missing pitch_type/events.")
        return False

    bbe = season_df[_mask(season_df["type"] == "X")]
    if bbe.empty:
        print("  Pitch-type HR rates skipped — no batted balls.")
        return False

    work = pd.DataFrame({
        "pitch_type": bbe["pitch_type"].astype(str),
        "hr": _mask(bbe["events"].astype(str) == "home_run").astype("int32"),
        # League BARREL rate per pitch type, alongside the HR rate. This
        # is the baseline a hitter's own per-pitch barrel rate gets
        # regressed toward — measured here rather than assumed, so no
        # constant has to be carried in the app.
        "brl": _mask(pd.to_numeric(bbe.get("launch_speed_angle"),
                                   errors="coerce") == 6).astype("int32"),
    })
    work = work[work["pitch_type"].notna() & (work["pitch_type"] != "nan")]
    g = work.groupby("pitch_type", observed=True).agg(
        hr_sum=("hr", "sum"), brl_sum=("brl", "sum"), count=("hr", "count"))
    g = g[g["count"] >= PITCH_TYPE_MIN_BBE]
    if g.empty:
        print("  Pitch-type HR rates skipped — no pitch cleared the floor.")
        return False
    g["hr_rate"] = g["hr_sum"] / g["count"]
    g["brl_rate"] = g["brl_sum"] / g["count"]

    out = g.reset_index()[["pitch_type", "hr_rate", "brl_rate", "count"]]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DATA_DIR / "pitch_type_hr.parquet", index=False)
    top = out.sort_values("hr_rate", ascending=False).iloc[0]
    print(f"  Pitch-type HR rates: {len(out)} pitch types "
          f"(most homer-prone: {top.pitch_type} at {top.hr_rate*100:.2f}%)")
    return True


# ------------------------------------------------------------
# PLATE APPEARANCES PER TEAM-GAME
# ------------------------------------------------------------
# The input behind lineup-slot opportunity, MEASURED rather than assumed.
#
# Every metric on this site describes how good a swing is. None of them
# describes how many times a hitter gets to take it — and a leadoff bat
# comes up meaningfully more often than a 9-hole bat. Home run
# probability scales almost linearly with plate appearances, so ignoring
# that means correctly ranking a 9-hole hitter above a leadoff hitter on
# skill while being wrong about who is likelier to go deep tonight.
#
# Rather than hardcode a table of "expected PA by slot", this measures
# the one real quantity the arithmetic needs: how many plate appearances
# a team actually gets in a game. Slot expectations then follow exactly —
# with T plate appearances spread over nine slots, slot i gets
# ceil((T - i + 1) / 9), because the order simply wraps. No constants, no
# estimates; the number tracks whatever the league is really doing, and
# a low-scoring era or a rules change moves it on its own.
#
# A PA is one at_bat_number within one game_pk for one batting side.
def build_pitcher_allowed_percentiles(season_df: pd.DataFrame) -> bool:
    """League percentile cut points for contact ALLOWED by pitchers.

    WHY: the HR Vulnerability card shows one pitcher, one row. Colouring a
    cell means grading it, and grading needs something to compare
    against — within a single row there is nothing, so every cell fell
    back to one flat shade. The comparison that actually answers "is this
    bad?" is against OTHER PITCHERS, which is exactly what this builds.

    For each metric, stores the value at each decile across every pitcher
    with a real sample. The app finds where tonight's starter sits in that
    distribution and colours by tier — so gold means "he allows more
    barrels than most pitchers", a claim backed by the league itself
    rather than by a threshold someone picked.

    MIN_BBE keeps a reliever with nine batted balls out of the
    distribution; a percentile built on noise would grade everyone
    against noise.
    """
    need = {"pitcher", "type", "launch_speed", "launch_angle", "events"}
    if not need.issubset(season_df.columns):
        print("  Pitcher percentiles skipped — missing required columns.")
        return False

    MIN_BBE = 50
    bbe = season_df[season_df["type"] == "X"].copy()
    if bbe.empty:
        print("  Pitcher percentiles skipped — no batted balls.")
        return False

    ls = pd.to_numeric(bbe["launch_speed"], errors="coerce")
    la = pd.to_numeric(bbe["launch_angle"], errors="coerce")
    bbe["_hh"] = _mask(ls >= 95)
    bbe["_fb"] = _mask(bbe.get("bb_type").astype(str) == "fly_ball") \
        if "bb_type" in bbe.columns else False
    bbe["_hrw"] = _mask((la >= 20) & (la <= 40))
    if "launch_speed_angle" in bbe.columns:
        bbe["_brl"] = _mask(pd.to_numeric(bbe["launch_speed_angle"],
                                          errors="coerce") == 6)
    else:
        # Same rule as the engine: barrels are MEASURED or absent. No
        # derived approximation ever enters a league distribution.
        print("  Pitcher percentiles: no launch_speed_angle, Brl% omitted.")
        bbe["_brl"] = None
    bbe["_ls"] = ls

    g = bbe.groupby("pitcher")
    agg = pd.DataFrame({
        "bbe": g.size(),
        "HH % Allowed": g["_hh"].mean() * 100,
        "FB % Allowed": g["_fb"].mean() * 100,
        "HRWindow % Allowed": g["_hrw"].mean() * 100,
        "EV90 Allowed": g["_ls"].quantile(0.90),
    })
    if bbe["_brl"] is not None and "_brl" in bbe.columns and bbe["_brl"].notna().any():
        agg["Brl % Allowed"] = g["_brl"].mean() * 100
    agg = agg[agg["bbe"] >= MIN_BBE]
    if len(agg) < 50:
        print(f"  Pitcher percentiles skipped — only {len(agg)} qualified.")
        return False

    out = {"n_pitchers": int(len(agg)), "min_bbe": MIN_BBE, "deciles": {}}
    for col in agg.columns:
        if col == "bbe":
            continue
        vals = agg[col].dropna()
        if vals.empty:
            continue
        out["deciles"][col] = [round(float(vals.quantile(q / 10.0)), 3)
                               for q in range(11)]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "pitcher_allowed_pct.json").write_text(json.dumps(out, indent=2))
    print(f"  Pitcher percentiles: {len(out['deciles'])} metrics over "
          f"{len(agg):,} qualified pitchers")
    return True


def build_pitcher_roles(season_df: pd.DataFrame) -> bool:
    """Precompute SP/RP for every pitcher in one pass.

    WHY: get_pitcher_role() derives the role from the median of each
    pitcher's first at_bat_number per game — cheap arithmetic, but it was
    loading that pitcher's FULL SEASON dataframe to do it, one pitcher at
    a time. The slate-wide bullpen baseline runs it across every team's
    roster, so the first MLB page load of the day was paying for a few
    hundred separate dataframe loads before anything rendered.

    The whole league is already in memory here. One groupby produces every
    role at once, and the app reads a small JSON instead.

    Same rule as the engine: fewer than 3 outings means the role is
    UNKNOWN and the pitcher is left out entirely, rather than guessed at.
    """
    need = {"pitcher", "game_pk", "at_bat_number"}
    if not need.issubset(season_df.columns):
        print("  Pitcher roles skipped — missing required columns.")
        return False

    df = season_df[["pitcher", "game_pk", "at_bat_number"]].dropna()
    if df.empty:
        print("  Pitcher roles skipped — no rows.")
        return False

    # First batter each pitcher faced in each game.
    firsts = df.groupby(["pitcher", "game_pk"])["at_bat_number"].min().reset_index()
    agg = firsts.groupby("pitcher")["at_bat_number"].agg(["median", "count"])
    agg = agg[agg["count"] >= 3]

    # <= 9 means he was in from the top of the order: a starter.
    roles = {str(int(pid)): ("SP" if row["median"] <= 9 else "RP")
             for pid, row in agg.iterrows()}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "pitcher_roles.json").write_text(json.dumps(roles))
    sp = sum(1 for v in roles.values() if v == "SP")
    print(f"  Pitcher roles: {len(roles):,} pitchers ({sp} SP, {len(roles)-sp} RP)")
    return True


def build_pa_per_game(season_df: pd.DataFrame):
    """League mean plate appearances per team-game, or None."""
    need = {"game_pk", "at_bat_number", "home_team", "events"}
    if not need.issubset(season_df.columns):
        print("  PA/game skipped — missing game_pk/at_bat_number.")
        return None

    df = season_df[_mask(season_df["events"].notna())]
    if df.empty:
        print("  PA/game skipped — no terminal events.")
        return None

    # One row per completed plate appearance.
    pa = df.drop_duplicates(subset=["game_pk", "at_bat_number"])
    # Two batting sides per game, so team-games = games x 2.
    games = pa["game_pk"].nunique()
    if not games:
        return None
    per_team_game = len(pa) / (games * 2.0)
    if not (25.0 < per_team_game < 60.0):
        # Outside this band the calculation is wrong, not the league.
        print(f"  PA/game skipped — implausible value {per_team_game:.1f}.")
        return None
    print(f"  PA per team-game: {per_team_game:.2f} "
          f"(from {len(pa):,} PA across {games:,} games)")
    return round(per_team_game, 2)


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

    print("Measuring league baselines (what a random starter does)...")
    build_baselines(season_df)

    print("Building league-wide HR metrics...")
    hrm_ok = build_hr_metrics(season_df)

    print("Building pitcher allowed-contact percentiles...")
    build_pitcher_allowed_percentiles(season_df)

    print("Precomputing pitcher roles (SP/RP)...")
    build_pitcher_roles(season_df)

    print("Measuring plate appearances per team-game...")
    pa_per_game = build_pa_per_game(season_df)

    print("Building HR park factors by handedness...")
    park_ok = build_park_hr_factors(season_df)

    print("Building league HR rates by pitch type...")
    pt_ok = build_pitch_type_hr(season_df)

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
        "park_hr_factors_included": park_ok,
        "pitch_type_hr_included": pt_ok,
        # Measured, not assumed — see build_pa_per_game.
        "pa_per_team_game": pa_per_game,
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Manifest:", json.dumps(manifest, indent=2))

    # Calibration is NOT graded here any more.
    #
    # It used to be, as `import calibration_pipeline; main()` wrapped in
    # `except Exception: print(...)`. Two ways that lost days of grading,
    # both silent and both leaving the CI job green:
    #
    #   1. The except swallowed every failure. A broken grader printed
    #      one line into a log nobody reads and the run still succeeded.
    #   2. This line sits at the END of a ~15-minute, half-a-million-pitch
    #      Statcast fetch. Any failure upstream of here — a Savant
    #      timeout, a pybaseball change, an OOM — meant grading never ran
    #      AT ALL that day, even though grading needs nothing from the
    #      fetch but a list of picks and MLB's box scores.
    #
    # It is now its own step in nightly-data.yml, running BEFORE the
    # fetch and failing the job loudly if it breaks. build_data/ is never
    # wiped, so the record it writes to build_data/data/calibration.json
    # is still sitting there for the tar below to pack into the archive.
    print("Packaging archive...")
    with tarfile.open(ARCHIVE, "w:gz") as tar:
        tar.add(OUT_ROOT / "data", arcname="data")
    print(f"Wrote {ARCHIVE} ({ARCHIVE.stat().st_size / 1024**2:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
