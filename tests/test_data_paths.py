"""Pins every nightly artifact's PRODUCTION path against what the
pipeline actually writes.

WHY THIS EXISTS
---------------
Four readers shipped pointing at `app/data/<file>` while precompute.py
writes to `build_data/data/statcast/<file>` and fetch_data.py extracts
the archive root at `app/` — so the real location is
`app/data/statcast/<file>`. hr_metrics, park_hr_factors, pitch_type_hr
and the lineup-slot manifest were all built, compressed, published,
downloaded and then never opened.

Nothing caught it, and the reason is instructive: every existing test
that touches these tables monkeypatches the module constant to a tmp
directory (`pm._LEAGUE_PATH = tmp / ...`, `ctx._PARK_PATH = tmp / ...`).
That is the right way to test a BUILDER and a READER, and it is
structurally incapable of testing the WIRING between them, because the
production path is overwritten before it is ever used.

Every one of these tables is also designed to degrade gracefully —
missing file means None, and every caller handles None. That is correct
behaviour and it is exactly what made this invisible: no traceback, no
empty column, no banner. Just the old fallback path quietly doing the
work while the new model sat unread on disk.

So this test never opens a file. It compares strings: the directory each
module resolves, against the directory precompute.py writes to. It runs
in milliseconds, needs no data package, and fails the moment a path and
its producer drift apart again.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

failures = []


def check(label, resolved: Path, expected_subdir: str, filename: str):
    """resolved is the full path a module will actually read."""
    expected = ROOT / "app" / "data" / expected_subdir / filename
    expected = Path(str(expected).replace("//", "/"))
    if Path(*resolved.parts[-3:]) != Path(*expected.parts[-3:]):
        failures.append(
            f"{label}\n"
            f"    reads   : .../{'/'.join(resolved.parts[-3:])}\n"
            f"    shipped : .../{'/'.join(expected.parts[-3:])}"
        )
    else:
        print(f"PASS: {label} -> {'/'.join(resolved.parts[-3:])}")


# ----------------------------------------------------------------------
# 1) What does precompute.py actually write, and where?
#
# Parsed from source rather than imported, so this test costs nothing and
# does not need pybaseball. DATA_DIR is data/statcast; calibration.json
# is the one artifact written a level up, by the grading step.
# ----------------------------------------------------------------------
pre_src = (ROOT / "precompute.py").read_text()

assert 'DATA_DIR = OUT_ROOT / "data" / "statcast"' in pre_src, (
    "precompute.DATA_DIR moved — this test's assumption about the archive "
    "layout is stale and every expectation below needs rechecking."
)
assert 'tar.add(OUT_ROOT / "data", arcname="data")' in pre_src, (
    "The archive is no longer packed with 'data' as its root — fetch_data.py "
    "extracts to app/, so the app-side paths below depend on this."
)

written = set(re.findall(r'DATA_DIR / "([a-z_0-9]+\.(?:parquet|json))"', pre_src))
print(f"precompute writes into data/statcast/: {sorted(written)}\n")

# ----------------------------------------------------------------------
# 2) Every consumer, at its real production path.
# ----------------------------------------------------------------------
import engines.savant_leaderboard as sl          # noqa: E402
import engines.hr_context as hc                  # noqa: E402
import engines.pitch_matchup as pm               # noqa: E402
import engines.edge as edge                      # noqa: E402
import engines.statcast_engine as se             # noqa: E402

check("savant_leaderboard._HR_METRICS_PATH", sl._HR_METRICS_PATH,
      "statcast", "hr_metrics.parquet")
check("savant_leaderboard._PCT_PATH", sl._PCT_PATH,
      "statcast", "savant_percentiles.parquet")
check("hr_context._PARK_PATH", hc._PARK_PATH,
      "statcast", "park_hr_factors.parquet")
check("pitch_matchup._LEAGUE_PATH", pm._LEAGUE_PATH,
      "statcast", "pitch_type_hr.parquet")
check("edge._PEN_PATH", edge._PEN_PATH,
      "statcast", "bullpen_profiles.json")
check("statcast_engine._DATA_DIR/xhr_table", se._DATA_DIR / "xhr_table.parquet",
      "statcast", "xhr_table.parquet")

# lineup_slot and daily_13 build their manifest path inside the function,
# so assert on the source line instead of a module constant.
ls_src = (ROOT / "app" / "engines" / "lineup_slot.py").read_text()
if '"data" / "statcast" / "manifest.json"' not in ls_src.replace(
        'base / "statcast" / "manifest.json"',
        '"data" / "statcast" / "manifest.json"'):
    failures.append("lineup_slot.league_pa_per_game does not resolve "
                    "data/statcast/manifest.json")
else:
    print("PASS: lineup_slot manifest -> data/statcast/manifest.json")

d13_src = (ROOT / "app" / "engines" / "daily_13.py").read_text()
if '"data" / "statcast" / "manifest.json"' not in d13_src:
    failures.append("daily_13 does not resolve data/statcast/manifest.json")
else:
    print("PASS: daily_13 manifest -> data/statcast/manifest.json")

# ----------------------------------------------------------------------
# 2b) The calibration record — the other producer/consumer pair, and the
# only artifact written a level ABOVE statcast/. Three places have to
# agree or graded picks silently stop reaching the app:
#   calibration_pipeline.RECORD_PATH  -> build_data/data/calibration.json
#   the archive                       -> data/calibration.json
#   engines.calibration               -> app/data/calibration.json
# ----------------------------------------------------------------------
cp_src = (ROOT / "calibration_pipeline.py").read_text()
if 'RECORD_PATH = BUILD_DATA / "calibration.json"' not in cp_src or \
        'BUILD_DATA = Path("build_data") / "data"' not in cp_src:
    failures.append("calibration_pipeline no longer writes "
                    "build_data/data/calibration.json")
else:
    import engines.calibration as cal          # noqa: E402
    check("calibration published record", cal._published_path(),
          "", "calibration.json")

# ----------------------------------------------------------------------
# 3) Nothing the pipeline builds should be unreachable.
#
# Catches the other direction: a new table added to precompute.py that no
# reader was ever wired up to. Kept as a warning rather than a failure —
# a table can legitimately land a run or two before its consumer does.
# ----------------------------------------------------------------------
app_src = "\n".join(
    p.read_text() for p in (ROOT / "app").rglob("*.py")
    if "__pycache__" not in str(p)
)
orphans = sorted(f for f in written if f not in app_src)
if orphans:
    print(f"\nNOTE: built nightly but referenced by no app module: {orphans}")

# ----------------------------------------------------------------------
if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    print("=" * 68)
    print(f"\n{len(failures)} data path(s) point somewhere the pipeline "
          f"does not write. These fail SILENTLY in production — the reader "
          f"returns None and the caller falls back — so nothing else will "
          f"tell you.")
    sys.exit(1)

print("\nPASS: every nightly artifact is read from where it is shipped.")
