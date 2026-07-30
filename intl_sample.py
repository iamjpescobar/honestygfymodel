"""
Source sampler v3 — WNBA recon.

KBO and NPB are solved and live. This pass tests WNBA data sources
from GitHub Actions' servers and dumps the JSON structure of whichever
answers, so the fetcher gets written against reality. Expectation
going in: ESPN's public scoreboard API is open; stats.wnba.com likely
blocks datacenter IPs like its NBA sibling. Reconnaissance only.
"""

import requests

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
}

TARGETS = [
    ("ESPN WNBA scoreboard", "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"),
    ("WNBA CDN today scoreboard", "https://cdn.wnba.com/static/json/liveData/scoreboard/todaysScoreboard_10.json"),
    ("stats.wnba.com (expect block)", "https://stats.wnba.com/stats/scoreboardv3?GameDate=&LeagueID=10"),
]


def trim(obj, depth=0):
    """Prints a JSON object's shape: keys, list lengths, first elements."""
    pad = "  " * depth
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:12]:
            if isinstance(v, (dict, list)):
                print(f"{pad}{k}:")
                trim(v, depth + 1)
            else:
                print(f"{pad}{k}: {str(v)[:70]}")
    elif isinstance(obj, list):
        print(f"{pad}[list, {len(obj)} items]")
        if obj:
            trim(obj[0], depth + 1)


def main():
    for label, url in TARGETS:
        print("\n" + "=" * 70 + f"\n{label}\n" + "=" * 70)
        try:
            r = requests.get(url, headers=UA, timeout=20)
            print(f"status {r.status_code}, {len(r.content):,} bytes")
            if r.status_code == 200:
                try:
                    data = r.json()
                    trim(data)
                except Exception:
                    print("(200 but not JSON) first 400 chars:")
                    print(r.text[:400])
        except Exception as exc:
            print(f"ERR: {exc}")
    print("\n=== WNBA recon done ===")


if __name__ == "__main__":
    main()
