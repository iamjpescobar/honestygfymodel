"""
What replaced <div class="away-starter"> on mykbostats?

WHY THIS EXISTS

Run 84211307417 answered the first question and raised the next one.
Across all six dates on the week page, every game returned HTTP 200 and
the literal word "starter" appeared ZERO times. So parse_starters() in
kbo_precompute is not being defeated by a nested </div> and is not
hitting a moved page — the class it hunts no longer exists. mykbostats
has been rebuilt on a `ds-`-prefixed design system (ds-panel-section,
ds-mega-panel, ds-team-logo), and the old markup went with the redesign.

That run could not say what replaced it, for a reason worth writing
down: it located its dump with `html.find("player-link")`, and the
FIRST occurrence of that substring on every page is

    <button data-ds-setting="player-links" ...>

in the settings menu — site chrome, printed before any game content. So
the raw dump was 6 KB of navigation links and contained no real anchor
at all.

The same substring match inflated the counts. `html.count("player-link")`
matches "player-links" too, and that settings button appears twice (the
desktop mega-panel and the mobile sheet). Subtract those:

    upcoming game   4 - 2 = 2 real anchors   <- one per side, the probables
    played game    40 - 2 = 38 real anchors  <- both full lineups

Two anchors on a game that has not been played is exactly the shape a
probable-pitcher pair would have. The data is most likely still on the
page under a new container name.

So this version does not search for a substring anywhere in the
document. It matches real anchor TAGS, and prints the element chain
enclosing them, which is the thing a corrected regex has to key on.

Still fixes nothing. A regex written against a guess is how this broke,
and guessing twice would be worse than guessing once.

Run from Actions so the answer reflects what the pipeline sees.
Touches nothing: no commit, no release, no deploy hook.
"""
import re
import sys
import time

import requests

from kbo_precompute import GAME_LINE, UA

# A real anchor, not the settings string. The class attribute is
# required and the name is word-bounded, so "player-links" cannot match:
# \b after "link" fails against the following "s".
ANCHOR = re.compile(
    r'<a[^>]*class="[^"]*\bplayer-link\b[^"]*"[^>]*>(.*?)</a>', re.S)

# Opening tags that carry a class, used to rebuild the container chain
# above an anchor.
OPEN_TAG = re.compile(r'<(div|section|table|tbody|tr|td|ul|li|span)\b[^>]*>',
                      re.I)

TAGS = re.compile(r'<[^>]+>')


def slugs_by_date():
    """One game slug per date on this week's page, past AND future.

    Kept from the previous version because it was the part that worked:
    two earlier probes each sampled a single game and each picked a
    useless one — the furthest fixture, then a game already finished,
    because date.today() is UTC and KBO runs on KST. Walking every date
    sidesteps the choice entirely.
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


def get(slug):
    try:
        r = requests.get(f"https://mykbostats.com/games/{slug}",
                         headers=UA, timeout=25)
    except Exception as exc:
        print(f"  {slug}: FAILED {type(exc).__name__}")
        return None
    if r.status_code != 200:
        print(f"  {slug}: HTTP {r.status_code}")
        return None
    return r.text


def container_chain(html, pos, depth=6):
    """The still-open class-bearing tags enclosing offset `pos`.

    Walks the document start->pos keeping a stack, popping on each
    closing tag. What remains is the ancestor chain, which is the
    answer to "what is the new away-starter called".
    """
    stack = []
    for m in re.finditer(r'<(/?)(\w+)\b([^>]*)>', html[:pos]):
        closing, tag, attrs = m.groups()
        if tag.lower() in ("br", "img", "input", "meta", "link", "hr"):
            continue
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag.lower():
                    del stack[i:]
                    break
        else:
            cls = re.search(r'class="([^"]*)"', attrs)
            stack.append((tag.lower(), cls.group(1) if cls else ""))
    return stack[-depth:]


def report(slug, html):
    hits = list(ANCHOR.finditer(html))
    print(f"\n{'=' * 70}\n{slug} — {len(hits)} real player-link anchor(s)\n{'=' * 70}")
    if not hits:
        print("  none. Not a probables page.")
        return

    for n, m in enumerate(hits[:4], 1):
        name = TAGS.sub("", m.group(1)).strip()
        did = re.search(r'data-id="(\d+)"', m.group(0))
        print(f"\n--- anchor {n}: {name!r}  data-id={did.group(1) if did else '?'}")
        print("    enclosing chain (outermost first):")
        for tag, cls in container_chain(html, m.start()):
            print(f"      <{tag}{(' class=' + repr(cls)) if cls else ''}>")

    lo = max(0, hits[0].start() - 1200)
    hi = min(len(html), hits[-1].end() + 600)
    print(f"\n--- raw HTML spanning the anchors ({hi - lo} chars) ---")
    print(html[lo:hi])


def main():
    print("=" * 70)
    print("KBO probables - what replaced away-starter")
    print("=" * 70)

    slugs = [sys.argv[1]] if len(sys.argv) > 1 else slugs_by_date()
    if not slugs:
        return 1

    # Survey first: real anchor counts, so the table is not distorted by
    # the settings-panel substring the way the last run's was.
    print("\n" + "-" * 70)
    print(f"{'date':<10} {'HTTP':<6} {'anchors':>8}  slug")
    print("-" * 70)
    pages = {}
    for slug in slugs:
        html = get(slug)
        n = len(ANCHOR.findall(html)) if html else -1
        print(f"{slug[-8:]:<10} {'200' if html else '---':<6} {n:>8}  {slug}")
        if html:
            pages[slug] = html
        time.sleep(0.3)

    # An upcoming game carries the probables and nothing else, so it is
    # the cleanest page to read. A played game buries them in 38 anchors.
    upcoming = [s for s, h in pages.items() if 1 <= len(ANCHOR.findall(h)) <= 6]
    if not upcoming:
        print("\nNo page has a small anchor count. Either nothing is announced")
        print("on any date, or the anchors are rendered client-side — check")
        print("whether the page ships a <script> with JSON instead.")
        for s, h in list(pages.items())[:1]:
            for kw in ("probable", "Probable", "pitcher", "Pitcher", "선발"):
                print(f"  {kw!r}: {h.count(kw)}")
        return 0

    for slug in upcoming[:2]:
        report(slug, pages[slug])

    print("\n" + "=" * 70)
    print("Done. Send the whole log.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
