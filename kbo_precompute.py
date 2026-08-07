"""
KBO slate + season data fetcher — real data from MyKBOStats, plus real
season stats from the official KBO stats site.

v2 adds the season layer: crawls every week's schedule page since
opening day, parses finals DEFENSIVELY, and — if nothing parses —
simply omits team stats and H2H rather than shipping anything invented.

v3 fixes a confirmed bug: MyKBOStats renders finished-game scores as
"5 : 0" (colon), the score pattern now matches that. Also adds the
real pitching leaderboard from eng.koreabaseball.com.

v4 adds a much more reliable second data source for team-level numbers:
eng.koreabaseball.com/Stats/TeamStats.aspx, which carries THREE things
this build never had a solid source for before:
  1. An OFFICIAL team-vs-team head-to-head win-loss-tie matrix — this
     replaces the old approach of reconstructing H2H by grepping
     individual game scorelines out of MyKBOStats, which only worked
     when the fragile per-game score regex actually matched.
  2. OFFICIAL team batting stats (AVG/OBP/SLG/OPS/HR/etc.), maintained
     by the league itself.
  3. OFFICIAL team pitching stats (ERA/WHIP/runs allowed/etc.), same
     standard.
Table identification is done by column-name signature (not position),
verified against a synthetic table built from real column headers
pulled from the live page before this shipped. If KBO changes the
page layout, identification simply fails to match and that section
is omitted — never guessed.

v4 also adds:
  - A real batting leaderboard (mirrors the existing pitching-leaders
    fetch, same two-page merge pattern), columns verified live against
    eng.koreabaseball.com/Stats/BattingLeaders.aspx (+ 02).
  - Home/away split, current streak, and per-team over/under trend
    against a few common reference totals — computed entirely from
    finals this pipeline already parses, so no new scraping risk.

CAVEAT — read this before trusting anything below blindly: the
TeamStats.aspx table-identification logic and BattingLeaders column
mapping were verified against the live site's actual HTML/column
headers at the time this was written, but NOT run end-to-end against
a live fetch inside this environment (no network access here). Check
the "KBO: team stats" / "KBO: batting leaders" log lines the first
time this runs in CI — if either logs a fetch/parse failure, that
section will simply be missing from the JSON (same honest-omission
policy as everything else in this file), not broken data.
"""

import json
import re
import time
from datetime import date, datetime, timedelta
from io import StringIO
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

KST = ZoneInfo("Asia/Seoul")
EASTERN = ZoneInfo("America/New_York")
SEASON_START = date(2026, 3, 17)   # first crawl week; pre-season weeks just parse empty

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

TEAMS = {
    "Kia": "Kia Tigers", "KT": "KT Wiz", "LG": "LG Twins",
    "Lotte": "Lotte Giants", "Doosan": "Doosan Bears", "NC": "NC Dinos",
    "Kiwoom": "Kiwoom Heroes", "Hanwha": "Hanwha Eagles",
    "Samsung": "Samsung Lions", "SSG": "SSG Landers",
}

# Short codes as they appear on eng.koreabaseball.com (TeamStats / *Leaders
# pages) mapped to the same full names used everywhere else in this file,
# so data from both sources joins cleanly on team name.
KBO_TEAM_CODE = {
    "SAMSUNG": "Samsung Lions", "KIA": "Kia Tigers", "KT": "KT Wiz",
    "LG": "LG Twins", "HANWHA": "Hanwha Eagles", "LOTTE": "Lotte Giants",
    "DOOSAN": "Doosan Bears", "KIWOOM": "Kiwoom Heroes", "NC": "NC Dinos",
    "SSG": "SSG Landers",
}

# app/ is not on sys.path for a script run from the repo root, and this
# file had never needed it until the weather engine arrived. The import
# was inside main(), so it survived a compile check AND a green test
# suite and only failed 800 lines into a live run — after the fetch, in
# a step nothing else could see. Hoisted here beside the path insert,
# the same shape wnba_precompute.py uses, so a bad import is now an
# immediate ImportError instead of a late one.
sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from engines.intl_slate import coverage_line  # noqa: E402
from engines.intl_weather import (  # noqa: E402
    forecast as _wx,
    summarize as _wxsum,
    venue_for_game as _venue_for,
)

OUT = Path("build_data") / "data" / "kbo"

GAME_LINE = re.compile(
    r'<a[^>]*href="/games/(\d+)-([A-Za-z]+)-vs-([A-Za-z]+)-(\d{8})"[^>]*>(.*?)</a>',
    re.S,
)
# Real finished-game text, confirmed against actual CI log output:
# "Kia Tigers 2 NC Dinos 3 Final" — away name, away score, home name,
# home score, then "Final". No colon anywhere (an earlier colon-based
# pattern here was wrong and matched zero real finals in production —
# see the changelog in the module docstring). Since each game's away/
# home full names are already known from the URL slug, the score
# pattern is built per-game anchored on those literal names rather
# than a generic digit pattern — far less likely to misfire on some
# other pair of numbers in the line.
def _score_pattern(away_full, home_full):
    return re.compile(re.escape(away_full) + r'\D*(\d{1,3})\D+?' + re.escape(home_full) + r'\D*(\d{1,3})')


POSTPONED_PAT = re.compile(r'postponed|cancell?ed', re.I)
FINAL_PAT = re.compile(r'final', re.I)

PITCHING_LEADER_URLS = (
    "https://eng.koreabaseball.com/Stats/PitchingLeaders.aspx",
    "https://eng.koreabaseball.com/Stats/PitchingLeaders02.aspx",
)
# Verified live: page1 has RK/PLAYER/TEAM/AVG/G/PA/AB/R/H/2B/3B/HR/TB/RBI/
# SB/CS/SAC/SF; page2 has RK/PLAYER/TEAM/BB/IBB/HBP/SO/GIDP/SLG/OBP/E/
# SBPCT/BB-K/XBH-H/MH/OPS/RISP/PH.
BATTING_LEADER_URLS = (
    "https://eng.koreabaseball.com/Stats/BattingLeaders.aspx",
    "https://eng.koreabaseball.com/Stats/BattingLeaders02.aspx",
)
TEAM_STATS_URL = "https://eng.koreabaseball.com/Stats/TeamStats.aspx"

OU_LINES = (7.5, 8.5, 9.5)  # informational reference totals, not a sportsbook line


def _team(short):
    return TEAMS.get(short, short)


def _strip(html):
    return re.sub(r"<[^>]+>", " ", html)


def fetch(url):
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


# THE 2026-08 REBUILD MOVED PROBABLES OFF THE GAME PAGE.
#
# parse_starters() used to read <div class="away-starter"> off each
# game-detail page. mykbostats shipped "v3 Build 886 (2026-08-04)", an
# Elixir/Phoenix rewrite, and that markup went with it. Measured from
# Actions on an upcoming game (13800-SSG-vs-NC-20260809): the words
# probable, starter, pitcher and the Korean 선발 / 예고 each appear ZERO
# times; there is no application/json blob and no JSON-bearing data-*
# attribute; /games/{slug}.json returns HTML and /games/{slug}/probables
# 404s. So it is not renamed, not client-side, and not behind an API —
# it is simply not on that page any more. The week schedule page has no
# player links either.
#
# It is on the HOMEPAGE, one line inside each game-card anchor:
#
#     Hanwha Eagles Samsung Lions 31° 6:30pm Daegu
#         Starters: Park Jun-yeong vs. Chris Paddack
#
# with "Compare starting pitchers →" linking to
#     /stats/compare?pids=15400,15284,15357,...
# which is two ids per game in slate order — the ids the old parser used
# to read off the anchors.
#
# WHY THIS KEYS ON TEXT AND HREF, NOT CLASS NAMES. The class vocabulary
# has now changed under this parser once, and KBO pitcher matchups ran
# blind for as long as nobody noticed, because a regex that matches
# nothing returns an empty dict without raising. The href pattern and
# the visible words "Starters:" and "vs." are the product rather than
# the styling, so they are what a redesign is least likely to touch.
#
# ONE REQUEST FOR THE WHOLE SLATE, replacing one per upcoming game.
#
# CAVEAT, and it is a real one: the homepage carries TODAY only. Games
# further out resolve to None and stay TBD, which is correct — nobody
# publishes them yet — but it means this can never fill a week ahead.
STARTERS_LINE = re.compile(r"Starters:\s*(.+?)\s+vs\.\s+(.+?)\s*$")
# "... 31\u00b0 6:30pm Daegu Starters: ..." / "... 6:30pm Seoul-Jamsil Chance
# of Heat Cancellation Starters: ...". The venue runs from the clock to
# whichever of those two labels comes next, or to the end of the card.
HOME_TIME_VENUE = re.compile(
    r"(\d{1,2}:\d{2}\s*[ap]m)\s+(.+?)(?:\s+(?:Chance of|Starters:)|$)",
    re.I)
HOME_GAME_A = re.compile(r'<a[^>]*href="/games/([^"]+)"[^>]*>(.*?)</a>', re.S)

# HEAT. The same stripped card text that carries "Starters:" also carries
# a temperature and, on at-risk games, a forward-looking void warning:
#
#   Hanwha Eagles Samsung Lions 31° 6:30pm Daegu
#       Chance of Heat Cancellation
#
# POSTPONED_PAT already catches "Canceled" once it happens, which is the
# half that arrives too late to act on. This is the half that does not.
# Measured live: the whole 2026-08-05 slate was heat-canceled, and the
# Aug 6 page carried three of these warnings in advance.
#
# Worded loosely on purpose — "heat" near "cancel" rather than the exact
# sentence — because the wording is the site's copy, not its data, and
# is likelier to be reworded than dropped. Rule 18 says key on the
# product; this keys on the two words the product cannot lose.
HEAT_RISK_PAT = re.compile(r'chance[^.]{0,40}heat[^.]{0,40}cancell?ation',
                           re.I)
# Either the literal degree sign or the HTML entity: _strip() removes
# tags, not entities, and which one a template emits is a rendering
# detail nobody should have to re-discover.
TEMP_PAT = re.compile(r'(\d{1,2})\s*(?:°|&deg;)')
COMPARE_PIDS = re.compile(r'href="/stats/compare\?pids=([^"&]+)"')

_STARTER_KEYS = ("away_starter", "home_starter", "away_starter_id",
                 "home_starter_id", "away_starter_stats", "home_starter_stats")


def _no_starters():
    return {k: None for k in _STARTER_KEYS}


def parse_homepage_starters(html):
    """{game_id: {away_starter, home_starter, ...ids...}} off the homepage.

    Keyed by the NUMERIC game id rather than the full slug: the id is the
    stable half of "13777-Hanwha-vs-Samsung-20260805", and a team-name or
    date-format change in the slug would otherwise silently match nothing
    — the same failure this whole function exists to replace.

    A game with no "Starters:" line is omitted rather than recorded as
    empty, so the caller can tell "not announced" from "announced as
    nothing". Absent stays absent; nothing here guesses.
    """
    out, ordered = {}, []
    for slug, inner in HOME_GAME_A.findall(html):
        text = re.sub(r"\s+", " ", _strip(inner)).strip()
        m = STARTERS_LINE.search(text)
        if not m:
            continue
        away, home = m.group(1).strip(), m.group(2).strip()
        if not away or not home:
            continue
        gid = slug.split("-", 1)[0]
        entry = _no_starters()
        entry["away_starter"], entry["home_starter"] = away, home
        out[gid] = entry
        ordered.append(gid)

    # Ids only when the count matches exactly two per game. A partial or
    # surprising list is dropped whole rather than aligned on a guess —
    # an id attached to the wrong pitcher is worse than no id, because
    # every downstream lookup would silently describe someone else.
    cm = COMPARE_PIDS.search(html)
    if cm and ordered:
        pids = [p for p in re.split(r"%2C|,", cm.group(1)) if p.strip()]
        if len(pids) == 2 * len(ordered):
            for n, gid in enumerate(ordered):
                out[gid]["away_starter_id"] = pids[2 * n]
                out[gid]["home_starter_id"] = pids[2 * n + 1]
        else:
            print(f"  KBO: compare link carried {len(pids)} pids for "
                  f"{len(ordered)} games with starters — ids left unset")
    return out


def parse_homepage_conditions(html):
    """{game_id: {"temp_c": int|None, "heat_risk": bool}} off the homepage.

    Deliberately a SEPARATE function from parse_homepage_starters rather
    than more keys on the same entry. That one omits a game with no
    "Starters:" line so a caller can tell "not announced" from
    "announced as nothing" — and a heat warning routinely lands on a
    game whose pitchers are not announced yet, which is exactly the game
    a bettor most needs warned about. Merging them would have forced a
    choice between breaking that contract and dropping the warning.

    A card with neither a temperature nor a warning is omitted. Absent
    stays absent; nothing here guesses a comfortable day.
    """
    out = {}
    for slug, inner in HOME_GAME_A.findall(html):
        text = re.sub(r"\s+", " ", _strip(inner)).strip()
        risk = bool(HEAT_RISK_PAT.search(text))
        tm = TEMP_PAT.search(text)
        if not risk and not tm:
            continue
        gid = slug.split("-", 1)[0]
        out[gid] = {"temp_c": int(tm.group(1)) if tm else None,
                    "heat_risk": risk}
    return out


_HOMEPAGE_CACHE = {}


def _homepage_html():
    """The homepage, fetched at most once per process.

    Both readings come off the same document, and hitting a fan-run site
    twice for one page we already have would be rude as well as slower.
    Caches the failure too, so a dead host costs one timeout rather than
    two.
    """
    if "html" not in _HOMEPAGE_CACHE:
        try:
            r = requests.get("https://mykbostats.com/", headers=UA, timeout=25)
            _HOMEPAGE_CACHE["html"] = r.text if r.status_code == 200 else ""
            if r.status_code != 200:
                print(f"  KBO: homepage returned HTTP {r.status_code}")
        except Exception as exc:
            print(f"  KBO: homepage fetch failed ({exc})")
            _HOMEPAGE_CACHE["html"] = ""
    return _HOMEPAGE_CACHE["html"]


def fetch_homepage_conditions():
    """Today's temperature and heat-void risk for the slate, or {}."""
    html = _homepage_html()
    if not html:
        return {}
    out = parse_homepage_conditions(html)
    at_risk = sum(1 for v in out.values() if v["heat_risk"])
    print(f"  KBO: homepage — {len(out)} game cards carried conditions, "
          f"{at_risk} flagged Chance of Heat Cancellation")
    return out


def parse_homepage_schedule(html):
    """{game_id: {"venue": str|None, "time": str|None}} off the homepage.

    SEPARATE FROM THE STARTERS READER ON PURPOSE. Membership of that map
    means "this game has announced starters", and tests depend on it —
    a heat warning or a first-pitch time routinely lands on a game whose
    pitchers are not posted, which is exactly the game a bettor most
    needs to see. Folding these together would make an entry mean two
    different things.

    WHY THIS EXISTS AT ALL. parse_week() reads venue and start time off
    the SCHEDULE page, keyed on <div class="venue"> and a datetime=
    attribute. The mykbostats v3 rewrite killed both the same way it
    killed away-starter, so every KBO card has rendered
    "TBD - TBD KST / TBD ET" since. That is the third and fourth regex
    in this file to die to one redesign.

    The homepage card already says "6:30pm Daegu" in plain text, so
    today's slate is repairable from a request we already make. It
    cannot help FUTURE dates — the homepage carries today only.

    Measured live at 13:13 KST on 2026-08-06: every card had a time and
    a venue, and not one had a starter. That is why these are read
    independently.
    """
    out = {}
    for slug, inner in HOME_GAME_A.findall(html):
        text = re.sub(r"\s+", " ", _strip(inner)).strip()
        m = HOME_TIME_VENUE.search(text)
        if not m:
            continue
        # Trailing junk is dropped rather than shipped: a wrong stadium
        # is worse than a missing one, because the forecast would then
        # describe the wrong city with full confidence.
        v = m.group(2).strip(" ,-\u00b7")
        out[slug.split("-", 1)[0]] = {
            "time": m.group(1).strip(),
            "venue": v if 1 < len(v) <= 40 else None,
        }
    return out


def _kst_24h(clock):
    """"6:30pm" -> "18:30", or None. None keeps the field TBD rather
    than inventing a first pitch, which is the whole convention here."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*([ap])m", (clock or "").strip(), re.I)
    if not m:
        return None
    h, mins, ap = int(m.group(1)), m.group(2), m.group(3).lower()
    if h == 12:
        h = 0
    if ap == "p":
        h += 12
    return f"{h:02d}:{mins}"


def _kbo_et(date_iso, kst_24h):
    """KST wall clock -> the same instant in ET, or "TBD".

    Goes through a real timezone conversion rather than subtracting a
    fixed offset: Korea does not observe DST but the US does, so the gap
    is 13 hours for part of the year and 14 for the rest.
    """
    try:
        dt = datetime.strptime(f"{date_iso} {kst_24h}", "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=KST).astimezone(EASTERN).strftime("%-I:%M %p")
    except Exception:
        return "TBD"


def fetch_homepage_starters():
    """Today's probables for the whole slate in one request, or {}.

    Returns {} on any failure, which leaves every game TBD — the same
    state the site itself shows before an announcement, and the same one
    this pipeline was already in while the old parser matched nothing.
    """
    html = _homepage_html()
    if not html:
        print("  KBO: no homepage — no probables this run")
        return {}

    found = parse_homepage_starters(html)
    cards = len(HOME_GAME_A.findall(html))
    print(f"KBO: homepage — {len(found)} of {cards} game cards carried a "
          f"Starters line")
    if not found:
        # WHEN THIS IS NORMAL, so a zero is not misread as a break.
        # Measured 0 at 06:36 KST on a day the slate was heat-canceled,
        # about twelve hours before first pitch. The scheduled refresh
        # runs at 18:20 KST, which is after the announcement window.
        print("  0 is expected before the announcement and on a canceled "
              "slate. If the 18:20 KST refresh also reports 0 on a day that "
              "is played, the line has moved again — re-probe, don't widen "
              "the regex.")
    return found


def fetch_homepage_schedule():
    """Today's first-pitch time and venue for the whole slate, or {}.

    A SIBLING of fetch_homepage_starters, not part of it. Both read the
    same cached document (_homepage_html caches, so this costs no extra
    request), but they answer different questions and a game routinely
    has one and not the other — measured live at 13:13 KST on
    2026-08-06, every card had a time and a venue and NOT ONE had a
    starter.

    WHY THIS FUNCTION HAD TO EXIST. The caller in main() was written
    against a two-value contract — `_hp, _hs = fetch_homepage_starters()`
    — that fetch_homepage_starters never had. It returns one dict, so
    every run since raised

        ValueError: not enough values to unpack (expected 2, got 0)

    and the KBO step of intl-late-refresh exited 1 (run 84386218583).
    Worse than the crash: on a slate where exactly two games HAD
    announced starters, unpacking would have SUCCEEDED and bound two
    game-id strings to _hp and _hs, and every lookup after it would have
    quietly found nothing. The loud failure was luck.

    Returns {} on any failure, which leaves the schedule page's own
    (broken since the v3 rewrite) values in place — TBD rather than a
    guess.
    """
    html = _homepage_html()
    if not html:
        return {}
    out = parse_homepage_schedule(html)
    cards = len(HOME_GAME_A.findall(html))
    print(f"KBO: homepage — {len(out)} of {cards} game cards carried a "
          f"time and venue")
    return out


def _card_time_venue(inner):
    """(kst_24h, venue) read out of a schedule card's VISIBLE TEXT.

    THE V3 REWRITE MOVED BOTH, AND ONE OF THEM SURVIVED. Probe run
    84409273265 fetched the week of 2026-08-18 from Actions and dumped
    a real upcoming card:

        <span class="ds-game-card__state is-time ">
          <time datetime="2026-08-18T10:00:00Z">7:00pm</time>
        </span>
        <span class="ds-game-card__sub is-prose">Daejeon</span>

    So `datetime=` is alive and parse_week's time regex still works —
    but `<div class="venue">` is gone, and the visible text now reads

        Kia Tigers Hanwha Eagles 7:00pm Daejeon

    which is the SAME SHAPE the homepage uses. HOME_TIME_VENUE already
    reads that shape, so this reuses it rather than adding a fifth
    regex to the file that has lost four (rule 18: key on the product).

    WHY NOT KEY ON `ds-game-card__sub`. That class holds the venue on an
    upcoming card and the words "Extreme Heat" on a canceled one. Keying
    on it would put a weather note in the stadium field and then forecast
    a city that does not exist. Requiring a CLOCK immediately before the
    venue is what separates them, and it is the product's own logic: a
    game with no first pitch has no venue to show.

    A card with no clock — final, canceled, postponed — yields (None,
    None) and the caller leaves both TBD. Absent stays absent.
    """
    text = re.sub(r"\s+", " ", _strip(inner)).strip()
    m = HOME_TIME_VENUE.search(text)
    if not m:
        return None, None
    v = m.group(2).strip(" ,-\u00b7")
    return _kst_24h(m.group(1)), (v if 1 < len(v) <= 40 else None)


def parse_week(html, today_str, sample_holder):
    for m in GAME_LINE.finditer(html):
        game_id, away_short, home_short, yyyymmdd, inner = m.groups()
        gdate = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"

        dt_utc = None
        t = re.search(r'datetime="([0-9T:+.Z-]+)"', inner)
        if t:
            try:
                dt_utc = datetime.fromisoformat(t.group(1).replace("Z", "+00:00"))
            except ValueError:
                pass

        venue = re.search(r'<div class="venue">\s*(.*?)\s*</div>', inner, re.S)

        # The v3 rewrite killed the venue div. Card text still carries
        # both, so read it and use it ONLY where the markup gave nothing
        # — a scraped value always wins, and if the div ever comes back
        # this quietly stops firing.
        _t_kst, _t_venue = _card_time_venue(inner)

        stadium = (re.sub(r"\s+", " ", _strip(venue.group(1))).strip()
                   if venue else (_t_venue or "TBD"))
        if dt_utc:
            time_kst = dt_utc.astimezone(KST).strftime("%H:%M")
            time_et = dt_utc.astimezone(EASTERN).strftime("%-I:%M %p")
        elif _t_kst:
            time_kst = _t_kst
            time_et = _kbo_et(gdate, _t_kst)
        else:
            time_kst = time_et = "TBD"

        g = {
            "date": gdate,
            "away": _team(away_short), "home": _team(home_short),
            "game_id": game_id,
            "game_slug": f"{game_id}-{away_short}-vs-{home_short}-{yyyymmdd}",
            "stadium": stadium,
            "time_kst": time_kst,
            "time_et": time_et,
            "status": "scheduled",
        }

        if gdate < today_str:
            text = re.sub(r"\s+", " ", _strip(inner))
            if sample_holder and sample_holder.get("sample") is None:
                sample_holder["sample"] = text[:400]
            if FINAL_PAT.search(text):
                sm = _score_pattern(g["away"], g["home"]).search(text)
                if sm:
                    g["away_score"], g["home_score"] = int(sm.group(1)), int(sm.group(2))
                    g["status"] = "final"
            elif POSTPONED_PAT.search(text):
                g["status"] = "postponed"
        yield g


def _val(row, col):
    v = row.get(col)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    return v


def _clean_columns(df):
    """koreabaseball.com appends sort-arrow glyphs (▼/▲) to sortable
    column headers, so pandas reads "ERA▼" instead of "ERA" and the
    column match below fails — the cause of the "0 pitchers/batters
    fetched" bug. Strip trailing arrows and whitespace so headers match
    their plain names. Returns the same df with cleaned column labels."""
    df.columns = [re.sub(r"[\u25b2\u25bc\s]+$", "", str(c)).strip() for c in df.columns]
    return df


def _pick_table(page_tables, required_cols):
    """Finds the table whose columns are a superset of required_cols.
    Replaces an earlier "just take the biggest table on the page"
    heuristic that, in production, picked the wrong table whenever some
    other table on the page (nav, related-players, whatever) happened
    to have more rows than the actual stats leaderboard — confirmed as
    the cause of a real bug (20 pitchers/batters fetched, 0 written,
    because the merged frame never actually had an ERA/OPS column).
    Returns None if no table matches, so the caller can log and skip
    that section rather than silently use the wrong data.

    Column headers are cleaned of sort-arrow glyphs first, so "ERA▼"
    matches a required "ERA"."""
    for t in page_tables:
        _clean_columns(t)
        cols = set(str(c) for c in t.columns)
        if required_cols <= cols:
            return t
    return None


def fetch_pitcher_stats():
    """Real season pitching lines from the official KBO leaderboard."""
    tables = []
    for url, required in zip(PITCHING_LEADER_URLS, ({"PLAYER", "TEAM", "ERA"}, {"PLAYER", "TEAM", "WHIP"})):
        try:
            r = requests.get(url, headers=UA, timeout=25)
            r.raise_for_status()
            page_tables = pd.read_html(StringIO(r.text))
        except Exception as exc:
            print(f"  KBO pitching leaders fetch failed for {url}: {exc}")
            continue
        picked = _pick_table(page_tables, required)
        if picked is None:
            print(f"  KBO pitching leaders: no table on {url} matched columns {required}")
            continue
        tables.append(picked)

    if not tables:
        return {}

    df = tables[0]
    for extra in tables[1:]:
        if "PLAYER" not in extra.columns or "TEAM" not in extra.columns:
            continue
        df = df.merge(extra, on=["PLAYER", "TEAM"], how="outer", suffixes=("", "_dup"))

    stats = {}
    for _, row in df.iterrows():
        name = str(row.get("PLAYER", "")).strip()
        team_code = str(row.get("TEAM", "")).strip()
        if not name or name.lower() == "nan":
            continue
        stats[name] = {
            "team": KBO_TEAM_CODE.get(team_code, team_code),
            "era": _val(row, "ERA"), "games": _val(row, "G"),
            "wins": _val(row, "W"), "losses": _val(row, "L"),
            "saves": _val(row, "SV"), "holds": _val(row, "HLD"),
            # GS = games STARTED. Captured if the leaderboard publishes
            # it, None if not. project_kbo_slate was dividing innings by
            # G (total appearances) and calling the result "IP per game
            # started" — identical for a pure starter, badly wrong for a
            # swingman who also relieves.
            "games_started": _val(row, "GS"),
            "innings_pitched": _val(row, "IP"), "strikeouts": _val(row, "SO"),
            "walks": _val(row, "BB"), "whip": _val(row, "WHIP"),
            "quality_starts": _val(row, "QS"),
            "runs_allowed": _val(row, "R"), "earned_runs": _val(row, "ER"),
        }
    return stats


def fetch_batting_leaders():
    """Real season batting lines from the official KBO leaderboard —
    same two-page merge pattern as the pitching leaders fetch. Columns
    verified live: page1 RK/PLAYER/TEAM/AVG/G/PA/AB/R/H/2B/3B/HR/TB/
    RBI/SB/CS/SAC/SF; page2 adds BB/IBB/HBP/SO/GIDP/SLG/OBP/E/SBPCT/
    BB-K/XBH-H/MH/OPS/RISP/PH. Degrades to {} on any failure — the KBO
    build must still ship without this section rather than break."""
    tables = []
    for url, required in zip(BATTING_LEADER_URLS, ({"PLAYER", "TEAM", "AVG", "HR"}, {"PLAYER", "TEAM", "OPS", "SLG"})):
        try:
            r = requests.get(url, headers=UA, timeout=25)
            r.raise_for_status()
            page_tables = pd.read_html(StringIO(r.text))
        except Exception as exc:
            print(f"  KBO batting leaders fetch failed for {url}: {exc}")
            continue
        picked = _pick_table(page_tables, required)
        if picked is None:
            print(f"  KBO batting leaders: no table on {url} matched columns {required}")
            continue
        tables.append(picked)

    if not tables:
        return {}

    df = tables[0]
    for extra in tables[1:]:
        if "PLAYER" not in extra.columns or "TEAM" not in extra.columns:
            continue
        df = df.merge(extra, on=["PLAYER", "TEAM"], how="outer", suffixes=("", "_dup"))

    leaders = {}
    for _, row in df.iterrows():
        name = str(row.get("PLAYER", "")).strip()
        team_code = str(row.get("TEAM", "")).strip()
        if not name or name.lower() == "nan":
            continue
        leaders[name] = {
            "team": KBO_TEAM_CODE.get(team_code, team_code),
            "avg": _val(row, "AVG"), "games": _val(row, "G"),
            "pa": _val(row, "PA"), "ab": _val(row, "AB"),
            "runs": _val(row, "R"), "hits": _val(row, "H"),
            "doubles": _val(row, "2B"), "triples": _val(row, "3B"),
            "hr": _val(row, "HR"), "rbi": _val(row, "RBI"),
            "sb": _val(row, "SB"), "obp": _val(row, "OBP"),
            "slg": _val(row, "SLG"), "ops": _val(row, "OPS"),
            "so": _val(row, "SO"), "bb": _val(row, "BB"),
            "risp_avg": _val(row, "RISP"),
        }
    return leaders


def _parse_ip(raw):
    """KBO renders partial innings as e.g. '771   2/3'. Converts to a
    plain float (771.667); returns None if unparseable."""
    raw = str(raw).strip()
    m = re.match(r"(\d+)\s+(\d)/(\d)", raw)
    if m:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return round(whole + num / den, 3)
    try:
        return float(raw)
    except ValueError:
        return None


def fetch_team_stats():
    """Official team-vs-team H2H matrix + official team batting/pitching
    stats from eng.koreabaseball.com/Stats/TeamStats.aspx. Tables are
    identified by column-name signature (not position), so a layout
    change causes a clean miss rather than silently misreading a table.
    Returns (h2h_dict, batting_dict, pitching_dict) — any of the three
    can come back empty if its table wasn't found, independent of the
    others.
    """
    try:
        r = requests.get(TEAM_STATS_URL, headers=UA, timeout=25)
        r.raise_for_status()
        tables = pd.read_html(StringIO(r.text))
    except Exception as exc:
        print(f"  KBO team stats fetch failed: {exc}")
        return {}, {}, {}

    h2h_matrix = bat1 = bat2 = pit1 = pit2 = None
    for t in tables:
        _clean_columns(t)
        cols = set(str(c) for c in t.columns)
        if "TEAM" not in cols:
            continue
        if any(str(c).endswith("(W-L-T)") for c in t.columns):
            h2h_matrix = t
        elif {"AVG", "HR", "G"} <= cols:
            bat1 = t
        elif {"OPS", "SLG", "OBP"} <= cols and "ERA" not in cols:
            bat2 = t
        elif "ERA" in cols:
            pit1 = t
        elif {"WHIP", "ER"} <= cols:
            pit2 = t

    h2h = {}
    if h2h_matrix is not None:
        opp_cols = [c for c in h2h_matrix.columns if str(c).endswith("(W-L-T)")]
        for _, row in h2h_matrix.iterrows():
            team = str(row["TEAM"]).strip()
            if team.upper() == "TOTAL":
                continue
            for oc in opp_cols:
                opp = str(oc).split(" (")[0].strip()
                val = str(row[oc]).strip()
                if opp == team or val in ("■", "nan", ""):
                    continue
                a = KBO_TEAM_CODE.get(team, team)
                b = KBO_TEAM_CODE.get(opp, opp)
                h2h[(a, b)] = val
    else:
        print("  KBO team stats: H2H matrix table not found on page")

    batting = {}
    if bat1 is not None:
        merged = bat1.merge(bat2, on="TEAM", how="outer") if bat2 is not None else bat1
        for _, row in merged.iterrows():
            team = KBO_TEAM_CODE.get(str(row["TEAM"]).strip(), str(row["TEAM"]).strip())
            g = _val(row, "G")
            runs = _val(row, "R")
            batting[team] = {
                "avg": _val(row, "AVG"), "obp": _val(row, "OBP"), "slg": _val(row, "SLG"),
                "ops": _val(row, "OPS"), "hr": _val(row, "HR"), "so": _val(row, "SO"),
                "games": g, "runs": runs,
                "runs_per_game": round(runs / g, 2) if (runs is not None and g) else None,
            }
    else:
        print("  KBO team stats: team batting table not found on page")

    pitching = {}
    if pit1 is not None:
        merged = pit1.merge(pit2, on="TEAM", how="outer") if pit2 is not None else pit1
        for _, row in merged.iterrows():
            team = KBO_TEAM_CODE.get(str(row["TEAM"]).strip(), str(row["TEAM"]).strip())
            g = _val(row, "G")
            runs_allowed = _val(row, "R")
            pitching[team] = {
                "era": _val(row, "ERA"), "whip": _val(row, "WHIP"),
                "ip": _parse_ip(row.get("IP")), "games": g,
                "runs_allowed": runs_allowed,
                "runs_allowed_per_game": round(runs_allowed / g, 2) if (runs_allowed is not None and g) else None,
                "quality_starts": _val(row, "QS"), "saves": _val(row, "SV"), "holds": _val(row, "HLD"),
            }
    else:
        print("  KBO team stats: team pitching table not found on page")

    return h2h, batting, pitching


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def team_form(finals):
    """Per-team record/form from parsed finals, including home/away
    splits and current streak — all derived from finals this pipeline
    already has, no new scraping."""
    per = {}
    for g in sorted(finals, key=lambda x: x["date"]):
        for side, opp in (("home", "away"), ("away", "home")):
            t = per.setdefault(g[side], {
                "w": 0, "l": 0, "t": 0, "rs": [], "ra": [], "res": [],
                "home_w": 0, "home_l": 0, "home_t": 0,
                "away_w": 0, "away_l": 0, "away_t": 0,
                "home_rs": [], "home_ra": [], "away_rs": [], "away_ra": [],
            })
            us, them = g[f"{side}_score"], g[f"{opp}_score"]
            t["rs"].append(us)
            t["ra"].append(them)
            r = "T" if us == them else ("W" if us > them else "L")
            t["w" if r == "W" else "l" if r == "L" else "t"] += 1
            t["res"].append(r)
            t[f"{side}_w" if r == "W" else f"{side}_l" if r == "L" else f"{side}_t"] += 1
            t[f"{side}_rs"].append(us)
            t[f"{side}_ra"].append(them)

    out = {}
    for team, t in per.items():
        l10 = t["res"][-10:]
        ties = f'-{t["t"]}' if t["t"] else ""
        home_ties = f'-{t["home_t"]}' if t["home_t"] else ""
        away_ties = f'-{t["away_t"]}' if t["away_t"] else ""

        streak_type, streak_len = None, 0
        if t["res"]:
            streak_type = t["res"][-1]
            for r in reversed(t["res"]):
                if r == streak_type:
                    streak_len += 1
                else:
                    break

        out[team] = {
            "record": f'{t["w"]}-{t["l"]}{ties}',
            "rs_pg": _avg(t["rs"]), "ra_pg": _avg(t["ra"]),
            "last10": f'{l10.count("W")}-{l10.count("L")}'
                      + (f'-{l10.count("T")}' if l10.count("T") else ""),
            "streak": f'{streak_len}{streak_type}' if streak_type else None,
            "home_record": f'{t["home_w"]}-{t["home_l"]}{home_ties}',
            "away_record": f'{t["away_w"]}-{t["away_l"]}{away_ties}',
            "home_rs_pg": _avg(t["home_rs"]), "home_ra_pg": _avg(t["home_ra"]),
            "away_rs_pg": _avg(t["away_rs"]), "away_ra_pg": _avg(t["away_ra"]),
        }
    return out


def over_under_trend(finals, team=None):
    """Informational O/U trend from real finals only — NOT tied to any
    sportsbook's actual posted total for tonight (this pipeline has no
    access to betting lines). Computed against a few common reference
    totals so it's useful regardless of where a book sets it."""
    games = finals if team is None else [g for g in finals if team in (g["home"], g["away"])]
    totals = [g["home_score"] + g["away_score"] for g in games]
    if not totals:
        return None
    trend = {
        "games": len(totals),
        "avg_total": _avg(totals),
        "high_total": max(totals),
        "low_total": min(totals),
    }
    for line in OU_LINES:
        overs = sum(1 for x in totals if x > line)
        pushes = sum(1 for x in totals if x == line)
        trend[f"line_{line}"] = {
            "over": overs, "under": len(totals) - overs - pushes, "push": pushes,
            "over_pct": round(100 * overs / len(totals), 1),
        }
    return trend


def h2h(finals, a, b):
    """Best-effort H2H reconstructed from parsed scorelines (only
    populated when the scoreline scraper actually parsed finals for
    this pair). See fetch_team_stats() for the OFFICIAL H2H W-L-T,
    which doesn't depend on scoreline parsing at all and should be
    treated as the primary number — this is a bonus layer providing
    the actual scorelines/avg total the official page doesn't give."""
    a_w = b_w = ties = 0
    a_runs, b_runs, totals, scorelines = [], [], [], []
    for g in sorted(finals, key=lambda x: x["date"]):
        if {g["home"], g["away"]} != {a, b}:
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
        elif (g["home"] if hs > as_ else g["away"]) == a:
            a_w += 1
        else:
            b_w += 1
    games = a_w + b_w + ties
    if not games:
        return None
    return {"a_wins": a_w, "b_wins": b_w, "ties": ties, "games": games,
            "a_avg_runs": _avg(a_runs), "b_avg_runs": _avg(b_runs),
            "avg_total": _avg(totals), "scorelines": scorelines}


def main():
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")

    seen, all_games = set(), []
    sample_holder = {"sample": None}
    d = SEASON_START
    while d <= now_kst.date() + timedelta(days=6):
        url = f"https://mykbostats.com/schedule/week_of/{d.isoformat()}"
        try:
            html = fetch(url)
        except Exception as exc:
            print(f"  week {d} failed: {exc}")
            d += timedelta(days=7)
            continue
        for g in parse_week(html, today, sample_holder):
            key = (g["date"], g["away"], g["home"])
            if key not in seen:
                seen.add(key)
                all_games.append(g)
        time.sleep(0.15)
        d += timedelta(days=7)

    finals = [g for g in all_games if g["status"] == "final"]
    print(f"KBO: crawled {len(all_games)} games; parsed {len(finals)} finals")
    if sample_holder["sample"]:
        print(f'  [verify-scores] sample past game-line text: {sample_holder["sample"]!r}')
    if not finals:
        print("KBO: no finals parsed from scorelines — team stats/H2H from "
              "TeamStats.aspx (below) don't depend on this and should still ship.")

    # Probable starters: the schedule listing doesn't carry them, but each
    # game-detail page does. Fetch only UPCOMING games (today or later,
    # not final) so we don't hammer the site for completed games. KBO
    # posts starters the day before, so most upcoming games resolve; any
    # that don't stay TBD. One extra request per upcoming game (~5-6/day).
    upcoming = [g for g in all_games
                if g["date"] >= today and g.get("status") != "final"
                and g.get("game_slug")]
    # Two separate reads of the SAME cached page (one request). Kept
    # separate because membership of _hp means "this game has announced
    # starters" and downstream tests depend on that; a time and venue
    # land on games with no pitchers posted.
    _hp = fetch_homepage_starters()
    _hs = fetch_homepage_schedule()
    starter_hits = 0
    venue_fixes, time_fixes = [0], [0]
    for g in upcoming:
        # Match on the numeric game id, the stable half of the slug.
        _gid = str(g.get("game_slug") or "").split("-", 1)[0]
        s = _hp.get(_gid)
        # Every upcoming game gets the keys either way, so a downstream
        # .get() never sees a game that simply lacks them.
        g.update({k: (s or {}).get(k) for k in _STARTER_KEYS})
        if s:
            starter_hits += 1

        # REPAIR TIME AND VENUE, but only where the schedule page failed.
        #
        # A scraped value always wins: if parse_week ever starts working
        # again this quietly stops firing, which is the behaviour you
        # want from a fallback. Only "TBD" is replaced.
        sc = _hs.get(_gid)
        if sc:
            if str(g.get("stadium") or "").upper() == "TBD" and sc.get("venue"):
                g["stadium"] = sc["venue"]
                venue_fixes[0] += 1
            if str(g.get("time_kst") or "").upper() == "TBD" and sc.get("time"):
                kst = _kst_24h(sc["time"])
                if kst:
                    g["time_kst"] = kst
                    g["time_et"] = _kbo_et(g["date"], kst)
                    time_fixes[0] += 1
    if venue_fixes[0] or time_fixes[0]:
        print(f"KBO: repaired {venue_fixes[0]} venue and {time_fixes[0]} "
              f"start-time fields from the homepage (the schedule page's "
              f"own markup has been broken since the v3 rewrite)")
    print(f"KBO: matched probables onto {starter_hits} of {len(upcoming)} "
          f"upcoming games (homepage carries TODAY only, so anything "
          f"further out stays TBD by design)")

    # WEATHER FROM A SOURCE WE OWN.
    #
    # This used to read a temperature and a "Chance of Heat Cancellation"
    # off the mykbostats homepage. That inherited their terms, their
    # upstream (the figure is Apple Weather) and their markup, which was
    # rewritten on 2026-08-04. Fetching a forecast directly removes all
    # three dependencies and adds one thing their page cannot give:
    # tomorrow's risk, not just today's.
    #
    # Keys are set on every upcoming game so a downstream .get() never
    # has to tell "no risk" from "not looked at".
    _wx_by_date = {}
    for g in upcoming:
        _wx_by_date.setdefault(g["date"], []).append(g)
    heat_hits = 0
    for _d, _games in _wx_by_date.items():
        # stadium is "TBD" whenever the venue scrape fails, which it has
        # been since the v3 rewrite. venue_for_game falls back to the
        # home club's park, which no redesign can take away.
        for g in _games:
            g["_venue"] = _venue_for(g.get("stadium"), g.get("home"), "kbo")
        _r = _wx("kbo", [g["_venue"] for g in _games], _d)
        print("  " + _wxsum(_r))
        for g in _games:
            c = _r.get(g.pop("_venue", "")) or {}
            g["temp_c"] = c.get("temp_c")
            g["max_temp_c"] = c.get("max_temp_c")
            g["precip_prob"] = c.get("precip_prob")
            g["heat_risk"] = bool(c.get("heat_risk"))
            g["weather_attribution"] = c.get("attribution")
            if g["heat_risk"]:
                heat_hits += 1
    print(f"KBO: {heat_hits} of {len(upcoming)} upcoming games at or above "
          f"the heat-cancellation threshold")

    stats = team_form(finals) if finals else {}

    # Slate selection: today in Korea if it has games; otherwise the
    # NEXT upcoming date that does (the crawl already pulled 6 days
    # ahead). This keeps the page useful on off-days / after the day
    # rolls in Korea, instead of showing an empty or stale slate. The
    # chosen date ships as slate_date_kst so the view labels it.
    _future = sorted([g for g in all_games
                      if g["date"] >= today and g.get("status") != "final"],
                     key=lambda x: x["date"])
    todays = [g for g in all_games if g["date"] == today]
    slate_date = today
    if not todays and _future:
        slate_date = _future[0]["date"]
        todays = [g for g in all_games if g["date"] == slate_date]
        print(f"KBO: no games today ({today} KST) — showing next slate {slate_date}")

    try:
        pitcher_stats = fetch_pitcher_stats()
    except Exception as exc:
        pitcher_stats = {}
        print(f"KBO: pitcher-stats fetch failed ({exc}) — shipping without it")
    print(f"KBO: {len(pitcher_stats)} pitchers with real season stats fetched")

    try:
        batter_leaders = fetch_batting_leaders()
    except Exception as exc:
        batter_leaders = {}
        print(f"KBO: batting-leaders fetch failed ({exc}) — shipping without it")
    print(f"KBO: {len(batter_leaders)} batters with real season stats fetched")

    try:
        official_h2h, team_batting, team_pitching = fetch_team_stats()
    except Exception as exc:
        official_h2h, team_batting, team_pitching = {}, {}, {}
        print(f"KBO: team-stats fetch failed ({exc}) — shipping without it")
    print(f"KBO: official H2H pairs={len(official_h2h)}, team batting rows={len(team_batting)}, "
          f"team pitching rows={len(team_pitching)}")

    games_out = []
    for g in todays:
        entry = {
            "away": g["away"], "home": g["home"], "stadium": g["stadium"],
            "time_kst": g["time_kst"], "time_et": g["time_et"],
            "away_starter": g.get("away_starter") or "TBD",
            "home_starter": g.get("home_starter") or "TBD",
            "status": g["status"],
            # THE FORECAST HAS TO SURVIVE SERIALISATION.
            #
            # These were computed onto the in-memory game above, logged
            # ("KBO: N of M upcoming games at or above the heat
            # threshold"), and then DROPPED here, because this entry is
            # a curated dict rather than a copy of the game. So the run
            # log said the weather worked, the archive shipped without
            # it, and the board rendered no badge at all while NPB's
            # rendered fine — the same "computed but never reaches the
            # reader" failure as rule 20, one step further down.
            #
            # Set unconditionally, so a downstream .get() never has to
            # tell "no risk" from "not looked at".
            "temp_c": g.get("temp_c"),
            "max_temp_c": g.get("max_temp_c"),
            "precip_prob": g.get("precip_prob"),
            "heat_risk": bool(g.get("heat_risk")),
            "weather_attribution": g.get("weather_attribution"),
        }
        # Real season line for each announced starter, straight from the
        # game page (W-L + ERA). Absent when the starter is still TBD.
        for side in ("away", "home"):
            ss = g.get(f"{side}_starter_stats")
            if ss:
                entry[f"{side}_starter_stats"] = ss
            sid = g.get(f"{side}_starter_id")
            if sid:
                entry[f"{side}_starter_id"] = sid
        for side in ("away", "home"):
            s = stats.get(g[side])
            if s:
                for k, v in s.items():
                    entry[f"{side}_{k}"] = v
            ou = over_under_trend(finals, g[side]) if finals else None
            if ou:
                entry[f"{side}_ou_trend"] = ou
            tb = team_batting.get(g[side])
            if tb:
                entry[f"{side}_team_batting"] = tb
            tp = team_pitching.get(g[side])
            if tp:
                entry[f"{side}_team_pitching"] = tp

        # Official H2H (reliable) + best-effort scoreline H2H (bonus detail)
        official = official_h2h.get((g["away"], g["home"]))
        if official:
            entry["h2h_official"] = f'{g["away"]} {official} {g["home"]} (season)'
        hh = h2h(finals, g["away"], g["home"]) if finals else None
        if hh:
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
    (OUT / "games.json").write_text(json.dumps({
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M"),
        "source": "mykbostats.com schedule (season crawl) + eng.koreabaseball.com team stats",
        "slate_date_kst": slate_date,
        "games": games_out,
    }, ensure_ascii=False, indent=2))
    print(f"KBO: wrote {len(games_out)} games for {today} KST")

    # COVERAGE OF THE SLATE THAT ACTUALLY SHIPS. Shared with NPB in
    # engines/intl_slate — rule 21. The first version of this lived
    # here and in npb_precompute separately, and the two copies
    # disagreed inside one run: this one tested the starter field for
    # truthiness while NPB tested it against "TBD", and since the
    # entry above writes `or "TBD"`, that string is always truthy. It
    # reported "a named starter 5/5" on a slate with no probables at
    # all. A counter that lies is worse than no counter.
    print(coverage_line("KBO", slate_date, games_out, "time_kst"))

    def _era_key(p):
        try:
            return float(p["era"])
        except (TypeError, ValueError):
            return float("inf")

    leaders_out = sorted(
        ({"name": name, **info} for name, info in pitcher_stats.items()
         if info.get("era") is not None),
        key=_era_key,
    )
    (OUT / "pitchers.json").write_text(json.dumps({
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M"),
        "source": "eng.koreabaseball.com official pitching leaderboard",
        "pitchers": leaders_out,
    }, ensure_ascii=False, indent=2))
    print(f"KBO: wrote {len(leaders_out)} pitchers to pitchers.json")

    def _ops_key(b):
        try:
            return -float(b["ops"])
        except (TypeError, ValueError):
            return float("inf")

    batters_out = sorted(
        ({"name": name, **info} for name, info in batter_leaders.items()
         if info.get("ops") is not None),
        key=_ops_key,
    )
    (OUT / "batters.json").write_text(json.dumps({
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M"),
        "source": "eng.koreabaseball.com official batting leaderboard",
        "batters": batters_out,
    }, ensure_ascii=False, indent=2))
    print(f"KBO: wrote {len(batters_out)} batters to batters.json")

    (OUT / "team_stats.json").write_text(json.dumps({
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M"),
        "source": "eng.koreabaseball.com/Stats/TeamStats.aspx",
        "h2h": {f"{a} vs {b}": v for (a, b), v in official_h2h.items()},
        "batting": team_batting,
        "pitching": team_pitching,
    }, ensure_ascii=False, indent=2))
    print(f"KBO: wrote team_stats.json (h2h={len(official_h2h)}, "
          f"batting={len(team_batting)}, pitching={len(team_pitching)})")

    if not leaders_out and not batters_out and not team_batting:
        print("KBO: none of the eng.koreabaseball.com sections parsed — markup "
              "may have changed since this was written; page will honestly "
              "omit these sections rather than guess.")


if __name__ == "__main__":
    main()
