"""
MLB Stats API access — lineups, rosters, team ids.

PERFORMANCE NOTE (this is why the module looks the way it does)

A cold Daily 13 build was measured at ~36 seconds in CI, and almost all
of it was spent here, waiting on statsapi.mlb.com. Three separate
causes, all fixed below:

  1. THE TEAM LIST WAS REFETCHED CONSTANTLY. `teams?sportId=1` — a list
     that changes about once a year — was fetched inside
     get_all_teams(), get_live_team_roster() AND get_last_starting_lineup(),
     on every call, per team. A slate with no confirmed lineups walks the
     fallback path for every club, so that was up to 30 identical
     requests. _team_ids() now fetches it once a day.

  2. NO CONNECTION REUSE. Every requests.get() opened a fresh TLS
     connection. At 100+ calls the handshakes alone were a large share of
     the wall clock. Everything now goes through one keep-alive Session.

  3. EVERYTHING WAS SEQUENTIAL. Each call waited for the last, though
     they are independent reads of a remote server. prefetch_slate()
     warms them concurrently before the serial code runs.

On the concurrency, deliberately: the pool runs _get_json, which is
plain requests and touches nothing from streamlit. st.cache_data
decorators stay on the OUTER functions, called from the main thread as
before. Calling a cached function from a worker thread has no script run
context and is not worth the risk — memoising one layer down gets the
same win with none of it.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
import streamlit as st

# One connection pool for the whole process. maxsize matches the
# prefetch worker count so concurrent warms never queue on a free socket.
_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=16))

_PREFETCH_WORKERS = 8

# Response memo, one layer BELOW st.cache_data. Its only job is to let a
# parallel prefetch and the serial code that follows share one fetch.
# TTL matches the shortest cache above it (5 min, the lineup window), so
# it can never serve something the caller would have considered stale.
_MEMO = {}
_MEMO_TTL = 300
_MEMO_MAX = 400


def _memo_key(url, params):
    return (url, tuple(sorted((params or {}).items())))


def _get_json(url, params=None, timeout=10):
    """GET returning parsed JSON, or None. Never raises."""
    key = _memo_key(url, params)
    hit = _MEMO.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _MEMO_TTL:
        return hit[1]
    try:
        resp = _SESSION.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        # Cache nothing on failure. A transient error must not be pinned
        # for five minutes — the retry a few seconds later is the whole
        # reason the scheduled runs are staggered.
        return None
    if len(_MEMO) >= _MEMO_MAX:
        _MEMO.clear()
    _MEMO[key] = (now, data)
    return data


def prefetch_json(specs, workers=_PREFETCH_WORKERS):
    """Warm the memo for many (url, params) pairs at once.

    Fire-and-forget: results land in _MEMO and callers just make their
    normal serial calls afterwards, which now hit memory. Every failure
    is swallowed, so a prefetch can only ever make things faster or
    leave them exactly as they were.
    """
    specs = [sp for sp in specs if sp]
    if len(specs) < 2:
        for url, params in specs:
            _get_json(url, params)
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(specs))) as pool:
        list(pool.map(lambda sp: _get_json(sp[0], sp[1]), specs))


_TEAMS_URL = "https://statsapi.mlb.com/api/v1/teams?sportId=1"


@st.cache_data(ttl=86400, max_entries=1, show_spinner=False)
def _teams_raw():
    """[(name, id)] for every MLB club. Fetched once a day, not per call.

    The single source for both the id lookup and the display list, so
    the two can never fall out of step and neither triggers its own
    fetch. Names are kept EXACTLY as MLB returns them — reconstructing
    them from a lowercased key would quietly mangle anything title-case
    does not round-trip.
    """
    data = _get_json(_TEAMS_URL) or {}
    return [(t["name"], t["id"]) for t in data.get("teams", [])
            if t.get("name") and t.get("id")]


def _team_ids():
    """{lowercased team name: team id}."""
    return {name.lower(): tid for name, tid in _teams_raw()}


def _team_id(team_name: str):
    return _team_ids().get((team_name or "").lower())


def prefetch_slate(team_names=(), game_sides=()):
    """Warm every request a slate build is about to make, concurrently.

    team_names: clubs whose rosters will be read.
    game_sides: (game_pk, side) pairs whose lineups will be read.

    Call this ONCE at the top of a board build, before the per-team and
    per-game loops. It is purely an optimisation — every function below
    still works correctly if it is never called.
    """
    ids = _team_ids()
    specs = []
    for pk, _side in game_sides:
        if pk:
            specs.append((f"https://statsapi.mlb.com/api/v1/game/{pk}/boxscore", None))
    for name in team_names:
        tid = ids.get((name or "").lower())
        if not tid:
            continue
        for roster_type in ("40Man", "active"):
            specs.append((f"https://statsapi.mlb.com/api/v1/teams/{tid}/roster",
                          {"rosterType": roster_type, "hydrate": "person"}))
    # de-dupe: two sides of one game share a boxscore
    seen, uniq = set(), []
    for sp in specs:
        k = _memo_key(*sp)
        if k not in seen:
            seen.add(k)
            uniq.append(sp)
    prefetch_json(uniq)


@st.cache_data(ttl=300, max_entries=40, show_spinner=False)
def get_confirmed_lineup(game_pk, side: str):
    """
    Real confirmed starting lineup for one specific game, straight from
    MLB's own boxscore endpoint — not a general roster slice. MLB
    typically posts this 1-3 hours before first pitch; before that, it
    genuinely doesn't exist yet (not a bug, a real timing constraint).

    side: "away" or "home"
    Returns (lineup, confirmed) where lineup is a list of
    {"id", "name", "position", "bats", "battingOrder"} sorted by real
    batting order, and confirmed is True only if MLB has actually
    posted a real lineup. Callers MUST check `confirmed` and label
    the data honestly if False — never silently pass off a fallback
    roster as if it were the real confirmed lineup.
    """
    if not game_pk:
        return [], False
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    data = _get_json(url)
    if not data:
        return [], False
    team_data = data.get("teams", {}).get(side, {})
    players = team_data.get("players", {})

    lineup = []
    for p in players.values():
        batting_order = p.get("battingOrder")
        if not batting_order:
            continue  # not in today's real starting lineup (bench/bullpen/unused)
        person = p.get("person", {})
        position = p.get("position", {})
        pid = person.get("id")

        lineup.append({
            "id": str(pid or ""),
            "name": person.get("fullName", "Unknown"),
            "position": position.get("abbreviation", ""),
            "is_pitcher": position.get("abbreviation") == "P",
            "bats": "?",  # filled in below via one bulk lookup, not N calls
            "battingOrder": int(batting_order),
        })

    if not lineup:
        return [], False

    # Bat side isn't reliably present on the boxscore player object itself,
    # so it needs a real separate lookup — but ONE bulk call for every
    # player in the lineup (MLB's people endpoint accepts a comma-separated
    # personIds list) instead of a request per player. That was the real
    # latency/fragility problem: a 9-player lineup used to mean 9 sequential
    # HTTP round trips just for handedness, and any single one of them
    # timing out on a slow connection could bog down the whole page load.
    ids = ",".join(x["id"] for x in lineup if x["id"])
    if ids:
        people_resp = _get_json("https://statsapi.mlb.com/api/v1/people",
                                params={"personIds": ids})
        # Leave everyone as "?" rather than silently guessing a side.
        if people_resp:
            bats_by_id = {
                str(person["id"]): (person.get("batSide", {}).get("code") or "?")
                for person in people_resp.get("people", [])
            }
            for x in lineup:
                x["bats"] = bats_by_id.get(x["id"], "?")

    lineup.sort(key=lambda x: x["battingOrder"])
    return lineup, True


@st.cache_data(ttl=1800, max_entries=40, show_spinner=False)
def get_all_teams():
    """
    Returns a clean list of all MLB team names. Returns an empty list
    (rather than crashing the page) if the MLB Stats API is unreachable —
    callers already handle an empty team list with a warning message.
    """
    # Names come from the shared _teams_raw() cache — this used to be
    # its own fetch of the very same list.
    return sorted(name for name, _tid in _teams_raw())


@st.cache_data(ttl=300, max_entries=40, show_spinner=False)
def get_live_team_roster(team_name: str):
    """
    Returns this team's CURRENT roster: rosterType=active (the real 26
    on the active roster right now) UNION rosterType=40Man (adds back
    anyone real but currently off the active 26 — IL, optioned,
    restricted, bereavement/paternity, etc.), de-duped by person id
    with the active entry kept on overlap.
    active-only was the actual bug: a team ALWAYS has some active
    roster, so a plain active-first/40Man-on-failure fallback never
    actually fell through — anyone off the active 26 was structurally
    guaranteed to be missing no matter what. Union is what "40Man as a
    backup" has to mean for every real player to show up.
    Cached for 5 minutes (short on purpose, so roster moves show up
    fast) rather than the 30-minute window used elsewhere.
    Returns an empty list (rather than crashing the page) if the MLB
    Stats API is unreachable or returns something unexpected.

    Uses hydrate=person on the roster call itself to get bats/throws
    inline, instead of one extra /people/{id} request per player — for
    a 40-man+active roster that used to mean 60-80 sequential HTTP
    calls per team (each with its own 10s timeout to fail badly on),
    which is what actually made roster pages slow and made a single
    flaky request look like a "missing player." Falls back to a single
    bulk /people?personIds=... call only for anyone hydrate didn't
    fill in, so worst case is a handful of extra calls, never one per
    player.
    """

    team_id = _team_id(team_name)
    if not team_id:
        return []

    roster_by_pid = {}  # active entries win on overlap; 40Man fills in the rest
    active_pids = set()  # who is on the ACTIVE 26 right now
    for roster_type in ("40Man", "active"):  # loaded in this order so active overwrites 40Man on overlap
        roster_url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
        resp = (_get_json(roster_url,
                          params={"rosterType": roster_type,
                                  "hydrate": "person"}) or {}).get("roster", [])
        for player in resp:
            pid = player.get("person", {}).get("id")
            if pid is not None:
                roster_by_pid[pid] = player
                if roster_type == "active":
                    # AVAILABILITY, free. This call already happens; we
                    # were simply throwing away which players came back
                    # from it. On the 40-man but NOT the active 26 means
                    # IL, optioned, or restricted — not playing tonight.
                    # MLB's own roster state, not a scrape or an inference.
                    active_pids.add(pid)

    if not roster_by_pid:
        return []

    players = []
    missing_bio_ids = []

    for player in roster_by_pid.values():
        pid = str(player["person"]["id"])
        is_active = player["person"]["id"] in active_pids
        full_name = player["person"]["fullName"]
        position_code = player.get("position", {}).get("abbreviation", "?")
        position_type = player.get("position", {}).get("type", "Unknown")  # "Pitcher" or "Hitter" etc.
        is_pitcher = position_type == "Pitcher" or position_code == "P"

        # hydrate=person should already have embedded batSide/pitchHand
        # on player["person"] — no per-player request needed for the
        # common case.
        bats = (player["person"].get("batSide", {}) or {}).get("code", "").upper() or None
        throws = (player["person"].get("pitchHand", {}) or {}).get("code", "").upper() or None
        if bats is None and throws is None:
            missing_bio_ids.append(pid)

        players.append({
            "name": full_name,
            "id": pid,
            "position": position_code,
            "is_pitcher": is_pitcher,
            "bats": bats,     # None means "unknown, real lookup failed" — not a guess
            "throws": throws,
            # True = on the active 26 today. False = on the 40-man but
            # not active, i.e. IL / optioned / restricted.
            "active": is_active,
        })

    # Rare fallback: hydrate didn't come through for a handful of players
    # (older cached edge or a schema hiccup) — one bulk call fills them
    # in rather than falling back to N individual requests.
    if missing_bio_ids:
        people_resp = (_get_json(
            "https://statsapi.mlb.com/api/v1/people",
            params={"personIds": ",".join(missing_bio_ids)}) or {}).get("people", [])
        # Leave as None rather than silently guessing "R".
        bio_by_id = {str(p["id"]): p for p in people_resp}
        for pl in players:
            if pl["id"] in bio_by_id:
                src = bio_by_id[pl["id"]]
                pl["bats"] = (src.get("batSide", {}).get("code", "").upper() or None)
                pl["throws"] = (src.get("pitchHand", {}).get("code", "").upper() or None)

    return players


@st.cache_data(ttl=300, max_entries=40, show_spinner=False)
def get_last_starting_lineup(team_name: str):
    """
    The real 9 starters from this team's most recently COMPLETED game —
    MLB's own posted lineup for that game, via the same boxscore source
    get_confirmed_lineup() uses. Nothing here is inferred from season
    usage patterns or depth-chart guessing; if MLB hasn't played/posted
    a game, this returns nothing rather than a fabricated "usual"
    lineup.

    Returns (lineup, game_date, confirmed) where lineup is a list of
    {"id", "name", "position", "bats", "battingOrder"} sorted by real
    batting order (9 real starters, one is "P" for the actual starter
    that day), game_date is the real date (YYYY-MM-DD) of that game, and
    confirmed is True only if a real posted lineup was found. Callers
    MUST check `confirmed` before showing this as "the starters."
    """
    team_id = _team_id(team_name)
    if not team_id:
        return [], None, False

    # Real schedule, last 14 real days through today — finds the most
    # recent actually-played (Final) game, never guesses one.
    from datetime import datetime, timedelta
    today = datetime.utcnow().date()
    start = today - timedelta(days=14)
    sched_url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={team_id}&startDate={start.isoformat()}&endDate={today.isoformat()}"
    )
    sched = _get_json(sched_url)
    if not sched:
        return [], None, False

    games = []
    for date_entry in sched.get("dates", []):
        for g in date_entry.get("games", []):
            state = g.get("status", {}).get("abstractGameState")
            if state == "Final":
                games.append(g)

    if not games:
        return [], None, False

    games.sort(key=lambda g: g.get("gameDate", ""))
    last_game = games[-1]
    game_pk = last_game.get("gamePk")
    away_id = last_game.get("teams", {}).get("away", {}).get("team", {}).get("id")
    side = "away" if away_id == team_id else "home"
    game_date = (last_game.get("gameDate") or "")[:10] or None

    lineup, confirmed = get_confirmed_lineup(game_pk, side)
    return lineup, game_date, confirmed


@st.cache_data(ttl=300, show_spinner=False)
def get_active_player_ids(team_name: str):
    """Set of player ids on this team's ACTIVE roster right now.

    Exists because a stale lineup is invisible. get_last_starting_lineup
    searches back FOURTEEN days for the most recent completed game, and
    the Game Card falls back to it whenever today's lineup hasn't been
    posted — which is exactly the window you'd be looking at the page in,
    the morning before lineups drop.

    A player who went on the IL nine days ago is still sitting in that
    lineup. He gets an HR Score, a matchup, park and wind adjustments,
    the whole row — every number correct except whether he is playing.
    Same failure as the WNBA boards had, on the other side of the site.

    Costs nothing extra: get_live_team_roster already requests the active
    roster, so this is data that was being fetched and discarded.

    Returns an EMPTY SET when the roster can't be read, and callers must
    treat empty as "unknown" rather than "nobody is active" — failing
    open beats blanking a lineup because one request timed out.
    """
    try:
        roster = get_live_team_roster(team_name) or []
    except Exception:
        return set()
    return {str(p.get("id")) for p in roster if p.get("active") and p.get("id")}
