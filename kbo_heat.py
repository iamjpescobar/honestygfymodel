#!/usr/bin/env python3
"""F1: read the heat-cancellation warning off the KBO homepage.

Edits accumulate per file; verifies what landed ON DISK.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
buf = {}
applied = []


def edit(relpath, old, new, label):
    s = buf.get(relpath)
    if s is None:
        s = (ROOT / relpath).read_text()
    if old not in s:
        sys.exit(f"ANCHOR NOT FOUND ({label}) - nothing written.")
    if s.count(old) != 1:
        sys.exit(f"ANCHOR NOT UNIQUE ({label}) - nothing written.")
    buf[relpath] = s.replace(old, new, 1)
    applied.append(label)


K = "kbo_precompute.py"

# ----------------------------------------------------------------------
# 1. Patterns, beside the ones they belong with.
# ----------------------------------------------------------------------
edit(K, '''HOME_GAME_A = re.compile(r'<a[^>]*href="/games/([^"]+)"[^>]*>(.*?)</a>', re.S)''',
     '''HOME_GAME_A = re.compile(r'<a[^>]*href="/games/([^"]+)"[^>]*>(.*?)</a>', re.S)

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
TEMP_PAT = re.compile(r'(\\d{1,2})\\s*(?:°|&deg;)')''', "patterns")

# ----------------------------------------------------------------------
# 2. One request, two readings.
# ----------------------------------------------------------------------
edit(K, '''def fetch_homepage_starters():''',
     '''def parse_homepage_conditions(html):
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
        text = re.sub(r"\\s+", " ", _strip(inner)).strip()
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


def fetch_homepage_starters():''', "conditions parser and cache")

# ----------------------------------------------------------------------
# 3. The starters fetch reuses the cached document.
# ----------------------------------------------------------------------
edit(K, '''    try:
        r = requests.get("https://mykbostats.com/", headers=UA, timeout=25)
    except Exception as exc:
        print(f"  KBO: homepage fetch failed ({exc}) — no probables this run")
        return {}
    if r.status_code != 200:
        print(f"  KBO: homepage HTTP {r.status_code} — no probables this run")
        return {}

    found = parse_homepage_starters(r.text)
    cards = len(HOME_GAME_A.findall(r.text))''',
     '''    html = _homepage_html()
    if not html:
        print("  KBO: no homepage — no probables this run")
        return {}

    found = parse_homepage_starters(html)
    cards = len(HOME_GAME_A.findall(html))''', "starters reuses cache")

# ----------------------------------------------------------------------
# 4. Onto the games.
# ----------------------------------------------------------------------
edit(K, '''    print(f"KBO: matched probables onto {starter_hits} of {len(upcoming)} "
          f"upcoming games (homepage carries TODAY only, so anything "
          f"further out stays TBD by design)")''',
     '''    print(f"KBO: matched probables onto {starter_hits} of {len(upcoming)} "
          f"upcoming games (homepage carries TODAY only, so anything "
          f"further out stays TBD by design)")

    # HEAT RISK, from the same document. This is the item that has been
    # costing real money: a game voided for extreme heat settles bets
    # nobody could have avoided, and the site publishes the warning
    # hours ahead. Keys are set on every upcoming game so a downstream
    # .get() never has to distinguish "no risk" from "not looked at" —
    # False means checked and clear, and temp_c stays None when the card
    # carried no figure.
    _hc = fetch_homepage_conditions()
    heat_hits = 0
    for g in upcoming:
        _gid = str(g.get("game_slug") or "").split("-", 1)[0]
        c = _hc.get(_gid) or {}
        g["temp_c"] = c.get("temp_c")
        g["heat_risk"] = bool(c.get("heat_risk"))
        if g["heat_risk"]:
            heat_hits += 1
    print(f"KBO: {heat_hits} of {len(upcoming)} upcoming games flagged at "
          f"risk of heat cancellation")''', "merge onto games")

# ----------------------------------------------------------------------
# 5. A permanent fixture test (rule 13: something must RUN the parser).
# ----------------------------------------------------------------------
TEST = '''"""
The KBO heat-cancellation warning must survive a redesign, and must not
invent calm weather.

WHY THIS EXISTS

parse_starters() died silently in the mykbostats Aug 2026 rewrite and
nobody noticed for weeks, because nothing ever ran it against a page.
This pins the conditions reader against the real card text so the same
thing cannot happen twice.

Plain script, not pytest. Exits non-zero on failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kbo_precompute as K

failures = []

# Real shape, captured from the homepage: an at-risk card, a clear card
# carrying the entity form of the degree sign, and a card with neither.
HTML = (
    '<a href="/games/13777-Hanwha-vs-Samsung-20260806">'
    'Hanwha Eagles Samsung Lions 31\u00b0 6:30pm Daegu '
    'Chance of Heat Cancellation</a>'
    '<a href="/games/13778-Lotte-vs-KT-20260806">'
    'Lotte Giants KT Wiz 27&deg; 6:30pm Suwon '
    'Starters: Park Jun-yeong vs. Chris Paddack</a>'
    '<a href="/games/13779-SSG-vs-NC-20260806">'
    'SSG Landers NC Dinos 6:30pm Changwon</a>'
)

cond = K.parse_homepage_conditions(HTML)

if cond.get("13777", {}).get("heat_risk") is not True:
    failures.append("an at-risk game was not flagged")
else:
    print("PASS: Chance of Heat Cancellation is read as a risk")

if cond.get("13777", {}).get("temp_c") != 31:
    failures.append("temperature not read from the literal degree sign")
elif cond.get("13778", {}).get("temp_c") != 27:
    failures.append("temperature not read from the &deg; entity form")
else:
    print("PASS: temperature reads in both degree forms")

if cond.get("13778", {}).get("heat_risk") is not False:
    failures.append("a clear game was flagged at risk")
else:
    print("PASS: a clear game is False, not missing")

# A card with no temperature and no warning is OMITTED, so a caller can
# tell "nothing published" from "published as fine". Same contract the
# starters parser keeps.
if "13779" in cond:
    failures.append("a card with neither reading was recorded anyway")
else:
    print("PASS: a card with nothing to say is omitted, not guessed")

# The two readers must stay independent: a heat warning routinely lands
# on a game whose pitchers are not announced, which is the game a bettor
# most needs warned about.
st = K.parse_homepage_starters(HTML)
if "13777" in st:
    failures.append("heat-only game leaked into the starters map")
elif st.get("13778", {}).get("home_starter") != "Chris Paddack":
    failures.append("starters parsing broke")
else:
    print("PASS: starters and conditions stay independent")

# Negative control: if the risk pattern matched anything, the suite
# would pass while telling every bettor every game is at risk.
if K.parse_homepage_conditions(
        '<a href="/games/1-A-vs-B-20260806">A B 24\u00b0 6:30pm</a>'
).get("1", {}).get("heat_risk") is not False:
    failures.append("risk pattern fires on a card that does not mention heat")
else:
    print("PASS: negative control - no warning means no risk")

if failures:
    print("\\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\\nAll KBO heat-risk checks passed.")
'''
(ROOT / "tests/test_kbo_heat_risk.py").write_text(TEST)
applied.append("tests/test_kbo_heat_risk.py")

for relpath, content in buf.items():
    (ROOT / relpath).write_text(content)
for label in applied:
    print(f"patched: {label}")

_k = (ROOT / K).read_text()
checks = {
    "HEAT_RISK_PAT defined": "HEAT_RISK_PAT = re.compile" in _k,
    "conditions parser": "def parse_homepage_conditions(html):" in _k,
    "single-fetch cache": "def _homepage_html():" in _k,
    "no dangling r": "r = None" not in _k,
    "one requests.get for homepage":
        _k.count('requests.get("https://mykbostats.com/"') == 1,
    "merged onto games": 'g["heat_risk"] = bool(c.get("heat_risk"))' in _k,
}

# RUN IT. Grepping for a function name proves the letters are present,
# not that calling it works - this script shipped `r = None` followed by
# `r.status_code` and every string check still passed.
FIX = (
    '<a href="/games/13777-Hanwha-vs-Samsung-20260806">'
    'Hanwha Eagles Samsung Lions 31° 6:30pm Daegu '
    'Chance of Heat Cancellation</a>'
    '<a href="/games/13778-Lotte-vs-KT-20260806">'
    'Lotte Giants KT Wiz 27&deg; 6:30pm Suwon '
    'Starters: Park Jun-yeong vs. Chris Paddack</a>'
    '<a href="/games/13779-SSG-vs-NC-20260806">'
    'SSG Landers NC Dinos 6:30pm Changwon</a>'
)
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("_kbo", ROOT / K)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cond = mod.parse_homepage_conditions(FIX)
    checks["at-risk game flagged"] = cond.get("13777", {}).get("heat_risk") is True
    checks["its temperature read"] = cond.get("13777", {}).get("temp_c") == 31
    checks["clear game not flagged"] = cond.get("13778", {}).get("heat_risk") is False
    checks["card with neither omitted"] = "13779" not in cond
    st = mod.parse_homepage_starters(FIX)
    checks["starters still parse"] = (
        st.get("13778", {}).get("home_starter") == "Chris Paddack")
    checks["heat game has no starters entry"] = "13777" not in st
except Exception as exc:
    checks["module executes"] = False
    print(f"  !! executing {K} raised {type(exc).__name__}: {exc}")

print()
for name, ok in checks.items():
    print(f"  {'OK  ' if ok else 'FAIL'} {name}")
print("done" if all(checks.values()) else "INCOMPLETE - tell Claude")
