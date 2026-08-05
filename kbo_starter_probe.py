"""
CONFIRM: KBO probables moved to the mykbostats HOMEPAGE.

WHAT IS ESTABLISHED (runs 84211307417, 84214829706, 84219057409)

  * mykbostats rebuilt as Elixir/Phoenix, "v3 Build 886 (2026-08-04)" —
    one day before the first probe. That is the whole story.
  * The GAME PAGE no longer carries probables at all. On an upcoming
    game (13800-SSG-vs-NC-20260809): probable/Probable/starter/Starter/
    pitcher/Pitcher/선발/예고 all count ZERO. Its <main> is fully
    server-rendered and complete — game-header, matchup, team-comparison
    (Record/BA/ERA/HR/Head-to-head), records rail, other-games panel —
    with no pitcher block and no placeholder.
  * Not client-side either: 4 <script> tags, zero application/json
    blobs, zero JSON-bearing data-* attributes.
  * No API: /games/{slug}.json returns HTML, /games/{slug}/probables 404s.
  * The week SCHEDULE page has no player links either (its only
    /players/ hrefs are the "Foreign Players" nav item, twice).

  * The HOMEPAGE has them. Read directly off https://mykbostats.com/ :
        Hanwha Eagles Samsung Lions 31° 6:30pm Daegu
            Starters: Park Jun-yeong vs. Chris Paddack
        NC Dinos Doosan Bears 35° 6:30pm Seoul-Jamsil
            Chance of Heat Cancellation
            Starters: Thompson vs. Choi Min-seok
    plus "Compare starting pitchers →" pointing at
        /stats/compare?pids=15400,15284,15357,15404,15448,15496,...
    which is TEN pids for FIVE games — two per game, in slate order.

WHY THIS RUN EXISTS ANYWAY

That reading came from a fetch outside Actions, and this repo already
learned the hard way that a result from one network says nothing about
another: ESPN serves 403 to cloud ranges and 200 elsewhere, which is
why all ESPN access was centralised. So this confirms from the runner
that publishes the slate.

It also captures RAW markup. The reading above came from a rendered
text extraction, which cannot show whether "Starters:" sits inside the
anchor, how the two names are delimited, or what wraps the temperature
and the cancellation warning. parse_starters() has to be written
against the real bytes — writing a regex against a guess is exactly how
this broke.

Still fixes nothing.

Run from Actions. Touches nothing: no commit, no release, no deploy.
"""
import re
import sys

import requests

from kbo_precompute import UA

TAGS = re.compile(r'<[^>]+>')
CLASSES = re.compile(r'class="([^"]{1,70})"')
GAME_A = re.compile(r'<a[^>]*href="(/games/[^"]+)"[^>]*>(.*?)</a>', re.S)


def txt(s):
    return re.sub(r'\s+', ' ', TAGS.sub(" ", s)).strip()


def main():
    print("=" * 70)
    print("KBO probables - confirming the HOMEPAGE from Actions")
    print("=" * 70)

    try:
        r = requests.get("https://mykbostats.com/", headers=UA, timeout=25)
    except Exception as exc:
        print(f"FAILED {type(exc).__name__}: {exc}")
        return 1
    html = r.text
    print(f"homepage HTTP {r.status_code}  {len(html):,} chars")
    if r.status_code != 200:
        return 1

    print("\n  keyword counts:")
    for kw in ("Starters:", "starter", "Cancel", "Chance of",
               "\u00b0", "Compare starting pitchers"):
        print(f"     {kw!r}: {html.count(kw)}")

    # The build stamp tells a future session whether the markup below is
    # still the one this parser was written against.
    b = re.search(r'(v\d+\s+Build\s+\d+\s*\([^)]*\))', html)
    print(f"\n  build stamp: {b.group(1) if b else 'not found'}")

    # The compare link carries the starter player ids, two per game in
    # slate order — the ids parse_starters used to read off the anchors.
    c = re.search(r'href="(/stats/compare\?pids=[^"]+)"', html)
    print(f"  compare link: {c.group(1) if c else 'NOT FOUND'}")
    if c:
        pids = re.search(r'pids=([^"&]+)', c.group(1)).group(1)
        pids = [p for p in re.split(r'%2C|,', pids) if p]
        print(f"    -> {len(pids)} pids: {pids}")

    games = GAME_A.findall(html)
    print(f"\n  /games/ anchors on the homepage: {len(games)}")

    print("\n" + "=" * 70)
    print("RAW ANCHOR MARKUP - what parse_starters must key on")
    print("=" * 70)
    shown = 0
    for href, inner in games:
        if "Starters" not in inner:
            continue
        shown += 1
        print(f"\n--- {href}")
        print(f"    text: {txt(inner)!r}")
        print(f"    classes inside: {list(dict.fromkeys(CLASSES.findall(inner)))}")
        print("    raw:")
        print(inner.strip()[:2200])
        if shown >= 2:
            break
    if not shown:
        print("  NO anchor contains 'Starters'. Either nothing is announced")
        print("  right now, or Actions is served a different page than a")
        print("  browser. Dumping the first game anchor so the difference")
        print("  is visible rather than guessed:")
        if games:
            print(games[0][1].strip()[:2200])

    # Everything above is today's slate. Confirm the section heading so a
    # future session knows the homepage only ever carries TODAY, and that
    # tomorrow's probables are simply not published yet.
    i = html.find("Today")
    print(f"\n  'Today' first appears at offset {i}")
    if i >= 0:
        print("  section text: " + txt(html[i:i + 1200])[:600])

    print("\n" + "=" * 70)
    print("Done. Send the whole log.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
