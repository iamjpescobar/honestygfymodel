"""
Last NHL season's periods, once (10-22) — what the period lines (1st
period goals, the period winner) and the per-period player props (1st
period point / shot / goal) are fitted and TESTED on.

For every 2025-26 regular-season final (ESPN scoreboards, the same window
and season-type rule as nhl_prior_season.py), the game summary ->
engines/nhl_periods.parse: each period's goals and shots per team, every
skater's goals, assists and shots on goal by period, the first goal.
Run by the manual workflow `nhl-periods-prior.yml`; the file is committed
(last season does not change).

Writes data/nhl/prior_periods.json: {"season", "games": {event_id:
{"date", "home", "away", ...parse()}}}. Refuses to write when fewer than
80% of games have period lines, or fewer than 90% of skaters' periods add
up to their box-score goals — a shape change at ESPN must not become a
quiet hole in a model. Prints the play types it saw so a new shape can
be read from the log.
"""
import json
import sys
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef  # noqa: E402
from engines import nhl_periods as npd  # noqa: E402
import nhl_precompute as nhp  # noqa: E402
import nhl_prior_season as nps  # noqa: E402

OUT = ROOT / "data" / "nhl" / "prior_periods.json"
MIN_SHARE = 0.80
MIN_GOALS_OK = 0.90


def game_record(summ, eid, d, home_id, away_id, home_name, away_name):
    """(record, check, play types) for one final."""
    sk, gk = {}, {}
    nhp.parse_summary(summ, eid, d, sk, gk)
    rec = npd.parse(summ, goalie_ids=gk.keys())
    box = {pid: r["games"].get(str(eid)) or {} for pid, r in sk.items()}
    chk = npd.check(rec, box)
    types = Counter(((p.get("type") or {}).get("text") or "?")
                    for p in (summ or {}).get("plays") or [] if isinstance(p, dict))
    return dict(rec, date=d, home=home_id, away=away_id), chk, types


def collect(sb_fn, summary_fn, start=nps.START, end=nps.END, sleep=0.06):
    games, checks, types = {}, Counter(), Counter()
    d = start
    while d <= end:
        try:
            sb = sb_fn(d)
        except Exception as exc:  # noqa: BLE001
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in (sb or {}).get("events") or []:
            stype = (ev.get("season") or {}).get("type") if isinstance(ev.get("season"),
                                                                       dict) else None
            if stype is None:
                stype = 2 if nps.REGULAR[0] <= d <= nps.REGULAR[1] else None
            if stype != 2:
                continue
            g = nhp.slate_game(ev, d)
            if not g or g["status"] != "final":
                continue
            try:
                summ = summary_fn(g["event_id"])
            except Exception as exc:  # noqa: BLE001
                print(f"  summary {g['event_id']} failed: {exc}")
                continue
            rec, chk, ty = game_record(summ, g["event_id"], d.isoformat(), g["home_id"],
                                       g["away_id"], g["home"], g["away"])
            games[str(g["event_id"])] = rec
            checks.update(chk)
            types.update(ty)
            if len(games) % 200 == 0:
                print(f"  ... {len(games)} games")
            time.sleep(sleep)
        d += timedelta(days=1)
    return games, checks, types


def main():
    games, chk, types = collect(lambda d: ef.fetch_scoreboard("nhl", d.strftime("%Y%m%d"))[0],
                                lambda eid: ef.fetch_summary("nhl", eid))
    n = len(games) or 1
    has_lines = sum(1 for g in games.values() if len(next(iter(g["lines"].values()), [])) >= 3
                    and len(g["lines"]) == 2)
    has_sog = sum(1 for g in games.values() if len(g["sog"]) == 2)
    has_fg = sum(1 for g in games.values() if g.get("first_goal"))
    P = max(1, chk["players"])
    print(f"  [verify] NHL periods: {len(games)} finals read; period lines {has_lines}, team "
          f"shots by period {has_sog}, a first goal {has_fg}")
    print(f"  [verify] skater periods that add up to his box score: goals "
          f"{100 * chk['goals_ok'] / P:.1f}%, assists {100 * chk['assists_ok'] / P:.1f}%, shots "
          f"{100 * chk['sog_ok'] / P:.1f}% of {chk['players']} skater-games")
    print(f"  [verify] play types seen: {dict(types.most_common(14))}")
    sog_pg = [sum(sum(v) for v in g["sog"].values()) for g in games.values() if g["sog"]]
    if sog_pg:
        print(f"  [verify] shots on goal per game from the plays: "
              f"{sum(sog_pg) / len(sog_pg):.1f} (box scores run ~58)")
    fg = Counter(g["first_goal"]["pid"] for g in games.values() if g.get("first_goal"))
    print(f"  [verify] most first goals (ids): {fg.most_common(5)}")
    if has_lines < MIN_SHARE * n or chk["goals_ok"] < MIN_GOALS_OK * P:
        print(f"Refusing to write: fewer than {int(100 * MIN_SHARE)}% of games with period lines "
              f"or fewer than {int(100 * MIN_GOALS_OK)}% of skaters adding up — ESPN's shape may "
              f"have changed. Send the log.")
        return 1
    OUT.write_text(json.dumps({"season": nps.SEASON, "games": games}, separators=(",", ":")))
    print(f"  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
