"""
MLB team logos — official MLB static CDN (www.mlbstatic.com), keyed by
the real MLBAM team id from the same statsapi teams endpoint the
roster engine already uses. No scraping, no third-party image hosts:
these are the league's own logo files.

Cached name->id map (24h — franchise ids don't move). Every helper
degrades to None when a name can't be resolved, and callers render
text instead — a missing logo is never a broken image.
"""
import json

import streamlit as st

from engines.roster import _teams_raw

_LOGO_URL = "https://www.mlbstatic.com/team-logos/{tid}.svg"


@st.cache_data(ttl=86400, max_entries=2, show_spinner=False)
def _team_ids_json() -> str:
    try:
        # THE THIRD COPY OF THIS FETCH, now removed.
        #
        # teams?sportId=1 was being pulled independently here, having
        # already been pulled inside get_all_teams(), get_live_team_roster()
        # and get_last_starting_lineup() — all four hitting the same
        # endpoint for the same list, which changes about once a year.
        # roster._teams_raw() caches it for 24 hours and is now the only
        # place it is fetched.
        teams = _teams_raw()
    except Exception:
        return json.dumps({})
    return json.dumps({name: tid for name, tid in teams})


def team_id(name):
    try:
        return json.loads(_team_ids_json()).get(name)
    except Exception:
        return None


def logo_url_by_id(tid):
    return _LOGO_URL.format(tid=int(tid)) if tid else None


def logo_for(name):
    """Logo URL for a full team name, or None if unresolvable."""
    return logo_url_by_id(team_id(name))


@st.cache_data(ttl=86400, max_entries=1, show_spinner=False)
def _abbr_to_logo_json() -> str:
    """One prebuilt {abbreviation: logo_url} map.

    Built ONCE per day instead of per lookup. The first version of
    logo_for_any walked TEAM_ABBREVIATIONS calling logo_for() on each
    entry until it found a match, and every one of those calls ran
    json.loads() over the whole team map. A thirty-row table with two
    team columns therefore did hundreds of JSON parses on every rerun —
    every filter change, every scroll-triggered rerender.
    """
    try:
        from engines.team_abbreviations import TEAM_ABBREVIATIONS
        ids = json.loads(_team_ids_json())
    except Exception:
        return json.dumps({})
    out = {}
    for full, abbr in TEAM_ABBREVIATIONS.items():
        url = logo_url_by_id(ids.get(full))
        if url:
            out[abbr] = url
    return json.dumps(out)


def logo_for_any(name):
    """Logo URL from EITHER a full team name or an abbreviation.

    logo_for() maps full names only, because that's what the schedule
    feed returns. But the boards store abbreviations — Daily 13 keeps
    "ARI", not "Arizona Diamondbacks" — so calling logo_for() with a
    board's value silently returned None and no logo ever appeared.

    Reverses TEAM_ABBREVIATIONS to resolve the short form. Still returns
    None when nothing matches, so a caller renders text rather than a
    broken image.
    """
    if not name:
        return None
    direct = logo_for(name)
    if direct:
        return direct
    try:
        # One cached dict lookup, not a loop of JSON parses.
        return json.loads(_abbr_to_logo_json()).get(name)
    except Exception:
        return None
