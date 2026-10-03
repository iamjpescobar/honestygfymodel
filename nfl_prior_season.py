"""
The 2025 NFL regular season's finals — what the NFL game model fits on
while 2026 has only a few weeks of its own.

Scores only (no box scores): the game model needs who played whom, where
and the final. ~125 scoreboard calls, so unlike NHL this is fetched by
nfl_precompute itself the first night data/nfl/prior_season.json is
missing, and the nightly commits it. After that it is read, never
refetched — 2025 does not change.

ESPN's NFL scoreboard answers a date with its WHOLE week (the 09-27
lesson), so events are keyed by id; a week seen seven times is one week.
The site.web.api header shape drops the season block (the NHL lesson,
10-03), so the regular season is decided by the 2025 date window.
"""
import json
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIOR_PATH = ROOT / "data" / "nfl" / "prior_season.json"
SEASON = 2025
# Week 1 kickoff to the Week 18 finale. Playoffs (Jan 10 on) excluded:
# a different population, and the model is a regular-season model.
REGULAR = (date(2025, 9, 4), date(2026, 1, 4))
# A complete 2025 regular season is 272 games. Anything well short of it
# is an outage mid-fetch, and a partial season written once would be
# read forever — so it is refused, not saved.
MIN_FINALS = 250


def collect(sb_fn, slate_game, sleep=0.05):
    finals = {}
    d = REGULAR[0]
    while d <= REGULAR[1]:
        try:
            sb = sb_fn(d)
        except Exception as exc:          # noqa: BLE001 — logged, day skipped
            print(f"  prior scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in (sb or {}).get("events") or []:
            g = slate_game(ev)
            if not g or g.get("status") != "final" or g.get("away_score") is None:
                continue
            kick = (g.get("kick_date_et") or "")[:10]
            if not kick or not (REGULAR[0].isoformat() <= kick <= REGULAR[1].isoformat()):
                continue
            finals[g["event_id"]] = {
                "date": kick, "event_id": g["event_id"],
                "home": g["home"], "away": g["away"],
                "home_id": g.get("home_id"), "away_id": g.get("away_id"),
                "home_score": g["home_score"], "away_score": g["away_score"]}
        time.sleep(sleep)
        d += timedelta(days=1)
    return sorted(finals.values(), key=lambda f: f["date"])


def load_or_fetch(sb_fn, slate_game, path=None):
    """The prior finals list, fetching and saving it once if missing."""
    path = Path(path or PRIOR_PATH)
    if path.exists():
        try:
            return json.loads(path.read_text()).get("finals") or []
        except Exception as exc:          # noqa: BLE001
            print(f"  prior season file unreadable ({exc}) — refetching")
    finals = collect(sb_fn, slate_game)
    print(f"  [verify] NFL {SEASON} prior season: {len(finals)} regular-season finals")
    if len(finals) < MIN_FINALS:
        print(f"::warning::NFL prior season short ({len(finals)} < {MIN_FINALS}) — "
              f"not saved; the model fits on {SEASON + 1} alone tonight.")
        return finals if finals else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"season": SEASON, "finals": finals}, separators=(",", ":")))
    return finals
