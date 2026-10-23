"""
Book prop lines snapshot (10-23) — every nightly run saves the
sportsbook's player-prop lines and prices (engines/book_props, ESPN's
free core feed, DraftKings) for every game in the next day and a half
(NFL: the coming week), to data/props/{league}/{date}.json in the repo,
committed by its own workflow step: a record that only exists if it is
saved the day it is posted.

Each run MERGES into the day's file: the first price seen is kept next
to the latest one (the 6 PM ET run is the closest to puck drop / tip).

What it is for: (1) the boards open on the book's line and price, (2)
every disagreement between the site's chance and the book's is graded
after the games — whether the site beats the book, market by market.
Neither is built yet; this is the record they need.

Prints [verify] lines: events, items, which of a pair is the over
(side_check, measured against the milestones), per-type counts.
Never fails the nightly: one league down costs that league's file.
"""
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import book_props as bp  # noqa: E402

OUT = ROOT / "data" / "props"
LEAGUES = {"nhl": 2, "nba": 2, "mlb": 2, "nfl": 7}     # days ahead to look


def upcoming(league, today, days, fetch_scoreboard):
    """{event_id: (date iso, label)} — games not yet started."""
    out = {}
    for k in range(days):
        d = today + timedelta(days=k)
        try:
            sb, _src = fetch_scoreboard(league, d.strftime("%Y%m%d"))
        except Exception as exc:  # noqa: BLE001
            print(f"  {league}: scoreboard {d} failed: {exc}")
            continue
        for ev in sb.get("events") or []:
            st = (((ev.get("status") or {}).get("type") or {}).get("state")) or ""
            if st == "pre":
                out[str(ev.get("id"))] = (d.isoformat(), ev.get("shortName") or ev.get("name"))
    return out


def run_league(league, today, get, fetch_scoreboard, sport_lg, out_dir=OUT, now=None,
               sleep=0.1):
    sport, lg = sport_lg
    evs = upcoming(league, today, LEAGUES.get(league, 2), fetch_scoreboard)
    by_date, types, n_items = {}, Counter(), 0
    all_rows = []
    for eid, (d, _lab) in evs.items():
        try:
            items = bp.fetch_event(get, sport, lg, eid)
        except Exception as exc:  # noqa: BLE001
            print(f"  {league}: props for {eid} failed: {type(exc).__name__}: {exc}")
            continue
        rows = bp.parse(items)
        n_items += len(rows)
        types.update(r["type"] for r in rows)
        all_rows += rows
        by_date.setdefault(d, {})[eid] = rows
        time.sleep(sleep)
    sc = bp.side_check(all_rows)
    now = now or datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    written = []
    for d, ev_rows in by_date.items():
        path = Path(out_dir) / league / f"{d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(path.read_text()) if path.exists() else {}
        path.write_text(json.dumps(bp.merge_snapshot(old, ev_rows, now), separators=(",", ":")))
        written.append(path.name)
    n_saved = sum(len(v) for v in by_date.values())
    print(f"  [verify] BOOK PROPS {league}: {len(evs)} upcoming events, {n_saved} with props "
          f"saved; {n_items} prop items -> {written}")
    print(f"  [verify] BOOK PROPS {league}: which of a pair is the over, measured against the "
          f"milestones: {sc}")
    print(f"  [verify] BOOK PROPS {league}: types {dict(types.most_common(14))}")
    return {"events": len(evs), "items": n_items, "side": sc, "files": written}


def main():
    from engines import espn_feed as ef
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date()
    for lg in LEAGUES:
        try:
            run_league(lg, today, ef.get_json, ef.fetch_scoreboard, ef.LEAGUES[lg])
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::book props {lg} failed: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
