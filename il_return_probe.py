"""Does a bat coming off the IL actually start that day — and which ones?

WHY THIS EXISTS BEFORE THE FLOOR IS TRUSTED

app/views/GameCard.py adds returning bats back into the projected lineup
and gates them on two numbers I chose by eye: _RET_MIN_PA = 40 and
_RET_MIN_PA_PER_GAME = 3.0. Standing rule 1 says measure before you set
any number, and this repo has now been burned by a guess twice:

  * WINDOW_GAMES sat at 14 for weeks. Measured on 2026-08-19 it was 2.4
    points WORSE than copying last night's lineup. Seven was the only
    window that beat the baseline at all.
  * hr_floors_probe exists because every threshold picked by eye on this
    site turned out wrong.

So these two are the same shape of number and get the same treatment.

THE CLAIMS UNDER TEST

  1. Does an activation predict a START AT ALL? If a returning bat
     starts 55% of the time, he is a coin flip and belongs in the table
     as one, not as a projected starter. If it is 90%, the add-back is
     doing real work.

  2. Does PA-per-game separate the ones who start from the ones who do
     not? That is the entire load-bearing assumption behind the floor.
     If starters and bench bats return at the same rate, PA-per-game is
     not the discriminator and the floor should come out.

  3. WHERE does the curve actually cut? Printed as a table by
     PA-per-game bucket, so the number gets set from the data rather
     than from the shape of an argument.

  4. What does the CURRENT floor cost? Both errors, named: regulars it
     would have hidden, and bench bats it would have shown.

WHAT IT DOES NOT DO

No commit, no release, no deploy, no writes of any kind. It prints.

HOW TO RUN IT: workflow_dispatch on
.github/workflows/il-return-probe.yml. Optional lookback in days.
"""
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")
API = "https://statsapi.mlb.com/api/v1"

# The floors currently live in the view. Duplicated here deliberately —
# this script must be able to say what the SHIPPED numbers cost, and
# importing a Streamlit view headlessly is not possible. If they diverge,
# the report below is measuring something the site is not doing, so keep
# them in step.
CURRENT_MIN_PA = 40
CURRENT_MIN_PA_PER_GAME = 3.0

RETURN_WORDS = ("activated", "reinstated", "recalled", "selected the contract",
                "returned from")


def _get(path, **params):
    for attempt in range(3):
        try:
            r = requests.get(f"{API}/{path}", params=params, timeout=20)
            r.raise_for_status()
            return r.json() or {}
        except Exception as exc:
            if attempt == 2:
                print(f"  [warn] {path} failed: {exc}", flush=True)
                return {}
            time.sleep(1.5 * (attempt + 1))
    return {}


def teams():
    return [(t["id"], t["name"])
            for t in _get("teams", sportId=1).get("teams", [])]


def activations(team_id, start, end):
    """[(date, pid, description)] — returns only, IL placements dropped.

    A bat activated and then re-placed on the IL before the date in
    question is dropped, same rule the shipped code uses. Without it the
    sample includes players who were not actually available, and they
    would count as "did not start" — biasing the measured rate down and
    making the floor look better than it is.
    """
    data = _get("transactions", teamId=team_id,
                startDate=start.isoformat(), endDate=end.isoformat())
    rows, placed = [], defaultdict(list)
    for tx in data.get("transactions", []) or []:
        pid = ((tx.get("person") or {}).get("id"))
        desc = (tx.get("description") or "").strip()
        when = tx.get("date") or ""
        if pid is None or not desc or not when:
            continue
        low = desc.lower()
        if any(w in low for w in RETURN_WORDS):
            rows.append((when, pid, desc))
        elif "injured list" in low:
            placed[pid].append(when)
    return [(w, p, d) for w, p, d in rows
            if not any(w2 <= w for w2 in placed.get(p, []) if w2 > w)]


def started_that_day(team_id, pid, date_str):
    """True / False / None. None means no game found — excluded from the
    sample rather than counted as a non-start, because a team that did
    not play tells you nothing about whether he would have started."""
    sched = _get("schedule", sportId=1, teamId=team_id,
                 startDate=date_str, endDate=date_str)
    pks = [g.get("gamePk") for d in sched.get("dates", [])
           for g in d.get("games", [])
           if (g.get("status", {}) or {}).get("abstractGameState") == "Final"]
    if not pks:
        return None
    for pk in pks:
        box = _get(f"game/{pk}/boxscore")
        for side in ("away", "home"):
            tb = ((box.get("teams", {}) or {}).get(side, {}) or {})
            if (tb.get("team", {}) or {}).get("id") != team_id:
                continue
            pl = (tb.get("players", {}) or {}).get(f"ID{pid}")
            if pl:
                order = pl.get("battingOrder")
                if order and str(order).endswith("00"):
                    return True
    return False


def season_shape(pid, season):
    """(PA, games) before the return — the two numbers the floor uses.

    Read from MLB's own season hitting totals rather than from this
    app's parquets, so the probe does not depend on an archive being
    present and can be run from a clean checkout.
    """
    data = _get(f"people/{pid}", hydrate=f"stats(group=hitting,type=season,season={season})")
    for person in data.get("people", []) or []:
        for st in person.get("stats", []) or []:
            for split in st.get("splits", []) or []:
                stat = split.get("stat", {}) or {}
                pa = stat.get("plateAppearances")
                g = stat.get("gamesPlayed")
                if pa is not None and g:
                    return int(pa), int(g)
    return None, None


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    today = datetime.now(EASTERN).date()
    start = today - timedelta(days=days)
    season = today.year
    print(f"IL-return probe — {start} to {today} ({days} days), {season}\n")

    sample = []          # (name, pa, games, pa_per_game, started)
    no_game, no_stats = 0, 0

    for tid, tname in teams():
        acts = activations(tid, start, today)
        if not acts:
            continue
        print(f"{tname}: {len(acts)} return move(s)", flush=True)
        for when, pid, desc in acts:
            started = started_that_day(tid, pid, when)
            if started is None:
                no_game += 1
                continue
            pa, g = season_shape(pid, season)
            if not pa or not g:
                no_stats += 1
                continue
            name = desc.split()[2] if len(desc.split()) > 2 else str(pid)
            sample.append((desc, pa, g, pa / g, started))

    if not sample:
        print("\nNo usable returns in this window. Widen the lookback.")
        return 0

    n = len(sample)
    started_n = sum(1 for r in sample if r[4])
    print(f"\n{'=' * 62}")
    print("=== 1. DOES AN ACTIVATION PREDICT A START AT ALL? ===")
    print(f"  {started_n}/{n} returning bats started that day: "
          f"{started_n / n * 100:.1f}%")
    print(f"  (excluded: {no_game} with no game that day, "
          f"{no_stats} with no season line)")
    print("  Below ~60% a returning bat is a coin flip and belongs in the")
    print("  table labelled as one, not as a projected starter.")

    print(f"\n{'=' * 62}")
    print("=== 2. DOES PA-PER-GAME SEPARATE THEM? ===")
    buckets = [(0, 1.5), (1.5, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 10)]
    print(f"  {'PA/game':<12}{'started':>10}{'n':>8}")
    spread = []
    for lo, hi in buckets:
        rows = [r for r in sample if lo <= r[3] < hi]
        if not rows:
            print(f"  {f'{lo}-{hi}':<12}{'—':>10}{0:>8}")
            continue
        pct = sum(1 for r in rows if r[4]) / len(rows) * 100
        spread.append(pct)
        print(f"  {f'{lo}-{hi}':<12}{pct:>9.1f}%{len(rows):>8}")
    if len(spread) >= 2:
        print(f"  spread top-to-bottom: {max(spread) - min(spread):.1f} pts")
        print("  FLAT MEANS PA-PER-GAME IS NOT THE DISCRIMINATOR and the")
        print("  floor should come out rather than be retuned.")

    print(f"\n{'=' * 62}")
    print("=== 3. WHERE SHOULD THE CUT GO? ===")
    print(f"  {'floor':<10}{'shown':>8}{'of those started':>20}{'regulars hidden':>18}")
    for cut in (0.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        shown = [r for r in sample if r[3] >= cut]
        hidden_starters = [r for r in sample if r[3] < cut and r[4]]
        if not shown:
            continue
        pct = sum(1 for r in shown if r[4]) / len(shown) * 100
        print(f"  {cut:<10.1f}{len(shown):>8}{pct:>19.1f}%"
              f"{len(hidden_starters):>18}")
    print("  Read this as a trade, not a maximum: a higher floor shows a")
    print("  cleaner list and hides more real starters. The right cut is")
    print("  where the percentage stops climbing meaningfully.")

    print(f"\n{'=' * 62}")
    print(f"=== 4. WHAT THE SHIPPED FLOOR COSTS "
          f"({CURRENT_MIN_PA} PA / {CURRENT_MIN_PA_PER_GAME} per game) ===")
    def passes(r):
        return r[1] >= CURRENT_MIN_PA and r[3] >= CURRENT_MIN_PA_PER_GAME
    missed = [r for r in sample if not passes(r) and r[4]]
    shown_sat = [r for r in sample if passes(r) and not r[4]]
    print(f"  STARTED but would be HIDDEN: {len(missed)}")
    for r in missed[:12]:
        print(f"    {r[0][:70]}  [{r[1]} PA, {r[3]:.1f}/g]")
    print(f"  SHOWN but did NOT start: {len(shown_sat)}")
    for r in shown_sat[:12]:
        print(f"    {r[0][:70]}  [{r[1]} PA, {r[3]:.1f}/g]")
    print("\n  The first list is the expensive error — a returning regular")
    print("  the page hides is the exact failure the add-back was built to")
    print("  fix. The second is clutter. Weight them accordingly.")

    print("\nSet _RET_MIN_PA / _RET_MIN_PA_PER_GAME in app/views/GameCard.py")
    print("from section 3, then say so in the comment above them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
