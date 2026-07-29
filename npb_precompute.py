"""
NPB slate + team stats fetcher — real data from npb.jp's official
monthly schedule/results pages.

Two jobs, one verified source:
1. Today's slate IN JST (which a US user sees as tomorrow's games
   tonight), with status: scheduled / postponed / final (ties reported
   as ties).
2. Real team stats computed from every final score of the season
   (all monthly pages parsed): W-L-T record, runs scored/allowed per
   game, last-10 form, and season head-to-head for each of today's
   matchups. Every number is arithmetic on scores npb.jp printed —
   nothing modeled, nothing estimated.

Anything the source doesn't state (e.g. starters) is TBD, never guessed.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

JST = ZoneInfo("Asia/Tokyo")
EASTERN = ZoneInfo("America/New_York")
SEASON_FIRST_MONTH = 3   # NPB opens late March
# One place for the season year. It was hardcoded inside the leaderboard
# URLs; the English name pages have to request the SAME year or the
# positional pairing would map one season's leaderboard onto another's.
SEASON_YEAR = 2026

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

TEAMS = {
    "巨人": "Yomiuri Giants", "ヤクルト": "Yakult Swallows",
    "阪神": "Hanshin Tigers", "中日": "Chunichi Dragons",
    "広島": "Hiroshima Carp", "DeNA": "Yokohama DeNA BayStars",
    "日本ハム": "Nippon-Ham Fighters", "ソフトバンク": "SoftBank Hawks",
    "楽天": "Rakuten Eagles", "オリックス": "Orix Buffaloes",
    "ロッテ": "Lotte Marines", "西武": "Seibu Lions",
}

STADIUMS = {
    "神宮": "Jingu Stadium", "甲子園": "Koshien Stadium",
    "東京ドーム": "Tokyo Dome", "横浜": "Yokohama Stadium",
    "マツダ": "Mazda Stadium", "バンテリン": "Vantelin Dome",
    "バンテリンド": "Vantelin Dome",
    "エスコンF": "Escon Field", "PayPay": "PayPay Dome",
    "みずほPayPay": "PayPay Dome", "楽天モバイル": "Rakuten Mobile Park",
    "京セラD大阪": "Kyocera Dome Osaka", "ZOZOマリン": "Zozo Marine Stadium",
    "ベルーナD": "Belluna Dome", "ベルーナドーム": "Belluna Dome",
}

OUT = Path("build_data") / "data" / "npb"

# Single-kanji team abbreviations used on npb.jp's league pitching
# leaderboards (pit_c.html / pit_p.html), e.g. "髙橋 遥人(神)" = Hanshin.
PIT_TEAM_ABBR = {
    "神": "Hanshin Tigers", "中": "Chunichi Dragons",
    "デ": "Yokohama DeNA BayStars", "ヤ": "Yakult Swallows",
    "巨": "Yomiuri Giants", "広": "Hiroshima Carp",
    "西": "Seibu Lions", "ソ": "SoftBank Hawks",
    "日": "Nippon-Ham Fighters", "オ": "Orix Buffaloes",
    "ロ": "Lotte Marines", "楽": "Rakuten Eagles",
}


# ------------------------------------------------------------
# JAPANESE -> ENGLISH PLAYER NAMES
# ------------------------------------------------------------
# Team names were already English (see _en_team). Player names were not:
# announced starters and the pitcher leaderboard both key on the kanji
# npb.jp prints, so every pitcher on the NPB page read as Japanese.
#
# THIS IS NOT DONE BY TRANSLITERATION, DELIBERATELY.
#
# Kanji readings are ambiguous for names in a way they aren't for
# ordinary words: the same characters are read differently by different
# people, and there is no rule that resolves it. 大谷 is Ohtani, but the
# same first character is "dai", "oo", or "hiro" depending on the person.
# Generating a reading would produce a confident, wrong, real-looking
# name — exactly the failure this codebase exists to avoid.
#
# So the mapping is FETCHED, not derived. npb.jp publishes the same
# leaderboards under /bis/eng/, romanised by the league itself. Rows are
# in identical order in both versions, so pairing them by position gives
# a real Japanese->English map with no guessing anywhere.
#
# When the English page can't be read, names stay in Japanese and the log
# says so. Japanese names are correct; invented romanisations are not.
_EN_STATS = ("https://npb.jp/bis/eng/{yr}/stats/pit_c.html",
             "https://npb.jp/bis/eng/{yr}/stats/pit_p.html")
_JP_STATS = ("https://npb.jp/bis/{yr}/stats/pit_c.html",
             "https://npb.jp/bis/{yr}/stats/pit_p.html")


def _get_html(url):
    """Fetch a page as text. Raises on failure so callers can log it."""
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def build_name_map(year):
    """{japanese_name: english_name} from npb.jp's own English pages.

    Empty dict when the English pages are unavailable — callers then keep
    the Japanese names, which are at least correct.
    """
    mapping = {}
    for jp_url, en_url in zip(_JP_STATS, _EN_STATS):
        try:
            jp_rows = _leader_names(_get_html(jp_url.format(yr=year)))
            en_rows = _leader_names(_get_html(en_url.format(yr=year)))
        except Exception as exc:
            print(f"  [names] English leaderboard unavailable ({exc}); "
                  f"keeping Japanese names.")
            continue
        if not jp_rows or not en_rows:
            continue
        if len(jp_rows) != len(en_rows):
            # Row counts must match or positional pairing is meaningless
            # and would silently attach the wrong English name.
            print(f"  [names] row count mismatch "
                  f"(jp={len(jp_rows)}, en={len(en_rows)}) — skipping this "
                  f"page rather than pairing rows that may not correspond.")
            continue
        for jp, en in zip(jp_rows, en_rows):
            if jp and en and jp != en:
                mapping[jp] = en
    print(f"  [names] {len(mapping)} pitcher names mapped to English."
          if mapping else
          "  [names] no English names available; NPB will display Japanese.")
    return mapping


def _leader_names(html):
    """Ordered player names from one leaderboard page."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    names = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 3:
            continue
        nm = _strip(re.sub(r"<[^>]+>", "", cells[1]))
        # Trim the trailing "(神)" team marker the Japanese page carries.
        nm = re.sub(r"\s*[(（][^)）]*[)）]\s*$", "", nm).strip()
        if nm:
            names.append(nm)
    return names


def en_name(name, name_map):
    """English name when we have a real one, otherwise unchanged."""
    if not name:
        return name
    return (name_map or {}).get(name.strip(), name)


def _avg(values):
    """Simple average that never blows up on an empty list."""
    return round(sum(values) / len(values), 2) if values else None


def _en_team(jp: str) -> str:
    return TEAMS.get(jp.strip(), jp.strip())


def _en_stadium(jp: str) -> str:
    return STADIUMS.get(jp.strip(), jp.strip())


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def fetch_month(year: int, month: int):
    url = f"https://npb.jp/games/{year}/schedule_{month:02d}_detail.html"
    try:
        r = requests.get(url, headers=UA, timeout=25)
        if r.status_code != 200:
            return None
        return r.content.decode("utf-8", errors="replace")
    except Exception:
        return None


def fetch_pitcher_stats() -> dict:
    """Season pitching lines (ERA, W-L, SV/HLD, IP, K, R/ER, etc.) from
    npb.jp's official league leaderboards — real box-score arithmetic
    NPB itself maintains, nothing modeled or estimated.

    Covers both leagues' three leaderboard tables each (innings-qualified,
    saves leaders, holds leaders), which together catch essentially every
    pitcher with meaningful season usage — starters land in the
    innings-qualified table, most high-leverage relievers in the other two.
    A pitcher appearing in more than one table just gets overwritten with
    an identical line, so no special de-duping logic is needed.

    Keyed by the pitcher's full name as npb.jp prints it (family + given,
    separated by a full-width space). The schedule page's starter
    announcement only gives the family name, so callers should match by
    team + surname prefix rather than expecting an exact key hit.

    Wrapped so a failure here (site down, markup change) degrades to an
    empty dict rather than taking down the whole NPB build — the slate
    itself must still ship even if pitcher stats can't be fetched.
    """
    stats = {}
    for url in (f"https://npb.jp/bis/{SEASON_YEAR}/stats/pit_c.html",
                f"https://npb.jp/bis/{SEASON_YEAR}/stats/pit_p.html"):
        try:
            r = requests.get(url, headers=UA, timeout=25)
            html = r.content.decode("utf-8", errors="replace") if r.status_code == 200 else None
        except Exception:
            html = None
        if not html:
            continue

        for row_m in re.finditer(r'<tr class="ststats">(.*?)</tr>', html, re.S):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_m.group(1), re.S)
            if len(cells) < 25:
                continue
            # Column order (verified against real npb.jp markup):
            # 0 rank, 1 name+team, 2 ERA, 3 G, 4 W, 5 L, 6 SV, 7 HLD, 8 HP,
            # 9 CG, 10 SHO, 11 no-walk, 12 win%, 13 batters, 14 IP,
            # 15 hits, 16 HR, 17 BB, 18 IBB, 19 HBP, 20 K, 21 WP, 22 balks,
            # 23 R, 24 ER.
            name_cell = cells[1]
            team_m = re.search(r'<span class="stteam">\((.)\)</span>', name_cell)
            team_abbr = team_m.group(1) if team_m else None
            name = _strip(re.sub(r'<span class="stteam">.*?</span>', '', name_cell))

            ip_cell = cells[14]
            ip_int = re.search(r'<span class="integer">(.*?)</span>', ip_cell)
            ip_dec = re.search(r'<span class="decimal">(.*?)</span>', ip_cell)
            innings = (_strip(ip_int.group(1)) if ip_int else _strip(ip_cell))
            if ip_dec:
                innings += _strip(ip_dec.group(1))

            stats[name] = {
                "team": PIT_TEAM_ABBR.get(team_abbr, team_abbr),
                "era": _strip(cells[2]),
                "games": _strip(cells[3]),
                "wins": _strip(cells[4]),
                "losses": _strip(cells[5]),
                "saves": _strip(cells[6]),
                "holds": _strip(cells[7]),
                "innings_pitched": innings,
                "hits_allowed": _strip(cells[15]),
                "home_runs_allowed": _strip(cells[16]),
                "walks": _strip(cells[17]),
                "strikeouts": _strip(cells[20]),
                "runs_allowed": _strip(cells[23]),
                "earned_runs": _strip(cells[24]),
            }
    return stats


def find_pitcher_stats(pitcher_stats: dict, surname: str, team: str):
    """Match a schedule-page starter (surname only) to their full stat
    line, scoped to the team they play for. Returns None if no real match
    is found — never guesses across teams or fabricates a line.

    AMBIGUITY IS A MISS, NOT A COIN FLIP.

    The schedule page announces starters by family name only, and this
    used to return the FIRST match on the team. Japanese surnames repeat
    heavily — Tanaka, Suzuki, Sato, Yamamoto — and a single NPB roster
    carrying two pitchers with the same family name is ordinary, not
    exotic. When that happened the page printed one pitcher's ERA, IP and
    strikeouts under the other's name: no error, no flag, a completely
    wrong line that looked exactly like a right one.

    Now every match on the team is collected. Exactly one is a real
    answer. Two or more means the surname alone cannot identify him, so
    this returns None and the page shows no line rather than a plausible
    wrong one — the same rule the rest of the site follows for data it
    cannot stand behind.
    """
    if not surname or not pitcher_stats:
        return None
    matches = [
        info for full_name, info in pitcher_stats.items()
        if info.get("team") == team
        # Split on the ideographic space OR a regular one. npb.jp uses
        # the ideographic form, but a single page switching separator
        # would silently stop every starter matching — cheap to cover.
        and (full_name == surname
             or re.split(r"[\u3000\s]", full_name)[0] == surname)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"  NPB: '{surname}' matches {len(matches)} pitchers on {team} "
              f"— surname alone can't identify him, showing no line.")
    return None


def parse_games(html: str, year: int):
    for m in re.finditer(r'<tr id="date(\d{4})"[^>]*>(.*?)</tr>', html, re.S):
        mmdd, row = m.group(1), m.group(2)
        team1 = re.search(r'<div class="team1">(.*?)</div>', row, re.S)
        team2 = re.search(r'<div class="team2">(.*?)</div>', row, re.S)
        if not team1 or not team2:
            continue

        home_jp, away_jp = _strip(team1.group(1)), _strip(team2.group(1))
        status, home_score, away_score = "scheduled", None, None
        if '<div class="cancel">' in row:
            status = "postponed"
        else:
            s1 = re.search(r'<div class="score1">(\d+)</div>', row)
            s2 = re.search(r'<div class="score2">(\d+)</div>', row)
            if s1 and s2:
                status = "final"
                home_score, away_score = int(s1.group(1)), int(s2.group(1))

        place = re.search(r'<div class="place">(.*?)</div>', row, re.S)
        time_m = re.search(r'<div class="time">\s*(\d{1,2}:\d{2})', row)

        # Announced starters live in two <div class="pit"> cells in the
        # last <td> of the row (verified against real npb.jp markup — the
        # <td> itself carries no class, only the inner divs do). For an
        # upcoming game each div reads "先発：<name>" (home listed first,
        # matching team1/team2 order). For a completed game the same divs
        # instead hold the decision pitchers, "勝：<name>" / "敗：<name>" /
        # "分：<name>" — those are NOT necessarily the starter, so they are
        # kept only as a raw reference string, never assigned as home/away
        # starter. Nothing present -> TBD, never guessed.
        home_sp, away_sp, sp_raw = None, None, None
        pit_divs = re.findall(r'<div class="pit">(.*?)</div>', row, re.S)
        entries = [t for t in (_strip(d) for d in pit_divs) if t]
        if len(entries) == 2:
            parts = [e.split('：', 1) for e in entries]
            labels = [p[0] if len(p) == 2 else None for p in parts]
            names = [p[1] if len(p) == 2 else p[0] for p in parts]
            if labels[0] == '先発' and labels[1] == '先発':
                home_sp, away_sp = names[0], names[1]
            else:
                sp_raw = ' / '.join(entries)
        elif entries:
            sp_raw = ' / '.join(entries)

        yield {
            "date": f"{year}-{mmdd[:2]}-{mmdd[2:]}",
            "home": _en_team(home_jp), "away": _en_team(away_jp),
            "stadium": _en_stadium(_strip(place.group(1))) if place else "TBD",
            "time_jst": time_m.group(1) if time_m else "TBD",
            "status": status,
            "home_score": home_score, "away_score": away_score,
            "home_sp": home_sp, "away_sp": away_sp, "sp_raw": sp_raw,
        }


def to_et(date_str: str, time_jst: str) -> str:
    try:
        dt = datetime.strptime(f"{date_str} {time_jst}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        return dt.astimezone(EASTERN).strftime("%-I:%M %p")
    except Exception:
        return "TBD"


def team_stats(finals: list) -> dict:
    """Per-team record, runs per game, last-10 — pure arithmetic on
    real final scores."""
    stats = {}
    for g in sorted(finals, key=lambda x: x["date"]):
        for side, opp_side in (("home", "away"), ("away", "home")):
            team = g[side]
            rec = stats.setdefault(team, {"w": 0, "l": 0, "t": 0,
                                          "rs": 0, "ra": 0, "g": 0,
                                          "recent": []})
            us, them = g[f"{side}_score"], g[f"{opp_side}_score"]
            rec["g"] += 1
            rec["rs"] += us
            rec["ra"] += them
            result = "T" if us == them else ("W" if us > them else "L")
            rec["w" if result == "W" else "l" if result == "L" else "t"] += 1
            rec["recent"].append(result)

    out = {}
    for team, r in stats.items():
        last10 = r["recent"][-10:]
        out[team] = {
            "record": f'{r["w"]}-{r["l"]}-{r["t"]}',
            "rs_pg": round(r["rs"] / r["g"], 2) if r["g"] else None,
            "ra_pg": round(r["ra"] / r["g"], 2) if r["g"] else None,
            "last10": f'{last10.count("W")}-{last10.count("L")}-{last10.count("T")}',
        }
    return out


def h2h(finals: list, a: str, b: str) -> dict:
    """Season head-to-head between two teams — record, every meeting's
    real scoreline, each team's average runs in those meetings, and the
    average total. All arithmetic on npb.jp's own final scores."""
    a_w = b_w = ties = 0
    a_runs, b_runs, totals, scorelines = [], [], [], []
    for g in sorted(finals, key=lambda x: x["date"]):
        pair = {g["home"], g["away"]}
        if pair != {a, b}:
            continue
        hs, as_ = g["home_score"], g["away_score"]
        a_sc = as_ if g["away"] == a else hs
        b_sc = as_ if g["away"] == b else hs
        a_runs.append(a_sc)
        b_runs.append(b_sc)
        totals.append(hs + as_)
        scorelines.append(f'{g["away"]} {g["away_score"]}-{g["home_score"]} {g["home"]} ({g["date"][5:]})')
        if hs == as_:
            ties += 1
        else:
            winner = g["home"] if hs > as_ else g["away"]
            if winner == a:
                a_w += 1
            else:
                b_w += 1
    return {"a_wins": a_w, "b_wins": b_w, "ties": ties, "games": a_w + b_w + ties,
            "a_avg_runs": _avg(a_runs), "b_avg_runs": _avg(b_runs),
            "avg_total": _avg(totals), "scorelines": scorelines}


def main():
    now_jst = datetime.now(JST)
    today = now_jst.strftime("%Y-%m-%d")

    all_games = []
    for month in range(SEASON_FIRST_MONTH, now_jst.month + 1):
        html = fetch_month(now_jst.year, month)
        if html:
            month_games = list(parse_games(html, now_jst.year))
            all_games.extend(month_games)
            print(f"  month {month:02d}: {len(month_games)} rows")

    finals = [g for g in all_games if g["status"] == "final"]
    stats = team_stats(finals)
    print(f"NPB: {len(finals)} real finals parsed across the season "
          f"({len(stats)} teams with stats)")

    try:
        pitcher_stats = fetch_pitcher_stats()
        # Japanese -> English, fetched from npb.jp's own English pages.
        # Empty when unavailable; names then stay Japanese, which is
        # correct, rather than being transliterated into a guess.
        name_map = build_name_map(SEASON_YEAR)
    except Exception as e:
        pitcher_stats = {}
        print(f"NPB: pitcher-stats fetch failed ({e}) — starters will ship without ERA/W-L/K")
    print(f"NPB: {len(pitcher_stats)} pitchers with season stats fetched")

    # Slate selection: today in Japan if it has games; otherwise the
    # NEXT upcoming date with games. See KBO pipeline for rationale.
    _future = sorted([g for g in all_games
                      if g["date"] >= today and g.get("status") != "final"],
                     key=lambda x: x["date"])
    todays = [g for g in all_games if g["date"] == today]
    slate_date = today
    if not todays and _future:
        slate_date = _future[0]["date"]
        todays = [g for g in all_games if g["date"] == slate_date]
        print(f"NPB: no games today ({today} JST) — showing next slate {slate_date}")
    games_out = []
    for g in todays:
        entry = {
            "away": g["away"], "home": g["home"],
            "stadium": g["stadium"],
            "time_jst": g["time_jst"],
            "time_et": to_et(g["date"], g["time_jst"]),
            "away_starter": g.get("away_sp") or "TBD",
            "home_starter": g.get("home_sp") or "TBD",
            "status": g["status"],
        }
        if g.get("sp_raw"):
            entry["starters_raw"] = g["sp_raw"]
        for side in ("away", "home"):
            sp_surname = g.get(f"{side}_sp")
            sp_stats = find_pitcher_stats(pitcher_stats, sp_surname, g[side])
            if sp_stats:
                # English name where the league publishes one. The MATCH
                # above still runs on the Japanese surname, because that's
                # what both the schedule and the leaderboard print — only
                # the displayed name is translated, so a missing mapping
                # costs a name in English, never a wrong pairing.
                sp_stats = {**sp_stats,
                            "name_en": en_name(sp_stats.get("name"), name_map)}
                entry[f"{side}_starter_stats"] = sp_stats
            # Announced starter, in English when we have it.
            if sp_surname:
                entry[f"{side}_sp"] = sp_surname
                entry[f"{side}_sp_en"] = en_name(sp_surname, name_map)
        print(f'  [verify-starters] {g["away"]} @ {g["home"]}: '
              f'home_sp={g.get("home_sp")!r} away_sp={g.get("away_sp")!r} raw={g.get("sp_raw")!r} '
              f'home_stats={"yes" if entry.get("home_starter_stats") else "no"} '
              f'away_stats={"yes" if entry.get("away_starter_stats") else "no"}')
        if g["status"] == "final":
            entry["final"] = f'{g["away"]} {g["away_score"]} - {g["home_score"]} {g["home"]}'
            if g["away_score"] == g["home_score"]:
                entry["status"] = "final (tie)"

        for side in ("away", "home"):
            s = stats.get(g[side])
            if s:
                entry[f"{side}_record"] = s["record"]
                entry[f"{side}_rs_pg"] = s["rs_pg"]
                entry[f"{side}_ra_pg"] = s["ra_pg"]
                entry[f"{side}_last10"] = s["last10"]

        hh = h2h(finals, g["away"], g["home"])
        if hh["games"] > 0:
            ties_bit = f'-{hh["ties"]}' if hh["ties"] else ""
            entry["h2h"] = (f'{g["away"]} {hh["a_wins"]}-{hh["b_wins"]}{ties_bit} '
                            f'{g["home"]} (2026, {hh["games"]} games)')
            entry["h2h_detail"] = {
                "avg_total": hh["avg_total"],
                "away_avg_runs": hh["a_avg_runs"],
                "home_avg_runs": hh["b_avg_runs"],
                "scorelines": hh["scorelines"],
            }
        games_out.append(entry)

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_jst": now_jst.strftime("%Y-%m-%d %H:%M"),
        "source": "npb.jp official monthly schedule/results",
        "slate_date_jst": slate_date,
        "games": games_out,
    }
    (OUT / "games.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"NPB: wrote {len(games_out)} games for {today} JST")
    if not games_out:
        print("NPB: empty slate — likely a league off-day. That is the honest state.")


if __name__ == "__main__":
    main()