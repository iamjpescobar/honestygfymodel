#!/usr/bin/env python3
"""
NPB void-risk parity probe — does npb.jp publish a FORWARD-LOOKING
cancellation warning of its own?

WHY THIS EXISTS

KBO ships two distinct void signals and NPB ships only one:

  void_reason  WHY a game that was already called off was called off.
               NPB HAS this — npb_precompute reads <div class="cancel">
               with no date gate, which is why NPB never had the bug KBO
               did (rule 21 / kbo_precompute's comment).
  void_risk    A warning on a game that is STILL ON. KBO gets this from
               mykbostats' "Chance of Rainout" text. NPB shows NOTHING,
               and per rule 21 a missing badge is unreadable: the reader
               cannot tell "no rain risk" from "we never looked".

Closing that gap honestly requires knowing whether npb.jp publishes such
a warning AT ALL. It may simply not — Japanese practice is often to call
a game on the day rather than flag risk in advance, and if that is the
answer then the correct fix is a LABEL saying NPB does not publish one,
not an invented badge. Either way the answer has to be measured, not
assumed. This probe measures it and writes nothing.

WHAT IT DOES

Fetches the current month's schedule detail page — the same URL
npb_precompute.fetch_month() already uses, so a failure here is a
failure there too — and, for TODAY AND FUTURE DATES ONLY, prints every
distinct piece of status text attached to a game that is still on. A
past game's "中止" is not a forward-looking warning and is filtered out;
that distinction is the entire question.

HOW TO READ THE RESULT

  RISK TEXT FOUND     npb.jp does publish something forward-looking.
                      The printed strings are the vocabulary to parse.
  NO RISK TEXT        npb.jp publishes nothing forward-looking. Ship a
                      label, not a badge. This is a real answer, not a
                      failed probe.
  FETCH FAILED        the page moved or is blocked from this IP. Says
                      which; do not read it as either answer above.

Run it, do not commit anything based on a guess about what it will say.
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

# Candidate forward-looking vocabulary. Deliberately WIDER than what we
# expect, because the failure mode to avoid is concluding "NPB publishes
# nothing" when it publishes something we did not think to look for.
#   中止    called off        雨天    rain
#   順延    postponed         延期    deferred
#   の可能性 possibility of    見込み  outlook / expected
#   中止の恐れ risk of cancellation
RISK_WORDS = ["中止", "雨天", "順延", "延期", "possibility", "恐れ",
              "見込み", "の可能性", "予備日", "流れ"]


def main() -> int:
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    today = now.strftime("%Y-%m-%d")
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

    # Split into per-day blocks. The page groups games under a date
    # heading; anything before the first heading is chrome.
    #
    # Matching the DATE rather than the row because the forward-looking
    # question is entirely about which side of today a row sits on, and
    # a row carries no date of its own.
    day_blocks = re.split(r'<div class="date"[^>]*>', html)[1:]

    found: dict[str, int] = {}
    future_days = 0

    for block in day_blocks:
        dm = re.match(r"\s*(\d{1,2})月(\d{1,2})日", block)
        if not dm:
            continue
        gdate = f"{now.year}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}"
        if gdate < today:
            continue  # a settled game's status is not a forward warning
        future_days += 1

        # Rows for a still-on game. A row already carrying a score is a
        # finished game inside today's block and is not forward-looking.
        for row in re.split(r"</tr>", block):
            if '<div class="score1">' in row:
                continue
            text = re.sub(r"<[^>]+>", " ", row)
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            for word in RISK_WORDS:
                if word in text:
                    snippet = text[:120]
                    found[snippet] = found.get(snippet, 0) + 1

    if not future_days:
        print(f"FETCH OK but no dated blocks on or after {today} — "
              f"page shape may have changed; check {url} by hand")
        return 1

    if not found:
        print(f"NO RISK TEXT: {future_days} day(s) from {today} onward, "
              f"zero forward-looking warnings. NPB publishes none — "
              f"ship a label, not a badge.")
        return 0

    print(f"RISK TEXT FOUND: {len(found)} distinct string(s) across "
          f"{future_days} day(s) from {today} onward")
    for snippet, count in sorted(found.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  x{count}  {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
