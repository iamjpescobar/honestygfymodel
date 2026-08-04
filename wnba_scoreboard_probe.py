"""
Print what each ESPN scoreboard MIRROR actually returns for one date.

WHY THIS EXISTS

wnba_probe.py answers a different question — it dumps an athlete's
gamelog, for diagnosing why a pick failed to grade. This one is about
the layer above: which scoreboard host answers at all, and whether what
it hands back is in the shape parse_scoreboard_events can read.

The nightly of 2026-08-04 is what prompted it. The backfill was routed
through the mirror list and a mirror DID answer — 87 of 124 days came
back 200 — and the run still produced zero games, zero box scores and
zero players. Three different failures were hiding behind one summary
line:

    site.api      -> HTTP 403 (blocked from cloud IPs, as documented)
    cdn.espn      -> 200, but the body is not JSON at all
    site.web.api  -> 200 with real JSON, but events in a DIFFERENT shape

That third one is the dangerous one, because it looks like success
everywhere except the number at the end. parse_scoreboard_events needs
event["competitions"][0]["competitors"] with homeAway on each side; if
the mirror nests them differently, every event is skipped by the
`if not comps: continue` guard and the day yields nothing, silently.

So this prints the STRUCTURE, not an interpretation: status, byte count,
content-type, top-level keys, where the events array lives, and — the
whole point — whether the first event carries a `competitions` block
that the real parser would accept. It also runs that parser directly and
reports how many games it got, which is the only answer that matters.

No parsing decisions are made here and nothing is written. Run it from
the workflow of the same name, or locally where espn.com is reachable:

    python wnba_scoreboard_probe.py 2026-08-03
"""
import json
import sys
from datetime import date

import requests

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
}

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"

# Deliberately duplicated from wnba_precompute rather than imported: this
# is a diagnostic, and it must keep working even if that module is mid-fix
# or fails to import. If the two ever disagree, that disagreement is
# itself worth seeing.
SOURCES = [
    ("site.api",
     lambda d: f"{BASE}/scoreboard?dates={d}",
     lambda j: j),
    ("cdn.espn",
     lambda d: f"https://cdn.espn.com/core/wnba/scoreboard?xhr=1&date={d}",
     lambda j: (j or {}).get("content", {}).get("sbData", j)),
    ("site.web.api",
     lambda d: ("https://site.web.api.espn.com/apis/v2/scoreboard/header"
                f"?sport=basketball&league=wnba&dates={d}"),
     lambda j: (j or {}).get("sports", [{}])[0].get("leagues", [{}])[0]
     if (j or {}).get("sports") else j),
]


def _keys(obj, limit=14):
    if isinstance(obj, dict):
        k = sorted(obj.keys())
        return k[:limit] + (["..."] if len(k) > limit else [])
    return f"<{type(obj).__name__}>"


def _find_events(obj, path="", depth=0):
    """Every 'events' array in the payload, with where it was found.

    Reported rather than assumed: if a mirror buries the array one level
    deeper than the unwrap expects, that is exactly the bug, and it is
    invisible unless you go looking for the array wherever it actually is.
    """
    out = []
    if depth > 4:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k == "events" and isinstance(v, list):
                out.append((p, len(v)))
            out.extend(_find_events(v, p, depth + 1))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            out.extend(_find_events(v, f"{path}[{i}]", depth + 1))
    return out


def probe(name, url, unwrap, want_date):
    print("\n" + "=" * 70)
    print(f"{name}\n{url}")
    print("=" * 70)

    try:
        r = requests.get(url, headers=UA, timeout=25)
    except Exception as exc:
        print(f"  REQUEST FAILED: {type(exc).__name__}: {exc}")
        return

    ctype = r.headers.get("content-type", "?")
    print(f"  HTTP {r.status_code}   {len(r.content):,} bytes   {ctype}")

    if r.status_code != 200:
        print(f"  body starts: {r.text[:200]!r}")
        return None

    try:
        raw = r.json()
    except Exception as exc:
        # The cdn.espn case. Seeing the first bytes tells you instantly
        # whether it is an HTML error page, a redirect, or a challenge.
        print(f"  NOT JSON: {type(exc).__name__}: {exc}")
        print(f"  body starts: {r.text[:300]!r}")
        return

    print(f"  raw top-level keys: {_keys(raw)}")

    found = _find_events(raw)
    print(f"  'events' arrays found in RAW payload: {found or 'NONE'}")

    try:
        data = unwrap(raw)
    except Exception as exc:
        print(f"  UNWRAP FAILED: {type(exc).__name__}: {exc}")
        return

    print(f"  after unwrap, keys: {_keys(data)}")
    events = (data or {}).get("events") if isinstance(data, dict) else None
    print(f"  unwrapped events: "
          f"{len(events) if isinstance(events, list) else 'NONE'}")

    if not events:
        return

    ev = events[0]
    print(f"\n  FIRST EVENT keys: {_keys(ev)}")
    _ids = (ev.get("id"), None)

    # THE QUESTION THIS PROBE EXISTS TO ANSWER.
    comps = ev.get("competitions") if isinstance(ev, dict) else None
    if isinstance(comps, list) and comps:
        cs = (comps[0] or {}).get("competitors") or []
        sides = [c.get("homeAway") for c in cs]
        print(f"  competitions[0].competitors: {len(cs)}  homeAway={sides}")
        print("  -> SHAPE OK: parse_scoreboard_events can read this")
    else:
        print(f"  competitions: {comps!r}")
        # Where did the teams go instead?
        alt = ev.get("competitors") if isinstance(ev, dict) else None
        if isinstance(alt, list):
            print(f"  BUT event.competitors exists: {len(alt)} entries")
            print(f"     first competitor keys: {_keys(alt[0]) if alt else '-'}")
        print("  -> SHAPE MISMATCH for the RAW parser "
              "(`if not comps: continue`)")
        if isinstance(alt, list) and alt:
            _ids = (ev.get("id"), str(alt[0].get("id") or ""))

    print("\n  first event, trimmed:")
    print("  " + json.dumps(ev, indent=2)[:1200].replace("\n", "\n  "))

    # The real parser's verdict, which is the only number that counts.
    try:
        sys.path.insert(0, ".")
        from wnba_precompute import (parse_scoreboard_events,
                                     _normalize_header_events)
        raw_n = len(list(parse_scoreboard_events(data)))
        got = list(parse_scoreboard_events(_normalize_header_events(data)))
        print(f"\n  parse_scoreboard_events(raw)        -> {raw_n} games")
        print(f"  parse_scoreboard_events(normalized) -> {len(got)} games")
        for _eid, _st, _done, g in got[:3]:
            print(f"     {g.get('away')} {g.get('away_score','-')} - "
                  f"{g.get('home_score','-')} {g.get('home')}  "
                  f"({_st}, completed={_done}, id={_eid})")
        if got:
            _e0 = got[0][3]
            _ids = (got[0][0], _e0.get("away_id") or _e0.get("home_id"))
    except Exception as exc:
        print(f"\n  could not run the parser: {type(exc).__name__}: {exc}")
    return _ids


def probe_downstream(event_id, team_id):
    """The endpoints the scoreboard is only the doorway to — across EVERY
    host that might serve them.

    The 2026-08-03 probe closed the first question: site.api.espn.com
    returns 403 Access Denied on /summary, on /teams/{id}/roster AND on
    the gamelog control, which had been working. So the whole host is
    shut to this runner, not one path.

    What it also showed, seconds apart in the same run, is that
    site.web.api.espn.com answered with 70 KB of real JSON. The runner is
    not banned from ESPN — it is banned from one hostname. So the only
    question left is whether the same paths exist on a host that answers,
    and that is a question about which URL, not about parsing.

    Each path is therefore tried on every candidate host, and the first
    combination that returns the blocks we need is the answer.
    """
    print("\n\n" + "#" * 70)
    print("# DOWNSTREAM ENDPOINTS — every path, on every host")
    print("#" * 70)

    # Hosts, in the order worth trying. site.web.api is FIRST because it
    # is the one measured to work.
    HOSTS = [
        ("site.web.api", "https://site.web.api.espn.com"),
        ("site.api", "https://site.api.espn.com"),
        ("cdn.espn", "https://cdn.espn.com"),
    ]

    V2 = "/apis/site/v2/sports/basketball/wnba"
    V3 = "/apis/common/v3/sports/basketball/wnba"

    paths = [
        ("box score / summary", f"{V2}/summary?event={event_id}",
         ("boxscore", "rosters", "injuries")),
        ("team roster", f"{V2}/teams/{team_id}/roster",
         ("athletes", "team")),
        ("athlete gamelog", f"{V3}/athletes/4398966/gamelog",
         ("events", "seasonTypes", "labels")),
    ]

    winners = {}
    for label, path, want in paths:
        print(f"\n--- {label}")
        for hname, root in HOSTS:
            url = root + path
            try:
                r = requests.get(url, headers=UA, timeout=25)
            except Exception as exc:
                print(f"    {hname:<14} REQUEST FAILED {type(exc).__name__}")
                continue
            line = (f"    {hname:<14} HTTP {r.status_code}  "
                    f"{len(r.content):>9,} bytes  "
                    f"{r.headers.get('content-type','?')[:30]}")
            if r.status_code != 200 or not r.content:
                print(line + "   -> no")
                continue
            try:
                j = r.json()
            except Exception:
                print(line + "   -> not JSON")
                continue
            present = [k for k in want if isinstance(j, dict) and k in j]
            if present:
                print(line + f"   -> USABLE  has {present}")
                winners.setdefault(label, (hname, url))
            else:
                print(line + f"   -> 200 but keys={_keys(j, 8)}")

    print("\n" + "-" * 70)
    if winners:
        print("WORKING COMBINATIONS FOUND:")
        for label, (hname, url) in winners.items():
            print(f"  {label:<22} {hname}")
            print(f"    {url}")
        print("\n-> Point wnba_precompute's BASE (and the gamelog URL) at")
        print("   the host above. This is a URL change, not a parser change.")
    else:
        print("NO HOST SERVED ANY OF THESE PATHS.")
        print("-> ESPN is not a viable source from GitHub Actions right now.")
        print("   Options: run the fetch elsewhere (a small VPS, Render")
        print("   cron, your own machine) and commit the result, or move")
        print("   to a different data provider. No parser change helps.")
    return winners


def main(want_date):
    d = want_date.replace("-", "")
    print(f"WNBA scoreboard probe — date {want_date} (as {d})")
    first_event, first_team = None, None
    for name, build_url, unwrap in SOURCES:
        got = probe(name, build_url(d), unwrap, want_date)
        if got and not first_event:
            first_event, first_team = got

    if first_event:
        probe_downstream(first_event, first_team or "17")
    else:
        print("\nNo event id recovered, so the downstream endpoints could "
              "not be probed.")

    print("\n" + "=" * 70)
    print("READ THIS AS: a source is usable only if it reports SHAPE OK")
    print("and a non-zero game count. 200 + JSON is not enough — that is")
    print("exactly what shipped an empty league on 2026-08-04.")
    print("And if the downstream section shows BLOCKED, fixing the")
    print("scoreboard alone will NOT bring the league back.")
    return 0


if __name__ == "__main__":
    _d = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    sys.exit(main(_d))
