"""
International source sampler — step 2 of recon.

The probe proved MyKBOStats (KBO) and npb.jp (NPB) answer from GitHub
Actions. This script downloads those pages and prints their actual
HTML structure — the tables, rows, and links the real fetchers will
parse — so the parsers get written against reality, not guesses.
Output is trimmed to stay readable. No data is saved.
"""

import re
import requests

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
}


def fetch(url):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        return r.status_code, r.text or ""
    except Exception as exc:
        return "ERR", str(exc)


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def show_links(html, keywords, limit=25):
    links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
    hits = []
    for href, text in links:
        t = re.sub(r"<[^>]+>", "", text).strip()[:60]
        blob = (href + " " + t).lower()
        if any(k in blob for k in keywords):
            hits.append(f"  {href}  ->  {t}")
    for h in hits[:limit]:
        print(h)
    if not hits:
        print("  (no matching links)")


def show_snippets(html, pattern, before=120, after=400, limit=6, label=""):
    print(f"--- snippets around {label or pattern!r} ---")
    count = 0
    for m in re.finditer(pattern, html):
        s = max(0, m.start() - before)
        e = min(len(html), m.end() + after)
        snip = re.sub(r"\s+", " ", html[s:e])
        print(f"  ...{snip}...")
        count += 1
        if count >= limit:
            break
    if count == 0:
        print("  (pattern not found)")


def main():
    # ---------------- KBO: MyKBOStats ----------------
    section("KBO / MyKBOStats — homepage")
    code, html = fetch("https://mykbostats.com/")
    print(f"status {code}, {len(html):,} bytes")
    if isinstance(code, int) and code == 200:
        show_links(html, ["sched", "game", "score", "standing", "team"])
        show_snippets(html, r"[0-2]?\d:\d{2}", label="times (game rows?)")

    section("KBO / MyKBOStats — /schedule (guess)")
    code, html = fetch("https://mykbostats.com/schedule")
    print(f"status {code}, {len(html):,} bytes")
    if isinstance(code, int) and code == 200:
        show_snippets(html, r"<tr", label="table rows", after=600, limit=8)

    # ---------------- NPB: official monthly schedule ----------------
    section("NPB / npb.jp — July schedule detail")
    code, html = fetch("https://npb.jp/games/2026/schedule_07_detail.html")
    print(f"status {code}, {len(html):,} bytes")
    if isinstance(code, int) and code == 200:
        # Day cell structure around mid-July
        show_snippets(html, r'date0?7[/_-]?1[45]|>7/1[45]<|0714|0715', label="July 14-15 rows", after=900, limit=4)
        show_snippets(html, r"<tr", label="generic table rows", after=700, limit=6)

    section("NPB / npb.jp — per-date score index (guess: /scores/2026/0714/)")
    code, html = fetch("https://npb.jp/scores/2026/0714/")
    print(f"status {code}, {len(html):,} bytes")
    if isinstance(code, int) and code == 200:
        show_links(html, ["score", "game", "s2026"])
        show_snippets(html, r"<tr", label="table rows", after=600, limit=6)

    print("\n=== sample done ===")


if __name__ == "__main__":
    main()
