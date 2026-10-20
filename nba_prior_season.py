"""
Last NBA season, once (10-20) — what the NBA model is fitted and TESTED
on while 2026-27 is days old.

Every 2025-26 regular-season final from ESPN's public API: the score, and
every player's line (engines/nba_box). Run by the manual workflow
`nba-prior-season.yml`; the file is committed (last season does not
change). nba_precompute reads it.

Writes data/nba/prior_season.json:
  {"season", "finals": [{date, event_id, home, away, hs, as}],
   "players": {pid: {"name", "pos", "team", "games": [tuples]}},
   "teams": {id: {"abbr", "name", "logo"}}}
Refuses to write a file with no box scores. Prints [verify] lines.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from engines import espn_feed as ef  # noqa: E402
from engines import nba_box as nb  # noqa: E402

LEAGUE = "nba"
SEASON = "2025-26"
REGULAR = (date(2025, 10, 21), date(2026, 4, 12))
OUT = ROOT / "data" / "nba" / "prior_season.json"


def season_type(ev):
    s = ev.get("season")
    return s.get("type") if isinstance(s, dict) else None


def collect(sb_fn, summary_fn, start=REGULAR[0], end=REGULAR[1], sleep=0.06):
    finals, players, teams = [], {}, {}
    seen = parsed = 0
    d = start
    while d <= end:
        try:
            sb = sb_fn(d)
        except Exception as exc:  # noqa: BLE001 — logged, day skipped
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in (sb or {}).get("events") or []:
            st = season_type(ev)
            if st not in (None, 2):            # preseason / play-in / playoffs
                continue
            status, _done, _det = ef.status_of(ev)
            if status != "final":
                continue
            comp, away, home = ef.event_sides(ev)
            if comp is None:
                continue
            seen += 1
            try:
                summ = summary_fn(str(ev.get("id")))
            except Exception as exc:  # noqa: BLE001
                print(f"  summary {ev.get('id')} failed: {exc}")
                continue
            lines = nb.parse(summ)
            for t in nb.teams(summ):
                if t["id"]:
                    teams[t["id"]] = {k: t[k] for k in ("abbr", "name", "logo")}
            finals.append({"date": d.isoformat(), "event_id": str(ev.get("id")),
                           "home": str((home.get("team") or {}).get("id") or ""),
                           "away": str((away.get("team") or {}).get("id") or ""),
                           "hs": ef.num(home.get("score")), "as": ef.num(away.get("score"))})
            if not lines:
                continue
            parsed += 1
            for pid, ln in lines.items():
                p = players.setdefault(pid, {"name": ln["name"], "pos": ln["pos"], "games": []})
                p["team"] = ln["team_id"]
                p["games"].append(nb.as_tuple(d.isoformat(), ln))
            time.sleep(sleep)
        d += timedelta(days=1)
    return finals, players, teams, seen, parsed


def main():
    finals, players, teams, seen, parsed = collect(
        lambda d: ef.fetch_scoreboard(LEAGUE, d.strftime("%Y%m%d"))[0],
        lambda eid: ef.fetch_summary(LEAGUE, eid))
    n_games = sum(len(p["games"]) for p in players.values())
    print(f"  [verify] NBA {SEASON}: {seen} regular-season finals seen, {parsed} box scores "
          f"parsed, {len(players)} players, {n_games:,} player-games, {len(teams)} teams")
    if players:
        top = max(players.values(), key=lambda p: sum(g[4] or 0 for g in p["games"]))
        tp = sum(g[4] or 0 for g in top["games"])
        print(f"  [verify] scoring leader: {top['name']} — {tp:.0f} pts in {len(top['games'])} GP "
              f"({tp / max(1, len(top['games'])):.1f} a game)")
        miss = sum(1 for p in players.values() for g in p["games"] if g[7] is None)
        print(f"  [verify] player-games with no 3PM read: {miss}")
    if not parsed:
        print("Refusing to write: no box scores parsed.")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"season": SEASON, "finals": finals, "players": players,
                               "teams": teams}, separators=(",", ":")))
    print(f"  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
