"""
ONE RUN, TWO QUESTIONS. Answers nothing by itself — it reports.

  A. Can the mykbostats SCHEDULE page give venue and first-pitch time
     for FUTURE dates?  (handoff item V2)
  B. Does either league publish PER-START pitcher game logs anywhere
     we can reach?  (handoff item PITCHER H2H)

WHY BOTH IN ONE SCRIPT. They are the only two open items that are
blocked on the same thing — looking at a page nobody has looked at from
Actions — and this repo has already paid for the habit of probing
before parsing four separate times. Bundling them costs one run instead
of two.

WHY IT MUST RUN FROM ACTIONS. A result from one network says nothing
about another. ESPN serves 403 to cloud ranges and 200 elsewhere;
stats.wnba.com hangs on datacenter IPs and answers instantly from a
phone. The runner that publishes the slate is the only network whose
answer counts.

WHAT A IS FOR. parse_week() still keys on `<div class="venue">` and a
`datetime=` attribute, both killed by the mykbostats v3 rewrite, so
every future KBO date renders TBD. Today's slate is now repaired off
the homepage, but the homepage carries today only. A chat-window
transcription of the schedule page suggested the card text reads
"Lotte Giants KT Wiz 34° 6:30pm Suwon" — the same shape as the
homepage. THAT TRANSCRIPTION IS NOT EVIDENCE (rule 15: retyped content
has already caused an outage here). This prints the real bytes so
whoever writes the parser writes it against the page.

Note what A must also establish: the date headings. The homepage is one
day, so parse_homepage_schedule keys each card to a game id and stops.
A week page has several dates, so a parser has to know whether the date
lives inside the card or only in a heading above it — a card matched to
the wrong day would forecast the wrong weather with full confidence.

WHAT B IS FOR. Both pipelines fetch SEASON leaderboards — aggregates,
qualified pitchers only (20 of them for a 10-team league). "This
pitcher against this opponent" cannot be computed from a season line,
so pitcher-vs-team H2H has no data behind it at all. Before designing
anything, confirm a per-start log exists and is SERVER-RENDERED. If it
is drawn client-side it is the Korean schedule page's 선발 problem
again and the answer is no, not "write more regex".

Discovery first, no guessed URLs: this finds a player link on a page we
already fetch, follows it, and describes what came back.

Still fixes nothing. No commit, no release, no deploy hook.
"""
import re
import sys
from datetime import date, timedelta

import requests

from kbo_precompute import UA
from npb_precompute import SEASON_YEAR

TAGS = re.compile(r"<[^>]+>")
CLASSES = re.compile(r'class="([^"]{1,70})"')
GAME_A = re.compile(r'<a[^>]*href="(/games/[^"]+)"[^>]*>(.*?)</a>', re.S)

# A per-start log is a table of DATES. Anything that has one will show
# many of these; a season aggregate shows none.
DATEISH = re.compile(r"\b\d{1,2}[./-]\d{1,2}\b")


def txt(s):
    return re.sub(r"\s+", " ", TAGS.sub(" ", s)).strip()


def get(label, url, **kw):
    """Fetch and report. Returns the response or None — never raises,
    because half a probe is still worth reading."""
    try:
        r = requests.get(url, headers=UA, timeout=30, **kw)
    except Exception as exc:
        print(f"  {label}: FAILED {type(exc).__name__}: {exc}")
        return None
    print(f"  {label}: HTTP {r.status_code}  {len(r.text):,} chars  {url}")
    return r if r.status_code == 200 else None


def rule(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ---------------------------------------------------------------------
# A.  KBO SCHEDULE PAGE — venue and first pitch for future dates
# ---------------------------------------------------------------------
def probe_schedule():
    rule("A. mykbostats SCHEDULE page — venue + time for FUTURE dates")

    # Next week, not this one: this week is mostly played, and a played
    # card shows a score where an upcoming one shows a time. The whole
    # question is what an UPCOMING card looks like.
    monday = date.today() + timedelta(days=(7 - date.today().weekday()))
    r = get("schedule", f"https://mykbostats.com/schedule/week_of/{monday}")
    if not r:
        print("  cannot continue with A.")
        return
    html = r.text

    b = re.search(r"(v\d+\s+Build\s+\d+\s*\([^)]*\))", html)
    print(f"  build stamp: {b.group(1) if b else 'not found'}")

    print("\n  DEAD KEYS — what parse_week still looks for:")
    print(f'     \'<div class="venue"\': {html.count(chr(60) + "div class=" + chr(34) + "venue")}')
    print(f"     'datetime=': {html.count('datetime=')}")

    print("\n  LIVE KEYS — what the product actually shows:")
    for kw in ("pm", "am", "\u00b0", "&deg;", "Chance of", "Forecast",
               "Postponed", "Canceled", "Final"):
        print(f"     {kw!r}: {html.count(kw)}")

    games = GAME_A.findall(html)
    print(f"\n  /games/ anchors: {len(games)}")

    # THE DATE QUESTION. If a weekday name never appears inside an
    # anchor, the date lives only in a heading and a parser must carry
    # it down the list rather than read it per card.
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")
    in_anchor = sum(1 for _h, i in games if any(d in i for d in days))
    print(f"  anchors containing a weekday name: {in_anchor} of {len(games)}")
    print("  weekday headings in the page: "
          + str({d: html.count(d) for d in days if html.count(d)}))

    # The slug carries yyyymmdd, which would settle the date question
    # outright if it survived the rewrite.
    dated = sum(1 for h, _i in games if re.search(r"-\d{8}", h))
    print(f"  anchors whose href carries yyyymmdd: {dated} of {len(games)}")

    rule("A. RAW MARKUP of the first three anchors")
    for href, inner in games[:3]:
        print(f"\n--- {href}")
        print(f"    text: {txt(inner)!r}")
        print(f"    classes: {list(dict.fromkeys(CLASSES.findall(inner)))}")
        print("    raw:")
        print(inner.strip()[:1800])

    # Everything between the first two anchors is whatever separates one
    # game from the next — headings included. This is where a date
    # heading would live.
    if len(games) >= 2:
        a = html.find(games[0][0])
        c = html.find(games[1][0])
        if 0 <= a < c:
            rule("A. WHAT SITS BETWEEN THE FIRST TWO GAMES")
            print(html[a:c][:1500])


# ---------------------------------------------------------------------
# B.  PER-START PITCHER LOGS — does either league publish one?
# ---------------------------------------------------------------------
def describe_player_page(label, r):
    """Say whether a fetched page looks like it holds a per-start log."""
    if not r:
        return
    html = r.text
    dates = DATEISH.findall(html)
    print(f"    <table> count: {html.count('<table')}")
    print(f"    <tr> count: {html.count('<tr')}")
    print(f"    date-like tokens: {len(dates)}  first few: {dates[:8]}")
    for kw in ("Opponent", "OPP", "vs", "Game Log", "GameLog", "Date",
               "\uc0c1\ub300", "\ub0a0\uc9dc", "\u5bfe\u6226", "\u767b\u677f"):
        n = html.count(kw)
        if n:
            print(f"    {kw!r}: {n}")
    # SERVER-RENDERED OR NOT. This is the whole question. If the numbers
    # above are absent but the page is full of scripts, the log is drawn
    # client-side and the answer is "needs an XHR endpoint", not "write
    # a parser".
    print(f"    <script> tags: {html.count('<script')}")
    print(f"    json-ish blobs: {html.count('application/json')}")
    print(f"    first 600 chars of visible text: {txt(html)[:600]!r}")


def probe_kbo_player():
    rule("B1. KBO — is there a per-start pitcher log on the official site?")
    r = get("pitching leaders",
            "https://eng.koreabaseball.com/Stats/PitchingLeaders.aspx")
    if not r:
        return
    # Discovery, not a guessed URL: find whatever the leaderboard links
    # its player names to.
    links = re.findall(r'href="([^"]*(?:Player|player)[^"]*)"', r.text)
    uniq = list(dict.fromkeys(links))
    print(f"  player-ish links on the leaderboard: {len(uniq)}")
    for u in uniq[:5]:
        print(f"     {u}")
    if not uniq:
        print("  NO player links. The English leaderboard is a dead end for")
        print("  per-start logs; the Korean site would be the next look.")
        return
    target = uniq[0]
    if target.startswith("/"):
        target = "https://eng.koreabaseball.com" + target
    elif not target.startswith("http"):
        target = "https://eng.koreabaseball.com/Stats/" + target.lstrip("./")
    describe_player_page("kbo player", get("player page", target))


def probe_npb_player():
    rule("B2. NPB — is there a per-start pitcher log on npb.jp?")
    r = get("pitching leaders",
            f"https://npb.jp/bis/eng/{SEASON_YEAR}/stats/pit_c.html")
    if not r:
        return
    links = re.findall(r'href="([^"]*players[^"]*)"', r.text)
    uniq = list(dict.fromkeys(links))
    print(f"  player links on the leaderboard: {len(uniq)}")
    for u in uniq[:5]:
        print(f"     {u}")
    if not uniq:
        print("  NO player links — the leaderboard is plain text names.")
        print("  That alone answers B for NPB: no per-start log is reachable")
        print("  from anything we already fetch.")
        return
    target = uniq[0]
    if target.startswith("/"):
        target = "https://npb.jp" + target
    elif not target.startswith("http"):
        target = f"https://npb.jp/bis/eng/{SEASON_YEAR}/stats/" + target
    describe_player_page("npb player", get("player page", target))


def main():
    print("=" * 70)
    print("intl_v2_probe — schedule markup (V2) + per-start logs (H2H)")
    print("Reports only. Writes nothing, commits nothing, deploys nothing.")
    print("=" * 70)
    probe_schedule()
    probe_kbo_player()
    probe_npb_player()
    rule("Done. Send the whole log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
