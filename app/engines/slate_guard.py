"""
One place that decides whether a league's slate file is actually for
tonight.

WHY THIS EXISTS

Every slate reader in the app trusted the file. The comment in
calibration_picks._wnba_games said it plainly: "slate-picks.yml runs
that fetch BEFORE this script, so the file is current by the time either
builder below asks for it."

That is true only when the nightly published. fetch_data.py downloads
the last SUCCESSFULLY published release asset, so when the nightly fails
— as it did for days on a stale assertion in test_data_integrity — the
fetch still succeeds and still returns a slate. Just an old one. Nothing
anywhere compared its date to today, so:

  * the WNBA boards showed subscribers picks for games that had already
    been played the night before, presented as tonight's slate;
  * calibration_picks logged those picks under TODAY's date, so the
    grader looked for box scores on a night those players did not play,
    found none, and closed 45 picks as DNP.

A slate file carries the date it was built for. Reading it without
checking that date is the whole bug, and it is a bug that gets quieter
the worse it is: a failing nightly leaves the site looking completely
normal while every board on it is wrong.

The rule here is that a stale slate is NOT a slate. Callers get an empty
list and the real date, so they can say what is actually true — "the
slate we have is from the 2nd" — instead of presenting it as tonight's.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
_DATA = Path(__file__).resolve().parent.parent / "data"


def today_et() -> str:
    return datetime.now(EASTERN).strftime("%Y-%m-%d")


def load_slate(league: str, on_date: str = None):
    """(games, slate_date, is_current) for a league's games.json.

    games is [] whenever the file is missing, unreadable, or built for a
    different date than the one asked about — a caller that ignores the
    flag still cannot show yesterday's games as tonight's.

    slate_date is whatever the file claims, or None. That is the value
    worth showing a user: "no slate for tonight" and "the slate we have
    is two days old" are different facts and should read differently.
    """
    on_date = on_date or today_et()
    path = _DATA / league.lower() / "games.json"
    try:
        payload = json.loads(path.read_text()) or {}
    except Exception:
        return [], None, False

    games = payload.get("games") or []
    slate_date = payload.get("slate_date_et") or None

    # No declared date is not a pass. An older build of the slate writer
    # may not have stamped one, and "we cannot tell how old this is"
    # must not read the same as "this is tonight's".
    if not slate_date:
        return [], None, False
    if slate_date != on_date:
        return [], slate_date, False
    return games, slate_date, True


def staleness_note(league: str, on_date: str = None) -> str:
    """A sentence for the user when the slate isn't tonight's, or ''.

    Deliberately states the date rather than a vague 'data unavailable':
    the reason this went unnoticed for days is that nothing anywhere
    said which night it was looking at.
    """
    on_date = on_date or today_et()
    _games, slate_date, ok = load_slate(league, on_date)
    if ok:
        return ""
    if slate_date is None:
        return (f"No {league.upper()} slate on disk for {on_date}. Nothing is "
                f"shown rather than showing an older night's games as "
                f"tonight's.")
    return (f"The most recent {league.upper()} slate on disk is for "
            f"{slate_date}, not {on_date} — the nightly build hasn't "
            f"published since. Those games have already been played, so "
            f"they aren't shown as tonight's board.")
