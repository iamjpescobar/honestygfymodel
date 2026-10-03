"""
Grade the game models' logged picks against real finals.

Runs in the nightly (before any fetch, beside the calibration grader)
and writes the results back into data/model_picks/{mlb,nhl,nfl}.json,
which the workflow commits. engines/model_picks.py has the rules; this
script only fetches finals and applies grade_pick.

Finals come from the same sources the models are built from: statsapi
for MLB, ESPN for NHL and NFL — keyed by the game id the pick was logged
under, never by team name.

A pick whose game is not final three days after its date is graded
"void" (postponed, suspended, cancelled) and counts nowhere — MISSING IS
NOT ZERO, and a postponement is not a loss.
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef      # noqa: E402
from engines import model_picks as mpk   # noqa: E402

EASTERN = ZoneInfo("America/New_York")
VOID_AFTER_DAYS = 3
MLB_SCHEDULE = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={d}"


def mlb_finals(day, _get=None):
    """{game_pk(str): (home, away, final?)}"""
    get = _get or (lambda u: requests.get(u, timeout=30).json())
    out = {}
    data = get(MLB_SCHEDULE.format(d=day))
    for d in (data or {}).get("dates") or []:
        for g in d.get("games") or []:
            t = g.get("teams") or {}
            hs, as_ = (t.get("home") or {}).get("score"), (t.get("away") or {}).get("score")
            final = (g.get("status") or {}).get("abstractGameState") == "Final"
            out[str(g.get("gamePk"))] = (hs, as_, final and hs is not None and as_ is not None)
    return out


def espn_finals(league, day, _fetch=None):
    fetch = _fetch or (lambda lg, d: ef.fetch_scoreboard(lg, d, require_events=False)[0])
    out = {}
    sb = fetch(league, day.replace("-", ""))
    for ev in (sb or {}).get("events") or []:
        comp, away, home = ef.event_sides(ev)
        if comp is None:
            continue
        status, _done, _detail = ef.status_of(ev)
        hs, as_ = ef.num(home.get("score")), ef.num(away.get("score"))
        out[str(ev.get("id"))] = (None if hs is None else int(hs),
                                  None if as_ is None else int(as_),
                                  status == "final" and hs is not None and as_ is not None)
    return out


def grade(sport, finals_for_day, today=None, root=None):
    """Grade every ungraded pick dated before today. Returns (graded, voided)."""
    today = today or datetime.now(EASTERN).date()
    rec = mpk.load(sport, root)
    pending = [p for p in rec["picks"] if not p.get("result")
               and date.fromisoformat(p["date"]) < today]
    if not pending:
        return 0, 0
    cache, graded, voided = {}, 0, 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in pending:
        d = p["date"]
        if d not in cache:
            try:
                cache[d] = finals_for_day(d)
            except Exception as exc:          # noqa: BLE001 — retried next night
                print(f"  {sport} finals {d} unavailable ({exc}) — left pending")
                cache[d] = None
        fin = (cache[d] or {}).get(str(p["game_id"]))
        if fin and fin[2]:
            res, units = mpk.grade_pick(p, fin[0], fin[1])
            if res:
                p.update(result=res, units=units, final=f"{fin[1]}-{fin[0]}", graded_at=now)
                graded += 1
        elif cache[d] is not None and (today - date.fromisoformat(d)).days >= VOID_AFTER_DAYS:
            p.update(result="void", units=0.0, graded_at=now)
            voided += 1
    if graded or voided:
        mpk.save(sport, rec, root)
    return graded, voided


def main():
    sources = {
        "mlb": mlb_finals,
        "nhl": lambda d: espn_finals("nhl", d),
        "nfl": lambda d: espn_finals("nfl", d),
    }
    for sport, fn in sources.items():
        g, v = grade(sport, fn)
        s = mpk.summary(mpk.load(sport)["picks"])["all"]
        print(f"model picks {sport}: graded {g}, voided {v} this run | record "
              f"{s['w']}-{s['l']}-{s['p']} over {s['n']}, units {s['units']:+}, ROI {s['roi']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
