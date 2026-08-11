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

    # ---- 2. THE GAME LIST, FROM THE WEB METHOD THAT BUILDS IT -----
    #
    # ROUND 6. Round 5's path sweep found the call rounds 1-4 could not
    # see, because it is a .asmx web method behind $.ajax rather than an
    # S2iAjaxHtml block:
    #
    #   $.ajax({ type: "post", url: "/ws/Main.asmx/GetKboGameList",
    #            dataType: "json",
    #            data: { leId: "1", srId: srId, date: $("#txtGameDate").val() } })
    #
    # THE IRONY IS WORTH RECORDING. v1 of this probe GUESSED .asmx
    # endpoint names, got 401/401/500, and that was written down as "no
    # endpoint found" — which sent four rounds down the HTML path. The
    # .asmx route was right the whole time. v1 guessed the wrong method
    # names, and a wrong guess and a dead route return the same thing.
    # GetKboGameList was sitting in the page's own script for all five
    # runs.
    #
    # .asmx WANTS JSON, NOT FORM FIELDS. A ScriptService method needs
    # Content-Type: application/json with a JSON body, and answers
    # {"d": ...}. Posting form-encoded data is what produces a 500 that
    # looks like a dead endpoint — almost certainly what v1 hit.
    print("-" * 72)
    list_url = f"{BASE}/ws/Main.asmx/GetKboGameList"
    # leId "1" is a LITERAL in the page's own call, not an assumption.
    # srId is a variable there; "0" is this probe's only remaining guess
    # and is labelled as such below.
    payload = {"leId": "1", "srId": "0", "date": today.strftime("%Y%m%d")}
    print(f"CALLING {list_url}")
    print(f"  json body: {payload}   (leId is the page's own literal; "
          f"srId '0' is the one guess left)")

    games, raw = [], ""
    try:
        lr = requests.post(list_url, headers={**UA,
                           "Content-Type": "application/json; charset=UTF-8"},
                           json=payload, timeout=25)
        # DECODE EXPLICITLY, AND STRIP A BOM.
        #
        # Round 6 got 200 with 11461 bytes of perfectly good JSON and
        # then reported "NO GAME ROWS" — because json.loads raised
        # "Unexpected UTF-8 BOM". The endpoint was fine; the probe threw
        # away a working answer over three bytes.
        #
        # utf-8-sig strips the BOM if present and is a no-op if not.
        # Explicit UTF-8 also matters here for a second reason: the
        # payload carries Korean stadium and team names (잠실), and
        # requests guesses ISO-8859-1 when the server omits a charset,
        # which would mangle every one of them while still parsing.
        raw = (lr.content or b"").decode("utf-8-sig", errors="replace")
        print(f"  -> {lr.status_code} | {len(raw)}b")
        if lr.status_code != 200 or not raw.strip():
            print("  ---- BODY, first 800 chars ----")
            print(raw[:800] or "  (empty)")
            print("  A .asmx 500 is usually the CONTENT TYPE or the field "
                  "names, not a dead route — that is what made v1 record "
                  "this whole path as unreachable. Read the fault string.")
        else:
            print("  ---- RAW JSON, first 1200 chars, UNPARSED ----")
            print(raw[:1200])
            # ScriptService wraps everything in "d". Parsed defensively:
            # the shape inside is unknown and is NOT guessed at.
            try:
                import json as _json
                # THE BODY IS SEVERAL CONCATENATED JSON DOCUMENTS.
                #
                # Round 7's own diagnostic found this, and it disproved my
                # guess in the process:
                #
                #   JSONDecodeError: Extra data: line 336 column 2
                #                    (char 8397)      body = 11460 bytes
                #   first 40 bytes: b'{\r\n  "game": [\r\n    {...'
                #
                # NO BOM — the body starts with a plain brace. Round 7
                # "fixed" a BOM because round 6 printed only the exception
                # NAME, and a BOM was a plausible cause I then confirmed
                # in isolation. Plausible and confirmed-in-isolation is
                # not the same as true. What actually found it was
                # printing the full message and the first bytes; the
                # utf-8-sig decode was harmless and beside the point.
                #
                # "Extra data" at char 8397 of 11460 means the first
                # document ENDS there and another begins — the endpoint
                # returns {"game":[...]} followed by at least one more
                # object. json.loads parses exactly one document and
                # refuses the rest, so it threw away a complete answer for
                # the second round running.
                #
                # raw_decode consumes one document at a time and reports
                # where it stopped. Every document is merged, so a payload
                # of one behaves identically and this cannot regress if
                # the endpoint ever returns a single object.
                dec, idx, docs = _json.JSONDecoder(), 0, []
                while idx < len(raw):
                    while idx < len(raw) and raw[idx] in " \r\n\t":
                        idx += 1
                    if idx >= len(raw):
                        break
                    try:
                        obj, idx = dec.raw_decode(raw, idx)
                    except ValueError as _e:
                        # SHOW THE BYTES AT THE FAILURE, NOT AT THE START.
                        #
                        # This is the diagnostic that should have existed
                        # three rounds ago. Every dump in this probe looks
                        # at the BEGINNING of the body — first 40 bytes,
                        # first 1200 chars — and the failure has never once
                        # been at the beginning:
                        #
                        #   round 7: Extra data      char 8397 of 11460
                        #   round 8: Expecting value char 8399 of 11462
                        #
                        # Both are ~8kb in, outside every window I printed,
                        # so both rounds theorised about a cause nobody had
                        # looked at. Round 8 "fixed" concatenated documents
                        # on the strength of an error message; the message
                        # moved and the fix did not hold.
                        #
                        # A window around the offset ends that: whatever is
                        # at 8399 will be visible, in repr, and can be read
                        # instead of guessed.
                        _pos = getattr(_e, "pos", idx)
                        _lo, _hi = max(0, _pos - 250), min(len(raw), _pos + 350)
                        print(f"  raw_decode stopped at char {_pos} of "
                              f"{len(raw)} after {len(docs)} document(s): {_e}")
                        print(f"  ---- BYTES {_lo}..{_hi}, AROUND THE "
                              f"FAILURE (repr) ----")
                        print("  " + repr(raw[_lo:_pos]))
                        print("  >>> FAILS HERE >>>")
                        print("  " + repr(raw[_pos:_hi]))
                        print(f"  ---- LAST 200 CHARS OF THE BODY ----")
                        print("  " + repr(raw[-200:]))
                        break
                    docs.append(obj)
                print(f"  {len(docs)} JSON document(s) in the body: "
                      f"{[list(o)[:4] if isinstance(o, dict) else type(o).__name__ for o in docs]}")

                merged = {}
                for o in docs:
                    if isinstance(o, dict):
                        merged.update(o)
                # "d" is still honoured in case a ScriptService wrapper
                # appears on a different method; this one does not use it.
                inner = merged.get("d", merged)
                if isinstance(inner, str):
                    inner = _json.loads(inner)
                rows = inner.get("game", inner) if isinstance(inner, dict) else inner
                if isinstance(rows, list):
                    games = [r for r in rows if isinstance(r, dict)]
                    print(f"  parsed {len(games)} game row(s)")
                    if games:
                        print(f"  keys on the first row: "
                              f"{', '.join(sorted(games[0])[:24])}")
                        print(f"  other top-level keys: "
                              f"{[k for k in merged if k != 'game']}")
            except Exception as exc:
                # SHOW THE BYTES, not just the exception name. Round 6
                # printed "could not parse as JSON (JSONDecodeError)" over
                # a body that was valid — the failure was a BOM, and the
                # exception name alone could not say that. The first bytes
                # as a repr would have named it immediately.
                print(f"  could not parse as JSON ({type(exc).__name__}: "
                      f"{exc})")
                print(f"  first 40 bytes on the wire: {lr.content[:40]!r}")
                print(f"  declared encoding: {lr.encoding!r}  "
                      f"content-type: {lr.headers.get('Content-Type')!r}")
    except Exception as exc:
        print(f"  FAILED {type(exc).__name__}: {exc}")

    if not games:
        print("-" * 72)
        print("NO GAME ROWS — but note the endpoint has returned 200 with "
              "~11.5kb of real game data on every run since round 6, and "
              "the FIRST document has always parsed. If this fires now, "
              "read the byte window above: it shows what is actually at "
              "the failure offset, which no previous round could see. "
              "Do NOT theorise from the exception message — rounds 7 and "
              "8 both did, and both fixed something that was not the "
              "cause.")
        return 1

    # Which key holds the id is UNKNOWN and not guessed: the script reads
    # li.attr("g_id"), but that is the ATTRIBUTE the page writes, and the
    # JSON key behind it may differ. Take whichever key looks like a game
    # id, and say which one was used.
    # THE KEYS ARE KNOWN NOW, from round 6's own dump:
    #
    #   LE_ID  SR_ID  SEASON_ID  G_DT  G_DT_TXT  G_ID  HEADER_NO
    #   G_TM   S_NM   AWAY_ID    ...   GAME_SC
    #
    # G_ID = "20260811HHOB0" — which means round 2's guessed FORMAT was
    # right all along (20YYMMDD + 4 letters + digit). It was just never
    # in the page; it lives behind this web method. Four rounds of
    # searching the HTML could not have found it at any format.
    #
    # Still matched case-insensitively with fallbacks: the dump showed
    # the first row's keys, not every row's, and a name read once is not
    # a name confirmed.
    def _pick(row, *names):
        for n in names:
            for k in row:
                if k.lower() == n:
                    return k, row[k]
        return None, None

    pick = games[0]
    for g in games:
        _k, v = _pick(g, "game_sc", "gamesc", "gamestatus")
        if str(v) == "1":
            pick = g
            break
    id_key, game_id = _pick(pick, "g_id", "gameid", "gid")
    print(f"  using {id_key}={game_id} from row: "
          f"{ {k: pick[k] for k in list(pick)[:8]} }")
    if not game_id:
        print("  NO ID-LOOKING KEY on the row. Read the key list above and "
              "name it explicitly next round — do not guess a third time.")
        return 1

    # ---- 3. CALL IT, BOTH WAYS ---------------------------------------
    #
    # GET and POST, because which one it wants is unknown and a 405 from
    # the wrong verb is indistinguishable from a dead route. Field names
    # come from setPreview's signature; if the block above shows
    # different ones, THAT is the answer and this attempt is only a
    # first guess — which is why it is labelled as one.
    url = f"{BASE}/Schedule/GameCenter/Preview/StartPitcher.aspx"

    # EVERY VALUE FROM THE PAGE OR FROM ITS OWN GAME LIST.
    #   field names  <- the `param` block round 2 printed verbatim
    #   gameId       <- the id key round 6 just read off the JSON row
    #   season/teams <- the same row, by whatever keys it carries
    #
    # awayPit/homePit go EMPTY on purpose: setPreview checks
    # `if (awayPit == undefined)` before firing this, which reads as
    # "this endpoint RESOLVES the starters" rather than "you pass them
    # in". If that is wrong the response will say so.
    def _v(*names):
        for n in names:
            for k in pick:
                if k.lower() == n:
                    return str(pick[k])
        return ""

    params = {
        "leId": "1",                       # the page's own literal
        "srId": "0",                       # the one remaining guess
        # SEASON_ID / AWAY_ID / HOME_ID, named by round 6's dump. Tried
        # first, with the old guesses kept behind them — a key seen on
        # one row is not a key confirmed on all of them.
        "seasonId": _v("season_id", "seasonid", "season") or str(today.year),
        "gameId": str(game_id),
        "awayTeam": _v("away_id", "awayteamid", "awayteam", "awaycode"),
        "homeTeam": _v("home_id", "hometeamid", "hometeam", "homecode"),
        "awayPit": "", "homePit": "",
    }
    print("-" * 72)
    print(f"CALLING {url}")
    print(f"  params: {params}")
    if not params["awayTeam"] or not params["homeTeam"]:
        print("  NOTE: team codes not found on the row under any tried key. "
              "Read the key list above. Sending empty rather than inventing "
              "a code — if that is what the endpoint needs, it will say so.")

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
