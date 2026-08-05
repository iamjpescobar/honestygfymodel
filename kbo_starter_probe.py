"""
Why does KBO report 0 probable starters on every game?

WHY THIS EXISTS

Every run says `fetched starters for N upcoming games; 0 had at least
one probable posted` — including a run at 16:49 KST, one hour forty
before first pitch, when mykbostats announces starters the day before.
Timing does not explain it.

`parse_starters()` in kbo_precompute.py looks for:

    <div class="away-starter"> ... </div>

with `re.search(rf'<div class="{cls}">(.*?)</div>', html, re.S)`.

THREE THINGS FAIL IDENTICALLY, and the log cannot tell them apart
because every one of them returns an empty dict without printing:

  1. NESTED DIVS — `(.*?)</div>` is non-greedy and stops at the FIRST
     closing tag. Wrap the photo or the stat line in an inner <div> and
     the capture ends before the player-link anchors.
  2. CLASS CHANGED — the regex demands the attribute be exactly
     `class="away-starter"`. One extra utility class and it matches
     nothing.
  3. PAGE MOVED — fetch_starters_for_game returns empty on any
     non-200, silently, so a URL change looks the same as no starters.

This prints enough of the real page to say which. It does NOT fix
anything; a regex written against a guess is how this broke.

Run from Actions so the answer reflects what the pipeline sees.
Touches nothing: no commit, no release, no deploy hook.
"""
import re
import sys
import time

import requests

from kbo_precompute import GAME_LINE, UA


def survey():
    """One game per date on this week's page, past AND future.

    Two earlier versions of this probe each sampled a single game and
    each picked a useless one: first the furthest fixture (four days
    out, nothing announced), then a game that had already been played,
    because date.today() is UTC and KBO runs on KST. Choosing one game
    correctly turns out to be the hard part of this question.

    So don't choose. Walk every date on the page and print the starter
    count for each. The pattern across past/today/future answers it
    outright: if NO date has a starter block the markup changed; if the
    near-future ones do, the scrape works and the pipeline is sampling
    or timing wrong.
    """
    from datetime import date
    url = f"https://mykbostats.com/schedule/week_of/{date.today().isoformat()}"
    print(f"schedule: {url}")
    r = requests.get(url, headers=UA, timeout=25)
    print(f"  HTTP {r.status_code}  {len(r.content):,} bytes")
    if r.status_code != 200:
        return []
    by_date = {}
    for m in GAME_LINE.finditer(r.text):
        game_id, away, home, ymd, _inner = m.groups()
        by_date.setdefault(ymd, f"{game_id}-{away}-vs-{home}-{ymd}")
    print(f"  {len(by_date)} dates: {sorted(by_date)}")
    return [by_date[d] for d in sorted(by_date)]


def main():
    print("=" * 70)
    print("KBO probable-starter probe - mykbostats")
    print("=" * 70)

    slugs = [sys.argv[1]] if len(sys.argv) > 1 else survey()
    if not slugs:
        return 1

    print("\n" + "-" * 70)
    print(f"{'date':<10} {'HTTP':<6} {'starter':>8} {'player-link':>12}  slug")
    print("-" * 70)
    detail = None
    for slug in slugs:
        try:
            r = requests.get(f"https://mykbostats.com/games/{slug}",
                             headers=UA, timeout=25)
        except Exception as exc:
            print(f"{slug[-8:]:<10} FAILED {type(exc).__name__}")
            continue
        html = r.text if r.status_code == 200 else ""
        n_start = html.count("starter")
        n_link = html.count("player-link")
        print(f"{slug[-8:]:<10} {r.status_code:<6} {n_start:>8} {n_link:>12}  {slug}")
        if n_start and detail is None:
            detail = (slug, html)
        time.sleep(0.3)

    if detail is None:
        print("\nNO DATE ON THIS PAGE HAS A STARTER BLOCK.")
        print("That is the finding: parse_starters is looking for markup")
        print("mykbostats no longer emits, and no amount of timing fixes it.")
        print("Next step is to read a game page by hand and find what")
        print("replaced <div class=\"away-starter\">.")
        return 0

    slug, html = detail
    print(f"\nFirst page WITH a starter block: {slug}")

    print("\n[2] Every class attribute containing 'starter':")
    for c in sorted(set(re.findall(r'class="([^"]*starter[^"]*)"', html))):
        exact = c in ("away-starter", "home-starter")
        print(f"    class=\"{c}\"{'' if exact else '   <-- NOT an exact match'}")

    print("\n[3] The regex kbo_precompute actually uses:")
    for cls in ("away-starter", "home-starter"):
        m = re.search(rf'<div class="{cls}">(.*?)</div>', html, re.S)
        if not m:
            print(f"    {cls}: NO MATCH")
            continue
        body = m.group(1)
        anchors = re.findall(
            r'<a class="player-link"[^>]*data-id="(\d+)"[^>]*>(.*?)</a>',
            body, re.S)
        print(f"    {cls}: matched {len(body)} chars, "
              f"{len(anchors)} player-link anchor(s)")
        if len(anchors) < 2:
            print("      -> CAUSE 1: capture stopped early (nested </div>).")
        print(f"      captured: {body[:300]!r}")

    print("\n[4] Raw HTML around the first 'starter' mention:")
    i = html.find("starter")
    print(html[max(0, i - 600):i + 1400])

    print("\n" + "=" * 70)
    print("Done. Send the whole log.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
