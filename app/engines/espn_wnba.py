"""ONE copy of ESPN's WNBA scoreboard access. Read by the nightly and by
the live page.

WHY THIS MODULE EXISTS

The mirror chain below was built in wnba_precompute.py after ESPN began
403-ing one API path from cloud IP ranges. It worked, and the pipeline
recovered. What nobody noticed was that app/views/WNBA.py had its own
private copy of the same idea — a single hardcoded URL:

    _SB_URL = "https://site.api.espn.com/apis/site/v2/.../wnba/scoreboard"

which is the exact host the pipeline had just been moved OFF. That call
returned a non-200 from Render, the reader returned {} rather than
raising, and so the live-score overlay was silently dead: no in-game
scores, and because `any_live_now` is derived from that same empty dict,
the 75-second auto-refresh fragment never armed either. Nothing looked
broken. The page just never updated.

slate_guard makes this argument about slate files in its own comments —
"holding a second copy of those paths here is how this reader drifted out
from under the guard" — and it is the same failure exactly one level up.
So the chain lives here, once, and both callers import it. Do NOT paste
the mirror list into a view again.

WHAT IS PROVEN AND WHAT IS NOT

The three mirrors were measured from GitHub Actions runners
(wnba_scoreboard_probe.py, 2026-08-03). They have NOT been measured from
Render, which is a different cloud range — ESPN blocks by range, so an
Actions result predicts Actions, not production. That is acceptable
because the fallback cannot do worse than the single blocked host it
replaces: if every mirror fails from Render, live_scores() returns {},
which is exactly today's behaviour.

No streamlit import here, on purpose. wnba_precompute and the probe
workflows install `requests` and nothing else.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")

BASE = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/wnba"

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
}

# Same map the pipeline writes into games.json, so a live override and a
# recorded slate can never disagree about what "in progress" means.
STATUS_MAP = {
    "STATUS_SCHEDULED": "scheduled",
    "STATUS_IN_PROGRESS": "in progress",
    "STATUS_HALFTIME": "in progress",
    "STATUS_END_PERIOD": "in progress",
    "STATUS_FINAL": "final",
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "postponed",
}


def get_json(url, _attempts=3):
    """GET with retries. Raises on final failure, as it always did.

    ESPN returns intermittent 403s to cloud IPs. A single attempt turned
    a transient block into a whole missing league for the day, so this
    backs off and tries again before giving up.
    """
    last = None
    for i in range(_attempts):
        try:
            r = requests.get(url, headers=UA, timeout=25)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if i < _attempts - 1:
                time.sleep(2 ** i)
    raise last


# ----------------------------------------------------------------------
# THE SCOREBOARD ENDPOINT GETS BLOCKED; THE GAMELOG ENDPOINT DOES NOT.
#
# Measured, in one CI run, minutes apart, from the same runner:
#
#   /apis/site/v2/.../wnba/scoreboard  -> 403 Forbidden
#   /apis/common/v3/.../wnba/gamelog   -> 200, 227 KB
#
# So this is not the User-Agent (both send the same one) and not an IP
# ban on Actions. ESPN blocks that one API path from cloud ranges, and
# when it does, wnba_precompute dies at its very first call — no slate,
# no players, no logs. Every WNBA page then falls through to its "engine
# is being connected" placeholder, because the whole league's data comes
# from this one request.
#
# Rather than pick a replacement blind, try the known mirrors of the same
# scoreboard in order and REPORT which one answered. They return
# different envelopes, so each is unwrapped to the shape
# parse_scoreboard_events already expects.
# ----------------------------------------------------------------------
SCOREBOARD_SOURCES = [
    ("site.api",
     lambda d: f"{BASE}/scoreboard?dates={d}",
     lambda j: j),
    # ESPN's own CDN serves the same payload under a different host, and
    # is not behind the same filter. The scoreboard sits one level down.
    ("cdn.espn",
     lambda d: f"https://cdn.espn.com/core/wnba/scoreboard?xhr=1&date={d}",
     lambda j: (j or {}).get("content", {}).get("sbData", j)),
    # The mobile/web API. Different host again, same events array.
    ("site.web.api",
     lambda d: ("https://site.web.api.espn.com/apis/v2/scoreboard/header"
                f"?sport=basketball&league=wnba&dates={d}"),
     lambda j: (j or {}).get("sports", [{}])[0].get("leagues", [{}])[0]
     if (j or {}).get("sports") else j),
]


# The source that last answered. The season backfill asks for ~120 days
# in a row, and without this every one of them re-probed site.api first —
# which is the host that gets blocked, so each day paid two failed
# attempts plus their backoff before reaching a mirror that works. Once
# one host has answered, it goes to the front of the queue.
_PREFERRED_SOURCE = None


def _sources_by_preference():
    if _PREFERRED_SOURCE is None:
        return SCOREBOARD_SOURCES
    return sorted(SCOREBOARD_SOURCES, key=lambda s: s[0] != _PREFERRED_SOURCE)


def _is_scoreboard(data):
    """True when a source actually ANSWERED, empty slate or not.

    Presence of the key is the test, not truthiness of the array: a day
    with no games returns events=[], and treating that as a failure is
    what made an off-day and a 403 look identical.
    """
    return isinstance(data, dict) and ("events" in data or "sports" in data)


def _normalize_header_events(data):
    """Reshape site.web.api's /scoreboard/header payload into the shape
    parse_scoreboard_events reads.

    MEASURED, not assumed. wnba_scoreboard_probe.py against 2026-08-03:

        site.api      HTTP 403, text/html "Access Denied"
        cdn.espn      HTTP 202, ZERO bytes
        site.web.api  HTTP 200, 70,704 bytes of real JSON, 3 events

    So exactly one host is answering, and its events carry the same games
    in a FLATTER shape: there is no `competitions` array at all, and the
    two sides sit directly on `event["competitors"]` — already carrying
    `homeAway`, with the team fields (id, displayName, color, logo)
    flattened onto the competitor rather than nested under `team`.

    parse_scoreboard_events opens with `comps = event.get("competitions")`
    and skips the event when that is empty, so every game of every day was
    dropped in silence. That is the whole of the 2026-08-04 failure: 87
    days answered 200 and produced zero games.

    This rebuilds the nesting rather than touching the parser, so the
    site.api shape keeps working unchanged if ESPN ever unblocks it — and
    a payload that ALREADY has competitions is returned untouched.
    """
    events = (data or {}).get("events")
    if not isinstance(events, list) or not events:
        return data
    # Already the full scoreboard shape — leave it alone.
    if isinstance(events[0], dict) and events[0].get("competitions"):
        return data

    # Team identity fields, which the header flattens onto the competitor.
    _TEAM_KEYS = ("id", "uid", "displayName", "shortDisplayName", "name",
                  "abbreviation", "location", "color", "alternateColor",
                  "logo", "logos", "links", "venue")

    out = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        comps = ev.get("competitors") or []
        if not comps:
            continue

        # fullStatus carries the {"type": {"name", "completed"}} block the
        # parser needs. `status` on this feed is often a bare string, which
        # would crash the .get("type") chain — so it is only used when it
        # is genuinely an object.
        status = ev.get("fullStatus")
        if not isinstance(status, dict):
            _s = ev.get("status")
            status = _s if isinstance(_s, dict) else {}

        norm = []
        for c in comps:
            if not isinstance(c, dict):
                continue
            entry = {
                "homeAway": c.get("homeAway"),
                "score": c.get("score"),
                "winner": c.get("winner"),
                "team": {k: c.get(k) for k in _TEAM_KEYS if c.get(k) is not None},
            }
            # _record() iterates records expecting dicts; this feed
            # sometimes gives a bare "20-8" string instead, and iterating
            # THAT yields characters and an AttributeError. Pass it
            # through only in the shape the reader can actually handle.
            _recs = c.get("records") or c.get("record")
            if isinstance(_recs, list):
                entry["records"] = _recs
            elif isinstance(_recs, str) and _recs:
                entry["records"] = [{"name": "overall", "summary": _recs}]
            for _k in ("leaders", "statistics"):
                if isinstance(c.get(_k), list):
                    entry[_k] = c[_k]
            norm.append(entry)

        out.append({
            "id": ev.get("id"),
            "uid": ev.get("uid"),
            "date": ev.get("date"),
            "name": ev.get("name"),
            "shortName": ev.get("shortName"),
            "status": status,
            "competitions": [{
                "id": ev.get("competitionId") or ev.get("id"),
                "date": ev.get("date"),
                "competitors": norm,
                # The header gives the arena as a plain string on the
                # event; the parser reads comp["venue"]["fullName"].
                "venue": {"fullName": ev.get("location") or ""},
                "broadcasts": ev.get("broadcasts") or [],
                "odds": ev.get("odds") or [],
                "status": status,
            }],
        })

    merged = dict(data)
    merged["events"] = out
    return merged


def fetch_scoreboard(yyyymmdd, require_events=True):
    """One day's slate, from whichever ESPN host is answering.

    Returns (payload, source_name). Raises only if every source fails,
    and then names all of them — a silent empty slate is indistinguishable
    from an off-day, which is the confusion that cost a full day of WNBA
    coverage.

    require_events=False is for the season backfill, where an empty day
    is an ordinary off-day and must be accepted as a real answer rather
    than sending the loop off to re-probe the other two hosts.
    """
    global _PREFERRED_SOURCE
    errors = []
    for name, build_url, unwrap in _sources_by_preference():
        url = build_url(yyyymmdd)
        try:
            data = unwrap(get_json(url, _attempts=2))
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__} {exc}")
            continue
        if not _is_scoreboard(data):
            errors.append(f"{name}: 200 but not a scoreboard payload")
            continue
        # Applied to EVERY source, not just the one known to need it: it
        # is a no-op on a payload that already carries `competitions`, and
        # making it conditional on the source name would mean a mirror
        # that changes shape silently goes back to yielding nothing.
        data = _normalize_header_events(data)
        if require_events and not (data.get("events") or data.get("sports")):
            errors.append(f"{name}: 200 but no events")
            continue
        if _PREFERRED_SOURCE != name:
            print(f"WNBA: scoreboard via {name}")
            _PREFERRED_SOURCE = name
        return data, name
    raise RuntimeError("every ESPN scoreboard source failed -> "
                       + " | ".join(errors))


def live_scores(yyyymmdd=None):
    """{(away_name, home_name): {status, detail, scoreline}} for one day.

    What app/views/WNBA.py overlays on the recorded slate. Keyed on the
    same displayName pair the pipeline writes into games.json, because
    both come out of this same feed — a name that matches on one side and
    not the other would show as a game with no live line rather than as
    an error, so they must not have independent sources.

    RETURNS {} ON ANY FAILURE, deliberately, and never raises. The caller
    is a page render: a live overlay that cannot be fetched means the
    page shows the pipeline snapshot, which is a true thing about a
    slightly older moment. An exception here would blank the board.

    require_events=False because an off-day is a real answer. Demanding
    events would send the loop through all three hosts on every quiet
    Tuesday and then raise.
    """
    day = yyyymmdd or datetime.now(EASTERN).strftime("%Y%m%d")
    try:
        data, _source = fetch_scoreboard(day, require_events=False)
    except Exception:
        return {}

    out = {}
    for event in (data or {}).get("events", []) or []:
        comp = (event.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        key = ((away.get("team") or {}).get("displayName", ""),
               (home.get("team") or {}).get("displayName", ""))
        stype = ((event.get("status") or {}).get("type")) or {}
        status = STATUS_MAP.get(stype.get("name", ""))
        entry = {"detail": stype.get("shortDetail") or stype.get("detail")}
        if status:
            entry["status"] = status
        try:
            a_s = int(float(away.get("score", 0)))
            h_s = int(float(home.get("score", 0)))
            # A scoreline is only published once there is a real one.
            # "Team 0 - 0 Team" beside a scheduled game reads as a
            # nil-nil tip-off that has already started.
            if status in ("in progress", "final"):
                entry["scoreline"] = f"{key[0]} {a_s} - {h_s} {key[1]}"
        except (TypeError, ValueError):
            pass
        out[key] = entry
    return out
