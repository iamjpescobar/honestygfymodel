"""
The live injury check (10-14) — what the boards learn AFTER the nightly.

The nightly reads every injury tag once, in the morning (engines/
availability). A skater ruled out at morning skate, a receiver downgraded
Saturday, an NFL inactive posted 90 minutes before kickoff — all of that
lands after the build, and until today the boards kept showing them.

Every NHL and NFL page now loads its slate through load_slate_live /
load_week_live: the nightly's slate, with ESPN's league injury list read
again (at most every LIVE_TTL seconds) laid over it.

  - Out / IR / Suspended NOW -> the player leaves the props, the
    goalies and the card, and is listed as "out since this morning".
  - Questionable / Day-to-day NOW -> his row keeps its number and
    carries the tag (the flag every board already prints).

A tag never changes a chance. It decides who is on the board — rule 1
still governs the numbers. A failed fetch changes nothing and says so.
"""
import copy
import time

from engines import availability as av

LIVE_TTL = 600            # seconds between reads of ESPN's list
FAIL_TTL = 120            # a failed read is retried sooner
TIMEOUT = 6               # per host; a page never waits long on ESPN
_CACHE = {}               # league -> (read_at, feed, ok)

_HOSTS = ("https://site.web.api.espn.com/apis/site/v2/sports/{sp}/{lg}/injuries",
          "https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/injuries")
_PATHS = {"nhl": ("hockey", "nhl"), "nfl": ("football", "nfl"),
          "nba": ("basketball", "nba")}


def _fetch(league, _get=None):
    import requests
    sp, lg = _PATHS[league]
    for url in _HOSTS:
        try:
            if _get:
                data = _get(url.format(sp=sp, lg=lg))
            else:
                r = requests.get(url.format(sp=sp, lg=lg), timeout=TIMEOUT,
                                 headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                data = r.json()
            feed = av.parse_injury_feed(data)
            if feed["by_id"] or feed["by_name"]:
                return feed, True
        except Exception:  # noqa: BLE001 — next host, then nothing
            continue
    return {"by_id": {}, "by_name": {}}, False


def feed(league, now=None, _get=None):
    """(feed, ok, read_at) — cached LIVE_TTL seconds (FAIL_TTL on failure)."""
    now = now if now is not None else time.time()
    hit = _CACHE.get(league)
    if hit and now - hit[0] < (LIVE_TTL if hit[2] else FAIL_TTL):
        return hit[1], hit[2], hit[0]
    f, ok = _fetch(league, _get)
    _CACHE[league] = (now, f, ok)
    return f, ok, now


def _status(p, f):
    return ((f.get("by_id") or {}).get(str(p.get("pid") or p.get("id") or ""))
            or (f.get("by_name") or {}).get(av.name_key(p.get("name"))))


def _apply(rows, f, newly_out, label):
    keep = []
    for p in rows or []:
        st = _status(p, f)
        if st and av.is_out(st):
            if not av.is_out(p.get("status")):
                newly_out.append(f"{p.get('name')} ({st})")
            continue
        if st and st != p.get("status"):
            p = dict(p, status=st, status_live=True)
        keep.append(p)
    return keep


def overlay(games, f, league):
    """A copy of the slate with the live tags laid over it, and the names
    ruled out since the nightly (each game gets "{side}_out_live")."""
    games = copy.deepcopy(games or [])
    lists = {"nhl": ("props", "goalie_props", "skaters", "goalies"),
             "nba": ("props",)}.get(league, ("players",))
    total = []
    for g in games:
        for side in ("away", "home"):
            newly = []
            for k in lists:
                key = f"{side}_{k}"
                if key in g:
                    g[key] = _apply(g[key], f, newly, k)
            if newly:
                g[f"{side}_out_live"] = sorted(set(newly))
                g[f"{side}_held_out"] = sorted(set((g.get(f"{side}_held_out") or [])
                                                   + [f"{n} — since this morning" for n in newly]))
                total += newly
    return games, sorted(set(total))


# ----------------------------------------------------------------------
# What the pages call
# ----------------------------------------------------------------------
LAST = {}                 # league -> {"ok", "read_at", "out": [...]} for the note


def load_slate_live(league="nhl"):
    from engines.slate_guard import load_slate
    games, d, cur = load_slate(league)
    if not games:
        return games, d, cur
    f, ok, at = feed(league)
    games, out = overlay(games, f, league) if ok else (games, [])
    LAST[league] = {"ok": ok, "read_at": at, "out": out}
    return games, d, cur


def load_week_live():
    from engines.nfl_week import load_week
    wk, state = load_week()
    if not wk or not wk.get("games"):
        return wk, state
    f, ok, at = feed("nfl")
    games, out = overlay(wk["games"], f, "nfl") if ok else (wk["games"], [])
    LAST["nfl"] = {"ok": ok, "read_at": at, "out": out}
    return dict(wk, games=games), state


def note(league):
    """The one line a page prints about the live check, or ''."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    x = LAST.get(league)
    if not x:
        return ""
    t = datetime.fromtimestamp(x["read_at"], ZoneInfo("America/New_York")).strftime("%-I:%M %p")
    if not x["ok"]:
        return f"Live injury check unavailable right now ({t}) — showing this morning's report."
    if not x["out"]:
        return f"Live injury check {t} ET: nobody ruled out since this morning's build."
    return (f"Live injury check {t} ET: ruled out since this morning — "
            + ", ".join(x["out"]) + ". Removed from every board.")


def render_note(league):
    """Print the live-check line on a page (warning colour when someone was
    ruled out since the nightly)."""
    import streamlit as st
    txt = note(league)
    if not txt:
        return
    x = LAST.get(league) or {}
    if x.get("out"):
        st.warning(txt)
    else:
        st.caption(txt)
