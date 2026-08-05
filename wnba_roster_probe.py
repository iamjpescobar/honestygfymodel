"""
Print what ESPN actually returns for WNBA ROSTERS, INJURIES and STARTERS.

WHY THIS EXISTS

fetch_team_roster() already pulls /teams/{id}/roster, but keeps only
{name, pos}. Everything else in that payload is discarded before anyone
can look at it, so nobody knows whether it carries injury status, jersey
number, experience, or availability. This prints the actual field
inventory instead of guessing at it.

The starters question is separate and harder. wnba_precompute documents
that the summary endpoint's "rosters" block is empty for the WNBA feed —
"0 announced starters" on every game. If that is still true, confirmed
lineups are not obtainable from that source at any hour, and no code
change fixes it. This probe checks the same block, plus two other
candidates, so the answer is measured rather than assumed.

MUST RUN FROM ACTIONS, NOT A LAPTOP. ESPN blocks some paths from cloud
IP ranges and not from residential ones, which is the whole reason
SCOREBOARD_SOURCES exists. A result from anywhere else does not predict
what the pipeline or Render will see.

Touches nothing: no commit, no release, no deploy hook.
"""
import json
import sys

import requests

from wnba_precompute import (BASE, UA, fetch_scoreboard,
                             parse_scoreboard_events)

CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba"

# Fields worth knowing about, checked per athlete. Presence only — the
# question is what exists, not what today's values happen to be.
WANTED = ["id", "displayName", "jersey", "position", "injuries", "status",
          "experience", "active", "starter", "headshot", "age", "height",
          "weight", "college", "slug", "links"]


def _get(url, label):
    """GET and report honestly. Never raises — a dead endpoint is a
    result, not a crash."""
    try:
        r = requests.get(url, headers=UA, timeout=25)
    except Exception as exc:
        print(f"    {label}: request failed ({exc})")
        return None
    print(f"    {label}: HTTP {r.status_code}  {len(r.content):,} bytes")
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        print(f"    {label}: 200 but not JSON")
        return None


def _flatten_athletes(data):
    """ESPN returns athletes flat OR grouped into position buckets.
    Same both-shapes handling fetch_team_roster does."""
    raw = (data or {}).get("athletes") or []
    flat = []
    for a in raw:
        if isinstance(a, dict) and isinstance(a.get("items"), list):
            flat.extend(a["items"])
        else:
            flat.append(a)
    return [a for a in flat if isinstance(a, dict)]


def probe_roster(tid, team_name):
    print(f"\n  TEAM {team_name} (id {tid})")
    data = _get(f"{BASE}/teams/{tid}/roster", "site.web.api /roster")
    if not data:
        return 0
    ath = _flatten_athletes(data)
    print(f"    athletes returned: {len(ath)}")
    if not ath:
        print("    NOTE: zero athletes - the roster shape may have changed.")
        return 0

    present = {k: sum(1 for a in ath if a.get(k) not in (None, "", [], {}))
               for k in WANTED}
    print("    field coverage (n of %d):" % len(ath))
    for k in WANTED:
        mark = "  " if present[k] else "--"
        print(f"      {mark} {k:<12} {present[k]}")

    # Anything we did not think to ask for.
    extra = sorted({k for a in ath for k in a} - set(WANTED))
    if extra:
        print(f"    other keys seen: {', '.join(extra)}")

    # One full athlete, so the nesting is visible rather than inferred.
    print("    --- one athlete verbatim (truncated) ---")
    print(json.dumps(ath[0], indent=2)[:1800])

    # The availability question, directly.
    hurt = [a for a in ath if a.get("injuries")]
    print(f"    athletes carrying an injuries[] entry: {len(hurt)}")
    if hurt:
        print("    --- one injury entry ---")
        print(json.dumps(hurt[0].get("injuries"), indent=2)[:900])
    return len(ath)


def probe_injuries(tid):
    for label, url in (
        ("site.web.api /injuries", f"{BASE}/teams/{tid}/injuries"),
        ("core /injuries", f"{CORE}/teams/{tid}/injuries"),
    ):
        data = _get(url, label)
        if data:
            print(f"      keys: {sorted(data)[:12]}")
            items = data.get("items") or data.get("injuries") or []
            print(f"      entries: {len(items)}")
            if items:
                print(json.dumps(items[0], indent=2)[:700])


def probe_starters(event_id, matchup):
    """The actual lineup question. Three candidates, all reported."""
    print(f"\n  STARTERS for {matchup} (event {event_id})")

    data = _get(f"{BASE}/summary?event={event_id}", "summary")
    if data:
        rosters = data.get("rosters") or []
        print(f"    rosters[] blocks: {len(rosters)}")
        total_named, total_starters = 0, 0
        for blk in rosters:
            entries = blk.get("roster") or []
            total_named += len(entries)
            total_starters += sum(1 for e in entries if e.get("starter"))
        print(f"    players named across blocks: {total_named}")
        print(f"    marked starter=true:         {total_starters}")
        if total_starters == 0:
            print("    -> still zero announced starters from summary.")
        if rosters and (rosters[0].get("roster") or []):
            print("    --- one roster entry verbatim ---")
            print(json.dumps(rosters[0]["roster"][0], indent=2)[:900])
        # Other blocks on summary sometimes carry availability.
        print(f"    summary top-level keys: {sorted(data)}")

    data = _get(f"{CORE}/events/{event_id}/competitions/{event_id}"
                f"/competitors", "core /competitors")
    if data:
        print(f"      keys: {sorted(data)[:12]}")


def main(want_date):
    d = want_date.replace("-", "")
    print("=" * 70)
    print(f"WNBA roster / injury / lineup probe - {want_date}")
    print("=" * 70)

    try:
        sb, source = fetch_scoreboard(d, require_events=False)
    except Exception as exc:
        print(f"scoreboard failed entirely: {exc}")
        return 1
    print(f"scoreboard answered by: {source}")

    games = []
    for eid, _st, _done, g in parse_scoreboard_events(sb):
        games.append((eid, g))
    print(f"games on this date: {len(games)}")
    if not games:
        print("No games - rerun with a date the WNBA actually played.")
        return 0

    seen = set()
    for eid, g in games:
        for side in ("away", "home"):
            tid = g.get(f"{side}_id")
            if tid and tid not in seen:
                seen.add(tid)
                probe_roster(tid, g.get(side, "?"))
                probe_injuries(tid)

    for eid, g in games:
        probe_starters(eid, f"{g.get('away')} @ {g.get('home')}")

    print("\n" + "=" * 70)
    print("Done. Download the log zip and send the whole thing.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-08-03"))
