"""A slate built for another night must never be shown as tonight's.

WHAT HAPPENED. fetch_data.py downloads the last SUCCESSFULLY published
archive. While the nightly was failing on a stale assertion in
test_data_integrity, nothing published — but the fetch kept succeeding
and kept returning a slate, just an older one. No reader compared its
date to today, so:

  * the WNBA boards showed subscribers picks for games already played,
    presented as tonight's slate;
  * calibration_picks logged those picks under TODAY's date, the grader
    looked for box scores on a night those players did not play, and 45
    picks closed as DNP.

Caught by probing ESPN directly: a player on the Aug 3 board whose most
recent game was Aug 2 at 7 PM ET.

The failure mode is what makes this worth a test — it is silent, and it
gets quieter the worse it is. A completely broken nightly leaves a site
that looks entirely normal and is entirely wrong.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines.slate_guard import load_slate, staleness_note  # noqa: E402

EASTERN = ZoneInfo("America/New_York")
failures = []

today = datetime.now(EASTERN).strftime("%Y-%m-%d")
yday = (datetime.now(EASTERN) - timedelta(days=1)).strftime("%Y-%m-%d")

_dir = ROOT / "app" / "data" / "wnba"
_dir.mkdir(parents=True, exist_ok=True)
_file = _dir / "games.json"
_had = _file.read_text() if _file.exists() else None

try:
    _file.write_text(json.dumps(
        {"slate_date_et": today, "games": [{"a": 1}, {"b": 2}]}))
    games, sd, ok = load_slate("wnba")
    if len(games) == 2 and ok and sd == today:
        print("PASS: tonight's slate passes through untouched")
    else:
        failures.append(f"a current slate was rejected: {len(games)} games, "
                        f"date={sd}, current={ok}")
    if staleness_note("wnba"):
        failures.append("a current slate produced a staleness warning")

    _file.write_text(json.dumps(
        {"slate_date_et": yday, "games": [{"a": 1}, {"b": 2}]}))
    games, sd, ok = load_slate("wnba")
    if games or ok:
        failures.append("YESTERDAY'S SLATE PASSED AS TONIGHT'S — this is the "
                        "bug: boards get built from games already played and "
                        "logged under today's date")
    elif sd != yday:
        failures.append("the real slate date is not reported, so nothing can "
                        "tell the user which night they're looking at")
    elif yday not in staleness_note("wnba"):
        failures.append("the warning doesn't name the night on disk; 'no "
                        "data' is what let this hide for days")
    else:
        print("PASS: yesterday's slate yields nothing, and says which night "
              "it was")

    # No stamp is not a pass. "We can't tell how old this is" must not
    # read the same as "this is current".
    _file.write_text(json.dumps({"games": [{"a": 1}]}))
    games, sd, ok = load_slate("wnba")
    if games or ok:
        failures.append("an undated slate was treated as current")
    else:
        print("PASS: an undated slate is not assumed to be tonight's")

    _file.unlink()
    games, sd, ok = load_slate("wnba")
    if games or ok or sd is not None:
        failures.append("a missing slate file did not come back empty")
    else:
        print("PASS: a missing slate is empty, not an error")
finally:
    if _had is not None:
        _file.write_text(_had)
    elif _file.exists():
        _file.unlink()

# The readers must actually use it.
picks_src = (ROOT / "calibration_picks.py").read_text()
if "load_slate(\"wnba\")" not in picks_src:
    failures.append("calibration_picks no longer routes through the guard — "
                    "it would log picks for games already played")
else:
    print("PASS: the pick logger refuses a stale slate")

for view in ("WNBA_Props", "WNBA_Defense"):
    src = (ROOT / "app" / "views" / f"{view}.py").read_text()
    if "load_slate" not in src or "staleness_note" not in src:
        failures.append(f"{view} reads the slate file without the date check, "
                        f"so it can show a played-out slate as tonight's")
    else:
        print(f"PASS: {view} shows nothing rather than an old night")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nA slate is only tonight's slate if it says it is.")
