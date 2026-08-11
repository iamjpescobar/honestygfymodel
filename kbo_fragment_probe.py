"""
Call the KBO endpoint the game centre calls, and DUMP WHAT COMES BACK.

WHERE THIS CAME FROM
--------------------
Run 85313739682, once kbo_probables_probe finally separated script from
rendered content:

    '선발' x8 raw, x0 in RENDERED content | 19 script blocks
    url: /Schedule/GameCenter/Preview/StartPitcher.aspx
    setPreview(section, leId, srId, seasonId, gameId, awayTeam, homeTeam,
               awayPit, homePit)

Three earlier rounds recorded the game centre as "server-rendered, KBO
unblocked". It never was. The page NAMES starters inside JavaScript and
fetches them over AJAX after load. This probe calls that fetch.

WHY IT DUMPS INSTEAD OF PARSING
--------------------------------
`S2iAjaxHtml` injects markup, so the response is an HTML FRAGMENT, not
JSON — and nobody has seen one. Every wrong answer in this whole
sequence came from a probe that INVENTED the structure it parsed:

    v1 npb_void_probe  split on <div class="date"> — does not exist.
                       Found zero rows and reported a verdict it never
                       measured.
    v1 kbo             guessed three .asmx names -> 401/401/500.
    v2 kbo             matched [가-힣]{2,4} near a marker and returned
                       ten Korean UI words as "names".

So this parses NOTHING. It prints the raw fragment and lets a human
decide what the container is. A parser comes in the NEXT round, keyed on
markup somebody has actually looked at.

THE PARAMETER NAMES ARE ALSO UNKNOWN, AND ARE NOT GUESSED
----------------------------------------------------------
`setPreview` names nine values but the AJAX `data:` block is what maps
them to POST fields. This probe prints that block VERBATIM before
attempting any call, because a 500 from wrong field names looks exactly
like a 500 from a dead endpoint, and last time that ambiguity was read
as "no endpoint found".

If the call fails, the printed block is still the useful output.
"""
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BASE = "https://www.koreabaseball.com"
MAIN = f"{BASE}/Schedule/GameCenter/Main.aspx"
KST = ZoneInfo("Asia/Seoul")

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    # The fragment endpoints are called by the page's own JS, so they may
    # check these. Sent because their ABSENCE would be a plausible reason
    # for a 403 and we would not be able to tell it from a dead endpoint.
    "X-Requested-With": "XMLHttpRequest",
    "Referer": MAIN,
}

# KBO game ids look like 20260811LGOB0 — date, away code, home code, and a
# sequence digit for doubleheaders. Matched loosely rather than assumed:
# if the shape is different, the count below says so instead of the probe
# silently finding none.
GAME_ID = re.compile(r"\b(20\d{6}[A-Z]{4}\d)\b")


def _clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def main() -> int:
    today = datetime.now(KST)
    print(f"KST {today:%Y-%m-%d %H:%M}")

    try:
        r = requests.get(MAIN, headers=UA, timeout=25)
        print(f"main page: {r.status_code} {len(r.text)}b")
        if r.status_code != 200:
            print("Cannot read the game centre at all — nothing else here "
                  "will mean anything. Stop and check the site by hand.")
            return 1
        html = r.text
    except Exception as exc:
        print(f"main page FAILED: {type(exc).__name__}: {exc}")
        return 1

    scripts = " ".join(re.findall(r"<script\b.*?</script>", html, re.S | re.I))

    # ---- 1. THE CALL BLOCK, VERBATIM. The most valuable output here. --
    print("-" * 72)
    print("S2iAjaxHtml CALL BLOCKS (verbatim — this is what maps setPreview's")
    print("nine arguments onto POST fields, and it is currently unknown):")
    blocks = re.findall(r"S2iAjaxHtml\s*\(\s*\{.{0,400}?\}\s*\)", scripts, re.S)
    for b in blocks[:6]:
        print("   " + re.sub(r"\s+", " ", b)[:360])
    if not blocks:
        print("   NONE — the script changed shape since run 85313739682.")
        print("   Do NOT guess field names. Dump the script and read it.")

    # ---- 2. GAME IDS ------------------------------------------------
    ids = list(dict.fromkeys(GAME_ID.findall(scripts) or GAME_ID.findall(html)))
    todays = [g for g in ids if g.startswith(today.strftime("%Y%m%d"))]
    print("-" * 72)
    print(f"GAME IDS: {len(ids)} on the page, {len(todays)} dated today")
    if ids:
        print("   " + ", ".join(ids[:8]))
    if not ids:
        print("   NONE MATCHED. Either the id format differs from "
              "YYYYMMDDAAAH0 or they arrive in a later fetch. Print a "
              "script excerpt and look before assuming the endpoint is "
              "unreachable — that mistake has been made three times here.")
        return 1

    target = (todays or ids)[0]
    stale = " (NOT today's — a stale id may 200 with an empty body)" if not todays else ""
    print(f"   using {target}{stale}")

    # ---- 3. CALL IT, BOTH WAYS ---------------------------------------
    #
    # GET and POST, because which one it wants is unknown and a 405 from
    # the wrong verb is indistinguishable from a dead route. Field names
    # come from setPreview's signature; if the block above shows
    # different ones, THAT is the answer and this attempt is only a
    # first guess — which is why it is labelled as one.
    url = f"{BASE}/Schedule/GameCenter/Preview/StartPitcher.aspx"
    params = {"gameId": target, "leId": "1", "srId": "0",
              "seasonId": target[:4]}
    print("-" * 72)
    print(f"CALLING {url}")
    print(f"  params (FIRST GUESS from setPreview's signature): {params}")

    for verb in ("GET", "POST"):
        try:
            fn = requests.get if verb == "GET" else requests.post
            key = "params" if verb == "GET" else "data"
            resp = fn(url, headers=UA, timeout=25, **{key: params})
            body = resp.text or ""
            print(f"  {verb:4} -> {resp.status_code} | {len(body)}b | "
                  f"'선발' x{body.count('선발')}")
            if resp.status_code == 200 and body.strip():
                print("  ---- RAW FRAGMENT, first 1200 chars, UNPARSED ----")
                print(body[:1200])
                print("  ---- TEXT ONLY, first 400 chars ----")
                print("  " + _clean(body)[:400])
        except Exception as exc:
            print(f"  {verb:4} -> FAILED {type(exc).__name__}: {exc}")

    print("-" * 72)
    print("READ THE RAW FRAGMENT ABOVE, NOT A VERDICT. This probe reaches no "
          "conclusion on purpose: every wrong answer in this sequence came "
          "from code that invented the structure it parsed. If names are in "
          "there, the NEXT round writes a parser keyed on the container you "
          "can see. If the body is empty or an error page, the params are "
          "wrong and the CALL BLOCKS section above is where the right ones "
          "are.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
