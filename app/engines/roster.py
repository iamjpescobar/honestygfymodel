import requests
import streamlit as st


@st.cache_data(ttl=300)
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
    try:
        url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
        data = requests.get(url, timeout=10).json()
        team_data = data.get("teams", {}).get(side, {})
        players = team_data.get("players", {})
    except Exception:
        return [], False

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
        try:
            people_resp = requests.get(
                "https://statsapi.mlb.com/api/v1/people",
                params={"personIds": ids},
                timeout=10,
            ).json()
            bats_by_id = {
                str(person["id"]): (person.get("batSide", {}).get("code") or "?")
                for person in people_resp.get("people", [])
            }
            for x in lineup:
                x["bats"] = bats_by_id.get(x["id"], "?")
        except Exception:
            pass  # leave everyone as "?" rather than silently guessing a side

    lineup.sort(key=lambda x: x["battingOrder"])
    return lineup, True


@st.cache_data(ttl=1800)
def get_all_teams():
    """
    Returns a clean list of all MLB team names. Returns an empty list
    (rather than crashing the page) if the MLB Stats API is unreachable —
    callers already handle an empty team list with a warning message.
    """
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        teams = resp.json().get("teams", [])
    except Exception:
        return []
    return sorted([t["name"] for t in teams])


@st.cache_data(ttl=300)
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

    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    try:
        teams = requests.get(teams_url, timeout=10).json().get("teams", [])
    except Exception:
        return []

    team_id = None
    for t in teams:
        if t["name"].lower() == team_name.lower():
            team_id = t["id"]
            break

    if not team_id:
        return []

    roster_by_pid = {}  # active entries win on overlap; 40Man fills in the rest
    for roster_type in ("40Man", "active"):  # loaded in this order so active overwrites 40Man on overlap
        roster_url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
        try:
            resp = requests.get(
                roster_url,
                params={"rosterType": roster_type, "hydrate": "person"},
                timeout=10,
            ).json().get("roster", [])
        except Exception:
            resp = []
        for player in resp:
            pid = player.get("person", {}).get("id")
            if pid is not None:
                roster_by_pid[pid] = player

    if not roster_by_pid:
        return []

    players = []
    missing_bio_ids = []

    for player in roster_by_pid.values():
        pid = str(player["person"]["id"])
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
            "throws": throws
        })

    # Rare fallback: hydrate didn't come through for a handful of players
    # (older cached edge or a schema hiccup) — one bulk call fills them
    # in rather than falling back to N individual requests.
    if missing_bio_ids:
        try:
            people_resp = requests.get(
                "https://statsapi.mlb.com/api/v1/people",
                params={"personIds": ",".join(missing_bio_ids)},
                timeout=10,
            ).json().get("people", [])
            bio_by_id = {str(p["id"]): p for p in people_resp}
            for pl in players:
                if pl["id"] in bio_by_id:
                    src = bio_by_id[pl["id"]]
                    pl["bats"] = (src.get("batSide", {}).get("code", "").upper() or None)
                    pl["throws"] = (src.get("pitchHand", {}).get("code", "").upper() or None)
        except Exception:
            pass  # leave as None rather than silently guessing "R"

    return players


@st.cache_data(ttl=300)
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
    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    try:
        teams = requests.get(teams_url, timeout=10).json().get("teams", [])
    except Exception:
        return [], None, False

    team_id = None
    for t in teams:
        if t["name"].lower() == team_name.lower():
            team_id = t["id"]
            break

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
    try:
        sched = requests.get(sched_url, timeout=10).json()
    except Exception:
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


def get_pitchers(team_name: str):
    """Convenience filter: only real pitchers on the roster."""
    return [p for p in get_live_team_roster(team_name) if p["is_pitcher"]]


def get_position_players(team_name: str):
    """Convenience filter: only real position players (non-pitchers) on the roster."""
    return [p for p in get_live_team_roster(team_name) if not p["is_pitcher"]]