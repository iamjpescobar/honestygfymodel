"""
Can the OFFICIAL KBO site replace mykbostats as our source?

WHY THIS EXISTS

mykbostats Acceptable Use clause 6 prohibits using their content to make
sports bets, which is what this project does. Separately, their v3
rewrite on 2026-08-04 broke parse_starters() silently and cost weeks of
blind KBO pitcher matchups. So the source is both legally awkward and
mechanically fragile.

eng.koreabaseball.com is the league's own site. A manual read of
DailySchedule.aspx shows a clean static table with dates, times, teams,
venues, final scores and a POSTPONED column - most of what
kbo_precompute needs, from the primary source.

THE QUESTION THIS ANSWERS is not "does the page parse" - it does. It is
whether a SPECIFIC date can be requested by GET. The site is ASP.NET and
its month control is a __doPostBack link, which usually means viewstate
round-trips. A source that only ever serves "this month" from a GET is
still usable, but a nightly that has to POST a viewstate to see
yesterday is a different and much worse proposition, and that should be
known before anything is rewritten rather than after.

Also checks, in one run:
  - whether probable starters appear anywhere (the English site shows
    none; the Korean schedule may)
  - whether the Korean site is reachable and what encoding it uses
  - what a box score URL returns

MUST RUN FROM ACTIONS. Korean sites regularly geo-fence or rate-limit by
region, and a laptop result predicts nothing about what the pipeline or
Render would see.

Touches nothing: no commit, no release, no deploy hook.
"""
import re
import sys
import time

import requests

ENG = "https://eng.koreabaseball.com"
KOR = "https://www.koreabaseball.com"

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}


def get(url, label, params=None):
    """GET and report honestly. A refusal is a finding, not a crash."""
    try:
        r = requests.get(url, headers=UA, params=params, timeout=25)
    except Exception as exc:
        print(f"  {label}: FAILED {type(exc).__name__}: {exc}")
        return None
    print(f"  {label}: HTTP {r.status_code}  {len(r.content):,} bytes  "
          f"enc={r.encoding}")
    return r if r.status_code == 200 else None


def rows_in(html):
    """Count schedule rows by looking for a venue name, not a class.

    Rule 18: key on the product. Stadium names are the thing the page
    exists to tell you and survive a restyle; a table class does not.
    """
    venues = ("JAMSIL", "SAJIK", "DAEGU", "SUWON", "GWANGJU", "MUNHAK",
              "CHANGWON", "DAEJEON", "GOCHEOK")
    return sum(html.upper().count(v) for v in venues)


def main():
    print("=" * 70)
    print("Official KBO site probe - can it replace mykbostats?")
    print("=" * 70)

    # --- 1. the default page, to establish a baseline -----------------
    print("\n[1] DailySchedule.aspx with no parameters")
    base = get(f"{ENG}/Schedule/DailySchedule.aspx", "default")
    if not base:
        print("  The English site did not answer. Everything below assumes")
        print("  it does, so stopping here rather than printing noise.")
        return 1
    html = base.text
    print(f"    venue mentions (rough row count): {rows_in(html)}")
    print(f"    POSTPONED occurrences: {html.upper().count('POSTPONED')}")
    for token in ("__VIEWSTATE", "__doPostBack", "ddlMonth", "ddlYear",
                  "선발", "Starting", "starter"):
        print(f"    {token:<14} {html.count(token)}")

    # --- 2. THE KEY QUESTION: can a month be requested by GET? --------
    print("\n[2] Asking for a DIFFERENT month by query string")
    print("    If any of these returns a page whose content differs from")
    print("    the default, this source is a plain GET away and the")
    print("    rewrite is easy. If they all echo the current month, the")
    print("    site needs a viewstate POST and that changes the design.")
    base_fingerprint = rows_in(html), html.upper().count("POSTPONED")
    for params in ({"seriesId": "0", "gameMonth": "07", "gameYear": "2026"},
                   {"gameMonth": "07", "gameYear": "2026"},
                   {"month": "07", "year": "2026"},
                   {"gyear": "2026", "gmonth": "07"}):
        time.sleep(0.4)
        r = get(f"{ENG}/Schedule/DailySchedule.aspx",
                f"params={params}", params=params)
        if not r:
            continue
        fp = rows_in(r.text), r.text.upper().count("POSTPONED")
        same = "SAME as default" if fp == base_fingerprint else "DIFFERENT <--"
        print(f"      fingerprint {fp}  {same}")

    # --- 3. the other pages kbo_precompute would need -----------------
    print("\n[3] Sibling pages")
    for path, label in (("/Schedule/Scoreboard.aspx", "scoreboard"),
                        ("/Standings/TeamStandings.aspx", "standings"),
                        ("/stats/PitchingLeaders.aspx", "pitching leaders"),
                        ("/stats/TeamStats.aspx", "team stats")):
        time.sleep(0.4)
        get(f"{ENG}{path}", label)

    # --- 4. probables: the one thing the English site lacks -----------
    print("\n[4] Probable starters")
    print("    The English pages carry none. The Korean schedule shows")
    print("    선발투수 (starting pitcher) in a browser, so the question is")
    print("    whether it is in the served HTML or drawn by script.")
    time.sleep(0.4)
    kr = get(f"{KOR}/Schedule/Schedule.aspx", "korean schedule")
    if kr:
        kr.encoding = kr.apparent_encoding or "utf-8"
        t = kr.text
        for token in ("선발", "투수", "예고", "우천", "취소", "__VIEWSTATE"):
            print(f"    {token:<12} {t.count(token)}")
        i = t.find("선발")
        if i != -1:
            print("\n    --- HTML around the first 선발 ---")
            print(t[max(0, i - 500):i + 900])
        else:
            print("    선발 does not appear in the served HTML. Either the")
            print("    page draws it client-side, or it lives elsewhere.")

    print("\n" + "=" * 70)
    print("Done. Send the whole log.")
    print("Reading it: [2] DIFFERENT means an easy GET-based rewrite.")
    print("[2] all SAME means viewstate POSTs, which is worth knowing")
    print("before committing to the switch, not after.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
