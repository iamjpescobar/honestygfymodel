#!/usr/bin/env python3
"""Derive the KBO stadium from the home club when the scrape says TBD."""
import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent
E = ROOT / "app/engines/intl_weather.py"
K = ROOT / "kbo_precompute.py"
T = ROOT / "tests/test_intl_weather.py"

s = E.read_text()
if "HOME_VENUE" in s:
    sys.exit("Already applied - nothing written.")

anchor = "# KBO venue strings are free text, so match on a distinctive substring"
if anchor not in s:
    sys.exit("ANCHOR NOT FOUND (KBO_PATTERNS comment) - nothing written.")

block = '''# EVERY KBO CLUB HAS ONE HOME PARK, AND THAT NEVER NEEDED SCRAPING.
#
# On 2026-08-06 the pipeline emitted `stadium: "TBD"` for all 50
# upcoming games: the mykbostats v3 rewrite broke the venue regex the
# same way it broke the starters one, and nothing had consumed the
# field since, so it failed silently for two days. The forecast then
# correctly refused to guess and reported no coordinates, which is how
# it surfaced at all.
#
# A club's home park is a fact about the league, not about anyone's
# markup. Ten clubs, nine parks — LG and Doosan share Jamsil. Keyed on
# both the full name _team() produces and the short code in the slug,
# because either can reach us.
#
# Caveat worth knowing: this assumes the home club is playing at home.
# KBO neutral-site games are rare but not impossible, so a real venue
# string always WINS over this — the fallback only fires on "TBD".
HOME_VENUE = {
    "Doosan Bears": "Jamsil",     "LG Twins": "Jamsil",
    "Kiwoom Heroes": "Gocheok",   "SSG Landers": "Munhak",
    "KT Wiz": "Suwon",            "Hanwha Eagles": "Daejeon",
    "Samsung Lions": "Daegu",     "Lotte Giants": "Sajik",
    "KIA Tigers": "Gwangju",      "NC Dinos": "Changwon",
    "Doosan": "Jamsil", "LG": "Jamsil", "Kiwoom": "Gocheok",
    "SSG": "Munhak", "KT": "Suwon", "Hanwha": "Daejeon",
    "Samsung": "Daegu", "Lotte": "Sajik", "KIA": "Gwangju",
    "NC": "Changwon",
}


def venue_for_game(stadium, home_team):
    """The venue string to forecast for, or "" when nothing is known.

    A scraped venue wins; the home park is only a fallback. Returns ""
    rather than a guess so the caller still omits genuinely unknown
    games instead of inventing a city for them.
    """
    s = (stadium or "").strip()
    if s and s.upper() != "TBD":
        return s
    return HOME_VENUE.get((home_team or "").strip(), "")


'''
E.write_text(s.replace(anchor, block + anchor, 1))

# --- kbo_precompute: use the resolver ---
k = K.read_text()
old_imp = """from engines.intl_weather import (  # noqa: E402
    forecast as _wx,
    summarize as _wxsum,
)"""
new_imp = """from engines.intl_weather import (  # noqa: E402
    forecast as _wx,
    summarize as _wxsum,
    venue_for_game as _venue_for,
)"""
if old_imp not in k:
    sys.exit("ANCHOR NOT FOUND (weather import) - nothing written.")
k = k.replace(old_imp, new_imp, 1)

old_call = '''        _r = _wx("kbo", [g.get("stadium") or g.get("venue") or ""
                         for g in _games], _d)'''
new_call = '''        # stadium is "TBD" whenever the venue scrape fails, which it has
        # been since the v3 rewrite. venue_for_game falls back to the
        # home club's park, which no redesign can take away.
        for g in _games:
            g["_venue"] = _venue_for(g.get("stadium"), g.get("home"))
        _r = _wx("kbo", [g["_venue"] for g in _games], _d)'''
if old_call not in k:
    sys.exit("ANCHOR NOT FOUND (forecast call) - nothing written.")
k = k.replace(old_call, new_call, 1)

old_get = '''            c = _r.get(g.get("stadium") or g.get("venue") or "") or {}'''
new_get = '''            c = _r.get(g.pop("_venue", "")) or {}'''
if old_get not in k:
    sys.exit("ANCHOR NOT FOUND (reading back) - nothing written.")
K.write_text(k.replace(old_get, new_get, 1))

# --- test coverage ---
t = T.read_text()
add = '''
# A scraped venue wins; the home park is only a fallback.
if W.venue_for_game("Sajik", "Doosan Bears") != "Sajik":
    failures.append("a real venue string did not win over the fallback")
elif W.venue_for_game("TBD", "Samsung Lions") != "Daegu":
    failures.append("TBD did not fall back to the home club's park")
elif W.venue_for_game("", "LG Twins") != "Jamsil":
    failures.append("an empty venue did not fall back")
elif W.venue_for_game("TBD", "Some Expansion Club") != "":
    failures.append("an unknown club was given a park")
else:
    print("PASS: venue falls back to the home park, never guesses")

# Every club maps to a park that has coordinates.
_bad = [c for c, v in W.HOME_VENUE.items() if v not in W.KBO_COORDS]
if _bad:
    failures.append(f"clubs mapped to parks without coordinates: {_bad}")
else:
    print("PASS: every home park has coordinates")

'''
mark = "if failures:"
T.write_text(t.replace(mark, add + mark, 1))

print("patched: HOME_VENUE + venue_for_game")
print("patched: kbo_precompute uses the resolver")
print("patched: tests/test_intl_weather.py\n")

r = subprocess.run([sys.executable, "-c",
    "import kbo_precompute as k; from engines.intl_weather import venue_for_game as v;"
    "print('import OK');"
    "print('TBD ->', v('TBD','Samsung Lions'));"
    "print('real wins ->', v('Sajik','Doosan Bears'));"
    "print('unknown ->', repr(v('TBD','Nobody')))"],
    cwd=str(ROOT), capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip()[-500:])
ok = "TBD -> Daegu" in r.stdout and "real wins -> Sajik" in r.stdout
print("\n  " + ("OK   resolver works inside the real module"
                if ok else "FAIL resolver did not work"))
print("done" if ok else "INCOMPLETE - tell Claude")
