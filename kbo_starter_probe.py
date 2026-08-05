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

import requests

from kbo_precompute import GAME_LINE, UA


def find_a_game():
    """Pull this week's schedule and return the first upcoming slug,
    built exactly the way kbo_precompute builds it."""
    from datetime import date
    url = f"https://mykbostats.com/schedule/week_of/{date.today().isoformat()}"
    print(f"schedule: {url}")
    r = requests.get(url, headers=UA, timeout=25)
    print(f"  HTTP {r.status_code}  {len(r.content):,} bytes")
    if r.status_code != 200:
        return None
    today = date.today().strftime("%Y%m%d")
    slugs = []
    for m in GAME_LINE.finditer(r.text):
        game_id, away, home, ymd, _inner = m.groups()
        slugs.append((ymd, f"{game_id}-{away}-vs-{home}-{ymd}"))
    print(f"  {len(slugs)} games matched GAME_LINE")
    if not slugs:
        print("  !! GAME_LINE matched nothing. The SCHEDULE parser is broken")
        print("     too, which would be a bigger finding than the starters.")
        return None

    # THE NEAREST upcoming game, not the furthest. The first version of
    # this probe took slugs[-1] and landed on a fixture four days out,
    # which of course had no announced starter and proved nothing.
    # mykbostats announces the day before, so only tomorrow-or-sooner
    # can distinguish "parser broken" from "not posted yet".
    upcoming = sorted(d for d, _ in slugs if d >= today)
    print(f"  dates on this page: {sorted({d for d, _ in slugs})}")
    if not upcoming:
        print("  !! no upcoming games this week. Try next week's schedule.")
        return None
    pick = upcoming[0]
    slug = next(s for d, s in slugs if d == pick)
    print(f"  nearest upcoming: {pick} -> {slug}")
    return slug


def main():
    print("=" * 70)
    print("KBO probable-starter probe - mykbostats")
    print("=" * 70)

    slug = sys.argv[1] if len(sys.argv) > 1 else find_a_game()
    if not slug:
        return 1

    url = f"https://mykbostats.com/games/{slug}"
    print(f"\ngame page: {url}")
    try:
        r = requests.get(url, headers=UA, timeout=25)
    except Exception as exc:
        print(f"  request failed: {type(exc).__name__}: {exc}")
        return 1
    print(f"  HTTP {r.status_code}  {len(r.content):,} bytes")
    if r.status_code != 200:
        print("  -> CAUSE 3: the game page moved or is gone. Everything")
        print("     downstream is fine; the URL is wrong.")
        print(f"  body starts: {r.text[:300]!r}")
        return 0

    html = r.text

    # --- does the word appear at all? ---
    print("\n[1] Does 'starter' appear anywhere in the page?")
    for token in ("away-starter", "home-starter", "starter", "player-link",
                  "probable", "Season:"):
        print(f"    {token:<14} {html.count(token)} occurrence(s)")

    # --- what does the real attribute look like now? ---
    print("\n[2] Every class attribute containing 'starter':")
    found = re.findall(r'class="([^"]*starter[^"]*)"', html)
    if found:
        for c in sorted(set(found)):
            exact = c in ("away-starter", "home-starter")
            print(f"    class=\"{c}\"{'' if exact else '   <-- NOT an exact match'}")
    else:
        print("    none. Either the page has no starter block (genuinely")
        print("    unannounced) or the markup was renamed entirely.")

    # --- the current regex, run verbatim ---
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

    # --- raw context, so the real shape is visible ---
    print("\n[4] Raw HTML around the first 'starter' mention:")
    i = html.find("starter")
    if i == -1:
        print("    'starter' does not appear. If the game is genuinely")
        print("    unannounced this is expected - rerun closer to tip.")
    else:
        print(html[max(0, i - 600):i + 1400])

    print("\n" + "=" * 70)
    print("Done. Send the whole log. The fix follows from [2] and [3]:")
    print("  NO MATCH + a different class  -> cause 2, widen the attribute")
    print("  match but <2 anchors          -> cause 1, stop using regex here")
    print("  no 'starter' anywhere         -> genuinely unannounced, recheck")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
