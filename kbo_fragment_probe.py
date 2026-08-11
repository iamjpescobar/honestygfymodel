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
# ROUND 4: THE IDS ARE HTML ATTRIBUTES, NOT SCRIPT VALUES.
#
# Round 3 printed the source instead of a count, and the source answered
# it outright:
#
#   var seasonId = li.attr("season");  var gameSc  = li.attr("game_sc");
#   var gameId   = li.attr("g_id");    var awayTeam = li.attr("away_id");
#   var homeTeam = li.attr("home_id");
#
# The page carries `var gameId = "";` — EMPTY — and fills it from the
# clicked `<li>` in `.game-list-n`, or from a `gameId` URL parameter.
# So no regex over script values could ever have found one: there are
# none in the script. They are markup attributes, and they are not
# `data-` prefixed either, which is why the data-attr sweep missed them
# too. Both round-2 and round-3 guesses were looking in the wrong place,
# not for the wrong shape.
#
# This no longer guesses ANY attribute name. It captures the whole
# opening <li> tag from the game list and prints it verbatim, so every
# attribute the page carries is visible — including leId/srId, which are
# still unaccounted for and may or may not live there.
GAME_LI = re.compile(r"<li\b[^>]*\bg_id\s*=\s*[\"'][^\"']+[\"'][^>]*>", re.I)
ATTR = re.compile(r"""([a-zA-Z_][\w:-]*)\s*=\s*["']([^"']*)["']""")

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
    blocks = re.findall(r"S2iAjax\w*\s*\(\s*\{.{0,400}?\}\s*\)", scripts, re.S)
    for b in blocks[:6]:
        print("   " + re.sub(r"\s+", " ", b)[:360])
    if not blocks:
        print("   NONE — the script changed shape since run 85313739682.")
        print("   Do NOT guess field names. Dump the script and read it.")

    # ---- 2. THE GAME LIST, VERBATIM -------------------------------
    print("-" * 72)
    tags = GAME_LI.findall(html)
    print(f"GAME LIST <li> TAGS carrying g_id: {len(tags)}")
    games = []
    for t in tags:
        a = dict(ATTR.findall(t))
        games.append(a)
    # Print the FULL opening tag of the first few. Every attribute the
    # page carries is visible here — including any this probe does not
    # know it needs. leId and srId are still unaccounted for and may be
    # among them; reading beats guessing, which is the whole lesson of
    # rounds 2 and 3.
    for t in tags[:4]:
        print("   " + re.sub(r"\s+", " ", t)[:300])
    if games:
        keys = sorted({k for g in games for k in g})
        print(f"   attributes present: {', '.join(keys)}")

    if not games:
        # ROUND 5: THE PAGE IS A STATIC SHELL. Measured, not inferred —
        # main page: 200 57178b on FIVE runs spanning 11:21 to 19:26 KST,
        # byte-identical every time. A live game centre whose size never
        # moves by one byte is not rendering games; it is a frame that
        # fetches everything after load. The <li> elements the script
        # reads g_id from are built by a call this probe has not found,
        # because it only ever extracted S2iAjaxHtml blocks and the game
        # list is filled by something else.
        #
        # So stop narrowing and dump EVERY call and EVERY path in the
        # script. One of them builds .game-list-n, and reading is what
        # has broken every previous deadlock here.
        print("   NONE — and the page has been 57178b on every run from "
              "11:21 to 19:26 KST, byte-identical. This is a SHELL: the "
              "game list is fetched after load, so no selector over this "
              "HTML will ever find it.")
        print("-" * 72)
        print("EVERY AJAX-SHAPED CALL IN THE SCRIPT (not just S2iAjaxHtml):")
        seen = set()
        for m in re.finditer(
                r"(\$\.(?:ajax|post|get|getJSON)|\.load|S2iAjax\w*)\s*\(.{0,260}",
                scripts, re.S):
            frag = re.sub(r"\s+", " ", m.group(0)).strip()
            if frag[:120] in seen:
                continue
            seen.add(frag[:120])
            print(f"   {frag[:250]}")
            if len(seen) >= 18:
                break
        print("-" * 72)
        print("EVERY QUOTED PATH IN THE SCRIPT:")
        paths = sorted({p for p in re.findall(r"""["'](/[A-Za-z0-9_./-]{4,80})["']""",
                                              scripts)})
        for pth in paths[:40]:
            print(f"   {pth}")
        print("-" * 72)
        print("FIND THE ONE THAT BUILDS .game-list-n. It is the call that "
              "has to come first — StartPitcher cannot be reached without "
              "a g_id, and the g_id only exists once that list is drawn. "
              "Do NOT guess which path it is; the list above is the whole "
              "set the page itself uses.")
        return 1

    # game_sc is the state code. The page's own switch:
    #   1 -> setPreview  (scheduled; the ONLY state with starters to
    #        preview, which is what this endpoint serves)
    #   2, 5 -> setLive     3 -> setReview
    # Preferring a "1" is not a guess — it is the page's own branch.
    prev = [g for g in games if g.get("game_sc") == "1"]
    pick = (prev or games)[0]
    if not prev:
        print("   NO game_sc==1 (preview) GAMES. Every game today is live "
              "or final, so StartPitcher may legitimately return nothing. "
              "That is a timing result, not a dead endpoint — re-run "
              "earlier in the KST day before concluding.")
    print(f"   using g_id={pick.get('g_id')} "
          f"season={pick.get('season')} game_sc={pick.get('game_sc')} "
          f"away={pick.get('away_id')} home={pick.get('home_id')}")

    # ---- 3. CALL IT, BOTH WAYS ---------------------------------------
    #
    # GET and POST, because which one it wants is unknown and a 405 from
    # the wrong verb is indistinguishable from a dead route. Field names
    # come from setPreview's signature; if the block above shows
    # different ones, THAT is the answer and this attempt is only a
    # first guess — which is why it is labelled as one.
    url = f"{BASE}/Schedule/GameCenter/Preview/StartPitcher.aspx"

    # EVERY VALUE HERE COMES FROM THE PAGE, NOT FROM ME.
    #
    # Field names: the `param` block round 2 printed verbatim.
    # Values: the <li> attributes round 3's excerpts named —
    #   gameId <- g_id, seasonId <- season,
    #   awayTeam <- away_id, homeTeam <- home_id.
    #
    # leId and srId are the two the page has not shown a source for. If
    # they appear in the attribute list above, THAT is where they come
    # from and this should use them; the fallbacks below are the only
    # remaining assumption in this probe and are labelled as such.
    #
    # awayPit/homePit go EMPTY on purpose: setPreview checks
    # `if (awayPit == undefined)` before firing this call, which reads as
    # "this endpoint RESOLVES the starters" rather than "you pass them
    # in". If that is wrong the response will say so.
    params = {
        "leId": pick.get("le_id", "1"),      # ASSUMED if absent above
        "srId": pick.get("sr_id", "0"),      # ASSUMED if absent above
        "seasonId": pick.get("season", ""),
        "gameId": pick.get("g_id", ""),
        "awayTeam": pick.get("away_id", ""),
        "homeTeam": pick.get("home_id", ""),
        "awayPit": "", "homePit": "",
    }
    print("-" * 72)
    print(f"CALLING {url}")
    print(f"  params: {params}")
    if "le_id" not in pick or "sr_id" not in pick:
        print("  NOTE: leId/srId were not attributes on the <li> — the two "
              "values above are the only assumption left in this probe. If "
              "the call fails, they are the first suspects.")

    for verb in ("GET", "POST"):
        try:
            fn = requests.get if verb == "GET" else requests.post
            key = "params" if verb == "GET" else "data"
            resp = fn(url, headers=UA, timeout=25, **{key: params})
            body = resp.text or ""
            print(f"  {verb:4} -> {resp.status_code} | {len(body)}b | "
                  f"'선발' x{body.count('선발')}")
            if resp.status_code == 200 and body.strip():
                print("  ---- RAW FRAGMENT, first 1500 chars, UNPARSED ----")
                print(body[:1500])
                print("  ---- TEXT ONLY, first 500 chars ----")
                print("  " + _clean(body)[:500])
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
