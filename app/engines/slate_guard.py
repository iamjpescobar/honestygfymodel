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

# Per-league slate vocabulary.
#
# This module was written for WNBA and hardcoded slate_date_et plus
# Eastern time. KBO stamps slate_date_kst and NPB stamps slate_date_jst,
# because "tonight" in Seoul is not "tonight" in New York — a KBO slate
# for Aug 5 KST is the correct slate while it is still Aug 4 in Newark.
# Reading those files with the Eastern vocabulary returned ([], None,
# False) for a perfectly good slate, which reads identically to "the
# nightly died". Every league that publishes a slate belongs here.
_LEAGUES = {
    "wnba": ("slate_date_et",  "generated_at_et",  "America/New_York"),
    "kbo":  ("slate_date_kst", "generated_at_kst", "Asia/Seoul"),
    "npb":  ("slate_date_jst", "generated_at_jst", "Asia/Tokyo"),
}


def _cfg(league: str):
    """(date_key, generated_key, tz) — unknown leagues raise, loudly.

    A typo'd league name silently returning the WNBA vocabulary is how
    you get a board that is quietly always empty, so this refuses to
    guess.
    """
    try:
        return _LEAGUES[league.lower()]
    except KeyError:
        raise KeyError(
            f"{league!r} has no slate vocabulary in slate_guard._LEAGUES. "
            f"Add its date key, generated key and timezone there."
        ) from None


def today_for(league: str) -> str:
    """Today's date in the league's OWN timezone."""
    _dk, _gk, tz = _cfg(league)
    return datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")


def today_et() -> str:
    return datetime.now(EASTERN).strftime("%Y-%m-%d")


def _read(league: str):
    """(payload, date_key, generated_key) or (None, ...) if unreadable."""
    date_key, gen_key, _tz = _cfg(league)
    path = _DATA / league.lower() / "games.json"
    try:
        return (json.loads(path.read_text()) or {}), date_key, gen_key
    except Exception:
        return None, date_key, gen_key


def load_slate(league: str, on_date: str = None):
    """(games, slate_date, is_current) for a league's games.json.

    games is [] whenever the file is missing, unreadable, undated, or
    built for a date ALREADY PAST — a caller that ignores the flag still
    cannot show games that have been played as tonight's.

    A slate dated in the FUTURE is passed through, because KBO and NPB
    build one deliberately: when there are no games today in Seoul or
    Tokyo the pipeline advances to the next date that has them, and the
    views already label it ("no games today — showing the next slate").
    Blanking that would delete a working feature in the name of safety it
    does not buy. Only the past is dangerous: a future slate cannot be a
    board of results presented as predictions.

    is_current is True only for an exact match, so a caller that wants
    strictly-tonight can still demand it.

    slate_date is whatever the file claims, or None. That is the value
    worth showing a user: "no slate for tonight" and "the slate we have
    is two days old" are different facts and should read differently.
    """
    on_date = on_date or today_for(league)
    payload, date_key, _gen = _read(league)
    if payload is None:
        return [], None, False

    games = payload.get("games") or []
    slate_date = payload.get(date_key) or None

    # No declared date is not a pass. An older build of the slate writer
    # may not have stamped one, and "we cannot tell how old this is"
    # must not read the same as "this is tonight's".
    if not slate_date:
        return [], None, False
    if slate_date < on_date:
        return [], slate_date, False
    if slate_date > on_date:
        return games, slate_date, False
    return games, slate_date, True


def generated_at(league: str):
    """When the pipeline built the slate on disk, or None.

    Separate from load_slate so a page can time-stamp its footer without
    a second hand-rolled read of the same file — which is precisely how
    four readers drifted out from under this guard in the first place.
    """
    payload, _dk, gen_key = _read(league)
    return (payload or {}).get(gen_key) or None


def staleness_note(league: str, on_date: str = None) -> str:
    """A sentence for the user when the slate isn't tonight's, or ''.

    Deliberately states the date rather than a vague 'data unavailable':
    the reason this went unnoticed for days is that nothing anywhere
    said which night it was looking at.
    """
    on_date = on_date or today_for(league)
    _games, slate_date, ok = load_slate(league, on_date)
    if ok:
        return ""
    if slate_date is None:
        return (f"No {league.upper()} slate on disk for {on_date}. Nothing is "
                f"shown rather than showing an older night's games as "
                f"tonight's.")
    if slate_date > on_date:
        # Not a fault. Say so plainly, or a lookahead reads as a failure.
        return (f"No {league.upper()} games on {on_date} — showing the next "
                f"slate, {slate_date}.")
    return (f"The most recent {league.upper()} slate on disk is for "
            f"{slate_date}, not {on_date} — the nightly build hasn't "
            f"published since. Those games have already been played, so "
            f"they aren't shown as tonight's board.")
