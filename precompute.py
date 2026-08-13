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

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from engines.hr_floors import FLOOR_SPECS, BASELINE_KEY  # noqa: E402

import numpy as np
import pandas as pd
import requests
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
    # THREE COLUMNS ADDED 2026-08-13, none used yet, all needed BEFORE
    # the next pull because they only populate going forward.
    #
    # swing_length — the other half of Statcast's bat tracking, beside
    #   bat_speed. Bat speed and swing length barely move year to year
    #   for almost every hitter, which is exactly why a CHANGE in them
    #   means something real: an offseason rebuild, an injury, aging.
    #   Intended as a rare "swing changed" flag, not a nightly column.
    #
    # bat_score / post_bat_score — the batting team's score before and
    #   after a plate appearance. The delta on the PA-ending pitch IS the
    #   RBI count, which is the only one of the requested prop columns
    #   that was missing for a fixable reason. (Runs are not recoverable
    #   from a pitch feed at all: nothing in these rows says whether the
    #   batter later crossed the plate.)
    "swing_length", "bat_score", "post_bat_score",
]
ID_COLS = ["batter", "pitcher"]
CATEGORY_COLS = ["type", "events", "description", "bb_type", "stand"]

OUT_ROOT = Path("build_data")
DATA_DIR = OUT_ROOT / "data" / "statcast"
ARCHIVE = Path("statcast_data.tar.gz")

# MUST STAY IDENTICAL to statcast_engine._OUT_EVENTS.
#
# build_bullpen_profiles estimates innings the same way the engine does
# (outs / 3 from terminal PA events), and the app pools precomputed pen
# numbers against live-computed ones whenever a team is missing from the
# nightly file. If the two definitions drift, the slate baseline quietly
# shifts depending on which path built it — a bug with no visible symptom
# beyond "the edges look different today". tests/test_baselines.py pins
# this equality.
_OUT_EVENTS = {
    "field_out", "strikeout", "strikeout_double_play", "double_play",
    "grounded_into_double_play", "force_out", "fielders_choice_out",
    "sac_fly", "sac_bunt", "triple_play", "field_error",
}


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

# Clears Anywhere thresholds. Deliberately strict: this metric's whole
# claim is "this gets out of ANY park", so a bucket that only mostly
# gets out does not belong in it.
CA_MIN_PROB = 0.90       # 90%+ of this bucket's contact left the yard
CA_MIN_PARKS = 28        # seen in essentially every park, and out of all
                         # of them. Not 30: a bucket can legitimately go
                         # unseen in a park or two over one season, and
                         # demanding a literal 30 would throw away real
                         # qualifying trajectories on a sampling accident.


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
    # Venue rides along so the "clears anywhere" flag below can be
    # VERIFIED rather than asserted. home_team identifies the park in
    # Statcast's pitch data and is already in the pull (see line 49).
    if "home_team" in bbe.columns:
        grid["park"] = bbe["home_team"].astype(str).values

    agg = grid.groupby(["ev_bin", "la_bin"], observed=True)["is_hr"].agg(["sum", "count"])
    agg = agg[agg["count"] >= XHR_MIN_BUCKET_N]
    if agg.empty:
        print("  xHR table skipped — no bucket cleared the sample floor.")
        return False
    agg["hr_prob"] = (agg["sum"] / agg["count"]).astype("float32")

    # ------------------------------------------------------------
    # CLEARS ANYWHERE — the launch floor that gets out of all 30 parks
    #
    # There is no single launch angle that clears every fence, because
    # the angle required depends on exit velocity: ~28 degrees at 95 mph,
    # ~18 at 110. The floor is a curve, and this is that curve, measured
    # instead of modelled.
    #
    # The alternative was a hand-built table of fence distances and wall
    # heights plus a drag-and-lift trajectory model. That produces an
    # ESTIMATE, and an estimate is the one thing the boards on this site
    # promise never to show. This grid is already averaged over all 30
    # parks — every batted ball in the league, wherever it was struck —
    # so a bucket sitting at 95% did not merely leave somewhere, it left
    # nearly everywhere it was hit. That contour IS the all-parks floor
    # and it was already in this file.
    #
    # Two conditions, both required:
    #
    #   hr_prob >= CA_MIN_PROB   most balls of this shape leave. On its
    #                            own this is not enough: a bucket can
    #                            record one homer in each of 30 parks
    #                            while most of its contact stays in.
    #   every park that saw contact in this bucket also saw it LEAVE,
    #   across at least CA_MIN_PARKS parks. This is the literal claim —
    #   "gets out of all 30" verified against 30 actual venues, not
    #   inferred from geometry.
    #
    # Parks are not sampled evenly (a Rockies hitter takes a large share
    # of his cuts at Coors), which is exactly why the park count is
    # checked per bucket rather than trusted from the league average.
    ca_flag = pd.Series(False, index=agg.index)
    parks_seen = pd.Series(0, index=agg.index, dtype="int16")
    parks_out = pd.Series(0, index=agg.index, dtype="int16")

    if "park" in grid.columns:
        by_park = grid.groupby(["ev_bin", "la_bin"], observed=True)["park"]
        parks_seen = by_park.nunique().reindex(agg.index).fillna(0).astype("int16")
        hr_rows = grid[grid["is_hr"] == 1]
        parks_out = (hr_rows.groupby(["ev_bin", "la_bin"], observed=True)["park"]
                     .nunique().reindex(agg.index).fillna(0).astype("int16"))
        ca_flag = ((agg["hr_prob"] >= CA_MIN_PROB)
                   & (parks_seen >= CA_MIN_PARKS)
                   & (parks_out >= parks_seen))
    else:
        print("  clears-anywhere flag skipped — home_team absent from the pull.")

    agg["parks_seen"] = parks_seen
    agg["parks_out"] = parks_out
    agg["clears_anywhere"] = ca_flag.astype(bool)

    out = agg.reset_index()[["ev_bin", "la_bin", "hr_prob",
                             "parks_seen", "parks_out", "clears_anywhere"]]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DATA_DIR / "xhr_table.parquet", index=False)
    print(f"  xHR table: {len(out):,} buckets from {len(bbe):,} batted balls "
          f"({int(grid['is_hr'].sum()):,} home runs)")
    _ca = out[out["clears_anywhere"]]
    if len(_ca):
        # Printed every night on purpose. If this contour drifts — a
        # juiced ball, a humidor, a fence moved — the log says so, and
        # nothing downstream has to be edited to follow it.
        print(f"  Clears Anywhere: {len(_ca)} buckets qualify "
              f"(EV {_ca['ev_bin'].min():.0f}+ mph, LA "
              f"{_ca['la_bin'].min():.0f}-{_ca['la_bin'].max():.0f} deg, "
              f"verified across {int(_ca['parks_out'].min())}-"
              f"{int(_ca['parks_out'].max())} parks)")
    else:
        print("  Clears Anywhere: no bucket qualified — metric reports N/A, "
              "not zero.")
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

# TRACKED batted balls — the ones Statcast measured an exit velocity AND
# a launch angle for. Every xHR-derived figure is computed over these and
# only these. An untracked ball used to bin to NaN, miss the grid merge,
# and take a filled-in hr_prob of 0.0 — scoring contact nobody measured
# as contact that had no chance of leaving, while it still sat in the
# denominator. Missing is not zero; this file already applies that rule
# to `ca` and to pull_air, and the xHR path was the one place it leaked.
HRM_MIN_TRACKED_BBE = 25

# The population that DEFINES the percentile scale.
#
# Inclusion (HRM_MIN_PA above) is deliberately low so a bench bat in
# tonight's lineup still gets a score. But ranking everyone against
# everyone let several hundred thin bats — all pulled to the league mean
# by the regression below, by construction — pile up in the middle of
# every distribution. A dense middle stretches the tails, so a regular
# was reading a percentile earned partly by being compared against
# part-timers who had been shrunk to average on purpose.
#
# Scale comes from regulars. Thin bats are PLACED on that scale rather
# than allowed to reshape it, so they still rank and still rank fairly.
HRM_CORE_PA = 150

# Which hr_metrics column carries each floor's profile key.
#
# DELIBERATELY PARTIAL. HH %, FB %, Blast %, ISO and AvgEV are computed
# in statcast_engine's per-player profile and have no column in this
# table, so their floors keep the fallback in engines/hr_floors.py until
# they do. Listing only what is genuinely measurable here is the point:
# a mapping that guessed at a column name would publish a floor built
# from the wrong stat, which is exactly the failure the EV90-vs-AvgEV
# mix-up already caused once.
_FLOOR_COLUMNS = {
    "Brl %": "brl_pct_raw",
    "Brl/PA": "brl_per_pa_raw",
    "PullAir %": "pull_air_pct_raw",
}


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

    # League HR/FB — the last asserted constant in the scoring engines.
    #
    # slam_engine and top_plays both scaled a batter's HR/FB against a
    # hardcoded 11.5. That number is close to reality, but it was typed in
    # rather than measured, so it silently went stale as the league moved
    # and nothing in the app could tell. Every other anchor on this site
    # is measured; this was the last one that wasn't.
    #
    # Definition: home runs divided by FLY BALLS, league-wide. Fly balls
    # only — the standard denominator. Returns None if bb_type is absent,
    # and the engines keep their literal fallback in that case rather than
    # scoring against nothing.
    _hr_fb = None
    if "bb_type" in season_df.columns:
        _bb = season_df[season_df["type"] == "X"]
        _fb_n = int((_bb["bb_type"].astype(str) == "fly_ball").sum())
        if _fb_n >= 1000:      # a season has tens of thousands; guard a partial pull
            _hr_n = int((_bb["events"].astype(str) == "home_run").sum())
            _hr_fb = round(_hr_n / _fb_n * 100, 2)

    out = {
        "hits": round(float(starters["hit"].mean()) * 100, 1),
        "homeRuns": round(float(starters["hr"].mean()) * 100, 1),
        "xbh": round(float(starters["xbh"].mean()) * 100, 1),
        "hrPerFlyBall": _hr_fb,
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
    print(f"  League HR/FB: {out['hrPerFlyBall']}%"
          if out["hrPerFlyBall"] is not None else
          "  League HR/FB: not measurable (bb_type absent)")
    return True


# The per-game stat lines the Research page reads.
#
# ONE ROW PER PLAYER PER GAME, not per player per threshold. That is the
# whole design decision here.
#
# The obvious build is to pre-bake rates — "cleared 1+ hit in 8 of his
# last 10" — but a rate needs a THRESHOLD, and baking one in means the
# page can only ever ask the question this file decided to ask. Storing
# the game lines instead lets the reader move the threshold live: 1+
# hit, 2+ hits, 2+ total bases, all off the same table, none of it
# recomputed nightly when someone changes their mind.
#
# It is also small. ~1,400 players x ~110 games x 8 integers is a few
# megabytes, against a batter-file directory already in the hundreds.
RATE_STATS = ("hits", "tb", "hr", "singles", "doubles", "triples", "k")


def build_player_game_logs(season_df: pd.DataFrame) -> bool:
    """Per-player per-game batting lines -> player_game_logs.parquet.

    NOT RBIs, and not runs. See the module notes: RBIs need bat_score and
    post_bat_score, which ENGINE_COLS does not carry yet; runs are not
    recoverable from a pitch feed at all except on a home run, because
    nothing in these rows says whether the batter later scored.

    Both are omitted rather than approximated. A "runs" column built by
    guessing would be the most convincing wrong number on the page.
    """
    need = {"batter", "game_date", "events"}
    if not need.issubset(season_df.columns):
        print(f"  player game logs: missing {sorted(need - set(season_df.columns))}")
        return False

    ev = season_df["events"].astype(str)
    # events is non-null only on the pitch that ENDS a plate appearance,
    # so counting these rows counts PAs, not pitches.
    is_pa = _mask(season_df["events"].notna())

    work = pd.DataFrame({
        "batter": season_df["batter"],
        "game_date": season_df["game_date"].astype(str).str[:10],
        "pa": is_pa.astype("int32"),
        "singles": _mask(ev == "single").astype("int32"),
        "doubles": _mask(ev == "double").astype("int32"),
        "triples": _mask(ev == "triple").astype("int32"),
        "hr": _mask(ev == "home_run").astype("int32"),
        # Both strikeout events. strikeout_double_play is still a
        # strikeout for the batter and a prop that pays on it counts it;
        # dropping it would quietly understate every K rate.
        "k": _mask(ev.isin(["strikeout", "strikeout_double_play"])).astype("int32"),
    })
    work["hits"] = (work["singles"] + work["doubles"]
                    + work["triples"] + work["hr"])
    work["tb"] = (work["singles"] + 2 * work["doubles"]
                  + 3 * work["triples"] + 4 * work["hr"])

    out = (work.groupby(["batter", "game_date"], observed=True)
               .sum().reset_index())
    out = out[out["pa"] > 0]
    # A game with no plate appearance is not a zero — it is an absence,
    # and a rate that counts it as a miss punishes a hitter for resting.
    out = out.sort_values(["batter", "game_date"])

    out.to_parquet(DATA_DIR / "player_game_logs.parquet", index=False)
    _games = out.groupby("batter", observed=True).size()
    print(f"  player game logs: {len(out):,} lines across "
          f"{out['batter'].nunique():,} batters "
          f"(median {int(_games.median())} games each)")
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
    # TRACKED CONTACT — see HRM_MIN_TRACKED_BBE. A batted ball with no
    # exit velocity or no launch angle cannot be binned into the xHR
    # grid, and it must not be counted as a ball that had no chance.
    is_tracked = _mask(is_bbe & ev.notna() & la.notna())

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
        # FB95: hard-hit fly balls. HH% and FB% each existed alone; the
        # intersection is the one that predicts home runs. A 95 mph
        # ground ball and a 78 mph fly ball each inflate one parent rate
        # without being a home-run trajectory.
        "fb95": _mask(is_bbe & _mask(df.get("bb_type") == "fly_ball")
                      & _mask(ev >= 95.0)).astype("int32"),
        "pullair": is_pull_air.astype("int32"),
        "hr": _mask(df["events"].astype(str) == "home_run").astype("int32"),
        "bbe_tracked": is_tracked.astype("int32"),
        # Home runs on TRACKED contact only. The xHR gap subtracts actual
        # home runs from expected ones, and expected is summed over
        # tracked balls — so an untracked home run used to land in the
        # subtrahend with nothing on the other side of it, pushing the
        # gap negative for a hitter who did nothing wrong.
        "hr_tracked": _mask(is_tracked
                            & _mask(df["events"].astype(str) == "home_run")
                            ).astype("int32"),
        "ev": ev.where(is_bbe),
        "bat_speed": pd.to_numeric(df.get("bat_speed"), errors="coerce"),
    })
    g = work.groupby("batter", observed=True)
    out = g[["pa", "bbe", "barrel", "window", "fb95", "pullair", "hr",
             "bbe_tracked", "hr_tracked"]].sum()
    out["ev90"] = g["ev"].quantile(0.90)
    out["max_ev"] = g["ev"].max()
    out["bat_speed"] = g["bat_speed"].mean()
    out = out[(out["pa"] >= HRM_MIN_PA) & (out["bbe"] >= HRM_MIN_BBE)]
    if out.empty:
        print("  HR metrics skipped — no batter cleared the sample floor.")
        return False

    # xHR and Clears Anywhere from the same empirical grid, so the app
    # and the build agree. Both come off one merge — the grid carries
    # hr_prob and the verified clears_anywhere flag in the same rows.
    xhr_path = DATA_DIR / "xhr_table.parquet"
    ca_measured = False
    if xhr_path.exists():
        tbl = pd.read_parquet(xhr_path)
        # TRACKED rows only — an unmeasured ball has no bin, and the
        # `how="left"` merge below turns a missing bin into a missing
        # probability, which the old code then filled with 0.0.
        key = pd.DataFrame({
            "batter": df["batter"],
            "ev_bin": (ev // 2.0 * 2.0),
            "la_bin": (la // 2.0 * 2.0),
        })[is_tracked.values]
        # IN-REGION vs OUT-OF-REGION, and they are not the same miss.
        #
        # build_xhr_table only grids EV 80-122 and LA 8-50, because that
        # is where home runs occur. A tracked ball outside that box — a
        # 71 mph chopper, a 60-degree pop-up — is a REAL zero: the region
        # was chosen precisely because contact outside it does not leave.
        #
        # A ball INSIDE the box whose bucket was dropped for thin sample
        # (XHR_MIN_BUCKET_N) is a different thing: unmeasurable, and
        # those buckets sit at the extremes where probability is HIGHEST.
        # Filling them with zero understated exactly the contact xHR
        # exists to find. They come out of the numerator AND the
        # denominator instead.
        _in_region = (key["ev_bin"].between(XHR_MIN_EV, XHR_MAX_EV)
                      & key["la_bin"].between(XHR_MIN_LA, XHR_MAX_LA))
        merged = key.merge(tbl, on=["ev_bin", "la_bin"], how="left")
        _unmeasurable = merged["hr_prob"].isna() & _in_region.to_numpy()
        merged["hr_prob"] = merged["hr_prob"].fillna(0.0)
        _drop = merged[_unmeasurable].groupby("batter", observed=True).size()
        merged = merged[~_unmeasurable.to_numpy()]

        out["xhr"] = merged.groupby("batter", observed=True)["hr_prob"].sum()
        out["xhr"] = out["xhr"].fillna(0.0)
        # Denominator for every xHR-derived rate: tracked contact we
        # could actually score, not every batted ball he put in play.
        out["bbe_scored"] = (out["bbe_tracked"]
                             - _drop.reindex(out.index).fillna(0)).astype("int32")
        if int(_unmeasurable.sum()):
            print(f"  xHR: {int(_unmeasurable.sum()):,} tracked batted ball(s) "
                  f"in-region with no bucket — excluded, not zeroed")
        # THE regression signal: trajectories that deserved to leave and
        # didn't. Positive = owed home runs. Kept as a raw count for
        # DISPLAY only; what gets ranked is the rate below, because a
        # count carries playing time inside it.
        out["xhr_gap"] = out["xhr"] - out["hr_tracked"]

        # Clears Anywhere: batted balls on a trajectory verified to leave
        # every park. An OLDER parquet has no such column — that means
        # "we cannot tell", so the count stays NaN and every rate built
        # on it stays NaN rather than becoming a fabricated zero.
        if "clears_anywhere" in merged.columns and bool(tbl["clears_anywhere"].any()):
            merged["_ca"] = merged["clears_anywhere"].fillna(False).astype(int)
            out["ca"] = merged.groupby("batter", observed=True)["_ca"].sum()
            out["ca"] = out["ca"].fillna(0).astype("int32")
            ca_measured = True
        else:
            # Column present but NOTHING qualified league-wide, or column
            # absent entirely. Both mean the same thing here: this season
            # has no measurable clears-anywhere contact, so the rate is
            # N/A for everyone and the component drops out of HR Threat
            # rather than scoring the whole league a flat zero. The app
            # applies the identical rule — see clears_anywhere_pct.
            out["ca"] = np.nan
    else:
        out["xhr"] = np.nan
        out["xhr_gap"] = np.nan
        out["ca"] = np.nan
        out["bbe_scored"] = 0

    # THE TRACKED FLOOR. A hitter with a handful of scoreable batted
    # balls has no xHR profile, and every rate built on that denominator
    # must read N/A rather than a number nobody should act on. Applied
    # after the merge so the reason is one place, not three.
    _thin = out["bbe_scored"] < HRM_MIN_TRACKED_BBE
    out.loc[_thin, ["xhr", "xhr_gap", "ca"]] = np.nan

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
    K_FB95 = 110        # batted balls
    K_XHR_GAP = 150     # SCOREABLE batted balls. The gap is a difference
                        # of two counts, so it is noisier per opportunity
                        # than any of the rates below and wants at least
                        # as much shrinkage.
    K_CA = 200          # batted balls. Higher than the rest on purpose:
                        # clears-anywhere contact is RARE (a couple of
                        # grid buckets league-wide), so a hitter with two
                        # of them in 40 batted balls would otherwise post
                        # an untouchable rate off two swings.

    def _regress(made, opp, k):
        """Rate per 100, pulled toward the league mean by sample size.

        A zero league denominator means the metric is unmeasurable for
        everyone (no grid on disk, so no scoreable contact). Return NaN
        rather than dividing by nothing — a numpy warning in the nightly
        log is how a real problem gets read as noise.
        """
        denom = float(opp.sum())
        if not denom:
            return pd.Series(np.nan, index=opp.index, dtype="float64")
        league = made.sum() / denom             # real league rate, measured
        return (made + k * league) / (opp + k) * 100

    out["brl_per_pa"] = _regress(out["barrel"], out["pa"], K_BRL_PA)
    out["hr_window_pct"] = _regress(out["window"], out["bbe"], K_WINDOW)
    out["pull_air_pct"] = _regress(out["pullair"], out["bbe"], K_PULL_AIR)
    out["fb95_pct"] = _regress(out["fb95"], out["bbe"], K_FB95)
    # Denominator is SCOREABLE contact, not every batted ball. `ca` can
    # only ever be counted on a ball that reached the grid, so dividing
    # it by total BBE charged a hitter for contact the metric never had
    # the chance to look at.
    out["clears_anywhere_pct"] = (_regress(out["ca"], out["bbe_scored"], K_CA)
                                  if ca_measured else np.nan)

    # THE CONVERSION SIGNAL, AS A RATE.
    #
    # This was ranked as `xhr - hr`, a count of whole home runs. A count
    # carries playing time inside it: a 550-PA bat can run six either
    # way and a 60-PA bat structurally cannot, so both tails of that
    # percentile were full-timers and part of what the correction
    # rewarded was simply being in the lineup every night. It was also
    # the one figure in this function that skipped the shrinkage every
    # other rate gets.
    #
    # Per SCOREABLE batted ball, not per PA. Contact rate is already
    # inside Brl/PA over in the power axis; putting it in the conversion
    # correction as well would count the same thing twice, which is the
    # exact failure this batch is fixing in hr_score.
    out["xhr_gap_rate"] = _regress(out["xhr"] - out["hr_tracked"],
                                   out["bbe_scored"], K_XHR_GAP)

    # Raw, unregressed rates kept alongside for DISPLAY. The regressed
    # values are what get ranked; the raw ones are what a hitter actually
    # did, and hiding them would be its own kind of dishonesty.
    out["brl_per_pa_raw"] = out["barrel"] / out["pa"] * 100
    # Barrels per BATTED BALL, alongside the per-PA rate above. Not a
    # duplicate: Brl% answers "when he connects, how good is it" and
    # Brl/PA folds in the strikeouts. They are the two floors that do
    # almost all of the cutting in the qualification gate, and the gate
    # cannot measure its own threshold from a column that isn't here.
    out["brl_pct_raw"] = out["barrel"] / out["bbe"] * 100
    out["hr_window_pct_raw"] = out["window"] / out["bbe"] * 100
    out["pull_air_pct_raw"] = out["pullair"] / out["bbe"] * 100
    out["fb95_pct_raw"] = out["fb95"] / out["bbe"] * 100
    out["clears_anywhere_pct_raw"] = (out["ca"] / out["bbe_scored"] * 100
                                      if ca_measured else np.nan)
    # The gap per 100 scoreable batted balls, before shrinkage. This is
    # the figure that is genuinely playing-time neutral — two hitters
    # converting identically post the same number whether one batted 40
    # times or 400. The regressed column above is what gets RANKED, and
    # it deliberately pulls the thinner sample further toward the league;
    # that is shrinkage doing its job, not playing time leaking back in.
    # Keeping both means the difference is visible instead of argued.
    out["xhr_gap_rate_raw"] = ((out["xhr"] - out["hr_tracked"])
                               / out["bbe_scored"].replace(0, np.nan) * 100)

    # HR Intent — same three process inputs and the same league anchors
    # as statcast_engine, averaged over whatever is measurable.
    # Built on the REGRESSED rates on purpose. Intent feeds a ranked
    # percentile like everything else, so a thin-sample hitter would
    # otherwise import exactly the noise the regression above removes.
    # ------------------------------------------------------------
    # LEAGUE ANCHORS — MEASURED, NOT TYPED
    #
    # Every composite below maps "league average" to 50, and the anchors
    # that define league average used to be literals: 71.0 bat speed,
    # 30.0 HR window, 18.0 pull air, and (in statcast_engine) 6.0 Brl/PA
    # and 4.0 clears-anywhere. Two problems with that. They were
    # duplicated between this file and the engine, so the build and the
    # app could silently disagree. And they go stale without saying so —
    # exactly what happened to the hardcoded 11.5 league HR/FB, which
    # build_baselines replaced after measuring the real figure at 17.1.
    #
    # The clears-anywhere anchor was the worst of them: it was set at 4.0
    # before any nightly had run, and the real contour turned out to be
    # so tight that hitters land near a tenth of that. Every hitter would
    # have scored the same near-zero on that component, contributing
    # noise to HRThreat instead of signal.
    #
    # So they are measured here, from the same qualified population the
    # percentiles are built on, and shipped for the app to read. A hitter
    # at the league mean scores exactly 50 by construction, every night,
    # whatever the league does next.
    anchors = {
        "bat_speed": float(out["bat_speed"].mean(skipna=True)),
        "hr_window_pct": float(out["hr_window_pct"].mean()),
        "pull_air_pct": float(out["pull_air_pct"].mean()),
        "brl_per_pa": float(out["brl_per_pa"].mean()),
        "clears_anywhere_pct": (float(out["clears_anywhere_pct"].mean())
                                if ca_measured else None),
        "qualified_batters": int(len(out)),
    }

    def _anchor(name, fallback):
        """Measured anchor, or the old literal if it came back unusable.

        A NaN or zero anchor would divide the whole league to infinity or
        NaN, so the literal survives as a floor. It is a fallback, not a
        default: the log says which one was used.
        """
        v = anchors.get(name)
        if v is None or not np.isfinite(v) or v <= 0:
            print(f"  anchor {name}: unmeasurable, falling back to {fallback}")
            anchors[name] = fallback
            return fallback
        return v

    intent = [
        (out["bat_speed"] / _anchor("bat_speed", 71.0) * 50.0).clip(upper=100),
        (out["hr_window_pct"] / _anchor("hr_window_pct", 30.0) * 50.0).clip(upper=100),
        (out["pull_air_pct"] / _anchor("pull_air_pct", 18.0) * 50.0).clip(upper=100),
    ]
    stacked = pd.concat(intent, axis=1)
    out["hr_intent"] = stacked.mean(axis=1, skipna=True)

    # HR THREAT — 60% direct outcome, 40% HRIntent. Same weights and the
    # same anchors the app uses, so a board built here and a player page
    # rendered live can never disagree.
    #
    # THIS USED TO SAY "40% process" AND THAT WAS NOT WHAT IT DID.
    # HRIntent is the mean of bat speed, HR window % and pull air %, and
    # the last two are outcomes — measurements of batted balls, not of
    # the swing. So the genuinely process-only share of HRThreat is bat
    # speed at 40/3 ≈ 13%, not 40%. The weights are unchanged (the
    # 60/40 outcome lean is the decision); only the label is, because a
    # right number under a wrong label is the one kind of error nobody
    # downstream can catch.
    _threat = [(0.35, (out["brl_per_pa"] / _anchor("brl_per_pa", 6.0)
                       * 50.0).clip(upper=100))]
    if ca_measured:
        _threat.append((0.25, (out["clears_anywhere_pct"]
                               / _anchor("clears_anywhere_pct", 0.5)
                               * 50.0).clip(upper=100)))
    _threat.append((0.40, out["hr_intent"]))
    _wsum = sum(w for w, _ in _threat)
    out["hr_threat"] = sum(w * v for w, v in _threat) / _wsum

    # Shipped alongside the baselines the app already reads.
    _bl_path = DATA_DIR / "baselines.json"
    try:
        _bl = json.loads(_bl_path.read_text()) if _bl_path.exists() else {}
    except Exception:
        _bl = {}
    _bl["hr_anchors"] = {k: (round(v, 3) if isinstance(v, float) else v)
                         for k, v in anchors.items()}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # ------------------------------------------------------------
    # THE QUALIFICATION FLOORS, MEASURED.
    #
    # engines/hr_floors.py stores each floor as the PERCENTILE it was
    # meant to express rather than a typed number, and this is where
    # that percentile becomes tonight's threshold. See that module for
    # why: a literal is a photograph of one season, and a "firm 40%
    # hard-hit" floor set in 2026 is the median in 2026 and below it by
    # 2028, with nothing about the number announcing that the league
    # moved.
    #
    # Measured over the SCALE CORE, not the whole qualified pool. Same
    # reason the percentiles above are: several hundred thin bats all
    # shrunk to the league mean would drag every quantile toward the
    # middle, and a floor is supposed to describe regulars.
    _floor_src = out[out["pa"] >= HRM_CORE_PA]
    if len(_floor_src) < 30:
        _floor_src = out
    _floors = {}
    for _key, _pkey, _pct, _fallback in FLOOR_SPECS:
        if _pct is None:
            continue          # not a percentile floor — see FLOOR_SPECS
        _col = _FLOOR_COLUMNS.get(_pkey)
        _series = (pd.to_numeric(_floor_src.get(_col), errors="coerce").dropna()
                   if _col else None)
        if _series is None or len(_series) < 30:
            continue          # unmeasurable tonight; the fallback stands
        _floors[_key] = float(_series.quantile(_pct))
    if _floors:
        _bl[BASELINE_KEY] = {k: round(v, 3) for k, v in _floors.items()}
        print("  HR floors (measured): "
              + " · ".join(f"{k} {v:.2f}" for k, v in sorted(_floors.items())))
    else:
        print("  HR floors: not enough measured hitters — fallbacks stand.")

    _bl_path.write_text(json.dumps(_bl, indent=2))
    print(f"  HR anchors (league means): bat speed "
          f"{anchors['bat_speed']:.1f} mph · HR window "
          f"{anchors['hr_window_pct']:.1f}% · pull air "
          f"{anchors['pull_air_pct']:.1f}% · Brl/PA "
          f"{anchors['brl_per_pa']:.2f}% · clears anywhere "
          + (f"{anchors['clears_anywhere_pct']:.2f}%"
             if anchors.get("clears_anywhere_pct") else "N/A"))


    # ------------------------------------------------------------
    # RANK TO 0-100 LEAGUE PERCENTILES, matching the Savant scale.
    #
    # Against the CORE population (HRM_CORE_PA), not against everyone in
    # the table. See that constant for why. Everyone still receives a
    # percentile — thin bats are placed on the regulars' scale by
    # searchsorted rather than ranked among themselves.
    _core = out[out["pa"] >= HRM_CORE_PA]

    def _pct_on_core(s):
        """0-100 placement of every value on the CORE distribution."""
        ref = np.sort(_core[s.name].dropna().to_numpy())
        if len(ref) < 30:
            # Not enough regulars to describe a league yet — early April,
            # or a partial pull. Rank within whoever is here and say so,
            # rather than inventing a distribution off a dozen bats.
            return s.rank(pct=True) * 100.0
        vals = s.to_numpy(dtype="float64")
        # side="left" so the core minimum lands at 0 rather than at
        # 1/len — the scale has to start where the league starts.
        pos = np.searchsorted(ref, vals, side="left") / len(ref) * 100.0
        # searchsorted sorts NaN to the top and would hand an unmeasured
        # hitter a 100th percentile. Unmeasured stays unmeasured.
        return pd.Series(np.where(np.isnan(vals), np.nan, pos), index=s.index)

    _ranked = ("brl_per_pa", "hr_window_pct", "pull_air_pct",
               "fb95_pct", "clears_anywhere_pct", "ev90",
               # bat_speed is ranked directly now. hr_score used to take
               # its process input as hr_intent_pct, but HRIntent is two
               # thirds hr_window and pull_air — the same two columns the
               # launch axis already carried — so the score was entering
               # them twice while the docstring claimed the axes were
               # independent. Bat speed is the part of intent that is
               # genuinely not measured anywhere else.
               "bat_speed",
               # hr_intent_pct and hr_threat_pct are PUBLISHED AND READ
               # BY NOTHING as of this change. hr_threat_pct already was
               # — rank_batters reads the raw hr_threat — and hr_intent_pct
               # became so when hr_score stopped taking its process input
               # from HRIntent. Left in rather than deleted: a
               # key-literal grep cannot see a dynamic access, and this
               # repo has already had a sweep wrongly report rendered
               # fields as unrendered for exactly that reason. Check the
               # views for an f-string access before removing them.
               "hr_intent", "hr_threat", "xhr_gap_rate")
    for col in _ranked:
        out[col + "_pct"] = _pct_on_core(out[col])
    if len(_core) < 30:
        print(f"  HR metrics: only {len(_core)} batter(s) at "
              f"{HRM_CORE_PA}+ PA — percentiles ranked within the whole "
              f"pool until the core fills out")

    out = out.reset_index()
    out["batter"] = out["batter"].astype("int64")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DATA_DIR / "hr_metrics.parquet", index=False)
    _bbe_all = int(out["bbe"].sum())
    _bbe_scored = int(out["bbe_scored"].sum())
    _share = (_bbe_scored / _bbe_all * 100) if _bbe_all else 0.0
    print(f"  HR metrics: {len(out):,} qualified batters "
          f"(>= {HRM_MIN_PA} PA, {HRM_MIN_BBE} BBE) · "
          f"{len(_core):,} in the {HRM_CORE_PA}+ PA scale core · "
          f"{_bbe_scored:,} of {_bbe_all:,} batted balls scoreable "
          f"({_share:.1f}%)")
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
        "HH% Allowed": g["_hh"].mean() * 100,
        "FB% Allowed": g["_fb"].mean() * 100,
        "HRWindow% Allowed": g["_hrw"].mean() * 100,
        "EV90 Allowed": g["_ls"].quantile(0.90),
    })
    if bbe["_brl"] is not None and "_brl" in bbe.columns and bbe["_brl"].notna().any():
        agg["Brl% Allowed"] = g["_brl"].mean() * 100
    agg = agg[agg["bbe"] >= MIN_BBE]
    if len(agg) < 50:
        print(f"  Pitcher percentiles skipped — only {len(agg)} qualified.")
        return False

    # Keys MUST match the view's column headers EXACTLY. They read
    # "Brl% Allowed" with no space before the %, and the first version
    # here wrote "Brl % Allowed" — so every metric except EV90 (the only
    # one without a % in its name) failed to match and rendered ungraded.
    # The lookup is by string, so a single space is the whole difference
    # between a coloured card and a flat one.
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


def build_bullpen_profiles(season_df: pd.DataFrame) -> bool:
    """Precompute every team's real bullpen, so the app doesn't have to.

    WHY THIS EXISTS — this is the single biggest first-load cost in the
    product. The Game Card's Matchup Edge needs a slate-wide bullpen
    baseline (see edge._slate_pen_avg_json), and building it live meant,
    for EVERY team on the slate:

        one HTTPS roster call to statsapi  (sequential, ~30 of them)
      + get_pitcher_role() per rostered pitcher
      + get_pitcher_advanced_splits() per reliever  (full metric derive)
      + get_pitcher_hand() per reliever

    That is the ~30-second "Computing matchup edges" spinner the first
    user of the day sits through — and on Render's free tier the process
    spins down, so st.cache_data is empty and SOMEBODY pays it again
    every single day, usually the first person to open the app.

    Everything it computes is already available right here: the whole
    league's pitches are in memory, and GitHub's runners can reach
    statsapi without the rate-limit exposure a user-facing request has.
    So we do it once, nightly, and ship a small JSON.

    SHAPE — per team, the reliever LIST rather than a finished HR/9:

        {"Team Name": {"relievers": [{"id", "hr", "ip", "hand"}, ...],
                       "unknown_role": n}, ...}

    Storing the arms instead of the pooled rate is what keeps this
    EXACTLY equivalent to the live path rather than merely close: the
    app still excludes tonight's starter (an opener classified RP is
    rare but real) and pools the rest itself, which is microseconds of
    arithmetic on a list this size.

    IP and HR use the same definitions as get_pitcher_advanced_splits —
    outs/3 from terminal PA events — because these numbers are pooled
    against numbers the live fallback produces. A different definition
    here would make the baseline shift depending on which path built it.
    """
    need = {"pitcher", "events"}
    if not need.issubset(season_df.columns):
        print("  Bullpen profiles skipped — missing pitcher/events columns.")
        return False

    roles_path = DATA_DIR / "pitcher_roles.json"
    if not roles_path.exists():
        print("  Bullpen profiles skipped — pitcher_roles.json not built.")
        return False
    roles = json.loads(roles_path.read_text())

    # Per-pitcher HR allowed and estimated IP, league-wide, in one pass.
    ev = season_df[["pitcher", "events"]].dropna()
    if ev.empty:
        print("  Bullpen profiles skipped — no terminal events.")
        return False
    grouped = ev.groupby("pitcher")["events"]
    hr_by_pid = grouped.apply(lambda s: int((s == "home_run").sum()))
    outs_by_pid = grouped.apply(lambda s: int(s.isin(_OUT_EVENTS).sum()))

    # Throwing hand from the pitcher's own rows — no extra lookup.
    hand_by_pid = {}
    if "p_throws" in season_df.columns:
        _h = season_df[["pitcher", "p_throws"]].dropna()
        if not _h.empty:
            hand_by_pid = (_h.groupby("pitcher")["p_throws"]
                             .agg(lambda s: s.mode().iat[0] if len(s.mode()) else None)
                             .to_dict())

    try:
        teams = requests.get(
            "https://statsapi.mlb.com/api/v1/teams", params={"sportId": 1}, timeout=20
        ).json().get("teams", [])
    except Exception as exc:
        print(f"  Bullpen profiles skipped — team list unreachable ({exc}).")
        return False

    out, total_arms = {}, 0
    for t in teams:
        tid, tname = t.get("id"), t.get("name")
        if not tid or not tname:
            continue
        try:
            roster = requests.get(
                f"https://statsapi.mlb.com/api/v1/teams/{tid}/roster",
                params={"rosterType": "active"}, timeout=20,
            ).json().get("roster", [])
        except Exception:
            # One unreachable team is not a reason to ship nothing —
            # the app falls back to the live build for that team only.
            continue

        relievers, unknown = [], 0
        for entry in roster:
            person = entry.get("person") or {}
            pid = person.get("id")
            pos = (entry.get("position") or {}).get("abbreviation")
            if not pid or pos != "P":
                continue
            role = roles.get(str(int(pid)))
            if role != "RP":
                # None means too few outings to judge. Excluded, not
                # guessed at — a misclassified starter would drag the
                # pooled rate straight back toward the rotation.
                if role is None:
                    unknown += 1
                continue
            outs = int(outs_by_pid.get(pid, 0))
            if outs <= 0:
                continue
            relievers.append({
                "id": str(pid),
                "hr": int(hr_by_pid.get(pid, 0)),
                "ip": round(outs / 3, 1),
                "hand": hand_by_pid.get(pid),
            })
        if relievers:
            out[tname] = {"relievers": relievers, "unknown_role": unknown}
            total_arms += len(relievers)

    if not out:
        print("  Bullpen profiles skipped — no team produced a usable pen.")
        return False

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "bullpen_profiles.json").write_text(json.dumps(out))
    print(f"  Bullpen profiles: {len(out)} teams, {total_arms} relievers")
    return True


def fetch_savant_percentiles() -> bool:
    """Ships MLB's own percentile-rank leaderboard with the data package.

    HR Score / Hit Score / K Score are all built on this table, so the
    Game Card loads it before it can rank a single batter — and it was
    loading it LIVE, from baseballsavant.mlb.com, on every cold start.
    On Render's free tier the process spins down, so "cold start" means
    most mornings.

    Same fix that was already applied to the FanGraphs leaderboard, for
    the same reason: GitHub's runners fetch it once, the app reads it
    from disk. The live call stays in the app as the fallback, so this
    only ever removes latency — it never becomes the thing that breaks
    the scores.
    """
    try:
        from pybaseball import statcast_batter_percentile_ranks
        pct = statcast_batter_percentile_ranks(date.today().year)
        if pct is None or pct.empty:
            print("  Savant percentiles returned no data — app will fetch live.")
            return False
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        pct.to_parquet(DATA_DIR / "savant_percentiles.parquet", index=False)
        print(f"  Savant percentile ranks saved: {len(pct):,} batters")
        return True
    except Exception as exc:
        print(f"  Savant percentile fetch failed ({exc}) — app will fetch live.")
        return False


# fetch_fangraphs() was REMOVED.
#
# It fetched the FanGraphs batting leaderboard every night and wrote
# data/statcast/fangraphs_batting.parquet — which NO app module ever read.
# Verified across the whole repo: the only references to that filename
# were the lines that produced it.
#
# It is a leftover from before the scoring migration. engines/top_plays.py
# documents that move in its own header: scores are built on Baseball
# Savant percentiles matched by MLBAM player_id, specifically because
# FanGraphs blocks cloud hosts and Savant is MLB's first-party data. Once
# that landed nothing consumed the leaderboard, but the nightly fetch kept
# running — a network round trip, a parquet write, and archive weight
# Render downloads and never opens.
#
# If a future feature wants FanGraphs data, restore this from git history
# rather than rewriting it, and wire the consumer in the SAME change so it
# cannot drift back into being built-but-unread. tests/test_data_paths.py
# prints a NOTE for any nightly artifact no app module references — that
# is how this was found.


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
    build_player_game_logs(season_df)

    print("Building pitcher allowed-contact percentiles...")
    build_pitcher_allowed_percentiles(season_df)

    print("Precomputing pitcher roles (SP/RP)...")
    build_pitcher_roles(season_df)

    # AFTER build_pitcher_roles — it reads the roles file that step writes.
    print("Precomputing bullpen profiles (kills the 30s edge spinner)...")
    pen_ok = build_bullpen_profiles(season_df)

    print("Measuring plate appearances per team-game...")
    pa_per_game = build_pa_per_game(season_df)

    print("Building HR park factors by handedness...")
    park_ok = build_park_hr_factors(season_df)

    print("Building league HR rates by pitch type...")
    pt_ok = build_pitch_type_hr(season_df)

    print("Fetching Savant percentile ranks (off the app's cold start)...")
    savant_ok = fetch_savant_percentiles()

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "season_start": SEASON_START.isoformat(),
        "through_date": date.today().isoformat(),
        "total_pitches": int(len(season_df)),
        "n_batters": counts["batters"],
        "n_pitchers": counts["pitchers"],
        "source": "Baseball Savant via pybaseball bulk statcast()",
        "xhr_table_included": xhr_ok,
        "hr_metrics_included": hrm_ok,
        "park_hr_factors_included": park_ok,
        "pitch_type_hr_included": pt_ok,
        "bullpen_profiles_included": pen_ok,
        "savant_percentiles_included": savant_ok,
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
