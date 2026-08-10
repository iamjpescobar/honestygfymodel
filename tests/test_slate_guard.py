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
import re
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

# --- "not built yet" is not "the build is broken" ---------------------
#
# MLB's slate needs probable starters, so slate-picks runs at 1, 5 and 7
# PM ET. From midnight to 1 PM — THIRTEEN HOURS, over half the day —
# there is legitimately no MLB slate for today, and the page was
# reporting it with the sentence for a broken workflow: "the slate-picks
# job hasn't published since". Fired daily, at a workflow that is fine.
#
# The repo already learned this once. The WNBA warning said "the nightly
# fetch may be failing" through the All-Star break, when the fetch was
# perfect and the league was not playing. A CONFIDENT WRONG DIAGNOSIS IS
# WORSE THAN NO MESSAGE.
#
# The danger in the fix is that it quietly becomes "suppress the warning
# when it is inconvenient", so these cases pin BOTH directions: when the
# gentle message must appear, and — more importantly — when the loud one
# must survive.
import engines.slate_guard as _sg

_MLB = ROOT / "app" / "data" / "mlb"
_MLB.mkdir(parents=True, exist_ok=True)
_mf = _MLB / "games.json"
_mprev = _mf.read_text() if _mf.exists() else None


def _note_at(hour, slate_date, league="mlb", on="2026-08-10"):
    """staleness_note() as if the clock read `hour` in the league's tz."""
    if slate_date:
        _mf.write_text(json.dumps({"slate_date_et": slate_date,
                                   "games": [{"away": "A", "home": "B"}]}))
    elif _mf.exists():
        _mf.unlink()
    _real = _sg.datetime

    class _Fake(_real):
        @classmethod
        def now(cls, tz=None):
            return _real(2026, 8, 10, hour, 0, tzinfo=tz)

    _sg.datetime = _Fake
    try:
        return _sg.staleness_note(league, on)
    finally:
        _sg.datetime = _real


try:
    _cases = [
        # hour, on disk,       must contain,        must NOT contain
        (6,  None,         "builds around",     "hasn't published"),
        (6,  "2026-08-09", "builds around",     "hasn't published"),
        # A THREE-DAY-OLD SLATE IS A REAL OUTAGE AT ANY HOUR. This is the
        # case that stops the branch becoming a blanket mute.
        (6,  "2026-08-07", "hasn't published",  "builds around"),
        # After the build hour, nothing is excused.
        (15, None,         "No MLB slate",      "builds around"),
        (15, "2026-08-09", "hasn't published",  "builds around"),
    ]
    for _h, _sd, _want, _not in _cases:
        _n = _note_at(_h, _sd)
        _label = f"{_h:02d}:00 with {_sd or 'no slate'}"
        if _want not in _n:
            failures.append(f"{_label}: expected {_want!r} in the note, got {_n!r}")
        elif _not in _n:
            failures.append(f"{_label}: note still says {_not!r} — {_n!r}")
        else:
            print(f"PASS: {_label} reads as "
                  f"{'not due yet' if 'builds' in _want else 'a fault'}")

    # THE OTHER THREE LEAGUES MUST BE UNTOUCHED. They come off the
    # nightly, which runs before anyone is awake, so "no slate today" at
    # 6 AM really is a fault for them. _FIRST_BUILD_HOUR having only an
    # mlb key is the mechanism — this fails if anyone gives it a default.
    for _lg, _key in (("kbo", "slate_date_kst"), ("npb", "slate_date_jst"),
                      ("wnba", "slate_date_et")):
        _d = ROOT / "app" / "data" / _lg
        _d.mkdir(parents=True, exist_ok=True)
        _lf = _d / "games.json"
        _lprev = _lf.read_text() if _lf.exists() else None
        try:
            _lf.write_text(json.dumps({_key: "2026-08-09",
                                       "games": [{"away": "A", "home": "B"}]}))
            _real = _sg.datetime

            class _F(_real):
                @classmethod
                def now(cls, tz=None):
                    return _real(2026, 8, 10, 6, 0, tzinfo=tz)

            _sg.datetime = _F
            try:
                _n = _sg.staleness_note(_lg, "2026-08-10")
            finally:
                _sg.datetime = _real
            if "builds around" in _n:
                failures.append(f"{_lg} got MLB's not-due-yet message; only "
                                f"MLB has a mid-day build clock")
            else:
                print(f"PASS: {_lg} at 06:00 still reports a stale slate as a fault")
        finally:
            if _lprev is not None:
                _lf.write_text(_lprev)
            elif _lf.exists():
                _lf.unlink()
finally:
    if _mprev is not None:
        _mf.write_text(_mprev)
    elif _mf.exists():
        _mf.unlink()

# THE CONSTANT AND THE CRON MUST NOT DRIFT APART.
#
# _FIRST_BUILD_HOUR["mlb"] = 13 duplicates the first cron in
# slate-picks.yml ("0 17 * * *" UTC = 1 PM EDT). Reading a workflow file
# at request time to render a sentence would be worse than duplicating
# it, so the duplication is deliberate — and pinned here, because an
# unpinned duplicate is just two things that will disagree later.
_cron = re.findall(r'cron:\s*"(\d+)\s+(\d+)', 
                   open(ROOT / ".github" / "workflows" / "slate-picks.yml").read())
if not _cron:
    failures.append("could not read slate-picks.yml's cron schedule")
else:
    _utc_hour = int(_cron[0][1])
    _expected = (_utc_hour - 4) % 24          # UTC -> EDT
    if _sg._FIRST_BUILD_HOUR.get("mlb") != _expected:
        failures.append(
            f"slate-picks' first run is {_utc_hour}:00 UTC ({_expected}:00 ET) "
            f"but _FIRST_BUILD_HOUR['mlb'] is "
            f"{_sg._FIRST_BUILD_HOUR.get('mlb')}. The message tells readers "
            f"when to come back; if the cron moved, that time is now a lie.")
    else:
        print("PASS: the build-hour constant still matches slate-picks' cron")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nA slate is only tonight's slate if it says it is.")
