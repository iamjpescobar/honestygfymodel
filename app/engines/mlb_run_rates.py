"""
MLB team runs scored and allowed per game — the input tier 2 of the
best-games ranking has been waiting on.

WHERE THIS COMES FROM, AND WHY IT TOOK FOUR PROBE ROUNDS
--------------------------------------------------------
`/api/v1/standings?leagueId=103,104&standingsTypes=regularSeason`.

Every `teams/stats` shape was tried first and all of them return exactly
ONE entry — the LEAGUE AGGREGATE. Run 85312622391:

    teams/stats hitting   200 | 1 entries | 1 w/stats | 1 w/runs
                              e.g. ?: 591 runs in 119 G

Note the missing team name. There wasn't one, because that row is not a
club. It reads like a club until you look at the name, which is exactly
how it survived two rounds recorded as "PARTIAL: 1 of 30".

Standings answers the right question. Run 85313739682:

    standings regularSeason  200 | 30 entries | 30 w/stats | 30 w/runs
                                 e.g. Rays: 519 runs in 117 G

Thirty clubs, one call, and a real name attached.

SHAPE. Entries nest TWO levels down — `records[]` is the six divisions,
and each carries `teamRecords[]`. Counting the outer list gives 6, and
6-of-30 reads like a partial failure rather than a parsing mistake. That
misread cost a round on its own.

WHAT THIS DOES NOT DO
---------------------
It does not project anything. `engines/run_total.project_total()` already
does that, has done since KBO and NPB, and is league-agnostic —
`league_rs_pg` is a PARAMETER measured from whatever teams it is handed,
not a frozen constant, so MLB's run environment goes in cleanly with no
second copy of the maths.

This module's whole job is to turn one HTTP response into the dict shape
that engine already accepts: {"rs_pg": float, "ra_pg": float}. It is
deliberately thin, because the thing most likely to go wrong here is the
PARSE, and a thin parser is one you can read in full.

WHY IT LIVES BESIDE THE SLATE BUILDER AND NOT IN A VIEW
-------------------------------------------------------
It makes a network call. calibration_picks runs it in CI at 1, 5 and 7
PM ET and writes the result into the published slate; Home reads the file
(rule 5 — Home makes zero network calls). Nothing on a page calls this.
"""
import requests

# The two league ids are American (103) and National (104). Both in one
# call: two calls would mean two chances for one to fail and leave half a
# league unmeasured, which is the failure mode that produces a ranking
# where fifteen clubs have a projected total and fifteen do not.
STANDINGS_URL = (
    "https://statsapi.mlb.com/api/v1/standings"
    "?leagueId=103,104&season={season}&standingsTypes=regularSeason"
)

# A club is only usable with BOTH runs and games. See the None-not-zero
# note in fetch_team_run_rates.
_NEEDED = ("runsScored", "runsAllowed", "gamesPlayed")


# ONE NAME PER CLUB, DERIVED — NOT A SECOND HAND-WRITTEN MAP.
#
# The two MLB endpoints disagree about what a team is called:
#
#   schedule   "Detroit Tigers"   "Cleveland Guardians"
#   standings  "Tigers"           "Guardians"
#
# Measured, not assumed — the 2026-08-11 run printed both and reported
# `home matched: False | away matched: False` for all fifteen games.
# Tier 2 wrote zero totals with no error, because the fetch succeeded
# and every lookup missed.
#
# Both forms are reduced to the abbreviation, and the mapping is DERIVED
# from engines/team_abbreviations — the map the app already uses and has
# already verified. A second hand-written table of thirty clubs would be
# a second thing to be wrong, and it would drift the day a team renames.
#
# AMBIGUOUS SUFFIXES ARE DROPPED. "Sox" is the last word of both Red Sox
# and White Sox; a suffix that resolves to more than one club resolves to
# NONE. Guessing which of two clubs is meant would put the wrong offense
# on a card, and nothing on screen could contradict it.
def _build_alias_index():
    from engines.team_abbreviations import TEAM_ABBREVIATIONS
    hits = {}
    for full, abbr in TEAM_ABBREVIATIONS.items():
        hits.setdefault(full.lower(), set()).add(abbr)
        parts = full.split()
        for n in range(1, min(3, len(parts)) + 1):
            hits.setdefault(" ".join(parts[-n:]).lower(), set()).add(abbr)
    return {k: next(iter(v)) for k, v in hits.items() if len(v) == 1}


_ALIASES = _build_alias_index()


def canonical(name):
    """Any known form of a club's name -> its abbreviation, or None.

    None means UNRECOGNISED, and the caller must treat it as unmeasured
    rather than falling back to the raw string — a raw-string fallback is
    what silently produced fifteen misses in the first place.
    """
    return _ALIASES.get(str(name or "").strip().lower())


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def parse_standings(payload):
    """{team_name: {"rs_pg": float, "ra_pg": float, "games": int}}

    Pure — no network, so the shape can be tested against a saved
    payload. That separation is the point: three of the four probe
    rounds went wrong in the PARSE, not the fetch, and a parser you
    cannot exercise offline is one you debug in production.
    """
    out = {}
    if not isinstance(payload, dict):
        return out
    for record in payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        for tr in record.get("teamRecords") or []:
            if not isinstance(tr, dict):
                continue
            name = ((tr.get("team") or {}).get("name") or "").strip()
            rs, ra, g = (_num(tr.get(k)) for k in _NEEDED)
            if not name or not g:
                continue
            # MISSING IS NOT ZERO. A club with runsScored absent is
            # unmeasured, not a club that has scored no runs — and a
            # 0.00 rs_pg would drag the league average down AND make
            # that team look like the worst offense in baseball. Both
            # errors are invisible on a card.
            if rs is None or ra is None:
                continue
            rec = {
                "rs_pg": round(rs / g, 3),
                "ra_pg": round(ra / g, 3),
                "games": int(g),
                "name": name,
                "abbr": canonical(name),
            }
            out[name] = rec
            # ALSO keyed by abbreviation, so a caller holding the
            # schedule's vocabulary finds the same record. Both keys
            # point at ONE dict — league_run_average would otherwise
            # count every club twice and halve nothing, but report a
            # 60-club league, which is the kind of wrong that looks fine.
            if rec["abbr"]:
                out[rec["abbr"]] = rec
    return out


def fetch_team_run_rates(season, timeout=25):
    """(rates, error) — every club's runs per game, or ({}, why).

    Returns a REASON rather than raising, because this runs beside six
    pick builders in CI and a standings outage must not cost the day's
    picks. The caller writes no proj_total when this comes back empty,
    and tier 2 simply does not fire — which is the behaviour it has had
    all along and is already tested.
    """
    try:
        r = requests.get(STANDINGS_URL.format(season=season), timeout=timeout)
        if r.status_code != 200:
            return {}, f"standings returned HTTP {r.status_code}"
        rates = parse_standings(r.json())
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"

    # A PARTIAL LEAGUE IS REFUSED, not shipped.
    #
    # 30 clubs or nothing. With 22, the eight unmeasured teams get no
    # projected total, tier 2 fires on some games and not others, and the
    # ranking silently mixes two different sorts — games ranked on three
    # tiers against games ranked on two. Nobody reading the card could
    # tell. The probe refused a partial for the same reason and it was
    # right to.
    # COUNT DISTINCT CLUBS, not keys. Every club is keyed twice (name and
    # abbreviation), so len(rates) is 60 on a healthy league and this
    # guard would never fire — a partial league would sail straight
    # through the check written to stop it.
    n_clubs = len({id(v) for v in rates.values()})
    if 0 < n_clubs < 30:
        return {}, (f"only {n_clubs} of 30 clubs carried runs — refusing a "
                    f"partial league rather than ranking half the slate on "
                    f"three tiers and half on two")
    if not rates:
        return {}, "standings carried no usable club records"
    return rates, None
