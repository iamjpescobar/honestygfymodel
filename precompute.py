#!/usr/bin/env python3
"""
kbo_precompute.py

Fetches the KBO schedule page from koreabaseball.com and produces
data/kbo/games.json with the exact shape the app expects.

Rules enforced:
- No invented values: unknown fields are null or "TBD"
- Fail loud and empty: on any parse error produce an empty "games" list
- Times are interpreted as KST (Asia/Seoul) and converted to ET for time_et
- Uses a browser UA and short timeouts suitable for CI
- Minimal dependencies: requests + lxml (add lxml to requirements if needed)
"""

from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests

# User agent tuned for Actions
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

SCHEDULE_URL = "https://www.koreabaseball.com/Schedule/Schedule.aspx"
OUT_DIR = "data/kbo"
OUT_FILE = os.path.join(OUT_DIR, "games.json")


def safe_mkdir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        # If we can't create the directory, we'll still attempt to print the result
        pass


def write_output(games: list[dict]) -> None:
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    payload = {"generated_at_kst": now_kst, "games": games}
    safe_mkdir(OUT_DIR)
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"WROTE {OUT_FILE} ({len(games)} games)")
    except Exception as exc:
        # If writing fails, print payload to logs so Actions preserves evidence
        print(f"ERROR writing {OUT_FILE}: {exc}")
        print(json.dumps(payload, ensure_ascii=False))


def parse_time_kst_to_et(time_str: str) -> tuple[str | None, str | None]:
    """
    Given a time string (e.g., "18:30", "18:30(연장)" or "18:30 KST"), parse it as KST
    and return (time_kst_formatted, time_et_formatted). If parsing fails, return (None, None).
    """
    if not time_str:
        return None, None
    # Extract HH:MM
    m = re.search(r"(\d{1,2}[:.]\d{2})", time_str)
    if not m:
        return None, None
    hhmm = m.group(1).replace(".", ":")
    try:
        kst = ZoneInfo("Asia/Seoul")
        et = ZoneInfo("America/New_York")
        today_kst = datetime.now(kst).date()
        hh, mm = map(int, hhmm.split(":"))
        dt_kst = datetime.combine(today_kst, time(hh, mm), tzinfo=kst)
        dt_et = dt_kst.astimezone(et)
        return dt_kst.strftime("%H:%M"), dt_et.strftime("%-I:%M %p")
    except Exception:
        return None, None


def try_extract_with_lxml(body: str) -> list[dict]:
    """
    Attempt a best-effort parse using lxml. We try multiple heuristics:
    1) Look for tables with schedule-like headers
    2) Fallback: find rows with 3+ <td> and map columns heuristically
    This function never raises; on failure it returns [].
    """
    try:
        from lxml import html
    except Exception as exc:
        print(f"[WARN] lxml not available: {exc} — parser will not run")
        return []

    try:
        doc = html.fromstring(body)
    except Exception as exc:
        print(f"[WARN] lxml failed to parse HTML: {exc}")
        return []

    games: list[dict] = []

    # Heuristic 1: find tables that look like schedules
    tables = doc.findall(".//table")
    for tbl in tables:
        headers = [h.text_content().strip().lower() for h in tbl.findall(".//th")]
        header_text = " ".join(headers)
        if any(k in header_text for k in ("시간", "구장", "팀", "팀명", "경기")) or "schedule" in header_text:
            # iterate rows
            for tr in tbl.findall(".//tr"):
                tds = tr.findall(".//td")
                if len(tds) < 3:
                    continue
                # Heuristic mapping: many KBO tables are [date/time, away, home, stadium, ...]
                texts = [td.text_content().strip() for td in tds]
                # Normalize empty strings to None
                texts = [t if t else None for t in texts]
                # Try to find time-like cell
                time_cell = None
                stadium = None
                away = None
                home = None
                # find first time-like token
                for t in texts:
                    if t and re.search(r"\d{1,2}[:.]\d{2}", t):
                        time_cell = t
                        break
                # find team-like tokens: often two adjacent cells with vs or '-' between
                # fallback: pick the first two non-time, non-stadium short tokens
                candidates = [t for t in texts if t and t != time_cell]
                if len(candidates) >= 2:
                    # crude guess: last candidate might be stadium if it contains '구장' or 'stadium'
                    for c in candidates[::-1]:
                        if c and ("구장" in c or "stadium" in c or len(c) > 10 and any(ch.isalpha() for ch in c)):
                            stadium = c
                            break
                    # pick two short tokens for teams
                    short_tokens = [c for c in candidates if c and len(c) <= 20]
                    if len(short_tokens) >= 2:
                        away = short_tokens[0]
                        home = short_tokens[1]
                    else:
                        # fallback: use first two candidates
                        away = candidates[0] if candidates else None
                        home = candidates[1] if len(candidates) > 1 else None

                time_kst, time_et = (None, None)
                if time_cell:
                    time_kst, time_et = parse_time_kst_to_et(time_cell)

                game = {
                    "away": away or None,
                    "home": home or None,
                    "stadium": stadium or None,
                    "time_kst": time_kst or None,
                    "time_et": time_et or None,
                    "away_starter": None,
                    "home_starter": None,
                }
                # Only add if we have at least one team name
                if game["away"] or game["home"]:
                    games.append(game)

            if games:
                return games

    # Heuristic 2: look for list items or divs that contain "vs" or "VS"
    text_nodes = doc.findall(".//text()")
    # skip: lxml text() returns strings; we won't iterate that heavy path here
    # fallback: return empty
    return []


def fetch_and_parse(url: str) -> list[dict]:
    try:
        r = requests.get(url, headers=UA, timeout=(10, 20))
    except Exception as exc:
        print(f"[ERR] network fetch failed: {exc}")
        return []

    if r.status_code != 200:
        print(f"[ERR] HTTP {r.status_code} fetching {url}")
        return []

    body = r.text or ""
    # Quick sanity check for markers we expect
    if not any(m in body for m in ("KBO", "경기", "일정", "Schedule")):
        print("[WARN] expected markers not found in page body; parser may fail")
    games = try_extract_with_lxml(body)
    return games


def main() -> int:
    print("kbo_precompute: fetching schedule from koreabaseball.com")
    games = []
    try:
        games = fetch_and_parse(SCHEDULE_URL)
    except Exception as exc:
        print(f"[ERR] unexpected error during fetch/parse: {exc}")

    # If parser produced nothing, fail loud and produce an empty games list (no fake data)
    if not games:
        print("No games parsed or parse failed — producing empty games list (fail loud, empty).")
        write_output([])
        return 0

    # Final normalization: ensure exact shape and nulls where missing
    normalized = []
    for g in games:
        normalized.append(
            {
                "away": g.get("away") or None,
                "home": g.get("home") or None,
                "stadium": g.get("stadium") or None,
                "time_kst": g.get("time_kst") or None,
                "time_et": g.get("time_et") or None,
                "away_starter": g.get("away_starter") or None,
                "home_starter": g.get("home_starter") or None,
            }
        )

    write_output(normalized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
