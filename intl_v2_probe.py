"""
ROUND 2. Answers nothing by itself — it reports.

WHAT ROUND 1 (run 84403678537) SETTLED, so nobody re-asks it:

  * The mykbostats SCHEDULE page carries NO time, NO venue and NO
    temperature. `<div class="venue"`: 0. `datetime=`: 0. `pm`: 0.
    `°`: 0. The "34° 6:30pm Suwon" line a previous session transcribed
    into chat was HOMEPAGE text, not schedule text. **Item V2 as scoped
    is dead** — the schedule page cannot repair future dates, because
    it does not have the data to repair them with.
  * The schedule page DOES carry probable starters, in a clean span:
        <span class="ds-game-team__starter">Oh Won-seok</span>
    That is worth more than what it replaces: the homepage carries
    TODAY only, the schedule page covers a window. But all three cards
    dumped were 2026-08-04, past or canceled. **Whether an UPCOMING
    card carries a starter is the open question**, and it is question
    A below.
  * `week_of/2026-08-10` served the 2026-08-04..09 window. Either the
    date clamps to the current week or it is ignored. The season crawl
    reaches 620 games so PAST weeks resolve; forward ones may not.
    Question A settles that too.
  * Two bugs in round 1, mine, fixed here: `am` was counted as a bare
    substring and matched "Samsung"/"team"/"name" 1,193 times — rule 17,
    in a script that cites rule 17 — and the KBO player-link picker took
    the first match, which was a `javascript:__doPostBack(...)` string,
    and dutifully fetched an error page. The log printed the real lead
    anyway: /teams/playerinfopitcher/summary.aspx?pcode=55268

ONE RUN, TWO QUESTIONS.

  A. Does an UPCOMING schedule card carry a starter, and does week_of
     reach forward at all?     (rewrites items V2 and F2)
  B. Does either league publish a PER-START pitcher log we can reach?
     (item PITCHER H2H)

WHY IT MUST RUN FROM ACTIONS. A result from one network says nothing
about another. ESPN serves 403 to cloud ranges and 200 elsewhere;
stats.wnba.com hangs on datacenter IPs and answers instantly from a
phone. The runner that publishes the slate is the only network whose
answer counts.

WHY A MATTERS MORE THAN IT LOOKS. KBO probables currently come off the
homepage and cover today only. If an upcoming schedule card carries
`ds-game-team__starter`, probables extend to the whole window from a
page the pipeline ALREADY fetches once per week — no new request, and
the "TODAY only, by design" line in the handoff stops being true.

WHY B IS ASKED THIS WAY. Both pipelines fetch SEASON leaderboards:
aggregates, qualified pitchers only, 20 of them for a 10-team league.
"This pitcher against this opponent" cannot be computed from a season
line, so pitcher-vs-team H2H has no data behind it at all. What matters
is not whether a log exists but whether it is SERVER-RENDERED. If it is
drawn client-side it is the Korean schedule page's missing 선발 all over
again, and the answer is "find the XHR endpoint", not "write a regex".

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
STARTER_SPAN = re.compile(r'ds-game-team__starter"?\s*>\s*(.*?)\s*</span>', re.S)

# A per-start log is a table of DATES. Anything holding one shows many;
# a season aggregate shows none.
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


def real_links(html, must_contain):
    """Hrefs that are actually fetchable and mention must_contain.

    Round 1 took the first regex match and got
    `javascript:__doPostBack(...)`, then pasted a base URL in front of
    it. A string in an href attribute is not a link.
    """
    out = []
    for h in re.findall(r'href="([^"]+)"', html):
        if not (h.startswith("/") or h.startswith("http")):
            continue
        if must_contain.lower() in h.lower():
            out.append(h)
    return list(dict.fromkeys(out))


def absolute(base, href):
    return href if href.startswith("http") else base.rstrip("/") + href


# ---------------------------------------------------------------------
# A.  UPCOMING schedule cards — starters, and how far forward week_of goes
# ---------------------------------------------------------------------
def probe_schedule():
    rule("A. Schedule page — do UPCOMING cards carry a starter?")

    today = date.today()
    # Ask for two windows: the one containing today, and one clearly in
    # the future. Comparing what comes back is how we learn whether the
    # date in the URL is honoured at all.
    for label, want in (("current", today),
                        ("future", today + timedelta(days=14))):
        url = f"https://mykbostats.com/schedule/week_of/{want}"
        r = get(f"{label} week (asked for {want})", url)
        if not r:
            continue
        html = r.text
        games = GAME_A.findall(html)
        dates = sorted({m.group(0) for h, _i in games
                        for m in [re.search(r"\d{8}", h)] if m})
        print(f"    anchors: {len(games)}   dates served: {dates}")
        if not dates:
            continue
        served = f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]}"
        print(f"    -> asked for the week of {want}, got {served} onward."
              f"  HONOURED: {want.isoformat() in [f'{d[:4]}-{d[4:6]}-{d[6:]}' for d in dates] or want.isoformat() <= dates[-1][:4] + '-' + dates[-1][4:6] + '-' + dates[-1][6:]}")

        # THE QUESTION. Split the cards by whether the game has happened.
        iso_today = today.strftime("%Y%m%d")
        past = [(h, i) for h, i in games if (re.search(r"\d{8}", h) or [""])
                and re.search(r"\d{8}", h).group(0) < iso_today]
        future = [(h, i) for h, i in games
                  if re.search(r"\d{8}", h)
                  and re.search(r"\d{8}", h).group(0) >= iso_today]
        for name, group in (("past/today", past), ("upcoming", future)):
            withsp = sum(1 for _h, i in group
                         if "ds-game-team__starter" in i)
            print(f"    {name}: {len(group)} cards, "
                  f"{withsp} carrying ds-game-team__starter")

        # Dump the FIRST UPCOMING card in full. This is the one the
        # parser would have to be written against, and round 1 only
        # showed played ones.
        if future:
            h, inner = future[0]
            print(f"\n    --- first UPCOMING card: {h}")
            print(f"        text: {txt(inner)!r}")
            print(f"        classes: "
                  f"{list(dict.fromkeys(CLASSES.findall(inner)))}")
            names = [txt(n) for n in STARTER_SPAN.findall(inner)]
            print(f"        starter spans found: {names}")
            print("        raw:")
            print(inner.strip()[:2000])
        else:
            print("    NO upcoming cards in this window — cannot answer "
                  "from this fetch.")


# ---------------------------------------------------------------------
# B.  PER-START PITCHER LOGS
# ---------------------------------------------------------------------
def describe(r):
    """Does this page look like it holds a per-start log, and is it
    server-rendered?"""
    if not r:
        return
    html = r.text
    dates = DATEISH.findall(html)
    print(f"    <table>: {html.count('<table')}   "
          f"<tr>: {html.count('<tr')}   "
          f"<script>: {html.count('<script')}   "
          f"json blobs: {html.count('application/json')}")
    print(f"    date-like tokens: {len(dates)}  first few: {dates[:10]}")
    # Word-boundary matching. Round 1 counted bare substrings and got
    # 1,193 hits on "am" from the word "Samsung" (rule 17).
    for kw in ("Opponent", "Game Log", "Date", "IP", "ERA",
               "\uc0c1\ub300", "\ub0a0\uc9dc", "\u5bfe\u6226", "\u767b\u677f"):
        n = len(re.findall(r"\b" + re.escape(kw) + r"\b", html))
        if n:
            print(f"    {kw!r}: {n}")
    print(f"    visible text, first 700: {txt(html)[:700]!r}")


def probe_kbo_player():
    rule("B1. KBO — the player page round 1 pointed at but never fetched")
    base = "https://eng.koreabaseball.com"
    r = get("pitching leaders", f"{base}/Stats/PitchingLeaders.aspx")
    if not r:
        return
    links = real_links(r.text, "playerinfopitcher")
    print(f"  real player-detail links: {len(links)}")
    for u in links[:5]:
        print(f"     {u}")
    if not links:
        print("  none — the English leaderboard stopped linking players.")
        return
    describe(get("player summary", absolute(base, links[0])))

    # ROUND 2 FOUND THE TAB. The player page links
    # /Teams/PlayerInfoPitcher/GameLogs.aspx?pcode=..., which is the
    # per-start log pitcher-vs-team H2H needs and that no leaderboard
    # can give. Fetch it and describe it: many <tr>, many dates and an
    # Opponent column means buildable; few rows and many scripts means
    # it is drawn client-side and the answer is an XHR endpoint.
    tab = ("/Teams/PlayerInfoPitcher/GameLogs.aspx?pcode="
           + links[0].split("pcode=")[-1])
    print(f"  game-log tab: {tab}")
    if not tab:
        return
    rlog = get("GAME LOGS", absolute(base, tab))
    describe(rlog)
    if not rlog:
        return

    # ROUND 3 CONFIRMED THE PAGE, AND LEFT ONE THING UNANSWERED.
    # 4 tables, 23 <tr>, 23 IP and 23 ERA, dates 04.02 / 04.08 / 04.14,
    # 0 json blobs — a server-rendered per-start log, one row per
    # appearance. But 'Opponent' matched ZERO times, and a game log
    # without an opponent column is useless for pitcher-vs-team H2H:
    # it would give per-start lines with nothing to group them by.
    #
    # So stop guessing at the header's spelling and PRINT IT. The
    # leaderboards are already read with pd.read_html, so if that works
    # here the build is a small extension of code that exists rather
    # than a new parser.
    try:
        import pandas as pd
        tables = pd.read_html(rlog.text)
        print(f"    pd.read_html parsed {len(tables)} tables")
        for n, t in enumerate(tables):
            print(f"    --- table {n}: {t.shape[0]} rows x {t.shape[1]} cols")
            print(f"        columns: {list(t.columns)}")
            if t.shape[0]:
                print(f"        first row: {t.iloc[0].tolist()}")
                if t.shape[0] > 1:
                    print(f"        last row:  {t.iloc[-1].tolist()}")
    except Exception as exc:
        print(f"    pd.read_html FAILED: {type(exc).__name__}: {exc}")
        print("    -> the log is a real table to the eye but not to pandas;"
              " that is a parser decision, not a source problem.")


def probe_npb_player():
    rule("B2. NPB — find a player page at all")
    # The English leaderboard links only /bis/eng/players/ (an index
    # stub, 218 chars). Try the index itself and the Japanese
    # leaderboard, which is the one the pipeline already parses for
    # names and is likelier to link players.
    r = get("player index", "https://npb.jp/bis/eng/players/")
    if r:
        links = real_links(r.text, "players")
        print(f"  links on the index: {links[:8]}")

    r2 = get("JP pitching leaders",
             f"https://npb.jp/bis/{SEASON_YEAR}/stats/pit_c.html")
    if r2:
        links = real_links(r2.text, "players")
        print(f"  player links on the JP leaderboard: {len(links)}")
        for u in links[:5]:
            print(f"     {u}")
        if links:
            describe(get("JP player page", absolute("https://npb.jp",
                                                    links[0])))
        else:
            print("  NONE. Both leaderboards are plain text names, so no")
            print("  per-start log is reachable from anything we fetch —")
            print("  that answers B for NPB unless a new source appears.")


def main():
    print("=" * 70)
    print("intl_v2_probe round 2 — upcoming starters + per-start logs")
    print("Reports only. Writes nothing, commits nothing, deploys nothing.")
    print("=" * 70)
    probe_schedule()
    probe_kbo_player()
    probe_npb_player()
    rule("Done. Send the whole log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
