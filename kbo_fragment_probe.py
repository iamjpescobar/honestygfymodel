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

# ROUND 3: THE ID FORMAT IS NO LONGER GUESSED.
#
# Round 2 assumed 20260811LGOB0 — date, away code, home code, sequence
# digit — and matched NOTHING in 57KB. `GAME IDS: 0 on the page`. The
# probe stopped rather than calling blind, which was right, but the
# guess was still a guess: the second thing this file got wrong by
# assuming a shape instead of looking at one.
#
# So there are now THREE patterns, from loosest to tightest, and the
# probe reports which ones hit. A pattern that finds nothing is
# information; a single pattern that finds nothing is just a dead end.
GAME_ID_PATTERNS = [
    # What round 2 assumed. Kept so its failure stays visible rather
    # than being quietly replaced — if this one starts matching, the
    # page changed, not our understanding.
    ("round-2 guess (20YYMMDD + 4 letters + digit)",
     re.compile(r"\b(20\d{6}[A-Z]{4}\d)\b")),
    # Same date prefix, ANY trailing run of letters/digits. Catches
    # 3-letter or 5-letter team codes, missing sequence digit, lowercase.
    ("date-prefixed, any suffix",
     re.compile(r"\b(20\d{6}[A-Za-z0-9]{2,8})\b")),
    # Anything assigned to a variable or attribute NAMED gameId. This is
    # the one that cannot be wrong about format, because it keys on the
    # NAME the page itself uses rather than on what the value looks like.
    ("assigned to something called gameId",
     re.compile(r"""gameId["'\s]*[:=]\s*["']([^"']{4,20})["']""", re.I)),
]

# Where a value gets ASSIGNED, so the probe can show the surrounding
# source instead of reporting a count and stopping. Round 2's failure
# was not "no ids" — it was "no ids MATCHING MY GUESS", and those look
# identical from a count alone.
GAME_ID_CONTEXT = re.compile(r".{0,90}gameId.{0,110}", re.I | re.S)

# data-* attributes carrying digits. If the ids live in markup rather
# than script, this is where they are.
DATA_ATTR = re.compile(r"""(data-[a-z-]*(?:game|id|gm)[a-z-]*)\s*=\s*["']([^"']{2,24})["']""", re.I)


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

    # ---- 2. GAME IDS — TRIED THREE WAYS, AND SHOWN EITHER WAY ------
    print("-" * 72)
    ids = []
    for label, pat in GAME_ID_PATTERNS:
        found = list(dict.fromkeys(pat.findall(scripts) + pat.findall(html)))
        print(f"GAME IDS via {label}: {len(found)}")
        if found:
            print("   " + ", ".join(found[:8]))
        ids.extend(found)
    ids = list(dict.fromkeys(ids))

    # data-* attributes, in case the ids live in markup rather than script.
    attrs = list(dict.fromkeys(DATA_ATTR.findall(html)))
    if attrs:
        print(f"data-* attributes that might carry one ({len(attrs)}):")
        for k, v in attrs[:10]:
            print(f"   {k}={v}")

    if not ids:
        # THE POINT OF ROUND 3. Round 2 printed "GAME IDS: 0" and
        # stopped, which is indistinguishable from "this page has no
        # ids" — and it does have them, under a shape nobody had looked
        # at. Show the source instead of reporting a count.
        print("-" * 72)
        print("NO IDS MATCHED ANY PATTERN. Not a dead end — a shape nobody "
              "has seen. Every mention of `gameId` in the page's own "
              "script, verbatim, so the next round keys on what is "
              "actually there:")
        seen = set()
        for m in GAME_ID_CONTEXT.finditer(scripts):
            frag = re.sub(r"\s+", " ", m.group(0)).strip()
            if frag in seen:
                continue
            seen.add(frag)
            print(f"   ...{frag}...")
            if len(seen) >= 12:
                break
        if not seen:
            print("   `gameId` does not appear in the script at all. It is "
                  "supplied by a fetch that happens BEFORE this one — find "
                  "that call rather than this value.")
        print("-" * 72)
        print("READ THE EXCERPTS, DO NOT GUESS A FORMAT. That is twice now: "
              "round 2 assumed 20260811LGOB0 and matched nothing, and the "
              "count alone could not tell 'wrong guess' from 'no ids'.")
        return 1

    todays = [g for g in ids if g.startswith(today.strftime("%Y%m%d"))]
    target = (todays or ids)[0]
    stale = "" if todays else " (NOT today's — a stale id may 200 with an empty body)"
    print(f"   using {target}{stale}")

    # ---- 3. CALL IT, BOTH WAYS ---------------------------------------
    #
    # GET and POST, because which one it wants is unknown and a 405 from
    # the wrong verb is indistinguishable from a dead route. Field names
    # come from setPreview's signature; if the block above shows
    # different ones, THAT is the answer and this attempt is only a
    # first guess — which is why it is labelled as one.
    url = f"{BASE}/Schedule/GameCenter/Preview/StartPitcher.aspx"

    # THE FIELD NAMES ARE NO LONGER A GUESS. Round 2 printed the page's
    # own call block verbatim:
    #
    #   S2iAjaxHtml({ url: ".../Preview/StartPitcher.aspx",
    #     param: { leId, srId, seasonId, awayTeam, homeTeam,
    #              awayPit, homePit, gameId }, async: false })
    #
    # EIGHT fields, not the four round 2 sent — awayTeam, homeTeam,
    # awayPit and homePit were missing. Note the key is `param`, which
    # is the S2i wrapper's own name for the payload; over the wire these
    # become ordinary query/form fields.
    #
    # awayPit/homePit are sent EMPTY on purpose. setPreview's own code
    # checks `if (awayPit == undefined)` before firing this call, which
    # says the endpoint is what RESOLVES the starters rather than
    # something you pass them to. If that reading is wrong the response
    # will say so, and an empty string is the honest way to ask.
    params = {
        "leId": "1", "srId": "0", "seasonId": target[:4],
        "gameId": target,
        "awayTeam": "", "homeTeam": "", "awayPit": "", "homePit": "",
    }
    print("-" * 72)
    print(f"CALLING {url}")
    print(f"  params (from the page's OWN param block, not guessed): {params}")

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
