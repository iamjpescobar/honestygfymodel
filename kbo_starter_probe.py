"""
Where did KBO probables go? They are not on the game page.

WHAT IS ESTABLISHED (runs 84211307417 and 84214829706)

  * mykbostats was rebuilt on a `ds-`-prefixed design system. The word
    "starter" appears ZERO times on any game page, so parse_starters()'s
    <div class="away-starter"> went with the redesign. Not a nested
    </div>, not a moved page — every fetch returned HTTP 200.
  * Counting REAL anchor tags instead of the "player-link" substring:
        played   20260804      -> 36 anchors  (a full box score)
        upcoming 20260805-09   ->  0 anchors
    Site chrome accounts for exactly 4 substring hits (40-36 and 4-0
    both give 4), which is why the raw counts read as 40 and 4.

A PREDICTION THAT WAS WRONG, recorded so nobody makes it again: run 1's
table was read as "2 real anchors per upcoming game, one probable
pitcher per side." That estimated chrome at 2 occurrences. It is 4, and
the true anchor count on an unplayed game is ZERO. There is no
probable-pitcher pair hiding in the game page markup.

So probables are not server-rendered into the game page at all. Three
places they can be instead, and this checks all three rather than
picking one — choosing wrong is what cost the two earlier runs.

  A. THE SCHEDULE PAGE. The old flow was schedule -> game page -> parse.
     A redesign that moves probables onto the listing is invisible to
     kbo_precompute, which only ever reads the game page. The week page
     is ~71 KB, which is a lot for six days of fixtures.
  B. CLIENT-SIDE JSON. The chrome carries data-turbolinks, so this is a
     Rails app, and a <script type="application/json"> payload or a
     .json endpoint is the normal pattern. requests cannot run JS, so
     anything rendered that way is invisible to every probe so far.
  C. NOWHERE PUBLIC YET. Possible, but the site has always announced the
     day before, so treat this as the residual, not the expectation.

ONE MORE THING TO EXPLAIN, and it may matter more than it looks. The
20260805 row showed 0 anchors. That game's 18:30 KST first pitch is
about 12:30 UTC and run 2 was at 21:09 UTC — roughly eight and a half
hours later. A completed game should look like 20260804 and carry a box
score. It does not. Either it was postponed (KBO voids are a known
problem here and the reason weather work is on the backlog), or these
pages are not server-rendering game data at all, which would point hard
at B. Section D prints the status text so the log answers it.

A BUG IN v2, fixed here: its closing keyword counts came from
`list(pages.items())[:1]` — the FIRST page, which is the PLAYED game,
not an upcoming one. So 'pitcher': 6 described a finished box score and
said nothing about probables. Section B counts on an explicitly chosen
upcoming page.

Still fixes nothing. A regex written against a guess is how this broke.

Run from Actions. Touches nothing: no commit, no release, no deploy.
"""
import re
import sys
import time

import requests

from kbo_precompute import GAME_LINE, UA

ANCHOR = re.compile(
    r'<a[^>]*class="[^"]*\bplayer-link\b[^"]*"[^>]*>(.*?)</a>', re.S)
PLAYER_HREF = re.compile(r'<a[^>]*href="(/players/[^"]+)"[^>]*>(.*?)</a>', re.S)
TAGS = re.compile(r'<[^>]+>')
CLASSES = re.compile(r'class="([^"]{1,70})"')


def txt(s):
    return re.sub(r'\s+', ' ', TAGS.sub(" ", s)).strip()


def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=25)
    except Exception as exc:
        print(f"  {url}: FAILED {type(exc).__name__}")
        return None, None
    return r.status_code, r.text


def main():
    print("=" * 70)
    print("KBO probables - where do they live now?")
    print("=" * 70)

    from datetime import date
    sched_url = f"https://mykbostats.com/schedule/week_of/{date.today().isoformat()}"
    code, sched = get(sched_url)
    print(f"schedule: {sched_url}  HTTP {code}  {len(sched or ''):,} chars")
    if not sched:
        return 1

    by_date = {}
    for m in GAME_LINE.finditer(sched):
        gid, away, home, ymd, _ = m.groups()
        by_date.setdefault(ymd, f"{gid}-{away}-vs-{home}-{ymd}")
    dates = sorted(by_date)
    print(f"  {len(dates)} dates: {dates}")

    # ---- A. Does the SCHEDULE page carry player links? -----------------
    print("\n" + "=" * 70)
    print("[A] SCHEDULE PAGE - does the listing itself name pitchers?")
    print("=" * 70)
    s_anchor = ANCHOR.findall(sched)
    s_href = PLAYER_HREF.findall(sched)
    print(f"  player-link class anchors : {len(s_anchor)}")
    print(f"  ANY /players/ hrefs       : {len(s_href)}")
    for href, inner in s_href[:12]:
        print(f"     {href}  ->  {txt(inner)!r}")
    if not s_href:
        print("  none - probables are not on the listing either.")

    # ---- B. An UPCOMING game page, in detail --------------------------
    # Explicitly the LAST date on the page: furthest from now, so it
    # cannot be a finished game masquerading as upcoming.
    slug = by_date[dates[-1]]
    print("\n" + "=" * 70)
    print(f"[B] UPCOMING GAME PAGE - {slug}")
    print("=" * 70)
    code, html = get(f"https://mykbostats.com/games/{slug}")
    print(f"  HTTP {code}  {len(html or ''):,} chars")
    if html:
        print("\n  keyword counts ON THIS upcoming page:")
        for kw in ("probable", "Probable", "starter", "Starter",
                   "pitcher", "Pitcher", "\uc120\ubc1c", "\uc608\uace0",
                   "postponed", "Postponed"):
            print(f"     {kw!r}: {html.count(kw)}")

        scripts = re.findall(r'<script([^>]*)>', html)
        print(f"\n  <script> tags: {len(scripts)}")
        for a in scripts:
            a = a.strip()
            if a:
                print(f"     <script {a[:110]}>")
        blobs = re.findall(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            html, re.S)
        print(f"  application/json blobs: {len(blobs)}")
        for b in blobs[:3]:
            print(f"     {b.strip()[:400]}")

        # data-* attributes carrying JSON are the other Rails pattern.
        dj = re.findall(r'(data-[\w-]+)="(\{[^"]{20,300})', html)
        print(f"  data-* attributes holding JSON: {len(dj)}")
        for k, v in dj[:5]:
            print(f"     {k}={v[:160]}")

        # The main content region, chrome stripped.
        i = html.find("<main")
        if i < 0:
            i = html.find('id="content"')
        print(f"\n  <main> found at offset {i}")
        if i >= 0:
            region = html[i:i + 7000]
            print("\n  --- distinct classes inside main ---")
            for c in list(dict.fromkeys(CLASSES.findall(region)))[:45]:
                print(f"     {c}")
            print("\n  --- main, tags stripped (first 1500 chars of text) ---")
            print("  " + txt(region)[:1500])
            print("\n  --- raw main HTML (first 4000 chars) ---")
            print(region[:4000])

    # ---- C. Is there a JSON endpoint? ---------------------------------
    print("\n" + "=" * 70)
    print("[C] JSON ENDPOINT CANDIDATES")
    print("=" * 70)
    for path in (f"/games/{slug}.json",
                 f"/games/{slug}/probables",
                 f"/schedule/week_of/{date.today().isoformat()}.json"):
        code, body = get("https://mykbostats.com" + path)
        head = (body or "")[:160].replace("\n", " ")
        print(f"  {path}\n     HTTP {code}  {len(body or ''):,} chars  {head!r}")
        time.sleep(0.3)

    # ---- D. The 20260805 anomaly --------------------------------------
    print("\n" + "=" * 70)
    print("[D] 20260805 - finished ~8.5h before run 2, yet 0 anchors")
    print("=" * 70)
    odd = by_date.get("20260805")
    if odd:
        code, h = get(f"https://mykbostats.com/games/{odd}")
        if h:
            print(f"  HTTP {code}  {len(h):,} chars  anchors={len(ANCHOR.findall(h))}")
            for kw in ("postponed", "Postponed", "Cancel", "cancel",
                       "\uc6b0\ucc9c", "\ucde8\uc18c", "Final", "final"):
                print(f"     {kw!r}: {h.count(kw)}")
            j = h.find("<main")
            if j >= 0:
                print("\n  --- its main text ---")
                print("  " + txt(h[j:j + 4000])[:900])

    print("\n" + "=" * 70)
    print("Done. Send the whole log.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
