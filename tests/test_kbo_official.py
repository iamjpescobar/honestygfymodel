"""KBO's own game list parses, and never reports half a matchup.

WHY THIS EXISTS

Nine probe rounds ended here, and two of them threw away perfect data
because of one property of this endpoint:

**IT RETURNS A COMPLETE, SUCCESSFUL JSON DOCUMENT AND THEN APPENDS AN
ASP.NET RUNTIME ERROR PAGE TO THE SAME RESPONSE BODY.**

    { "game": [...], "code": "100", "msg": "성공" }<!DOCTYPE html>...런타임 오류...

`json.loads` refuses the whole thing with "Extra data: char 8398". Round
7 read that as a BOM and round 8 as concatenated JSON documents; both
shipped a fix for a cause nobody had looked at, and both reported a
working endpoint as broken. The trailing page is present on EVERY
successful call, so treating it as a failure means never succeeding.

That is the first thing this file pins, and it is pinned with the real
bytes rather than a paraphrase.

THE SECOND THING IS THE HONESTY GATE

`starters_for` excludes a game unless BOTH starters are named. One name
beside a blank reads as "the other team hasn't announced" — a claim
about the league, when the truth is we only read one side. That
distinction is invisible on a card, which is why it has to be enforced
here.

Measured on a real slate (run 85398873888): 5 of 5 games with both
starters — 왕옌청/곽빈, 비슬리/아빌라, 페덱/올러, 로건/라일리,
카라스코/안우진.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from engines.kbo_official import (  # noqa: E402
    parse_game_list, game_records, starters_for, NORMAL_GAME,
)

failures = []


def check(label, ok):
    if ok:
        print(f"PASS: {label}")
    else:
        failures.append(label)


def row(gid, away, home, asp, hsp, cancel=NORMAL_GAME, status="정규경기"):
    return {
        "G_ID": gid, "G_DT": "20260811", "G_TM": "19:00", "S_NM": "잠실",
        "AWAY_ID": away, "HOME_ID": home,
        "AWAY_NM": away, "HOME_NM": home,
        "T_PIT_P_NM": asp, "T_PIT_P_ID": "101",
        "B_PIT_P_NM": hsp, "B_PIT_P_ID": "202",
        "GAME_SC_NM": status, "CANCEL_SC_NM": cancel,
    }


def body(rows, code="100", msg="성공", trailing=""):
    import json as _j
    return _j.dumps({"game": rows, "code": code, "msg": msg},
                    ensure_ascii=False) + trailing


# The real trailing page, shortened. This is what actually arrives.
ASPNET_ERROR = ('<!DOCTYPE html>\r\n<html>\r\n    <head>\r\n        '
                '<title>런타임 오류</title>\r\n    </head>\r\n    <body>'
                '\r\n    </body>\r\n</html>\r\n')

REAL = [row("20260811HHOB0", "한화", "두산", "왕옌청", "곽빈"),
        row("20260811LTSK0", "롯데", "SSG", "비슬리", "아빌라"),
        row("20260811SSHT0", "삼성", "KIA", "페덱", "올러"),
        row("20260811KTNC0", "KT", "NC", "로건", "라일리"),
        row("20260811LGWO0", "LG", "키움", "카라스코", "안우진")]

# ----------------------------------------------------------------------
# 1. THE TRAILING ERROR PAGE. The regression that cost two rounds.
# ----------------------------------------------------------------------
rows, code, msg = parse_game_list(body(REAL, trailing=ASPNET_ERROR))
check(f"a trailing ASP.NET error page is ignored (got {len(rows)} rows)",
      len(rows) == 5)
check("the success code is still read through it", str(code) == "100")

# json.loads alone must genuinely fail on this input, or the assertion
# above proves nothing about the fix.
import json as _json  # noqa: E402
try:
    _json.loads(body(REAL, trailing=ASPNET_ERROR))
    failures.append("json.loads did NOT fail — the fixture is wrong and "
                    "the test above is not testing anything")
except ValueError:
    check("json.loads alone really does fail on it (fixture is honest)", True)

# And a clean body must not regress.
check("a body with no trailing page still parses",
      len(parse_game_list(body(REAL))[0]) == 5)

# ----------------------------------------------------------------------
# 2. BOTH STARTERS OR NEITHER.
# ----------------------------------------------------------------------
mixed = [row("g-both", "A", "B", "류현진", "곽빈"),
         row("g-away-only", "C", "D", "김광현", ""),
         row("g-home-only", "E", "F", "", "안우진"),
         row("g-neither", "G", "H", "", "")]
got = starters_for(mixed)
check(f"only the fully-named game is reported (got {sorted(got)})",
      set(got) == {"g-both"})
check("a half-named game is EXCLUDED, not reported with a blank",
      "g-away-only" not in got and "g-home-only" not in got)

# game_records keeps them all — the gate belongs to starters_for, so a
# caller that wants the schedule still gets every game.
check("game_records still returns every game, gate or no gate",
      len(game_records(mixed)) == 4)

check(f"the real slate yields all five ({len(starters_for(REAL))})",
      len(starters_for(REAL)) == 5)
_h = starters_for(REAL)["20260811HHOB0"]
check("Korean names survive the round trip",
      _h["away_starter"] == "왕옌청" and _h["home_starter"] == "곽빈")
check("player ids come through for both sides",
      _h["away_starter_id"] == "101" and _h["home_starter_id"] == "202")

# ----------------------------------------------------------------------
# 3. CANCELLATION. Anything the league does not call a normal game.
#
# Compared against the ONE known-normal value rather than a list of
# reasons: the field is free text from the league, and a whitelist of
# reasons would pass an unlisted one through as fine.
# ----------------------------------------------------------------------
recs = {g["game_id"]: g for g in game_records([
    row("norm", "A", "B", "x", "y", cancel=NORMAL_GAME),
    row("rain", "C", "D", "x", "y", cancel="우천취소"),
    row("odd", "E", "F", "x", "y", cancel="어떤새로운사유"),
    row("blank", "G", "H", "x", "y", cancel=""),
])}
check("a normal game is not cancelled", recs["norm"]["cancelled"] is False)
check("a rainout is cancelled", recs["rain"]["cancelled"] is True)
check("an UNSEEN reason is still cancelled (no reason whitelist)",
      recs["odd"]["cancelled"] is True)
check("an empty field is not a cancellation — unknown is not a claim",
      recs["blank"]["cancelled"] is False)

# ----------------------------------------------------------------------
# 4. NOTHING CRASHES A NIGHTLY BUILD.
# ----------------------------------------------------------------------
for bad in ("", None, "not json at all", "<html>error</html>", "[]", "{}"):
    r, _c, _m = parse_game_list(bad)
    if r != []:
        failures.append(f"malformed body {bad!r} produced rows")
        break
else:
    check("malformed bodies yield no rows rather than raising", True)

check("a row with no game id is skipped",
      len(game_records([{"G_TM": "19:00"}])) == 0)
check("an off-day (empty game list) is empty, not an error",
      parse_game_list(body([]))[0] == [])

# ----------------------------------------------------------------------
# 4b. A FAILURE CODE IS NOT AN OFF-DAY.
#
# The endpoint answers 200 with `code` and `msg` inside the body, so a
# rejected call and a genuine off-day both arrive as HTTP 200 with no
# rows. Only `code` separates them — and reading it wrong means a broken
# call renders as "no KBO games today", which is a normal-looking page
# and a completely false statement about the league.
#
# fetch_game_list needs the network, so requests.post is stubbed. Added
# after a negative control (deleting the code check) left every other
# assertion green — the check existed and nothing was testing it.
# ----------------------------------------------------------------------
import engines.kbo_official as _ko  # noqa: E402


class _Resp:
    def __init__(self, text, status=200):
        self.status_code = status
        self.content = text.encode("utf-8")


_real_post = _ko.requests.post
try:
    _ko.requests.post = lambda *a, **k: _Resp(body(REAL))
    got, err = _ko.fetch_game_list("20260811")
    check(f"code 100 with rows is a success ({len(got)} rows)",
          len(got) == 5 and err is None)

    _ko.requests.post = lambda *a, **k: _Resp(body([], code="500", msg="실패"))
    got, err = _ko.fetch_game_list("20260811")
    check("a FAILURE code is an error, not an empty slate",
          got == [] and err and "500" in err)

    _ko.requests.post = lambda *a, **k: _Resp(body([], code="100", msg="성공"))
    got, err = _ko.fetch_game_list("20260811")
    check("code 100 with no games IS an off-day, not an error",
          got == [] and err is None)

    _ko.requests.post = lambda *a, **k: _Resp("", status=503)
    got, err = _ko.fetch_game_list("20260811")
    check("a non-200 is reported as an error", got == [] and "503" in err)

    def _boom(*a, **k):
        raise ConnectionError("down")

    _ko.requests.post = _boom
    got, err = _ko.fetch_game_list("20260811")
    check("an outage costs the KBO board, not the nightly run",
          got == [] and "ConnectionError" in err)
finally:
    _ko.requests.post = _real_post

# ----------------------------------------------------------------------
# 5. NO SECOND DEFINITION OF THE FIELD MAPPING.
#
# T is the top of the inning (away), B the bottom (home). Getting that
# backwards would swap every starter on the board and look completely
# normal, so the mapping lives in one module and this asserts it is not
# duplicated in a view or a pipeline.
# ----------------------------------------------------------------------
src = open(os.path.join(os.path.dirname(__file__), "..", "app", "engines",
                        "kbo_official.py"), encoding="utf-8").read()
check("T_PIT maps to AWAY in exactly one place",
      src.count('"t_pit_p_nm"') == 1)
check("B_PIT maps to HOME in exactly one place",
      src.count('"b_pit_p_nm"') == 1)
check("the module makes no attempt to project or grade anything",
      "def project" not in src and "def grade" not in src)

# ----------------------------------------------------------------------
# 6. WALKING A WINDOW — an off-day and a broken date are NOT the same.
#
# GetKboGameList takes one date. GetKboGameDate was probed to see if a
# range came in one call; it returns a CURSOR instead —
# BEFORE_G_DT / NOW_G_DT / AFTER_G_DT — so a window is one call per date
# regardless. The cursor is deliberately unused: following AFTER_G_DT
# costs an extra request per step to skip off-days that GetKboGameList
# already reports as empty.
#
# The property that makes the loop safe: an off-day (code 100, no rows)
# is silence, a 503 is a gap. Conflating them means a nightly either
# publishes a fortnight with holes it does not know about, or refuses to
# publish over a Monday with no baseball.
# ----------------------------------------------------------------------
_calls = []


def _walk_stub(url, **kw):
    d = kw["json"]["date"]
    _calls.append(d)
    if d == "20260812":
        return _Resp("", status=503)          # a real failure
    if d == "20260810":
        return _Resp(body([]))               # an off-day
    return _Resp(body(REAL))


_real_post2 = _ko.requests.post
try:
    _ko.requests.post = _walk_stub
    got, errs = _ko.fetch_window("20260810", 4, sleep=0)
    check(f"every date in the window is asked for ({len(_calls)})",
          _calls == ["20260810", "20260811", "20260812", "20260813"])
    check("an off-day contributes no rows and NO error",
          "20260810" not in got and not any("20260810" in e for e in errs))
    check("a broken date is recorded as an error, not silence",
          any("20260812" in e and "503" in e for e in errs))
    check("neither one stops the walk — the good dates still come back",
          sorted(got) == ["20260811", "20260813"])

    _ko.requests.post = lambda *a, **k: _Resp(body(REAL))
    check("a zero-day window asks for nothing",
          _ko.fetch_window("20260810", 0, sleep=0) == ({}, []))
    check("a malformed start date is an error, not a crash",
          _ko.fetch_window("not-a-date", 3, sleep=0)[1] != [])
finally:
    _ko.requests.post = _real_post2

# The cursor endpoint is NOT used for the walk. Asserted on the RUNNABLE
# code with comments stripped — the first version of this checked the
# whole source and failed on the paragraph EXPLAINING why the cursor is
# unused, which is the same "matched the comment, not the command"
# mistake as rule 26. The reasoning should stay in the file; only the
# code has to be clean.
#
# Worth asserting at all because "we chose the cheaper path" silently
# reverses the moment someone reads GetKboGameDate's name and assumes it
# must be involved. Following AFTER_G_DT would double the requests to
# learn something the cheaper call already reports.
_code = "\n".join(l for l in src.splitlines()
                  if not l.lstrip().startswith("#"))
check("the walk does not chase the GetKboGameDate cursor in code",
      "AFTER_G_DT" not in _code and "GetKboGameDate" not in _code)
check("but the reasoning for that choice is still written down",
      "AFTER_G_DT" in src)

if failures:
    print()
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(1)

print("\nA complete JSON document with a stack trace stapled to it is still "
      "a complete JSON document.")
