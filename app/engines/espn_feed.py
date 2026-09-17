"""ESPN scoreboard/summary access for ANY league — NFL and NHL today.

WHY NOT JUST COPY espn_wnba.py

espn_wnba's own docstring says it: a second private copy of the mirror
chain is how the WNBA live overlay died silently. So this module does
NOT re-implement the parts that are league-agnostic — get_json (retries
+ backoff) and _normalize_header_events (the header->competitions
reshape, measured 2026-08-03) are IMPORTED from espn_wnba and used as-is.
What is new here is only the thing espn_wnba hard-codes: which sport and
league the URLs point at.

WHAT IS PROVEN AND WHAT IS NOT

The host that answers from GitHub Actions was measured for WNBA
(site.web.api). NFL and NHL are the same hosts with a different path
segment, which is strong evidence but NOT a measurement.
nfl_nhl_probe.py (workflow: nfl-nhl-probe) measures it for these two
leagues. Until it has run, the fetchers' own [verify] lines are the
check: they print what parsed, and refuse to publish a league whose
finals produced zero box scores.

No streamlit import, same reason as espn_wnba: the fetchers and the
probe install only `requests`.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from engines.espn_wnba import UA, get_json, _normalize_header_events  # noqa: F401

EASTERN = ZoneInfo("America/New_York")

# (sport, league) path segments ESPN uses. One table, so a typo'd league
# raises instead of silently fetching the wrong sport.
LEAGUES = {
    "nfl": ("football", "nfl"),
    "nhl": ("hockey", "nhl"),
}

# Same vocabulary espn_wnba writes, plus the two statuses football and
# hockey add. A live override and a recorded slate must agree on what
# "in progress" means.
STATUS_MAP = {
    "STATUS_SCHEDULED": "scheduled",
    "STATUS_IN_PROGRESS": "in progress",
    "STATUS_HALFTIME": "in progress",
    "STATUS_END_PERIOD": "in progress",
    "STATUS_END_OF_REGULATION": "in progress",
    "STATUS_OVERTIME": "in progress",
    "STATUS_SHOOTOUT": "in progress",
    "STATUS_DELAYED": "in progress",
    "STATUS_RAIN_DELAY": "in progress",
    "STATUS_FINAL": "final",
    "STATUS_FINAL_OT": "final",
    "STATUS_FINAL_SO": "final",
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "postponed",
}


def _paths(league):
    try:
        return LEAGUES[league.lower()]
    except KeyError:
        raise KeyError(f"{league!r} is not in espn_feed.LEAGUES") from None


def base(league):
    """site.web.api base for summary/teams calls — the host measured to
    answer from Actions (see espn_wnba.BASE). NOT site.api."""
    sport, lg = _paths(league)
    return f"https://site.web.api.espn.com/apis/site/v2/sports/{sport}/{lg}"


def scoreboard_sources(league):
    """The same three-host chain espn_wnba uses, for this league.

    Order: the header host FIRST, because it is the one that was
    measured answering with real JSON while the other two returned a 403
    and an empty 202. espn_wnba keeps site.api first for historical
    reasons and learns the preference at runtime; starting here saves
    every run two failed attempts.
    """
    sport, lg = _paths(league)
    return [
        ("site.web.api",
         lambda d: ("https://site.web.api.espn.com/apis/v2/scoreboard/header"
                    f"?sport={sport}&league={lg}&dates={d}"),
         lambda j: (j or {}).get("sports", [{}])[0].get("leagues", [{}])[0]
         if (j or {}).get("sports") else j),
        ("site.api",
         lambda d: (f"https://site.api.espn.com/apis/site/v2/sports/"
                    f"{sport}/{lg}/scoreboard?dates={d}"),
         lambda j: j),
        ("cdn.espn",
         lambda d: f"https://cdn.espn.com/core/{lg}/scoreboard?xhr=1&date={d}",
         lambda j: (j or {}).get("content", {}).get("sbData", j)),
    ]


_PREFERRED = {}


def _is_scoreboard(data):
    # Key presence, not truthiness: an off-day is events=[] and is a
    # real answer. See espn_wnba._is_scoreboard.
    return isinstance(data, dict) and ("events" in data or "sports" in data)


def fetch_scoreboard(league, yyyymmdd, require_events=False, _get=None):
    """(payload, source_name) for one day. Raises only when every host
    fails, naming each — a silent empty slate reads like an off-day.

    require_events defaults to FALSE here (espn_wnba defaults True):
    football plays four days a week and hockey has a two-week preseason
    gap, so an empty day is the common case, not the suspicious one.
    """
    get = _get or get_json
    sources = scoreboard_sources(league)
    pref = _PREFERRED.get(league)
    if pref:
        sources = sorted(sources, key=lambda s: s[0] != pref)
    errors = []
    for name, build_url, unwrap in sources:
        try:
            data = unwrap(get(build_url(yyyymmdd), _attempts=2))
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__} {exc}")
            continue
        if not _is_scoreboard(data):
            errors.append(f"{name}: 200 but not a scoreboard payload")
            continue
        data = _normalize_header_events(data)
        if require_events and not data.get("events"):
            errors.append(f"{name}: 200 but no events")
            continue
        if _PREFERRED.get(league) != name:
            print(f"{league.upper()}: scoreboard via {name}")
            _PREFERRED[league] = name
        return data, name
    raise RuntimeError(f"every ESPN {league.upper()} scoreboard source "
                       f"failed -> " + " | ".join(errors))


def fetch_summary(league, event_id, _get=None):
    get = _get or get_json
    return get(f"{base(league)}/summary?event={event_id}")


def event_sides(event):
    """(comp, away, home) or (None, None, None)."""
    comp = ((event or {}).get("competitions") or [{}])[0]
    cs = comp.get("competitors") or []
    home = next((c for c in cs if c.get("homeAway") == "home"), None)
    away = next((c for c in cs if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None, None, None
    return comp, away, home


def status_of(event):
    """(status, completed, short_detail) for an event."""
    st = (event or {}).get("status") or {}
    t = st.get("type") if isinstance(st, dict) else None
    t = t if isinstance(t, dict) else {}
    status = STATUS_MAP.get(t.get("name", ""), "scheduled")
    completed = bool(t.get("completed")) or status == "final"
    return status, completed, (t.get("shortDetail") or t.get("detail") or "")


def odds_of(comp):
    """{'details','spread','total'} from whichever odds shape arrived.

    The full scoreboard gives a LIST of odds objects; the flattened
    header has been seen to give a single object. Reading [0] off a dict
    raises KeyError, so both are accepted here and nothing else is
    assumed. Values are copied, never computed.
    """
    raw = (comp or {}).get("odds")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, dict):
        return {}
    out = {}
    if raw.get("details"):
        out["details"] = str(raw["details"])
    if raw.get("overUnder") not in (None, ""):
        try:
            out["total"] = float(raw["overUnder"])
        except (TypeError, ValueError):
            pass
    if raw.get("spread") not in (None, ""):
        try:
            out["spread"] = float(raw["spread"])
        except (TypeError, ValueError):
            pass
    return out


def live_scores(league, yyyymmdd=None, _fetch=None):
    """{(away, home): {status, detail, scoreline?}} — {} on ANY failure.

    Same contract as espn_wnba.live_scores: a page render must never
    blank because an overlay could not be fetched.
    """
    day = yyyymmdd or datetime.now(EASTERN).strftime("%Y%m%d")
    fetch = _fetch or fetch_scoreboard
    try:
        data, _src = fetch(league, day, require_events=False)
    except Exception:
        return {}
    out = {}
    for ev in (data or {}).get("events") or []:
        _comp, away, home = event_sides(ev)
        if not away:
            continue
        key = ((away.get("team") or {}).get("displayName", ""),
               (home.get("team") or {}).get("displayName", ""))
        status, _done, detail = status_of(ev)
        entry = {"status": status, "detail": detail}
        if status in ("in progress", "final"):
            try:
                a = int(float(away.get("score")))
                h = int(float(home.get("score")))
                entry["scoreline"] = f"{key[0]} {a} - {h} {key[1]}"
                entry["away_score"], entry["home_score"] = a, h
            except (TypeError, ValueError):
                pass
        out[key] = entry
    return out


def box_group_index(group, wanted):
    """{our_key: column index} for one boxscore statistics group.

    Matches ESPN's machine `keys` first, then its display `labels`,
    because the two have each gone missing on some feed at some point.
    `wanted` is {our_key: (key_aliases, label_aliases)}. A stat whose
    column is not found is simply absent — never defaulted to 0.
    """
    keys = [str(k).lower() for k in (group.get("keys") or [])]
    labels = [str(l).upper() for l in (group.get("labels") or group.get("names") or [])]
    out = {}
    for ours, (k_alias, l_alias) in wanted.items():
        for k in k_alias:
            if k.lower() in keys:
                out[ours] = keys.index(k.lower())
                break
        else:
            for l in l_alias:
                if l.upper() in labels:
                    out[ours] = labels.index(l.upper())
                    break
    return out


def num(s):
    """Float from a box-score cell, or None. '--' and '' are missing."""
    if s is None:
        return None
    try:
        t = str(s).strip().replace(",", "")
        if t in ("", "-", "--", "—"):
            return None
        if t.endswith("%"):
            t = t[:-1]
        return float(t)
    except (TypeError, ValueError):
        return None


def pair(s):
    """'22/31' or '2-14' -> (22.0, 31.0); anything else -> (None, None)."""
    if s is None:
        return None, None
    t = str(s).strip()
    for sep in ("/", "-"):
        if sep in t:
            a, _, b = t.partition(sep)
            x, y = num(a), num(b)
            if x is not None and y is not None:
                return x, y
    return None, None


def clock_minutes(s):
    """'18:42' -> 18.7 minutes; '31:05' possession -> 31.08."""
    if s is None:
        return None
    t = str(s).strip()
    if ":" not in t:
        return num(t)
    m, _, sec = t.partition(":")
    mm, ss = num(m), num(sec)
    if mm is None or ss is None:
        return None
    return round(mm + ss / 60.0, 2)


def team_logo(team):
    t = team or {}
    u = t.get("logo")
    if not u:
        for cand in (t.get("logos") or []):
            if isinstance(cand, dict) and cand.get("href"):
                return cand["href"]
    return u or None


def to_et(iso_utc):
    """datetime in Eastern, or None."""
    try:
        return datetime.fromisoformat(str(iso_utc).replace("Z", "+00:00")).astimezone(EASTERN)
    except Exception:
        return None
