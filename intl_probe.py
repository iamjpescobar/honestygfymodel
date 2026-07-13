"""
International source probe — KBO + NPB.

Tests, FROM GITHUB ACTIONS' SERVERS, which candidate data sources are
actually reachable and look parseable. This runs on Actions because
that's exactly where the nightly fetcher will live — a source that
works from a laptop but 403s from datacenter IPs (hi, FanGraphs) is
useless to us, and this probe is how we find out BEFORE building on it.

Prints one report line per source: HTTP status, response size, page
<title>, and whether known content markers appear. No data is saved;
this is reconnaissance only.
"""

import requests

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
}

# (label, url, content markers that suggest the page is the real thing)
TARGETS = [
    # Control — known-good from Actions, proves the probe itself works
    ("CONTROL  MLB statsapi", "https://statsapi.mlb.com/api/v1/teams?sportId=1", ["teams"]),

    # ---- KBO ----
    ("KBO  official schedule", "https://www.koreabaseball.com/Schedule/Schedule.aspx", ["Schedule", "KBO"]),
    ("KBO  official EN", "https://eng.koreabaseball.com/", ["KBO"]),
    ("KBO  MyKBOStats", "https://mykbostats.com/", ["KBO", "stats"]),
    ("KBO  Statiz (sporki)", "https://statiz.sporki.com/", ["statiz", "STATIZ"]),
    ("KBO  Naver schedule", "https://sports.news.naver.com/kbaseball/schedule/index", ["schedule", "naver"]),

    # ---- NPB ----
    ("NPB  official EN", "https://npb.jp/eng/", ["NPB", "Nippon"]),
    ("NPB  official schedule (July)", "https://npb.jp/games/2026/schedule_07_detail.html", ["2026", "npb"]),
    ("NPB  official scores", "https://npb.jp/scores/", ["scores", "npb"]),
    ("NPB  DELTA (1point02)", "https://1point02.jp/op/index.aspx", ["1point02", "DELTA"]),
]


def probe(label, url, markers):
    try:
        r = requests.get(url, headers=UA, timeout=20)
        body = r.text or ""
        title = ""
        lo = body.lower()
        if "<title" in lo:
            i = lo.index("<title")
            j = lo.find(">", i)
            k = lo.find("</title", j)
            if j != -1 and k != -1:
                title = body[j + 1:k].strip()[:80]
        hits = [m for m in markers if m.lower() in lo]
        print(f"[{r.status_code}] {label:32s} | {len(body):>9,} bytes | "
              f"title: {title!r} | markers hit: {hits}")
    except Exception as exc:
        print(f"[ERR] {label:32s} | {exc}")


def main():
    print("=== International source probe (running from GitHub Actions) ===")
    for label, url, markers in TARGETS:
        probe(label, url, markers)
    print("=== done — a 200 with markers hit means buildable; 403/406/ERR means blocked ===")


if __name__ == "__main__":
    main()
