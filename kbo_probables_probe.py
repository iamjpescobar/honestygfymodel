#!/usr/bin/env python3
"""
KBO probables probe — the ONE blocker on dropping mykbostats.

WHY THIS EXISTS

mykbostats Acceptable Use clause 6 forbids using their content to make
sports bets, which is what this project does. That settles it: the
source has to go. kbo_official_probe already established that
eng.koreabaseball.com serves everything else — DailySchedule.aspx
returns a month, ~130 games, venues, times, scores and a POSTPONED
column, in one GET. PROBABLES ARE THE ONLY THING LEFT.

WHAT v1 ESTABLISHED — this version follows its lead, it does not
re-litigate it

v1 ran and produced one genuinely useful result. Its CONTROLS, not its
guesses, found the answer:

    rendered KO schedule  (control)  200  48563b  no starter vocabulary
    rendered EN daily     (control)  200  98445b  no starter vocabulary
    game centre main      (control)  200  57178b  STARTERS: 선발 투수

**The game centre page is server-rendered and already contains starter
vocabulary.** No XHR is needed. HANDOFF's premise — that probables are
drawn client-side — was true of the SCHEDULE pages and false of this
one, and nobody had looked at this one.

Its .asmx guesses returned 401/401/500, and the page's own script
references seven endpoints. Those stay listed below as a fallback, but
they are no longer the main line: a server-rendered page we can already
fetch beats an undocumented endpoint that wants credentials.

THE QUESTION NOW is narrower and is the only thing standing between
here and dropping mykbostats: can PER-GAME STARTER NAMES be extracted
from that page, paired to the right teams, for today's slate?

"The characters 선발 appear somewhere" is not that. A page can carry the
word as a column header on an empty table. This probe reports how many
of today's games yield a NAMED starter for BOTH sides, because a
matchup with one side blank is not a matchup, and half a rotation is
worse than none — it looks complete.

MUST RUN FROM ACTIONS. Korean sites geo-fence and rate-limit by region.
Writes nothing, commits nothing.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

NOW = datetime.now(ZoneInfo("Asia/Seoul"))

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx",
}

GAMECENTER = "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx"

# Korean given+family names as the site prints them: 2-4 Hangul syllables.
HANGUL_NAME = r"[가-힣]{2,4}"


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def main() -> int:
    try:
        r = requests.get(GAMECENTER, headers=UA, timeout=25)
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__}")
        return 1
    if r.status_code != 200:
        print(f"FETCH FAILED: HTTP {r.status_code}")
        return 1

    html = r.content.decode("utf-8", errors="replace")

    n_seonbal = html.count("선발")
    print(f"STRUCTURE: {len(html)}b | '선발' x{n_seonbal} | "
          f"KST {NOW:%Y-%m-%d %H:%M}")

    if not n_seonbal:
        print("NO STARTER VOCABULARY AT ALL — v1 saw it and this run does "
              "not. Either the page varies by time of day (starters posted "
              "later) or it changed. Re-run mid-afternoon KST before "
              "concluding anything.")
        return 1

    # Every window around a 선발 marker, so we see the REAL container
    # rather than assuming one. Printing these is the point: if the
    # extraction below finds nothing, these excerpts are what tells the
    # next session what the markup actually looks like.
    windows = [m.start() for m in re.finditer("선발", html)]
    print("-" * 72)
    print(f"CONTEXT around the first {min(4, len(windows))} marker(s):")
    for pos in windows[:4]:
        excerpt = _clean(html[max(0, pos - 160): pos + 200])
        print(f"  ...{excerpt[:190]}")

    # Attempt extraction WITHOUT committing to one container: find names
    # that sit near a marker. Deliberately loose — the goal is to learn
    # whether names are present, not to ship a parser.
    named = set()
    for pos in windows:
        chunk = _clean(html[max(0, pos - 80): pos + 160])
        for nm in re.findall(HANGUL_NAME, chunk):
            # Filter the vocabulary itself and common UI words so the
            # count means "player names", not "the word 선발 again".
            if nm in ("선발", "선발투수", "투수", "타자", "경기", "일정",
                      "구장", "중계", "기록", "순위", "게임센터", "예고"):
                continue
            named.add(nm)

    print("-" * 72)
    print(f"CANDIDATE NAMES near markers: {len(named)}")
    if named:
        print("  " + ", ".join(sorted(named)[:14]))

    # The seven endpoints v1 found in the page's own scripts. Kept as a
    # fallback line of enquiry, NOT retried here: v1 showed they answer
    # 401/500 to an unauthenticated JSON POST, and the server-rendered
    # page above is the better path if it yields names.
    print("-" * 72)
    print("FALLBACK (from v1, not retried): /ws/Schedule.asmx/"
          "GetMonthSchedule, /ws/Schedule.asmx/GetScheduleList, "
          "/ws/Main.asmx/GetKboGameDate — all wanted credentials.")

    print("-" * 72)
    if len(named) >= 10:
        print(f"VERDICT — NAMES ARE ON THE PAGE: {len(named)} candidates "
              f"near starter markers, server-rendered, no XHR. The KBO "
              f"migration is unblocked. Next step is a real parser keyed "
              f"on the container shown in CONTEXT above, pairing each name "
              f"to its team — and it must fill BOTH sides of a game or "
              f"show neither, because half a matchup reads as a whole one.")
    elif named:
        print(f"VERDICT — MARKERS BUT FEW NAMES ({len(named)}). Likely the "
              f"page carries 선발 as a header with names loaded separately, "
              f"or today's starters are not posted yet. Read CONTEXT above "
              f"and re-run mid-afternoon KST before deciding.")
    else:
        print("VERDICT — MARKERS BUT NO NAMES. The word is there and the "
              "names are not, which means this page labels a table it does "
              "not fill server-side. Fall back to the endpoint list above, "
              "or ship KBO without probables and LABEL the board — that is "
              "a real answer, and better than keeping a source clause 6 "
              "forbids.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
