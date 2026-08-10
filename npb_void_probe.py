#!/usr/bin/env python3
"""
NPB void-risk parity probe — does npb.jp publish a FORWARD-LOOKING
cancellation warning of its own?

WHY THIS EXISTS

KBO ships two distinct void signals and NPB ships only one:

  void_reason  WHY a game already called off was called off. NPB HAS
               this — npb_precompute reads <div class="cancel"> with no
               date gate.
  void_risk    A warning on a game that is STILL ON. KBO gets this from
               mykbostats' "Chance of Rainout". NPB shows NOTHING, and
               per rule 21 a missing badge is unreadable: the reader
               cannot tell "no rain risk" from "we never looked".

If npb.jp publishes no such warning, the correct fix is a LABEL saying
so, not an invented badge. That is a real answer and closes the item.

WHY THIS IS THE SECOND VERSION — READ BEFORE WRITING A THIRD

v1 invented its own page structure: it split on `<div class="date">`,
which does not exist on that page. It found zero dated blocks and
reported "no forward-looking warnings" — an answer it had not measured.
**A probe that guesses at markup can manufacture either verdict**, and
the wrong one here would have shipped a label asserting something never
checked.

The real structure was never in doubt. `npb_precompute.parse_games()`
has parsed this exact page in production for months. v2 uses ITS
selectors, verbatim:

    rows      <tr id="dateMMDD">      not a date div
    called    <div class="cancel">    what void_reason already reads
    played    <div class="score1">    a finished game
    starters  <div class="pit">       announced starter cells

Rule: when the pipeline already parses a page, the probe reads it the
same way. A second parser is a second thing to be wrong.

WHAT IT REPORTS

A STRUCTURE line FIRST. If that says zero rows, the page changed and
nothing after it is an answer about NPB — it is an answer about this
script, and the NPB build is probably already broken.

Then, for rows dated today or later in JST on games not yet played:
every distinct piece of risk vocabulary. A past game's 中止 is excluded;
that distinction is the entire question.

MUST RUN FROM ACTIONS. Japanese sites geo-fence and rate-limit by
region. Writes nothing, commits nothing.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# Deliberately WIDER than expected. The failure to avoid is concluding
# "NPB publishes nothing" because we did not think to look for the word
# it actually uses.
#   中止 called off   雨天 rain     順延 postponed   延期 deferred
#   恐れ risk of      見込み outlook 予備日 reserve date  微妙 doubtful
RISK_WORDS = ["中止", "雨天", "順延", "延期", "恐れ", "見込み",
              "予備日", "微妙", "流れ"]

CANCEL_DIV = '<div class="cancel">'
SCORE_DIV = '<div class="score1">'
PIT_DIV = '<div class="pit">'


def main() -> int:
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    today_mmdd = now.strftime("%m%d")
    url = (f"https://npb.jp/games/{now.year}/"
           f"schedule_{now.month:02d}_detail.html")

    try:
        r = requests.get(url, headers=UA, timeout=25)
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__} on {url}")
        return 1
    if r.status_code != 200:
        print(f"FETCH FAILED: HTTP {r.status_code} on {url}")
        return 1

    html = r.content.decode("utf-8", errors="replace")

    # The selector npb_precompute.parse_games() uses in production.
    rows = re.findall(r'<tr id="date(\d{4})"[^>]*>(.*?)</tr>', html, re.S)

    # STRUCTURE FIRST. v1's whole failure was reporting a verdict on a
    # page it had not actually parsed, so this line comes before any
    # conclusion and is the first thing to read.
    print(f"STRUCTURE: {len(rows)} dated rows | "
          f"{html.count(CANCEL_DIV)} cancel | "
          f"{html.count(PIT_DIV)} starter | {len(html)}b | JST {today_mmdd}")

    if not rows:
        print("STRUCTURE IS WRONG — the page no longer matches the selector "
              "npb_precompute uses in production. Fix the PIPELINE first: "
              "this probe cannot answer anything until then, and the NPB "
              "schedule build is probably already broken.")
        return 1

    upcoming = 0
    called_off_ahead = 0
    found: dict[str, int] = {}

    for mmdd, row in rows:
        if mmdd < today_mmdd:
            continue          # settled game — not a forward warning
        if SCORE_DIV in row:
            continue          # already played, inside today's block
        upcoming += 1

        if CANCEL_DIV in row:
            # Called off for a date not yet reached — the one case that
            # IS forward-looking in NPB's own markup.
            called_off_ahead += 1

        text = re.sub(r"<[^>]+>", " ", row)
        text = re.sub(r"\s+", " ", text).strip()
        for word in RISK_WORDS:
            if word in text:
                key = text[:110]
                found[key] = found.get(key, 0) + 1
                break

    print(f"UPCOMING: {upcoming} unplayed row(s) dated {today_mmdd} or later, "
          f"{called_off_ahead} of them already called off")

    if not upcoming:
        print("NO UPCOMING ROWS — the month rolled over or every remaining "
              "game is played. Re-run mid-month. NOT an answer about "
              "void_risk.")
        return 1

    if not found:
        print(f"VERDICT — NO FORWARD-LOOKING WARNING: {upcoming} upcoming "
              f"game(s), zero risk vocabulary. npb.jp publishes no advance "
              f"warning. SHIP A LABEL saying NPB does not publish one — do "
              f"not invent a badge, and do not leave the space blank.")
        return 0

    print(f"VERDICT — RISK TEXT FOUND: {len(found)} distinct string(s). "
          f"This is the vocabulary to parse:")
    for snippet, count in sorted(found.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  x{count}  {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
