"""
Print what ESPN actually returns for a WNBA gamelog.

WHY THIS EXISTS

Every fix to _wnba_line so far has been reasoned from a payload shape
rather than from the payload. That produced two real fixes — the ET/UTC
date comparison, and reading the short `labels` array plus the stat rows
under seasonTypes — and it still left thirty picks failing with "no
event matching the date", which nobody has actually looked at.

The container this was written in cannot reach espn.com. GitHub Actions
can. So this fetches one gamelog and prints its STRUCTURE: the top-level
keys, the shape of `events`, the real gameDate strings, and where the
stat rows live. No parsing, no interpretation, no guessing.

Run it from the workflow of the same name, or locally:

    python wnba_probe.py 4398966 2026-08-03

Defaults to a player and date taken from a real pick that failed.
"""
import json
import sys

import requests

URL = ("https://site.api.espn.com/apis/common/v3/sports/basketball/wnba/"
       "athletes/{pid}/gamelog")


def main(pid: str, want_date: str):
    print(f"GET {URL.format(pid=pid)}\n")
    resp = requests.get(URL.format(pid=pid), timeout=20)
    print(f"HTTP {resp.status_code}  ({len(resp.content)} bytes)")
    resp.raise_for_status()
    data = resp.json()

    if not isinstance(data, dict):
        print(f"Response is a {type(data).__name__}, not an object.")
        print(json.dumps(data)[:800])
        return 0

    print(f"\nTOP-LEVEL KEYS: {sorted(data.keys())}")

    for key in ("labels", "names", "displayNames"):
        val = data.get(key)
        if val:
            print(f"\n{key} ({len(val)}): {val}")

    events = data.get("events")
    print(f"\nevents: {type(events).__name__}, "
          f"{len(events) if hasattr(events, '__len__') else 'n/a'} entries")
    if isinstance(events, dict) and events:
        eid, ev = next(iter(events.items()))
        print(f"  one entry, key={eid!r}:")
        print("  " + json.dumps(ev, indent=2)[:900].replace("\n", "\n  "))
        # The whole question: what dates are actually in here, and in
        # what format? "no event matching the date" means this list did
        # not contain want_date after conversion.
        dates = sorted({str(e.get("gameDate") or "") for e in events.values()})
        print(f"\n  ALL gameDate values ({len(dates)}):")
        for d in dates:
            print(f"    {d}")
        print(f"\n  looking for ET date: {want_date}")

    seasons = data.get("seasonTypes")
    print(f"\nseasonTypes: {type(seasons).__name__}, "
          f"{len(seasons) if hasattr(seasons, '__len__') else 'n/a'} entries")
    if isinstance(seasons, list) and seasons:
        s0 = seasons[0]
        print(f"  [0] keys: {sorted(s0.keys()) if isinstance(s0, dict) else s0}")
        cats = (s0 or {}).get("categories") or []
        print(f"  [0].categories: {len(cats)}")
        if cats:
            evs = (cats[0] or {}).get("events") or []
            print(f"  [0].categories[0].events: {len(evs)}")
            if evs:
                print("  one stat row:")
                print("  " + json.dumps(evs[0], indent=2)[:600].replace("\n", "\n  "))

    print("\nDone. Paste this whole block back.")
    return 0


if __name__ == "__main__":
    _pid = sys.argv[1] if len(sys.argv) > 1 else "4398966"
    _date = sys.argv[2] if len(sys.argv) > 2 else "2026-08-03"
    sys.exit(main(_pid, _date))
