#!/usr/bin/env python3
"""
International source probe — KBO + NPB

Runs from GitHub Actions to verify candidate data sources are reachable
and look parseable from Actions' datacenter IPs. Prints one line per
target: HTTP status, response size, <title>, and which markers were found.

Safe rules:
- No files written
- Short timeouts and clear errors
- No guessing or data extraction beyond title + marker checks
"""

from __future__ import annotations
import sys
import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
}

# (label, url, content markers that suggest the page is the real thing)
TARGETS = [
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


def extract_title(body: str) -> str:
    lo = body.lower()
    if "<title" not in lo:
        return ""
    try:
        i = lo.index("<title")
        j = lo.find(">", i)
        k = lo.find("</title", j)
        if j == -1 or k == -1:
            return ""
        title = body[j + 1 : k].strip()
        # normalize whitespace
        return " ".join(title.split())[:120]
    except Exception:
        return ""


def probe(label: str, url: str, markers: list[str]) -> None:
    try:
        # split connect/read timeouts: connect 10s, read 20s
        r = requests.get(url, headers=UA, timeout=(10, 20))
        body = r.text or ""
        title = extract_title(body)
        lo = body.lower()
        hits = [m for m in markers if m.lower() in lo]
        print(
            f"[{r.status_code}] {label:32s} | {len(body):>9,} bytes | "
            f"title: {title!r} | markers hit: {hits}"
        )
    except requests.exceptions.RequestException as exc:
        # Common network/HTTP errors (DNS, connect, timeout, SSL, 4xx/5xx raised here)
        print(f"[ERR] {label:32s} | {exc}")
    except Exception as exc:
        # Any other unexpected error
        print(f"[ERR] {label:32s} | unexpected error: {exc}")


def main() -> int:
    print("=== International source probe (running from GitHub Actions) ===")
    for label, url, markers in TARGETS:
        probe(label, url, markers)
    print(
        "=== done — a 200 with markers hit means buildable; 403/406/ERR means blocked ==="
    )
    # Always exit 0 so the workflow run is preserved for inspection.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
