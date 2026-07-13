#!/usr/bin/env python3
"""
kbo_precompute.py

Fast, safe, conservative KBO slate + basic stats fetcher.

Primary source: koreabaseball.com schedule page.
Secondary source: mykbostats.com for starters when available.

Safety rules:
- Never invent values: unknown fields are None/"TBD".
- Fail loud and empty: on parse failure produce an empty "games" list.
- Times computed in KST (Asia/Seoul) and converted to ET for time_et.
- Minimal deps: requests; lxml optional (recommended).
- CI-friendly: browser UA, split connect/read timeouts, clear logs.
- Writes exactly data/kbo/games.json with the shape the app expects.
"""

from __future__ import annotations
import json
import os
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import List, Dict, Tuple, Optional

import requests

# Config
SCHEDULE_URL = "https://www.koreabaseball.com/Schedule/Schedule.aspx"
MYKBO_BASE = "https://mykbostats.com/"
OUT_DIR = "data/kbo"
OUT_FILE = os.path.join(OUT_DIR, "games.json")
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
REQUEST_TIMEOUT = (10, 20)  # connect, read


def safe_mkdir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def write_output(games: List[Dict]) -> None:
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    payload = {"generated_at_kst": now_kst, "games": games}
    safe_mkdir(OUT_DIR)
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"WROTE {OUT_FILE} ({len(games)} games)")
    except Exception as exc:
        print(f"[ERR] writing {OUT_FILE}: {exc}")
        print(json.dumps(payload, ensure_ascii=False))


def parse_time_kst_to_et(time_str: str) -> Tuple[Optional[str], Optional[str]]:
    if not time_str:
        return None, None
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


def try_lxml_parse_schedule(body: str) -> List[Dict]:
    try:
        from lxml import html
    except Exception:
        print("[WARN] lxml not installed; skipping lxml parsing")
        return []

    try:
        doc = html.fromstring(body)
    except Exception as exc:
        print(f"[WARN] lxml failed to parse HTML: {exc}")
        return []

    games: List[Dict] = []
    tables = doc.findall(".//table")
    for tbl in tables:
        ths = [t.text_content().strip().lower() for t in tbl.findall(".//th")]
        header_text = " ".join(ths)
        # proceed even if headers are absent; we still inspect rows
        for tr in tbl.findall(".//tr"):
            tds = tr.findall(".//td")
            if len(tds) < 3:
                continue
            texts = [td.text_content().strip() for td in tds]
            texts = [t if t else None for t in texts]

            time_cell = None
            for t in texts:
                if t and re.search(r"\d{1,2}[:.]\d{2}", t):
                    time_cell = t
                    break

            away = None
            home = None
            stadium = None
            joined = " ".join([t for t in texts if t])
            m_vs = re.search(r"([^\n\r\t]{1,30})\s*(?:vs|VS|[-–—]|대)\s*([^\n\r\t]{1,30})", joined)
            if m_vs:
                away = m_vs.group(1).strip()
                home = m_vs.group(2).strip()
            else:
                candidates = [t for t in texts if t and t != time_cell]
                if len(candidates) >= 2:
                    away = candidates[0]
                    home = candidates[1]
                if len(candidates) >= 3:
                    for c in candidates[2:]:
                        if "구장" in c or "stadium" in c.lower():
                            stadium = c
                            break

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
            if game["away"] or game["home"]:
                games.append(game)

        if games:
            return games

    return []


def fetch_schedule() -> List[Dict]:
    try:
        r = requests.get(SCHEDULE_URL, headers=UA, timeout=REQUEST_TIMEOUT)
    except Exception as exc:
        print(f"[ERR] network fetch failed for schedule: {exc}")
        return []

    if r.status_code != 200:
        print(f"[ERR] HTTP {r.status_code} fetching schedule")
        return []

    body = r.text or ""
    if not any(m in body for m in ("KBO", "경기", "일정", "Schedule")):
        print("[WARN] schedule page missing expected markers; parser may fail")

    games = try_lxml_parse_schedule(body)
    if games:
        return games

    # Fallback regex extraction (conservative)
    lines = body.splitlines()
    games = []
    for line in lines:
        if re.search(r"\d{1,2}[:.]\d{2}", line) and re.search(r"(vs|VS|대|[-–—])", line):
            text = re.sub(r"<[^>]+>", " ", line)
            text = re.sub(r"\s+", " ", text).strip()
            m = re.search(r"(\d{1,2}[:.]\d{2}).{0,60}?([^\d<>]{1,30})\s*(?:vs|VS|대|[-–—])\s*([^\d<>]{1,30})", text)
            if m:
                time_kst, time_et = parse_time_kst_to_et(m.group(1))
                away = m.group(2).strip()
                home = m.group(3).strip()
                games.append({
                    "away": away or None,
                    "home": home or None,
                    "stadium": None,
                    "time_kst": time_kst or None,
                    "time_et": time_et or None,
                    "away_starter": None,
                    "home_starter": None,
                })
    return games


def fetch_starters_from_mykbostats(games: List[Dict]) -> List[Dict]:
    try:
        r = requests.get(MYKBO_BASE, headers=UA, timeout=REQUEST_TIMEOUT)
    except Exception:
        return games

    body = r.text or ""
    if not body:
        return games

    for i, g in enumerate(games):
        away = g.get("away") or ""
        home = g.get("home") or ""
        if away and away in body:
            idx = body.find(away)
            snippet = body[max(0, idx - 200): idx + 200]
            m = re.search(r"(선발|Starter|SP)[:\s]*([A-Za-z\u00C0-\u017F\uAC00-\uD7AF\.\- ]{2,40})", snippet)
            if m:
                games[i]["away_starter"] = m.group(2).strip()
        if home and home in body:
            idx = body.find(home)
            snippet = body[max(0, idx - 200): idx + 200]
            m = re.search(r"(선발|Starter|SP)[:\s]*([A-Za-z\u00C0-\u017F\uAC00-\uD7AF\.\- ]{2,40})", snippet)
            if m:
                games[i]["home_starter"] = m.group(2).strip()
    return games


def main() -> int:
    print("kbo_precompute: starting conservative fetch for koreabaseball.com")
    games = []
    try:
        games = fetch_schedule()
    except Exception as exc:
        print(f"[ERR] unexpected error during schedule fetch: {exc}")
        games = []

    if not games:
        print("No games parsed or parse failed — producing empty games list (fail loud, empty).")
        write_output([])
        return 0

    try:
        games = fetch_starters_from_mykbostats(games)
    except Exception as exc:
        print(f"[WARN] enrichment from MyKBOStats failed: {exc}")

    normalized = []
    for g in games:
        normalized.append({
            "away": g.get("away") or None,
            "home": g.get("home") or None,
            "stadium": g.get("stadium") or None,
            "time_kst": g.get("time_kst") or None,
            "time_et": g.get("time_et") or None,
            "away_starter": g.get("away_starter") or None,
            "home_starter": g.get("home_starter") or None,
        })

    write_output(normalized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
