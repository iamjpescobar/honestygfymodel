"""
KBO's own game list — probables, status and cancellation, from the
league rather than from a fan site.

WHERE THIS CAME FROM
--------------------
Nine probe rounds. The short version:

  /ws/Main.asmx/GetKboGameList   POST, JSON body {leId, srId, date}

returns every game for one date with, per row:

    G_ID         20260811HHOB0        AWAY_ID / AWAY_NM
    G_DT  G_TM   S_NM (stadium)       HOME_ID / HOME_NM
    T_PIT_P_NM / T_PIT_P_ID          away starter, name + player id
    B_PIT_P_NM / B_PIT_P_ID          home starter, name + player id
    GAME_SC_NM   status in words      CANCEL_SC_NM  cancellation in words
    LINEUP_CK

T is the top of the inning (away), B the bottom (home). Measured on a
real slate: 5 of 5 games with BOTH starters named — 왕옌청/곽빈,
비슬리/아빌라, 페덱/올러, 로건/라일리, 카라스코/안우진.

WHY THIS EXISTS AT ALL: mykbostats' Acceptable Use clause 6 forbids
using their content to make sports bets. This site does exactly that, so
that source has to go. It is the only reason nine rounds were spent here.

THE RESPONSE IS NOT VALID JSON, AND THAT IS NORMAL
---------------------------------------------------
The server returns a COMPLETE, SUCCESSFUL JSON document —

    { "game": [...], "code": "100", "msg": "성공" }

— and then appends an ASP.NET runtime error page to the same response
body. `json.loads` refuses the whole thing with "Extra data", which is
how two probe rounds threw away perfect data and reported the endpoint
as broken.

`raw_decode` reads the first document and stops. The trailing page is
IGNORED, deliberately and permanently: it is present on every successful
call, so treating it as a failure would mean never succeeding. `code`
and `msg` are what say whether the call worked.

BOTH STARTERS OR NEITHER
------------------------
`starters_for` returns a game only when both sides are named. Half a
matchup reads as a whole one — a card showing one starter and a blank
looks like the other team is undecided, when in fact we simply did not
read it. That gate is the whole reason this module has a test.
"""
import json

import requests

BASE = "https://www.koreabaseball.com"
GAME_LIST_URL = f"{BASE}/ws/Main.asmx/GetKboGameList"

# leId "1" is the page's own literal for the top league. srId "0" is the
# full regular series. Both are taken verbatim from the site's own call:
#   $.ajax({ url: "/ws/Main.asmx/GetKboGameList",
#            data: { leId: "1", srId: srId, date: ... } })
LEAGUE_ID = "1"
SERIES_ID = "0"

_UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/Schedule/GameCenter/Main.aspx",
    "Content-Type": "application/json; charset=UTF-8",
}

# A cancelled game's CANCEL_SC_NM. Normal games carry 정상경기 ("normal
# game"), so anything else is a real signal. NOT hardcoded as a list of
# cancellation reasons — the field is free text from the league and a
# whitelist would silently pass an unlisted reason as normal.
NORMAL_GAME = "정상경기"


def _get(row, *names):
    """Case-insensitive field read. The payload uses SCREAMING_SNAKE and
    a caller should not have to care."""
    for n in names:
        for k in row:
            if k.lower() == n:
                return row[k]
    return None


def _text(v):
    return str(v).strip() if v is not None else ""


def parse_game_list(raw):
    """(rows, code, msg) from a GetKboGameList body. Pure — no network.

    Tolerates the trailing ASP.NET error page by decoding exactly one
    JSON document and ignoring whatever follows. Returns ([], None, None)
    rather than raising: this feeds a nightly build, and a parse failure
    must cost the KBO board, not the run.
    """
    if not raw:
        return [], None, None
    try:
        obj, _end = json.JSONDecoder().raw_decode(raw.lstrip("\ufeff \r\n\t"))
    except ValueError:
        return [], None, None
    if not isinstance(obj, dict):
        return [], None, None
    rows = obj.get("game")
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    return rows, obj.get("code"), obj.get("msg")


def fetch_game_list(date_str, timeout=25):
    """(rows, error) for one YYYYMMDD. Never raises.

    `code` is checked rather than assumed: a 200 with a failure code is
    exactly the shape that would otherwise be read as an empty slate,
    and an empty slate is indistinguishable from an off-day.
    """
    body = {"leId": LEAGUE_ID, "srId": SERIES_ID, "date": date_str}
    try:
        r = requests.post(GAME_LIST_URL, headers=_UA, json=body, timeout=timeout)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}"

    # utf-8 explicitly: the payload carries Korean names and requests
    # guesses ISO-8859-1 when a server omits its charset, which would
    # mangle every one of them while still parsing cleanly.
    raw = (r.content or b"").decode("utf-8-sig", errors="replace")
    rows, code, msg = parse_game_list(raw)
    if code is not None and str(code) != "100":
        return [], f"KBO returned code {code} ({msg})"
    if not rows:
        return [], None      # a real off-day, not an error
    return rows, None


def game_records(rows):
    """One tidy dict per game, in the site's own vocabulary.

    Every field is passed through as read. Nothing is inferred, and a
    missing value stays empty rather than becoming a guess.
    """
    out = []
    for r in rows:
        gid = _text(_get(r, "g_id"))
        if not gid:
            continue
        cancel = _text(_get(r, "cancel_sc_nm"))
        out.append({
            "game_id": gid,
            "date": _text(_get(r, "g_dt")),
            "time": _text(_get(r, "g_tm")),
            "stadium": _text(_get(r, "s_nm")),
            "away_id": _text(_get(r, "away_id")),
            "home_id": _text(_get(r, "home_id")),
            "away_name": _text(_get(r, "away_nm")),
            "home_name": _text(_get(r, "home_nm")),
            "away_starter": _text(_get(r, "t_pit_p_nm")),
            "home_starter": _text(_get(r, "b_pit_p_nm")),
            "away_starter_id": _text(_get(r, "t_pit_p_id")),
            "home_starter_id": _text(_get(r, "b_pit_p_id")),
            "status": _text(_get(r, "game_sc_nm")),
            "cancel_status": cancel,
            # A cancellation is anything the league does not call a
            # normal game. Comparing against the ONE known-normal value
            # rather than listing reasons: the field is free text, and a
            # whitelist of reasons would pass an unlisted one as fine.
            "cancelled": bool(cancel) and cancel != NORMAL_GAME,
        })
    return out


def starters_for(rows):
    """{game_id: record} for games where BOTH starters are named.

    THE GATE. A game with one starter named is EXCLUDED, not
    half-reported. On a card, one name beside a blank reads as "the other
    team hasn't announced" — a claim about the league, when the truth is
    that we only managed to read one side. Both or neither.
    """
    return {
        g["game_id"]: g
        for g in game_records(rows)
        if g["away_starter"] and g["home_starter"]
    }


# ----------------------------------------------------------------------
# WALKING A WINDOW
#
# GetKboGameList takes ONE date. GetKboGameDate was probed to see whether
# a range came in one call; it does not — it returns a CURSOR:
#
#     BEFORE_G_DT 20260809 | NOW_G_DT 20260811 | AFTER_G_DT 20260812
#
# previous / current / next game date. Useful, but not a range, so a
# window means one call per date either way.
#
# THE CURSOR IS DELIBERATELY NOT USED FOR THE WALK. Following AFTER_G_DT
# would be one extra request per step to skip off-days that
# GetKboGameList already reports as empty in a single call — twice the
# requests to learn something the cheaper call tells us anyway. Walking
# calendar dates is simpler and halves the traffic against the league's
# servers.
#
# An off-day returns code 100 with no rows and is NOT an error; see
# fetch_game_list. That distinction is what makes this loop safe.
# ----------------------------------------------------------------------

def fetch_window(start_date, days, sleep=0.4, log=None):
    """({date: rows}, [errors]) across `days` calendar dates from start.

    Errors are COLLECTED, not raised, and the caller decides. A single
    bad date must not cost the other thirteen — the nightly has to
    publish whatever it could read, and a partial window is honest as
    long as the gaps are known.

    `sleep` is a courtesy pause between requests. This is a league site
    being asked for two weeks of its own schedule; there is no hurry.
    """
    import time
    from datetime import datetime, timedelta

    try:
        d0 = datetime.strptime(str(start_date), "%Y%m%d").date()
    except (TypeError, ValueError):
        return {}, [f"bad start date {start_date!r}"]

    out, errs = {}, []
    for i in range(max(0, int(days))):
        ds = (d0 + timedelta(days=i)).strftime("%Y%m%d")
        rows, err = fetch_game_list(ds)
        if err:
            errs.append(f"{ds}: {err}")
        elif rows:
            out[ds] = rows
        if log:
            log(f"  {ds}: {len(rows)} game(s)" + (f" [{err}]" if err else ""))
        if sleep and i + 1 < days:
            time.sleep(sleep)
    return out, errs
