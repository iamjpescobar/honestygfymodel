"""
PROP LINES PROBE (10-23) — print only. Does a FREE public feed carry the
sportsbooks' PLAYER PROP lines and prices, so the boards can open on the
book's own line instead of a line the model guessed?

Izzy: "a lot of times i have to manually insert the line and the price
and most of the time it be off by 2 and up". The pages open each player
on a line the MODEL picks (the half-line under his projection, the line
nearest a coin flip) because no prop lines were ever loaded — the public
scoreboard and summary carry GAME odds only (handoff, NFL step 6). Rule:
no paid odds API. Rule 1: measure before building.

Asks ESPN's core API (sports.core.api.espn.com — the same company's feed
the site already reads) for one upcoming event per league:
  .../events/{id}/competitions/{id}/odds            -> which providers
  .../odds/{provider}/propBets?limit=1000           -> the player props
and prints: providers, the number of prop items, the prop TYPES (names),
and the raw shape of the first two items, so a parser can be written to
what is really there. Nothing is written, committed or deployed.

Usage: python prop_lines_probe.py [YYYY-MM-DD] (default: today, Eastern)
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

CORE = "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{lg}"
LEAGUES = ("nfl", "nhl", "nba", "mlb")


def _shape(obj, depth=0, maxd=5):
    """Keys and leaf samples, a few levels deep (dicts / first list item)."""
    if depth >= maxd:
        return "…"
    if isinstance(obj, dict):
        return {k: _shape(v, depth + 1, maxd) for k, v in list(obj.items())[:25]}
    if isinstance(obj, list):
        return [_shape(obj[0], depth + 1, maxd)] if obj else []
    return obj if not isinstance(obj, str) else obj[:120]


def upcoming_event(league, day, fetch_scoreboard):
    """(event id, label) of the first not-yet-final event from `day` on
    (up to 6 days ahead — football plays weekly)."""
    for k in range(7):
        d = day + timedelta(days=k)
        try:
            sb, _src = fetch_scoreboard(league, d.strftime("%Y%m%d"))
        except Exception as exc:  # noqa: BLE001
            print(f"  {league}: scoreboard {d} failed: {exc}")
            continue
        for ev in sb.get("events") or []:
            st = (((ev.get("status") or {}).get("type") or {}).get("state")) or ""
            if st != "post":
                return str(ev.get("id")), f"{ev.get('shortName') or ev.get('name')} ({d})"
    return None, None


def probe(league, eid, get, sport_lg):
    sport, lg = sport_lg
    base = CORE.format(sport=sport, lg=lg) + f"/events/{eid}/competitions/{eid}"
    out = {"league": league, "event": eid, "providers": [], "props": {}}
    try:
        odds = get(f"{base}/odds?lang=en&region=us")
    except Exception as exc:  # noqa: BLE001
        print(f"  [verify] PROPS {league}: odds list failed: {type(exc).__name__}: {exc}")
        return out
    items = (odds or {}).get("items") or []
    provs = []
    for it in items:
        p = (it or {}).get("provider") or {}
        provs.append((str(p.get("id")), p.get("name")))
    out["providers"] = provs
    print(f"  [verify] PROPS {league} event {eid}: {len(items)} odds providers {provs}")
    for pid, pname in provs[:4]:
        try:
            pb = get(f"{base}/odds/{pid}/propBets?lang=en&region=us&limit=1000")
        except Exception as exc:  # noqa: BLE001
            print(f"  [verify] PROPS {league} provider {pid} ({pname}): propBets failed: "
                  f"{type(exc).__name__}: {exc}")
            continue
        its = (pb or {}).get("items") or []
        types = Counter(str(((x or {}).get("type") or {}).get("name")
                            or ((x or {}).get("type") or {}).get("id")) for x in its)
        out["props"][pid] = {"n": len(its), "types": dict(types)}
        print(f"  [verify] PROPS {league} provider {pid} ({pname}): {len(its)} prop items "
              f"(count {(pb or {}).get('count')}); types {dict(types.most_common(25))}")
        for x in its[:2]:
            print(f"  [verify] PROPS {league} sample: {json.dumps(_shape(x), default=str)[:1500]}")
    return out


def main(argv=None):
    from engines import espn_feed as ef
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0]:
        day = datetime.strptime(argv[0], "%Y-%m-%d").date()
    else:
        from zoneinfo import ZoneInfo
        day = datetime.now(ZoneInfo("America/New_York")).date()
    found = 0
    for lg in LEAGUES:
        eid, lab = upcoming_event(lg, day, ef.fetch_scoreboard)
        if not eid:
            print(f"  [verify] PROPS {lg}: no upcoming event within a week of {day}")
            continue
        print(f"  [verify] PROPS {lg}: probing {lab}")
        r = probe(lg, eid, ef.get_json, ef.LEAGUES[lg])
        found += sum(v["n"] for v in r["props"].values())
    print(f"  [verify] PROPS total prop items seen: {found}"
          + ("" if found else " -> no free player-prop lines from ESPN's core feed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
