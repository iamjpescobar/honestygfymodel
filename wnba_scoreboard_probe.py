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
        return

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
        print("  -> SHAPE MISMATCH: every event would be SKIPPED by "
              "parse_scoreboard_events (`if not comps: continue`)")

    print("\n  first event, trimmed:")
    print("  " + json.dumps(ev, indent=2)[:1200].replace("\n", "\n  "))

    # The real parser's verdict, which is the only number that counts.
    try:
        sys.path.insert(0, ".")
        from wnba_precompute import parse_scoreboard_events
        got = list(parse_scoreboard_events(data))
        print(f"\n  parse_scoreboard_events() -> {len(got)} games")
        for _eid, _st, _done, g in got[:3]:
            print(f"     {g.get('away')} @ {g.get('home')}  "
                  f"({_st}, completed={_done})")
    except Exception as exc:
        print(f"\n  could not run parse_scoreboard_events: "
              f"{type(exc).__name__}: {exc}")


def main(want_date):
    d = want_date.replace("-", "")
    print(f"WNBA scoreboard probe — date {want_date} (as {d})")
    for name, build_url, unwrap in SOURCES:
        probe(name, build_url(d), unwrap, want_date)
    print("\n" + "=" * 70)
    print("READ THIS AS: a source is usable only if it reports SHAPE OK")
    print("and a non-zero game count. 200 + JSON is not enough — that is")
    print("exactly what shipped an empty league on 2026-08-04.")
    return 0


if __name__ == "__main__":
    _d = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    sys.exit(main(_d))
