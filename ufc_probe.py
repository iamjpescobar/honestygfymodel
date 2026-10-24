"""
UFC PROBE (10-24) — print only. What can the site build for UFC from free
feeds? Izzy, 10-24: "What can we do with ufc?" Rule 1: measure first.

Asks, from an Actions runner:
  1. ESPN's MMA scoreboard (site.web.api, then site.api): the next UFC
     card — its fights (competitions), fighters, records, odds on the
     scoreboard.
  2. ESPN's core API for that card: each fight's odds providers and
     DraftKings' propBets for the first fights (method of victory, total
     rounds, goes the distance, fighter stat props?) — counts, types and
     two raw samples.
  3. ESPN's core event list for 2025 (how many past cards a backfill would
     have), one finished fight's summary keys (method, round, time?) and
     one fighter's statistics record.
  4. ufcstats.com (the official per-fight striking / grappling stats):
     does it answer from Actions, and how big is the completed-events page.
Nothing is written, committed or deployed.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

SITE = ("https://site.web.api.espn.com/apis/site/v2/sports/mma/ufc",
        "https://site.api.espn.com/apis/site/v2/sports/mma/ufc")
CORE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"


def _shape(obj, depth=0, maxd=4):
    if depth >= maxd:
        return "…"
    if isinstance(obj, dict):
        return {k: _shape(v, depth + 1, maxd) for k, v in list(obj.items())[:30]}
    if isinstance(obj, list):
        return [_shape(obj[0], depth + 1, maxd)] if obj else []
    return obj if not isinstance(obj, str) else obj[:100]


def say(msg):
    print(f"  [verify] UFC {msg}")


def scoreboard(get):
    for base in SITE:
        try:
            js = get(f"{base}/scoreboard")
            if isinstance(js, dict) and "events" in js:
                say(f"scoreboard via {base.split('/')[2]}: {len(js.get('events') or [])} events")
                return js, base
        except Exception as exc:  # noqa: BLE001
            say(f"scoreboard {base.split('/')[2]} failed: {type(exc).__name__}: {exc}")
    return None, None


def card_info(js):
    """(event id, name, date, [(competition id, fighter A, fighter B)])"""
    evs = (js or {}).get("events") or []
    if not evs:
        return None, None, None, []
    ev = evs[0]
    fights = []
    for c in ev.get("competitions") or []:
        names = [((x.get("athlete") or {}).get("displayName")) for x in c.get("competitors") or []]
        fights.append((str(c.get("id")), *(names + [None, None])[:2]))
    return str(ev.get("id")), ev.get("name"), ev.get("date"), fights


def probe_odds(get, eid, fights, k=3):
    types, n_items = Counter(), 0
    for cid, a, b in fights[:k]:
        base = f"{CORE}/events/{eid}/competitions/{cid}/odds"
        try:
            od = get(f"{base}?lang=en&region=us")
        except Exception as exc:  # noqa: BLE001
            say(f"odds {a} vs {b} failed: {type(exc).__name__}: {exc}")
            continue
        provs = [(str((i.get("provider") or {}).get("id")), (i.get("provider") or {}).get("name"))
                 for i in (od or {}).get("items") or []]
        say(f"fight {a} vs {b}: odds providers {provs}")
        for it in ((od or {}).get("items") or [])[:1]:
            say(f"fight odds sample: {json.dumps(_shape(it), default=str)[:1200]}")
        for pid, _pn in provs[:1]:
            try:
                pb = get(f"{base}/{pid}/propBets?lang=en&region=us&limit=1000")
            except Exception as exc:  # noqa: BLE001
                say(f"propBets failed: {type(exc).__name__}: {exc}")
                continue
            its = (pb or {}).get("items") or []
            n_items += len(its)
            types.update(str((x.get("type") or {}).get("name")) for x in its)
            for x in its[:2]:
                say(f"prop sample: {json.dumps(_shape(x), default=str)[:900]}")
    say(f"props over the first {k} fights: {n_items} items; types {dict(types.most_common(30))}")
    return n_items, types


def main():
    from engines import espn_feed as ef
    get = ef.get_json
    js, base = scoreboard(get)
    eid, name, date, fights = card_info(js)
    say(f"next card: {name} ({date}), event {eid}, {len(fights)} fights: "
        f"{[f'{a} vs {b}' for _c, a, b in fights[:6]]}")
    if js and js.get("events"):
        c0 = ((js["events"][0].get("competitions") or [{}])[0]) or {}
        say(f"scoreboard fight shape: {json.dumps(_shape(c0, maxd=3), default=str)[:1500]}")
    if eid and fights:
        probe_odds(get, eid, fights)
    try:
        lst = get(f"{CORE}/seasons/2025/types/1/events?limit=100")
        say(f"core 2025 events: count {(lst or {}).get('count')}, pages {(lst or {}).get('pageCount')}")
    except Exception as exc:  # noqa: BLE001
        say(f"core 2025 event list failed: {type(exc).__name__}: {exc}")
        try:
            lst = get(f"{CORE}/events?dates=2025&limit=100")
            say(f"core events?dates=2025: count {(lst or {}).get('count')}")
        except Exception as exc2:  # noqa: BLE001
            say(f"core events?dates=2025 failed: {type(exc2).__name__}: {exc2}")
    try:
        past = get(f"{base or SITE[0]}/scoreboard?dates=20251018")
        evp = ((past or {}).get("events") or [{}])[0]
        cp = ((evp.get("competitions") or [{}])[0]) or {}
        say(f"a finished card ({evp.get('name')}): fight keys {sorted(cp)[:40]}; status "
            f"{json.dumps(_shape(cp.get('status'), maxd=3), default=str)[:500]}")
        ath = (((cp.get("competitors") or [{}])[0]).get("athlete") or {})
        if ath.get("id"):
            st = get(f"https://sports.core.api.espn.com/v2/sports/mma/athletes/{ath['id']}"
                     f"/statistics")
            say(f"fighter statistics ({ath.get('displayName')}): "
                f"{json.dumps(_shape(st, maxd=4), default=str)[:1500]}")
    except Exception as exc:  # noqa: BLE001
        say(f"finished card / fighter stats failed: {type(exc).__name__}: {exc}")
    try:
        import requests
        r = requests.get("http://ufcstats.com/statistics/events/completed?page=all", timeout=20,
                         headers={"User-Agent": "Mozilla/5.0"})
        say(f"ufcstats.com completed events: HTTP {r.status_code}, {len(r.text)} bytes, "
            f"{r.text.count('event-details/')} event links")
    except Exception as exc:  # noqa: BLE001
        say(f"ufcstats.com failed: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
