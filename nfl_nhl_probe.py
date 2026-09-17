"""What ESPN's NFL and NHL feeds actually return, from wherever this runs.

espn_feed.py assumes the WNBA measurement carries over: same hosts, a
different sport segment. Some box-score column names are also assumed
(matched two ways — machine keys, then display labels). This prints
the truth so nobody has to guess:

  * each scoreboard host: HTTP status, bytes, event count, and the shape
    the header gives (odds object vs list, broadcasts, record type);
  * one FINAL game's summary: team stat names, every player group's
    name / keys / labels, the period field, gameInfo keys, injuries;
  * a team roster: how many players the walker finds;
  * then runs the real parsers on that game and prints what they got.

Touches nothing — no files, no commit, no deploy.

    python nfl_nhl_probe.py [NFL_DATE] [NHL_DATE]      (YYYY-MM-DD)
"""
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef  # noqa: E402


def _shape(v):
    if isinstance(v, dict):
        return "dict{" + ",".join(sorted(v)[:12]) + "}"
    if isinstance(v, list):
        return f"list[{len(v)}]" + (f" of {type(v[0]).__name__}" if v else "")
    return type(v).__name__


def probe(league, day):
    print(f"\n{'=' * 70}\n{league.upper()} on {day}\n{'=' * 70}")
    ymd = day.replace("-", "")
    for name, build, unwrap in ef.scoreboard_sources(league):
        url = build(ymd)
        try:
            r = requests.get(url, headers=ef.UA, timeout=25)
            print(f"\n[{name}] HTTP {r.status_code}, {len(r.content):,} bytes, "
                  f"{r.headers.get('content-type')}")
            if r.status_code != 200 or not r.content:
                continue
            data = ef._normalize_header_events(unwrap(r.json()))
        except Exception as exc:
            print(f"[{name}] ERROR {type(exc).__name__}: {exc}")
            continue
        evs = data.get("events") or []
        print(f"  events: {len(evs)}")
        if evs:
            comp, away, home = ef.event_sides(evs[0])
            print(f"  first event keys: {sorted(evs[0])}")
            print(f"  competition odds: {_shape((comp or {}).get('odds'))}  "
                  f"broadcasts: {_shape((comp or {}).get('broadcasts'))}")
            print(f"  away competitor keys: {sorted(away or {})}")
            print(f"  away records: {_shape((away or {}).get('records'))}")
            print(f"  status: {ef.status_of(evs[0])}")

    data, src = ef.fetch_scoreboard(league, ymd)
    finals = [e for e in data.get("events") or [] if ef.status_of(e)[0] == "final"]
    print(f"\nchain answered via {src}; {len(finals)} finals")
    if not finals:
        print("  no final on this date — pick a date with completed games")
        return
    eid = str(finals[0].get("id"))
    s = ef.fetch_summary(league, eid)
    box = s.get("boxscore") or {}
    print(f"\nsummary {eid}: top-level keys {sorted(s)}")
    for t in box.get("teams") or []:
        print(f"  team stat names ({(t.get('team') or {}).get('abbreviation')}): "
              f"{[x.get('name') for x in t.get('statistics') or []]}")
    for b in (box.get("players") or [])[:1]:
        for g in b.get("statistics") or []:
            a0 = (g.get("athletes") or [{}])[0]
            print(f"  group name={g.get('name')!r}\n    keys={g.get('keys')}\n"
                  f"    labels={g.get('labels')}\n    first athlete keys={sorted(a0)} "
                  f"stats={a0.get('stats')}")
    comp = ((s.get("header") or {}).get("competitions") or [{}])[0]
    print(f"  header status: {json.dumps(comp.get('status'))[:300]}")
    print(f"  gameInfo keys: {sorted(s.get('gameInfo') or {})}")
    print(f"  injuries blocks: {len(s.get('injuries') or [])}; pickcenter: {_shape(s.get('pickcenter'))}")

    away_id = str((((ef.event_sides(finals[0])[1]) or {}).get("team") or {}).get("id") or "")
    if league == "nfl":
        import nfl_precompute as pc
        roster = pc.fetch_roster(away_id)
        logs = {}
        lines, n = pc.parse_summary_final(s, eid, day, 1, logs)
        print(f"\nPARSED: team lines {lines}\n        {n} player lines, e.g. "
              f"{next(iter(logs.values()), None)}")
    else:
        import nhl_precompute as pc
        roster = pc.fetch_roster(away_id)
        sk, gk = {}, {}
        tb, ns, ng = pc.parse_summary(s, eid, day, sk, gk)
        print(f"\nPARSED: team box {tb}\n        {ns} skater / {ng} goalie lines; "
              f"OT? {pc.went_to_extra(s)}; goalie e.g. {next(iter(gk.values()), None)}")
    print(f"ROSTER {away_id}: walker found {len(roster)} players")


if __name__ == "__main__":
    nfl_day = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "2026-09-13"
    nhl_day = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "2026-09-20"
    for lg, d in (("nfl", nfl_day), ("nhl", nhl_day)):
        try:
            probe(lg, d)
        except Exception as exc:
            print(f"{lg.upper()} probe failed: {type(exc).__name__}: {exc}")
