#!/usr/bin/env python3
"""
KBO probables probe — the ONE blocker on dropping mykbostats.

WHY THIS EXISTS

mykbostats Acceptable Use clause 6 forbids using their content to make
sports bets, which is what this project does. That settles the question:
the source has to go, not because it broke but because we should not be
using it. kbo_official_probe already established that
eng.koreabaseball.com serves everything else we need —
DailySchedule.aspx returns a whole month, ~130 games, with venues,
times, scores and a POSTPONED column, in one GET.

PROBABLES ARE THE ONLY THING LEFT. The rendered Korean schedule page
serves ZERO occurrences of 선발 / 투수 / 예고: the starters are drawn
client-side, so they arrive over an XHR the page makes after load. If
that endpoint can be called directly, the migration is unblocked and
mykbostats can be dropped whole. If it cannot, the honest options are to
ship KBO without probables and SAY SO on the board, or to keep a source
we have decided we should not keep — and that is a decision to make with
the answer in hand, not before.

WHAT IT DOES

Tries the candidate endpoints the KBO site's own game centre uses, plus
the rendered pages as controls, and reports for each: status, size, and
whether starter vocabulary appears. Writes nothing, commits nothing.

THE CANDIDATES ARE GUESSES AND ARE LABELLED AS SUCH. ASP.NET sites of
this vintage expose .asmx web methods that take JSON and return an HTML
fragment; the names below are the conventional ones for this site's
schedule module. A 404 on all of them is not proof that no endpoint
exists — it means the guesses were wrong and the next step is reading
the page's own scripts, which is why the last check prints any
.asmx/.ashx/ajax URL the schedule page itself references. THAT LIST is
the real output if the guesses miss.

MUST RUN FROM ACTIONS. Korean sites geo-fence and rate-limit by region;
a result from a laptop or a Codespace predicts nothing about what the
nightly or Render would see. Run it locally to smoke-test the script,
believe it only from Actions.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

NOW = datetime.now(ZoneInfo("Asia/Seoul"))
SEASON = NOW.year

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.koreabaseball.com/Schedule/Schedule.aspx",
}

# Starter vocabulary. Checked as a SET rather than one word because the
# site could label the column any of these ways and a miss on the exact
# noun we happened to pick would read as "no probables here".
#   선발 starter   투수 pitcher   예고 announced/advance   선발투수
STARTER_WORDS = ["선발", "투수", "예고", "先発"]

# (label, method, url, json payload or None)
CANDIDATES = [
    ("rendered KO schedule  (control)", "GET",
     "https://www.koreabaseball.com/Schedule/Schedule.aspx", None),
    ("rendered EN daily     (control)", "GET",
     "https://eng.koreabaseball.com/Schedule/DailySchedule.aspx", None),
    ("game centre main      (control)", "GET",
     "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx", None),

    # --- guesses, per the docstring ---
    ("asmx GetScheduleList", "POST",
     "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList",
     {"leId": "1", "srIdList": "0,9,6", "seasonId": str(SEASON),
      "gameMonth": f"{NOW.month:02d}"}),
    ("asmx GetGameList", "POST",
     "https://www.koreabaseball.com/ws/Schedule.asmx/GetGameList",
     {"leId": "1", "srId": "0", "gameDate": NOW.strftime("%Y%m%d")}),
    ("asmx GetKboGameList", "POST",
     "https://www.koreabaseball.com/ws/Main.asmx/GetKboGameList",
     {"leId": "1", "srId": "0,9,6", "gameDate": NOW.strftime("%Y%m%d")}),
]


def _hit(body: str):
    """Which starter words appear, if any."""
    return [w for w in STARTER_WORDS if w in body]


def main() -> int:
    any_starters = False

    for label, method, url, payload in CANDIDATES:
        try:
            if method == "GET":
                r = requests.get(url, headers=UA, timeout=25)
            else:
                h = dict(UA)
                h["Content-Type"] = "application/json; charset=UTF-8"
                r = requests.post(url, headers=h, data=json.dumps(payload),
                                  timeout=25)
        except Exception as e:
            print(f"{label:32s} ERROR {type(e).__name__}")
            continue

        body = r.content.decode("utf-8", errors="replace")
        words = _hit(body)
        # A .asmx that answers 200 with an empty d is a working endpoint
        # with the wrong arguments, which is a very different result from
        # a 404 and worth telling apart.
        empty = '"d":null' in body or '"d":""' in body
        note = ""
        if words:
            note = f'STARTERS: {" ".join(words)}'
            if r.status_code == 200 and not label.endswith("(control)"):
                any_starters = True
        elif empty:
            note = "200 but empty payload — endpoint real, args wrong"
        else:
            note = "no starter vocabulary"
        print(f"{label:32s} {r.status_code} {len(body):>7}b  {note}")

    # THE REAL OUTPUT WHEN THE GUESSES MISS. Whatever the schedule page
    # itself calls is the ground truth, and it is in the page's markup.
    print("-" * 64)
    try:
        r = requests.get(
            "https://www.koreabaseball.com/Schedule/Schedule.aspx",
            headers=UA, timeout=25)
        page = r.content.decode("utf-8", errors="replace")
        urls = sorted(set(re.findall(
            r'["\']([^"\']*\.(?:asmx|ashx)/?[A-Za-z]*)["\']', page)))
        if urls:
            print(f"ENDPOINTS THE PAGE ITSELF REFERENCES ({len(urls)}):")
            for u in urls[:12]:
                print(f"  {u}")
        else:
            print("PAGE REFERENCES NO .asmx/.ashx — starters may come from "
                  "an inline script or a different host; read the page by "
                  "hand next")
    except Exception as e:
        print(f"endpoint scan failed: {type(e).__name__}")

    print("-" * 64)
    if any_starters:
        print("VERDICT: a direct endpoint returns starter data — KBO "
              "migration is unblocked, mykbostats can be dropped whole.")
    else:
        print("VERDICT: no direct probables endpoint found from these "
              "candidates. Read the endpoint list above before concluding "
              "none exists. If none does: ship KBO without probables and "
              "label the board, rather than keeping a source clause 6 "
              "forbids.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
