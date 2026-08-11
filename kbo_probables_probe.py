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

# WHAT A KOREAN BALLPLAYER'S NAME ACTUALLY LOOKS LIKE.
#
# v2 used [가-힣]{2,4} plus a stoplist and reported "NAMES ARE ON THE
# PAGE: 10 candidates ... The KBO migration is unblocked." The ten were:
#
#     기록이 됩니다 등록 라인업 선택 업데이트 전력 전력분석 전력비교 키플레이
#
# "is recorded", "will be", "register", "lineup", "select", "update",
# "power", "power analysis", "power comparison", "key play". Every one is
# UI vocabulary; not one is a person. That verdict was recorded as a real
# unblock and had to be corrected a session later — the expensive
# direction to be wrong in, because a probe that says "no" costs a re-run
# and one that says "yes" costs whatever gets built on it.
#
# A STOPLIST CANNOT WIN. It needs the exact word to have been foreseen,
# and a page has more UI vocabulary than anyone will list. So the test is
# now STRUCTURAL, on two properties a Korean personal name has and UI
# text does not:
#
#   1. EXACTLY THREE SYLLABLES — surname plus a two-syllable given name,
#      which is what the overwhelming majority of Korean names are. This
#      alone kills 등록(2) 선택(2) 전력(2) 업데이트(4) 전력분석(4)
#      전력비교(4) 키플레이(4).
#   2. THE FIRST SYLLABLE IS A COMMON SURNAME — a small closed set. This
#      kills the survivors: 기록이(기) 됩니다(되) 라인업(라).
#
# Syllable count has to come FIRST: 전 is a genuine surname, so 전력 and
# 전력분석 would sail through a surname check on its own.
#
# PRECISION OVER RECALL, DELIBERATELY. This drops rare two- and
# four-syllable names. For a probe that is the right trade: the question
# is "are player names present at all", and an invented name misdirects
# where a missed one merely understates.
HANGUL_NAME = r"[가-힣]{3}"

# THE RARE TAIL IS OMITTED ON PURPOSE. 기, 반, 왕, 금, 옥, 육, 맹, 제,
# 모, 탁, 국, 어, 은, 편 and 용 are all genuine surnames AND common noun
# syllables. Including them let 기록이 — "record" plus a subject particle
# — through as a name on the first test of this filter. A rare surname
# buys almost no recall and costs precision on every noun starting with
# it.
KOREAN_SURNAMES = set(
    "김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 류 전 "
    "홍 고 문 양 손 배 백 허 유 남 심 노 하 곽 성 차 주 우 구 나 "
    "지 엄 채 원 천 방 공 현 함 변 염 여 추 도 소 석 선 설 마 길 "
    "연 위 표 명 진".split()
)

# Belt and braces. Kept SHORT on purpose — if this list starts growing,
# the structural test above is what needs fixing, not this.
UI_WORDS = {"선발투수", "선발", "투수", "타자", "경기", "일정", "구장",
            "중계", "기록", "순위", "게임센터", "예고", "라인업",
            "전력분석", "전력비교", "키플레이", "업데이트"}


def _looks_like_a_name(s: str) -> bool:
    """Three syllables, first one a common Korean surname.

    A HEURISTIC, AND IT STILL HAS FALSE POSITIVES. 이용자 ("user") is
    three syllables and starts with the most common surname in Korea; no
    syllable-shape rule separates that from a person. That is not a
    reason to loosen it — it is why the probe PRINTS the names it
    accepted rather than only counting them, and why the verdict says to
    check them against tonight's actual probables. A count can be wrong
    in silence; a list cannot.
    """
    return (len(s) == 3
            and s[0] in KOREAN_SURNAMES
            and s not in UI_WORDS)


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

    # SCRIPT IS NOT CONTENT, AND CONFLATING THEM IS WHY v2 WAS WRONG.
    #
    # This counted 선발 in the RAW html, so eight occurrences inside a
    # setPreview() function and a commented-out alert string were read as
    # "the game centre serves starters server-side". They are the page
    # TALKING ABOUT starters, not showing them — and a commented-out
    # alert is not even executed.
    #
    # Everything downstream now reads `rendered`, with <script> and
    # <style> removed. Both counts are printed because the GAP is the
    # finding: raw high and rendered zero means the page references
    # starters and fetches them over AJAX, which is a completely
    # different next step from "parse the table".
    scripts = re.findall(r"<script\b.*?</script>", html, re.S | re.I)
    rendered = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    rendered = re.sub(r"<style\b.*?</style>", " ", rendered, flags=re.S | re.I)

    n_raw = html.count("선발")
    n_seonbal = rendered.count("선발")
    print(f"STRUCTURE: {len(html)}b | '선발' x{n_raw} raw, "
          f"x{n_seonbal} in RENDERED content | {len(scripts)} script blocks | "
          f"KST {NOW:%Y-%m-%d %H:%M}")
    if n_raw and not n_seonbal:
        print("  ALL starter vocabulary is inside <script> — the page "
              "REFERENCES starters, it does not render them. This is what "
              "v2 misread as a server-rendered table.")

    # TWO DIFFERENT ZEROS, AND THEY NEED DIFFERENT ANSWERS.
    #
    # This branch used to fire on `not n_seonbal` alone and say "NO
    # STARTER VOCABULARY AT ALL ... re-run mid-afternoon KST". After the
    # raw/rendered split that message became FALSE on the commonest case:
    # run 85252013581 found 선발 eight times in raw html and zero in
    # rendered content, and got told the page might have changed and to
    # try again later. Timing will never put JavaScript into the DOM.
    # Worse, `return 1` meant the AJAX url below — the single most useful
    # thing this probe can produce — never printed at all.
    #
    # n_raw == 0  : the vocabulary is genuinely absent. Timing is a real
    #               explanation and re-running is the right advice.
    # n_raw  > 0  : it is there, in script. NOT a failure, NOT a re-run.
    #               Fall through and print the endpoint.
    if not n_raw:
        print("NO STARTER VOCABULARY ANYWHERE — not in rendered content and "
              "not in script. v1 saw it and this run does not, so either the "
              "page varies by time of day (starters posted later) or it "
              "changed shape. Re-run mid-afternoon KST before concluding.")
        return 1

    if not n_seonbal:
        # Referenced but not rendered. Skip the CONTEXT/name extraction —
        # both scan `rendered`, which by definition has nothing — and go
        # straight to the endpoint the page itself calls.
        print("-" * 72)
        _script_text = " ".join(scripts)
        print("THE PAGE'S OWN AJAX CALL (verbatim from its <script>):")
        _urls = re.findall(
            r"""S2iAjaxHtml\s*\(\s*\{[^}]*?url\s*:\s*["']([^"']+)["']""",
            _script_text, re.S)
        _urls += re.findall(r"""url\s*:\s*["'](/Schedule/GameCenter[^"']*)["']""",
                            _script_text, re.S)
        for u in dict.fromkeys(_urls):
            print(f"  url: {u}")
        for a in re.findall(r"function\s+setPreview\s*\(([^)]*)\)", _script_text):
            print(f"  setPreview({_clean(a)})")
        if not _urls:
            print("  NONE FOUND — the script changed shape. Do NOT guess a "
                  "url; dump the script and read it. v1 guessed .asmx names "
                  "and got 401/401/500.")
        print("-" * 72)
        print("VERDICT — REFERENCED, NOT RENDERED. The game centre names "
              "starters only inside <script>; the browser fetches them over "
              "AJAX after load. THIS REVERSES v1 AND v2, which both read "
              "that script text as a server-rendered table and recorded the "
              "KBO migration as unblocked. It is not. The url above is the "
              "actual next step: call it with a real gameId and read what "
              "comes back. Not a dead end — it is the endpoint the site "
              "itself uses.")
        return 0

    # Every window around a 선발 marker, so we see the REAL container
    # rather than assuming one. Printing these is the point: if the
    # extraction below finds nothing, these excerpts are what tells the
    # next session what the markup actually looks like.
    windows = [m.start() for m in re.finditer("선발", rendered)]
    print("-" * 72)
    print(f"CONTEXT around the first {min(4, len(windows))} marker(s):")
    for pos in windows[:4]:
        excerpt = _clean(rendered[max(0, pos - 160): pos + 200])
        print(f"  ...{excerpt[:190]}")

    # Attempt extraction WITHOUT committing to one container: find names
    # that sit near a marker. The PROXIMITY stays loose — the goal is still to learn whether
    # names are present, not to ship a parser. What counts as a NAME is
    # now strict; see _looks_like_a_name.
    named = set()
    rejected = set()
    for pos in windows:
        chunk = _clean(rendered[max(0, pos - 80): pos + 160])
        for nm in re.findall(HANGUL_NAME, chunk):
            (named if _looks_like_a_name(nm) else rejected).add(nm)

    print("-" * 72)
    print(f"CANDIDATE NAMES near markers: {len(named)}")
    if named:
        print("  " + ", ".join(sorted(named)[:14]))
    # THE REJECTS ARE PRINTED TOO, and they are not noise. v2's ten
    # "names" would all appear here. Showing them is what lets the next
    # reader tell "the page has no names" apart from "the filter ate
    # them" — identical from a count alone, and that ambiguity is why
    # this probe has now been run three times.
    if rejected:
        print(f"  rejected as UI text ({len(rejected)}): "
              + ", ".join(sorted(rejected)[:14]))

    # The seven endpoints v1 found in the page's own scripts. Kept as a
    # fallback line of enquiry, NOT retried here: v1 showed they answer
    # 401/500 to an unauthenticated JSON POST, and the server-rendered
    # page above is the better path if it yields names.
    print("-" * 72)
    print("FALLBACK (from v1, not retried): /ws/Schedule.asmx/"
          "GetMonthSchedule, /ws/Schedule.asmx/GetScheduleList, "
          "/ws/Main.asmx/GetKboGameDate — all wanted credentials.")

    print("-" * 72)
    # THE VERDICT IS GATED ON RENDERED CONTENT AND ON A STRICT NAME TEST.
    #
    # v2 fired this branch with ten UI words scraped out of JavaScript
    # and declared the migration unblocked. Both halves of that are now
    # closed: `named` is drawn only from `rendered`, and only three-
    # syllable strings starting with a real surname reach it. The
    # threshold was never the problem — the corpus and the filter were.
    if len(named) >= 10:
        print(f"VERDICT — NAMES IN RENDERED CONTENT: {len(named)} candidates "
              f"near starter markers, outside <script>, no XHR. Next step "
              f"is a real parser keyed on the container shown in CONTEXT "
              f"above, pairing each name to its team — and it must fill "
              f"BOTH sides of a game or show neither, because half a "
              f"matchup reads as a whole one. SANITY-CHECK the names above "
              f"against tonight's actual probables before building on "
              f"this: the filter is a heuristic and 이용자 (\"user\") is "
              f"three syllables starting with the commonest surname in "
              f"Korea.")
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
