#!/usr/bin/env python3
"""
MLB team RS/RA probe — is TIER 2 of the best-games ranking buildable?

WHY THIS EXISTS

The ranking is three strict tiers: biggest modeled edge -> highest
projected run total -> biggest weather/park swing. TIER 2 NEVER FIRES.
engines/run_total needs each team's runs scored and runs allowed per
game; nothing on disk carries those for MLB, so proj_total is never
written and the sort falls through to tier 3.

HANDOFF is explicit about the two ways to get this wrong:

  1. DO NOT substitute the O/U signal count. It counts signals toward
     Over. It is not a number of runs, and ranking by it would be a
     different quantity wearing the decided label.
  2. A new source is a new failure mode — PROBE IT FIRST.

WHY THIS IS THE SECOND VERSION — READ BEFORE TRUSTING ANY VERDICT

v1 tried ONE query shape (`hydrate=stats(group=[hitting,pitching],
type=season)`), got zero clubs with runs, and printed "NOT BUILDABLE
HERE: tier 2 needs a different source".

**That verdict was not earned.** Zero out of thirty is the signature of
a malformed query, not of a missing field — a real absence would more
likely show partial or odd data. v1 could not tell "the API does not
carry this" apart from "my hydrate syntax was wrong", because it never
checked whether ANY stats block came back. It reported the first as if
it had ruled out the second.

That is precisely the confident wrong diagnosis this repo has a rule
against, and recording it would have closed tier 2 as impossible on the
strength of a typo.

v2 therefore tries SEVERAL documented query shapes and, for each,
reports what actually came back — team count, whether stats blocks are
present at all, and whether a runs field exists. **The diagnostics are
the output; the verdict is a summary of them.** If every shape fails
identically, that is finally evidence about the API rather than about
this script.

Using statsapi rather than a new scraper on purpose: calibration.py,
roster.py and weather_engine already call it, so it adds no dependency,
no terms question, and no new IP-blocking risk.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

SEASON = datetime.now(ZoneInfo("America/New_York")).year

# Several documented shapes for the same question. Named so the log says
# which one worked rather than just that something did.
CANDIDATES = [
    ("teams/stats hitting",
     f"https://statsapi.mlb.com/api/v1/teams/stats"
     f"?season={SEASON}&sportId=1&stats=season&group=hitting"),
    ("teams/stats pitching",
     f"https://statsapi.mlb.com/api/v1/teams/stats"
     f"?season={SEASON}&sportId=1&stats=season&group=pitching"),
    ("teams hydrate combined (v1's shape)",
     f"https://statsapi.mlb.com/api/v1/teams"
     f"?sportId=1&season={SEASON}"
     f"&hydrate=stats(group=[hitting,pitching],type=season)"),
    ("teams hydrate hitting only",
     f"https://statsapi.mlb.com/api/v1/teams"
     f"?sportId=1&season={SEASON}&hydrate=stats(type=season,group=hitting)"),
    # THE LEAD FROM RUN 85217159493, and the reason for this round.
    #
    # Every teams/stats shape above returns ONE entry — the LEAGUE
    # AGGREGATE (591 runs in 118 G), not a club. That is not "the API
    # lacks per-team runs"; it is this endpoint answering a
    # league-level question.
    #
    # Standings answers a different one. Each teamRecord carries
    # runsScored and runsAllowed for THAT club, and leagueId=103,104
    # covers all 30 in a single call — which is what tier 2 of the
    # best-games ranking needs and has never had.
    #
    # HYPOTHESIS, NOT A FINDING. Nobody has called this. It is here to
    # be measured, and the per-shape diagnostics below are what decides
    # it — not the verdict line.
    ("standings regularSeason (the untested lead)",
     f"https://statsapi.mlb.com/api/v1/standings"
     f"?leagueId=103,104&season={SEASON}&standingsTypes=regularSeason"),
]


def _walk_for_runs(node, depth=0):
    """Find any dict carrying a 'runs' value. Returns (runs, gamesPlayed).

    Walks rather than assuming a shape, because the shape is exactly
    what v1 got wrong. Depth-capped so a deep payload cannot hang.
    """
    if depth > 8:
        return None
    if isinstance(node, dict):
        # STANDINGS SPELLS IT DIFFERENTLY. teams/stats returns `runs`;
        # a standings teamRecord returns `runsScored` / `runsAllowed`
        # with the game count under `gamesPlayed`. Looking only for
        # `runs` would have walked the whole standings payload, found
        # nothing, and reported 0 with runs — the endpoint working
        # perfectly and the probe calling it empty. That is precisely
        # the failure this file exists to stop repeating.
        if node.get("runsScored") is not None:
            return node.get("runsScored"), node.get("gamesPlayed")
        if node.get("runs") is not None:
            return node.get("runs"), node.get("gamesPlayed")
        for v in node.values():
            hit = _walk_for_runs(v, depth + 1)
            if hit:
                return hit
    elif isinstance(node, list):
        for v in node:
            hit = _walk_for_runs(v, depth + 1)
            if hit:
                return hit
    return None


def _entries(payload):
    """The per-CLUB records in a payload, whatever its shape.

    ONE EXTRACTOR, USED BY BOTH THE DIAGNOSTIC AND THE RUNS COUNTER, and
    that is the whole point of it existing.

    When the standings shape was added, only _diagnose learned the new
    nesting. main() kept its own private copy, keyed on the top-level teams /
    stats lists, which are empty for standings. Run
    85312622391 therefore printed:

        standings regularSeason  200 | 30 entries | 30 w/stats | 0 w/runs

    Thirty entries, thirty carrying runsScored, and zero counted. The
    verdict then ranked shapes by w/runs, picked `teams/stats hitting`
    with its ONE league-aggregate row, and reported PARTIAL — declaring
    tier 2 unbuildable off a payload that had all thirty clubs in it.

    Two places extracting entries meant one of them was always going to
    be forgotten. Now there is one.
    """
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("records"), list):
        return [tr for rec in payload["records"]
                if isinstance(rec, dict)
                for tr in (rec.get("teamRecords") or [])
                if isinstance(tr, dict)]
    entries = payload.get("teams") or payload.get("stats") or []
    return entries if isinstance(entries, list) else []


def _diagnose(payload):
    """What actually came back — the part v1 never printed.

    STANDINGS NESTS ONE LAYER DEEPER and had to be handled explicitly:
    its entries live under records[].teamRecords[], not under a top-level
    `teams` or `stats` list. Counting only the outer `records` would have
    reported 6 entries (the divisions) for a payload holding all 30
    clubs, and 6-of-30 reads exactly like the partial failure this probe
    already refused once. Getting the count wrong is how a working
    endpoint gets recorded as broken.
    """
    if not isinstance(payload, dict):
        return "payload is not an object", 0, 0
    top = ", ".join(sorted(payload.keys())[:5]) or "(no keys)"

    if isinstance(payload.get("records"), list):
        entries = _entries(payload)
        with_stats = sum(1 for t in entries
                         if t.get("runsScored") is not None
                         or t.get("runsAllowed") is not None)
        return (f"top keys: {top} ({len(payload['records'])} division "
                f"records)", len(entries), with_stats)

    teams = _entries(payload)
    with_stats = sum(
        1 for t in teams
        if isinstance(t, dict) and (t.get("stats") or t.get("splits")))
    return f"top keys: {top}", len(teams), with_stats


def main() -> int:
    verdict_shape = None
    verdict_count = 0

    for label, url in CANDIDATES:
        try:
            r = requests.get(url, timeout=25)
        except Exception as e:
            print(f"{label:36s} ERROR {type(e).__name__}")
            continue

        if r.status_code != 200:
            print(f"{label:36s} HTTP {r.status_code}")
            continue

        try:
            payload = r.json()
        except Exception:
            print(f"{label:36s} 200 but body is not JSON ({len(r.content)}b)")
            continue

        shape, n_entries, n_with_stats = _diagnose(payload)
        entries = _entries(payload)

        with_runs = 0
        sample = None
        for e in entries:
            hit = _walk_for_runs(e)
            if hit and hit[0] is not None:
                with_runs += 1
                if sample is None:
                    nm = (e.get("team") or {}).get("name") if isinstance(
                        e.get("team"), dict) else e.get("name")
                    sample = (nm or "?", hit[0], hit[1])

        print(f"{label:36s} 200 | {n_entries:>3} entries | "
              f"{n_with_stats:>3} w/stats | {with_runs:>3} w/runs | {shape}")
        if sample:
            print(f"{'':36s}      e.g. {sample[0]}: {sample[1]} runs "
                  f"in {sample[2]} G")

        if with_runs > verdict_count:
            verdict_count, verdict_shape = with_runs, label

    print("-" * 72)
    if verdict_count >= 30:
        print(f"TIER 2 BUILDABLE: {verdict_count} clubs carry season runs via "
              f"'{verdict_shape}'. Next step is writing RS/RA into the slate "
              f"and letting run_total compute proj_total — the ranking is "
              f"already wired and tested for it.")
    elif verdict_count:
        print(f"PARTIAL: best shape '{verdict_shape}' returned {verdict_count} "
              f"club(s) with runs, not 30. MISSING IS NOT ZERO — tier 2 stays "
              f"dark rather than half-firing. Find why the rest are absent "
              f"before building on this.")
    else:
        print("NO SHAPE RETURNED RUNS. Read the per-row diagnostics above "
              "before concluding the API lacks this: if the rows show "
              "entries but 0 w/stats, the query is still wrong and the next "
              "step is the endpoint docs, NOT a new source. Only if entries "
              "arrive WITH stats blocks and still no runs field is this "
              "evidence about statsapi itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
