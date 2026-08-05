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

for view in ("WNBA_Props", "WNBA_Defense", "WNBA"):
    src = (ROOT / "app" / "views" / f"{view}.py").read_text()
    if "load_slate" not in src or "staleness_note" not in src:
        failures.append(f"{view} reads the slate file without the date check, "
                        f"so it can show a played-out slate as tonight's")
    else:
        print(f"PASS: {view} shows nothing rather than an old night")

# Home and Player of the Day are not in the loop above because neither
# renders a staleness warning — Home omits the league from its chip rail
# and PotD returns the note as its own message — but both MUST still go
# through the guard. Home is the landing page; it was advertising game
# counts off whatever was on disk.
for label, path in (("Home", ROOT / "app" / "views" / "Home.py"),
                    ("player_of_the_day",
                     ROOT / "app" / "engines" / "player_of_the_day.py")):
    src = path.read_text()
    if "load_slate" not in src:
        failures.append(f"{label} reads the slate without the date check")
    elif "games.json" in src.split('"""', 2)[-1]:
        failures.append(f"{label} still holds its own path to games.json — "
                        f"a second copy of that path is exactly how a reader "
                        f"drifts back out from under the guard")
    else:
        print(f"PASS: {label} routes through the guard")

# --- every league's own vocabulary ------------------------------------
#
# THIS IS THE CHECK THAT WAS MISSING. load_slate hardcoded slate_date_et
# and Eastern time, so a perfectly good KBO slate stamped slate_date_kst
# came back ([], None, False) — indistinguishable from a dead nightly.
# Rolling Home onto the guard without this would have silently emptied
# the KBO and NPB chips and passed every test in the suite.
from engines.slate_guard import _LEAGUES, today_for  # noqa: E402

for _lg, (_date_key, _gen_key, _tz) in _LEAGUES.items():
    _d = ROOT / "app" / "data" / _lg
    _d.mkdir(parents=True, exist_ok=True)
    _f = _d / "games.json"
    _prev = _f.read_text() if _f.exists() else None
    _local_today = today_for(_lg)
    try:
        _f.write_text(json.dumps({_date_key: _local_today,
                                  _gen_key: "built",
                                  "games": [{"a": 1}]}))
        g, sd, ok = load_slate(_lg)
        if not (g and ok and sd == _local_today):
            failures.append(
                f"{_lg}: a current slate stamped {_date_key} was rejected "
                f"({len(g)} games, date={sd}, current={ok}) — the league's "
                f"date key or timezone is wrong in _LEAGUES")
        else:
            print(f"PASS: {_lg} slate read with its own key ({_date_key}) "
                  f"and timezone ({_tz})")
    finally:
        if _prev is not None:
            _f.write_text(_prev)
        elif _f.exists():
            _f.unlink()

# A slate dated AHEAD is a deliberate KBO/NPB lookahead, not staleness.
# Blanking it would delete the "no games today — showing the next slate"
# feature those views already ship.
_d = ROOT / "app" / "data" / "kbo"
_d.mkdir(parents=True, exist_ok=True)
_f = _d / "games.json"
_prev = _f.read_text() if _f.exists() else None
try:
    _ahead = (datetime.now(ZoneInfo("Asia/Seoul"))
              + timedelta(days=1)).strftime("%Y-%m-%d")
    _f.write_text(json.dumps({"slate_date_kst": _ahead, "games": [{"a": 1}]}))
    g, sd, ok = load_slate("kbo")
    if not g or ok or sd != _ahead:
        failures.append("a lookahead slate was blanked or mislabelled as "
                        "current; KBO/NPB publish one on purpose")
    elif "already been played" in staleness_note("kbo"):
        failures.append("a lookahead slate is described as already played")
    else:
        print("PASS: a lookahead slate is shown and labelled, not blanked")
finally:
    if _prev is not None:
        _f.write_text(_prev)
    elif _f.exists():
        _f.unlink()

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nA slate is only tonight's slate if it says it is.")
