#!/usr/bin/env python3
"""
MLB team RS/RA probe — is TIER 2 of the best-games ranking buildable?

WHY THIS EXISTS

The ranking is three strict tiers: biggest modeled edge -> highest
projected run total -> biggest weather/park swing. TIER 2 NEVER FIRES.
engines/run_total needs each team's runs scored and runs allowed per
game, nothing on disk carries those for MLB, so proj_total is
deliberately never written and the sort falls through to tier 3.

HANDOFF is explicit about the two ways to get this wrong:

  1. DO NOT substitute the O/U signal count. It counts signals toward
     Over. It is not a number of runs, and ranking by it would be a
     different quantity wearing the decided label.
  2. A new source is a new failure mode — PROBE IT FIRST. This repo has
     shipped correct-and-tested code with no working source behind it
     (rule 22, parse_homepage_schedule) and paid for it.

This probe answers one question and writes nothing: does the MLB Stats
API this app ALREADY depends on expose season runs-scored and
runs-allowed per team, for all 30 clubs, in one call?

Using statsapi rather than a new scraper on purpose. calibration.py,
roster.py and weather_engine already call it, so it carries no new
dependency, no new terms question, and no new IP-blocking risk — the
three things that have sunk source additions here before.

HOW TO READ THE RESULT

  TIER 2 BUILDABLE     all 30 clubs returned RS and RA. The follow-on
                       work is writing those into the slate and letting
                       run_total compute proj_total; the ranking is
                       already wired and tested for it.
  PARTIAL              says how many clubs are missing. Missing is not
                       zero (best_games' own rule) — a partial source
                       means tier 2 stays dark, not that it half-fires.
  NOT BUILDABLE HERE   the fields are absent. Tier 2 needs a different
                       source and this probe was the cheap way to find
                       out.
"""
from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

SEASON = datetime.now(ZoneInfo("America/New_York")).year

# hydrate=stats(...) returns season totals inline with the team list, so
# this is ONE call for all 30 clubs rather than 30 calls — the version
# that gets rate-limited in CI is the one that loops.
URL = (
    "https://statsapi.mlb.com/api/v1/teams"
    f"?sportId=1&season={SEASON}"
    "&hydrate=stats(group=[hitting,pitching],type=season)"
)


def _runs(team: dict, group: str):
    """Season runs for one stat group, or None.

    Returns None rather than 0 for an absent field. MISSING IS NOT ZERO
    is the rule the whole ranking module is built on: a club with no
    measured runs must not read as a club that scored none.
    """
    for block in team.get("stats") or []:
        gname = ((block.get("group") or {}).get("displayName")
                 or (block.get("group") or {}).get("name") or "")
        if gname.lower() != group:
            continue
        for split in block.get("splits") or []:
            stat = split.get("stat") or {}
            if stat.get("runs") is not None:
                return stat["runs"], stat.get("gamesPlayed")
    return None


def main() -> int:
    try:
        r = requests.get(URL, timeout=25)
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__}")
        return 1
    if r.status_code != 200:
        print(f"FETCH FAILED: HTTP {r.status_code}")
        return 1

    teams = (r.json() or {}).get("teams") or []
    if not teams:
        print("FETCH OK but zero teams returned — payload shape changed")
        return 1

    complete, missing = [], []
    for t in teams:
        rs = _runs(t, "hitting")
        ra = _runs(t, "pitching")
        if rs and ra and rs[1] and ra[1]:
            complete.append((t.get("name"), rs[0], ra[0], rs[1]))
        else:
            missing.append(t.get("name") or "?")

    if len(complete) == len(teams) == 30:
        sample = complete[0]
        print(f"TIER 2 BUILDABLE: {len(complete)}/30 clubs have RS and RA. "
              f"e.g. {sample[0]}: {sample[1]} RS / {sample[2]} RA in "
              f"{sample[3]} G")
        return 0

    if complete:
        print(f"PARTIAL: {len(complete)}/{len(teams)} clubs complete, "
              f"missing {', '.join(missing[:4])}"
              f"{'...' if len(missing) > 4 else ''} — tier 2 stays dark")
        return 0

    print(f"NOT BUILDABLE HERE: 0/{len(teams)} clubs carry season runs; "
          f"tier 2 needs a different source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
