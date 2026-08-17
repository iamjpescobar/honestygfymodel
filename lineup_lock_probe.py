"""Does a bat's recent start rate actually predict tonight's start?

WHY THIS EXISTS BEFORE THE FEATURE IS TRUSTED

lineup_lock_precompute.py publishes a number, and the Game Card is
about to put it next to nine hitters at six in the morning. Standing
rule 1: measure before you set any number. Everything on this site
chosen by eye turned out wrong, and every one of those was caught by
writing a probe first.

The claim under test is NOT "80% of bats repeat" — that is a
description of the past. It is the forecast: **given that a bat started
N of his team's last W games, how often does he start the next one?**
Those are different questions and only the second one justifies the
column.

WHAT IT PRINTS

  1. Calibration. For each rate bucket, the share who actually started
     the following game. A useful column has these lining up: bats at
     90-100% should start ~90-100% of the time. If every bucket comes
     back near the league average, the rate carries no information and
     the column should not ship.

  2. Window comparison, 7 / 14 / 21 games. WINDOW_GAMES in the
     precompute is currently a guess, and this is what sets it.

  3. Whether the split by opposing hand beats the flat rate. If it does
     not, the split is complexity with no payoff and should come out.

  4. The naive baseline: "he started last game, so he starts tonight."
     THE RATE HAS TO BEAT THIS or the whole build is a slower way of
     looking at yesterday's lineup. This is the same trap as the HR
     Edge baseline — any plausible-looking method clears a bar nobody
     checked.

HOW TO RUN IT: workflow_dispatch on .github/workflows/lineup-lock-probe.yml.
No nightly step — this is a measurement, not a feed, and it costs
several hundred API calls.
"""
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")
API = "https://statsapi.mlb.com/api/v1"

BACKFILL_DAYS = 45          # enough for a 21-game window plus games to test on
WINDOWS = (7, 14, 21)
BUCKETS = [(0.0, 0.34, "  0-33%"), (0.34, 0.66, " 34-65%"),
           (0.66, 0.90, " 66-89%"), (0.90, 1.01, "90-100%")]


def _get(url, params=None, tries=3):
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            if attempt == tries - 1:
                print(f"  [warn] {url}: {exc}", flush=True)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def teams():
    d = _get(f"{API}/teams", {"sportId": 1})
    return [(t["id"], t["name"]) for t in (d or {}).get("teams", [])]


def game_history(team_id):
    """Every completed game in the backfill, OLDEST FIRST."""
    today = datetime.now(EASTERN).date()
    d = _get(f"{API}/schedule", {
        "sportId": 1, "teamId": team_id,
        "startDate": (today - timedelta(days=BACKFILL_DAYS)).isoformat(),
        "endDate": today.isoformat()})
    games = []
    for day in (d or {}).get("dates", []):
        for g in day.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            away = g.get("teams", {}).get("away", {}).get("team", {}).get("id")
            games.append({"game_pk": g.get("gamePk"),
                          "date": (g.get("gameDate") or "")[:10],
                          "side": "away" if away == team_id else "home"})
    games.sort(key=lambda x: x["date"])
    return games


def starters(game_pk, side, hand_cache):
    box = _get(f"{API}/game/{game_pk}/boxscore")
    if not box:
        return None, None
    tb = (box.get("teams") or {}).get(side) or {}
    ids = set()
    for p in (tb.get("players") or {}).values():
        if not p.get("battingOrder"):
            continue
        if (p.get("position") or {}).get("abbreviation") == "P":
            continue
        pid = (p.get("person") or {}).get("id")
        if pid:
            ids.add(str(pid))
    other = "home" if side == "away" else "away"
    pitchers = ((box.get("teams") or {}).get(other) or {}).get("pitchers") or []
    hand = None
    if pitchers:
        sp = pitchers[0]
        if sp not in hand_cache:
            people = _get(f"{API}/people/{sp}")
            got = (people or {}).get("people") or [{}]
            code = (got[0].get("pitchHand") or {}).get("code")
            hand_cache[sp] = code if code in ("L", "R") else None
        hand = hand_cache[sp]
    return ids, hand


def rate_from(history, upto, pid, window, hand=None):
    """Start rate over the `window` games BEFORE index `upto`.

    Strictly before — including tonight's game in the history that
    predicts tonight is the classic leak, and it would report a
    perfect column."""
    prior = history[max(0, upto - window):upto]
    if hand:
        prior = [g for g in prior if g["hand"] == hand]
    if not prior:
        return None
    hits = sum(1 for g in prior if pid in g["starters"])
    return hits / len(prior)


def main():
    all_teams = teams()
    if not all_teams:
        print("MLB schedule API unreachable — nothing measured.")
        return 1

    hand_cache = {}
    # (window, hand_split) -> bucket -> [started, total]
    cal = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    naive = [0, 0]
    base = [0, 0]

    for team_id, team_name in all_teams:
        games = game_history(team_id)
        if len(games) < max(WINDOWS) + 3:
            print(f"{team_name}: {len(games)} games, too few — skipped.")
            continue
        for g in games:
            ids, hand = starters(g["game_pk"], g["side"], hand_cache)
            g["starters"] = ids or set()
            g["hand"] = hand

        roster = set().union(*[g["starters"] for g in games]) or set()
        # Test on every game that has a full max-window of history before it.
        for i in range(max(WINDOWS), len(games)):
            tonight = games[i]
            if not tonight["starters"]:
                continue
            for pid in roster:
                started = pid in tonight["starters"]
                base[0] += int(started); base[1] += 1

                # baseline: did he start the immediately previous game?
                if (pid in games[i - 1]["starters"]) == started:
                    naive[0] += 1
                naive[1] += 1

                for w in WINDOWS:
                    r = rate_from(games, i, pid, w)
                    if r is not None:
                        for lo, hi, label in BUCKETS:
                            if lo <= r < hi:
                                cal[(w, False)][label][0] += int(started)
                                cal[(w, False)][label][1] += 1
                                break
                    if tonight["hand"]:
                        rh = rate_from(games, i, pid, w, tonight["hand"])
                        if rh is not None:
                            for lo, hi, label in BUCKETS:
                                if lo <= rh < hi:
                                    cal[(w, True)][label][0] += int(started)
                                    cal[(w, True)][label][1] += 1
                                    break
        print(f"{team_name}: {len(games)} games measured.", flush=True)

    if not base[1]:
        print("Nothing measurable.")
        return 1

    league = base[0] / base[1]
    print(f"\n=== BASE RATE ===\n  any roster bat starts a given game: "
          f"{league * 100:.1f}%  ({base[0]}/{base[1]})")
    print(f"\n=== NAIVE BASELINE (started last game -> starts tonight) ===\n"
          f"  agrees {naive[0] / naive[1] * 100:.1f}% of the time  "
          f"({naive[0]}/{naive[1]})\n"
          f"  THE RATE COLUMN HAS TO BEAT THIS. If it does not, the honest "
          f"move is to keep showing last game's nine and drop the column.")

    for w in WINDOWS:
        for split in (False, True):
            rows = cal[(w, split)]
            if not any(v[1] for v in rows.values()):
                continue
            tag = f"window {w:2d} games" + (" · split by opposing hand" if split else "")
            print(f"\n=== CALIBRATION — {tag} ===")
            print("  prior rate     started tonight        n")
            for _lo, _hi, label in BUCKETS:
                hit, n = rows[label]
                if not n:
                    print(f"  {label}          (no bats)")
                    continue
                print(f"  {label}        {hit / n * 100:5.1f}%          {n:6d}")
            spread = [rows[l][0] / rows[l][1] for _a, _b, l in BUCKETS if rows[l][1]]
            if spread:
                print(f"  spread top-to-bottom: {(max(spread) - min(spread)) * 100:.1f} pts "
                      f"— flat means the rate carries no information.")

    print("\nSET WINDOW_GAMES in lineup_lock_precompute.py from the window "
          "with the widest spread that still beats the naive baseline, then "
          "flip window_is_measured to True so the app stops labelling the "
          "column provisional.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
