"""Who actually starts — measured from MLB's own posted lineups.

THE PROBLEM THIS SOLVES

MLB posts a real lineup 1-3 hours before first pitch. Slate breakdowns
get recorded in the MORNING, when no lineup exists for any game on the
board. Every morning read is therefore a projection, and the honest
question is not "what is the lineup" but "which of these bats is
actually going to be in it".

Measured on the HR research log for 2026-08-12..16, roughly 80% of a
team's bats repeat from one game to the next. So last night's nine gets
about seven right and two wrong, every night — and the two are not
random, they are the catcher, the platoon corner and the DH rotation.

THE UNCERTAINTY IS NOT EVENLY SPREAD, and that is the whole opening.
Over that same window, 40% of bats started every single game their team
played and another 28% started at least two thirds. A projection that
says "seven of these nine are locks and these two are coin flips" is
both more useful and more honest than nine rows that all look equally
certain.

WHAT THIS WRITES

data/mlb/lineup_lock.json — per team, per player: starts, team games in
the window, and the same split by the hand of the opposing STARTER,
because the flux bucket is almost entirely platoon bats and the
probable pitcher IS knowable in the morning.

WHY A NIGHTLY JOB AND NOT A PAGE

A window of team games is 14 boxscore requests per team, 420 for a
league. That cannot happen during a render — see the Boards column that
took the Game Card down on 2026-08-16 by building what it should have
read. This writes the file; app/engines/lineup_lock.py only reads it.

NOTHING HERE IS INFERRED. Every start counted is a real posted lineup
from MLB's own boxscore endpoint. A player with no games in the window
gets no rate rather than a zero — a bat that was on the IL all week has
not been benched, and MISSING IS NOT ZERO.
"""
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")
API = "https://statsapi.mlb.com/api/v1"
OUT_PATH = Path(__file__).resolve().parent / "data" / "mlb" / "lineup_lock.json"

# The window is the number of a team's most recent COMPLETED games this
# reads back over.
#
# 7 IS MEASURED. lineup_lock_probe.py ran on 2026-08-19 over 30 teams and
# 9,417 bat-games and compared 7 / 14 / 21 against the naive baseline the
# rate has to beat ("he started last game, so he starts tonight",
# which agreed 81.7% of the time):
#
#   window   best accuracy   vs naive   top-to-bottom spread
#      7         82.2%          +0.5            80.0 pts
#     14         79.3%          -2.4            76.1 pts
#     21         77.4%          -4.3            70.6 pts
#
# SEVEN IS THE ONLY WINDOW THAT BEATS THE BASELINE AT ALL, and it also
# has the widest calibration spread, so the probe's own selection rule
# ("widest spread that still beats the naive baseline") lands on it
# unambiguously.
#
# 14 was the previous value and was a GUESS. It is 2.4 points WORSE than
# simply copying last night's lineup — so for as long as it was set, this
# whole build was a slower way of being wrong. That is the standing-rule-1
# lesson in one number, and it is why nothing here gets set by eye.
#
# The split by opposing hand did NOT earn its complexity: it narrowed the
# spread at every window (80.0 -> 74.7 at 7, 76.1 -> 73.7 at 14,
# 70.6 -> 70.2 at 21). It is still computed and published, because the
# per-hand counts are real and a reader can use them, but nothing should
# treat it as the better signal until a probe says otherwise.
#
# RE-MEASURE PERIODICALLY. Distributions drift, which is what standing
# rule 1 says about every number on this site. Re-run the probe every few
# weeks and reset this from its output, not from this comment.
WINDOW_GAMES = 7
LOOKBACK_DAYS = 30          # calendar reach needed to find WINDOW_GAMES

# Below this many team games the rates are noise, so they are published
# with the count and the reader decides. Nothing is suppressed — a rate
# out of 3 games is a real rate out of 3 games, and the count says so.
MIN_GAMES_TO_REPORT = 3


def _get(url, params=None, tries=3):
    """One GET with retries. Returns None rather than raising: a single
    flaky boxscore should cost one game, not the whole build."""
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            if attempt == tries - 1:
                print(f"  [warn] {url} failed: {exc}", flush=True)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def teams():
    data = _get(f"{API}/teams", {"sportId": 1})
    if not data:
        return []
    return [(t["id"], t["name"]) for t in data.get("teams", [])]


def completed_games(team_id):
    """This team's completed games, newest first, within the lookback."""
    today = datetime.now(EASTERN).date()
    start = today - timedelta(days=LOOKBACK_DAYS)
    data = _get(f"{API}/schedule", {
        "sportId": 1, "teamId": team_id,
        "startDate": start.isoformat(), "endDate": today.isoformat()})
    if not data:
        return []
    games = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            away = g.get("teams", {}).get("away", {}).get("team", {}).get("id")
            games.append({
                "game_pk": g.get("gamePk"),
                "date": (g.get("gameDate") or "")[:10],
                "side": "away" if away == team_id else "home",
            })
    games.sort(key=lambda x: x["date"], reverse=True)
    return games[:WINDOW_GAMES]


def _hand_of(pid):
    """Throwing hand of a pitcher id, from MLB's own people endpoint.

    Returns None when unknown. None is carried through as its own
    bucket rather than being folded into R: guessing the common case
    would put a lefty-mashing platoon bat's starts under the wrong
    hand, which is worse than an honest gap."""
    data = _get(f"{API}/people/{pid}")
    if not data:
        return None
    people = data.get("people") or []
    if not people:
        return None
    code = (people[0].get("pitchHand") or {}).get("code")
    return code if code in ("L", "R") else None


def starters_and_opposing_hand(game_pk, side, hand_cache):
    """(list of batter ids who STARTED, hand of the opposing starter).

    A starter is a player MLB gave a battingOrder to — the same
    definition get_confirmed_lineup uses, so this counts exactly what
    the app calls a confirmed lineup and not a definition of its own."""
    box = _get(f"{API}/game/{game_pk}/boxscore")
    if not box:
        return [], None
    team_box = (box.get("teams") or {}).get(side) or {}
    ids = []
    for p in (team_box.get("players") or {}).values():
        if not p.get("battingOrder"):
            continue
        pos = (p.get("position") or {}).get("abbreviation")
        if pos == "P":
            continue          # the pitcher in an NL-style order is not a bat
        pid = (p.get("person") or {}).get("id")
        if pid:
            ids.append(str(pid))

    other = "home" if side == "away" else "away"
    opp_pitchers = ((box.get("teams") or {}).get(other) or {}).get("pitchers") or []
    hand = None
    if opp_pitchers:
        sp = opp_pitchers[0]          # MLB lists pitchers in appearance order
        if sp not in hand_cache:
            hand_cache[sp] = _hand_of(sp)
        hand = hand_cache[sp]
    return ids, hand


def build():
    all_teams = teams()
    if not all_teams:
        print("Could not reach the MLB schedule API — writing nothing.")
        return 1

    out = {
        "window_games": WINDOW_GAMES,
        # True since 2026-08-19: WINDOW_GAMES is set from
        # lineup_lock_probe.py output, not by eye. See the block
        # above WINDOW_GAMES for the table it was set from.
        "window_is_measured": True,
        # WHAT THE MEASUREMENT ACTUALLY SAYS, carried in the file so
        # a reader of the data does not have to find this script.
        # The rate is WELL CALIBRATED (a bat in the 90-100% bucket
        # started 92.9% of the time; one in the 0-33% bucket, 12.9%)
        # but it is only +0.5 points better than copying last night's
        # lineup as a BINARY predictor. So it earns its place as a
        # confidence tier, not as a replacement for the posted nine.
        "measured_on": "2026-08-19",
        "naive_baseline_pct": 81.7,
        "window_accuracy_pct": 82.2,
        "generated_at_et": datetime.now(EASTERN).isoformat(timespec="seconds"),
        "slate_date_et": datetime.now(EASTERN).date().isoformat(),
        "teams": {},
    }
    hand_cache = {}
    total_players = 0

    for team_id, team_name in all_teams:
        games = completed_games(team_id)
        if not games:
            print(f"{team_name}: no completed games in {LOOKBACK_DAYS}d — skipped.")
            continue

        starts = defaultdict(int)
        by_hand = defaultdict(lambda: defaultdict(int))
        hand_games = defaultdict(int)
        counted = 0

        for g in games:
            ids, hand = starters_and_opposing_hand(g["game_pk"], g["side"], hand_cache)
            if not ids:
                continue          # a boxscore that failed is a game we did not see
            counted += 1
            if hand:
                hand_games[hand] += 1
            for pid in ids:
                starts[pid] += 1
                if hand:
                    by_hand[pid][hand] += 1

        if counted < MIN_GAMES_TO_REPORT:
            print(f"{team_name}: only {counted} readable game(s) — skipped.")
            continue

        players = {}
        for pid, n in starts.items():
            players[pid] = {
                "starts": n,
                "games": counted,
                "rate": round(n / counted, 3),
                # Per hand: starts out of the games the team faced that
                # hand. Absent when the team never faced it in the
                # window — an unmeasured split, not a zero one.
                "vs": {h: {"starts": by_hand[pid].get(h, 0),
                           "games": hand_games[h],
                           "rate": round(by_hand[pid].get(h, 0) / hand_games[h], 3)}
                       for h in ("L", "R") if hand_games.get(h)},
            }
        out["teams"][team_name] = {"games": counted, "players": players}
        total_players += len(players)
        print(f"{team_name}: {counted} games, {len(players)} bats "
              f"(vsL {hand_games.get('L', 0)}, vsR {hand_games.get('R', 0)})",
              flush=True)

    if not out["teams"]:
        print("No team produced a readable window — writing nothing rather "
              "than an empty file that would read as 'nobody is a lock'.")
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUT_PATH} — {len(out['teams'])} teams, "
          f"{total_players} bats, window {WINDOW_GAMES} games.")

    # SELF-VERIFY, in the log, every run. A file that builds is not a
    # file that is right, and the shape of a wrong one here is a league
    # where everybody is a 100% lock (a boxscore parse that fell back to
    # the roster) or nobody is (a battingOrder key that moved).
    rates = [p["rate"] for t in out["teams"].values() for p in t["players"].values()]
    locks = sum(1 for r in rates if r == 1.0)
    flux = sum(1 for r in rates if 0.34 <= r < 0.66)
    print(f"[verify-lock] {len(rates)} bats: {locks} at 100% "
          f"({locks / len(rates) * 100:.0f}%), {flux} between 34-65% "
          f"({flux / len(rates) * 100:.0f}%).")
    if locks == len(rates) or locks == 0:
        print("[verify-lock] *** EVERY bat has the same standing. That is not "
              "what a real league looks like — suspect the boxscore parse "
              "(battingOrder) rather than the teams.")
    return 0


if __name__ == "__main__":
    sys.exit(build())
