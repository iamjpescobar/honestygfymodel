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
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# TWO PLACES A SLATE CAN LIVE, and they arrive by different routes.
#
# _PUBLISHED is app/data/, where fetch_data.py extracts the nightly
# release archive. That is how WNBA, KBO and NPB slates reach Render, and
# app/data/ is gitignored — it exists only after a build.
#
# _REPO is the repository's own data/, which CI commits to and Render
# gets in the checkout. calibration.json already travels this way; see
# engines/calibration._repo_path(), which documents the same split and
# the bug that came from reading only one of them.
#
# MLB uses the repo path because its slate is written by
# calibration_picks.py at 1, 5 and 7 PM ET — the only clock on which
# probable starters exist — and that job publishes no archive. Writing it
# to app/data/ would have left it on the Actions runner to die with the
# job: correct-looking code, a green run, and a file production never
# sees. Reading only app/data/ here would have done the same thing one
# layer later.
_PUBLISHED = Path(__file__).resolve().parent.parent / "data"
_REPO = Path(__file__).resolve().parents[2] / "data"

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
    # MLB arrives last and is the odd one: its schedule is a live API
    # call, so for a long time no MLB slate existed on disk at all and
    # every board built one on demand. Home cannot do that (rule 5), so
    # calibration_picks now writes one in CI at 1, 5 and 7 PM ET, and it
    # goes through the same guard as every other league rather than
    # getting its own private staleness check.
    #
    # Eastern, like WNBA: an MLB schedule day IS an Eastern day. A game
    # at 10 PM ET on the 8th is the 8th's slate even though it is already
    # the 9th in UTC, which is the exact bug weather_engine documents in
    # its own EASTERN comment. (That constant lives in weather_engine;
    # this module holds no timezone of its own — every zone comes from
    # the table below, so a league's timezone is stated in exactly one
    # place instead of two that can disagree.)
    "mlb":  ("slate_date_et",  "generated_at_et",  "America/New_York"),
}

# WHICH JOB PUBLISHES EACH SLATE — for the staleness sentence only.
#
# The message used to say "the nightly build hasn't published since" for
# every league. True for three of them and WRONG for MLB, whose slate is
# written by slate-picks at 1, 5 and 7 PM ET because that is the only
# clock on which probable starters exist. A stale MLB board would have
# sent whoever read it to debug nightly-data, which is working.
#
# The codebase already learned this once: the WNBA staleness threshold
# was reworded because "the nightly fetch may be failing" fired during
# the All-Star break when the fetch was fine. A confident wrong diagnosis
# is worse than no message.
_WRITER = {
    "wnba": "the nightly build",
    "kbo":  "the nightly build",
    "npb":  "the nightly build",
    "mlb":  "the slate-picks job",
}

# WHEN EACH LEAGUE'S SLATE FIRST EXISTS, in the league's own timezone.
#
# Only MLB has an entry, and the absence of the others is the mechanism —
# NOT an oversight. KBO, NPB and WNBA come off the nightly, which runs
# before anyone is awake, so for them "no slate today" at any hour really
# is a fault and the loud message is right.
#
# MLB is different because its slate needs PROBABLE STARTERS, and MLB
# posts those one to three hours before first pitch. slate-picks
# therefore runs at 1, 5 and 7 PM ET. Which means that from midnight
# until 1 PM — THIRTEEN HOURS, over half the day — there is legitimately
# no MLB slate for today, and the page was reporting it as
# "the slate-picks job hasn't published since": the sentence for a broken
# workflow, fired daily at a workflow that is fine, sending whoever read
# it to debug something green.
#
# This codebase has already made this mistake once. The WNBA staleness
# warning said "the nightly fetch may be failing" through the All-Star
# break, when the fetch was perfect and the league simply was not
# playing. The rule left behind: A CONFIDENT WRONG DIAGNOSIS IS WORSE
# THAN NO MESSAGE.
#
# 13 duplicates the first cron in .github/workflows/slate-picks.yml
# ("0 17 * * *" UTC). The duplication is real and deliberate — reading a
# workflow file at request time to render a sentence is worse — so
# tests/test_slate_guard.py pins the two together and fails if the cron
# moves without this constant following.
#
# DST caveat, stated because it is a real one-hour hole: the cron is
# fixed in UTC, so 17:00 UTC is 1 PM in EDT and noon in EST. Under EST
# the job runs an hour before this threshold, so a job that RUNS AND
# FAILS at noon gets the gentle message for one hour instead of the loud
# one. That is the safe direction to be wrong in — an hour late to shout
# beats shouting every morning — but it is not free, so it is written
# down rather than discovered.
_FIRST_BUILD_HOUR = {"mlb": 13}


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



def _read(league: str):
    """(payload, date_key, generated_key) or (None, ...) if unreadable.

    Reads BOTH locations and returns whichever carries the LATER slate
    date. Not "first one that exists": on the day the nightly archive
    starts carrying a league the repo path also has, first-wins would
    pin the app to whichever path happened to be checked first and the
    staleness would be invisible — the exact class of bug this whole
    module exists for.

    Comparing dates rather than mtimes on purpose. An mtime says when a
    file was touched; the slate date says which night it describes, and
    that is the only one of the two a reader cares about. A checkout
    rewrites every mtime.
    """
    date_key, gen_key, _tz = _cfg(league)

    best = None
    for root in (_PUBLISHED, _REPO):
        try:
            payload = json.loads((root / league.lower() / "games.json").read_text()) or {}
        except Exception:
            continue
        if best is None:
            best = payload
            continue
        # A payload with no declared date never wins. load_slate rejects
        # an undated slate anyway, so preferring one here would only
        # convert a usable slate into a rejected one.
        if (payload.get(date_key) or "") > (best.get(date_key) or ""):
            best = payload
    return best, date_key, gen_key


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


def _not_built_yet(league: str, on_date: str, slate_date):
    """True when today's slate is simply not due yet — a fact about the
    clock, not a fault.

    Deliberately narrow. It fires ONLY when all three hold:

      1. the league has a known daily build hour (MLB alone);
      2. that hour has not come round yet today, in the league's own
         timezone;
      3. what is on disk is either nothing at all, or EXACTLY yesterday's
         slate.

    Condition 3 is the one that keeps this honest. Overnight, holding
    yesterday's slate is the normal, expected, healthy state. Holding a
    slate from three days ago is a real outage at any hour of any day,
    and must keep the loud message — otherwise this branch quietly
    becomes "suppress the warning when it is inconvenient", which is the
    opposite of what it is for.
    """
    hour = _FIRST_BUILD_HOUR.get(league.lower())
    if hour is None:
        return False
    _dk, _gk, tz = _cfg(league)
    if datetime.now(ZoneInfo(tz)).hour >= hour:
        return False
    if slate_date is None:
        return True
    try:
        gap = (date.fromisoformat(on_date) - date.fromisoformat(slate_date)).days
    except (TypeError, ValueError):
        return False
    return gap == 1


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
    if slate_date is not None and slate_date > on_date:
        # Not a fault. Say so plainly, or a lookahead reads as a failure.
        return (f"No {league.upper()} games on {on_date} — showing the next "
                f"slate, {slate_date}.")
    if _not_built_yet(league, on_date, slate_date):
        # Checked BEFORE the two fault branches below, because both of
        # those describe something going wrong and nothing has.
        hour = _FIRST_BUILD_HOUR[league.lower()]
        clock = f"{hour - 12} PM" if hour > 12 else f"{hour} AM"
        return (f"Tonight's {league.upper()} slate builds around {clock} ET, "
                f"once MLB posts probable starters. Nothing is shown before "
                f"then rather than ranking games on data that doesn't exist "
                f"yet.")
    if slate_date is None:
        return (f"No {league.upper()} slate on disk for {on_date}. Nothing is "
                f"shown rather than showing an older night's games as "
                f"tonight's.")
    return (f"The most recent {league.upper()} slate on disk is for "
            f"{slate_date}, not {on_date} — {_WRITER.get(league.lower(), 'the nightly build')} "
            f"hasn't published since. Those games have already been "
            f"played, so they aren't shown as tonight's board.")
