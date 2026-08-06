"""
The forecast engine must not guess a stadium, and must not lose its
licence attribution.

WHY THIS EXISTS

Weather used to be read off mykbostats' rendered homepage, which meant
inheriting their terms, their upstream (Apple Weather) and their markup.
This engine fetches directly. Rule 13: something must RUN a parser.

Plain script, not pytest. Exits non-zero on failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from engines import intl_weather as W

failures = []

# An unrecognised venue must return None. A default would produce a
# confident forecast for the wrong city, which is worse than none.
if W.coords_for("kbo", "Wrigley Field") is not None:
    failures.append("an unknown KBO venue was given coordinates")
elif W.coords_for("kbo", "") is not None:
    failures.append("an empty venue was given coordinates")
else:
    print("PASS: unknown venues get no coordinates")

# Free-text KBO venue strings match on a substring, case-insensitively.
if W.coords_for("kbo", "SAJIK") != W.coords_for("kbo", "sajik stadium"):
    failures.append("KBO venue matching is not case/substring tolerant")
elif W.coords_for("kbo", "Gocheok Sky Dome") != W.KBO_COORDS["Gocheok"]:
    failures.append("Gocheok did not resolve")
else:
    print("PASS: KBO venue strings resolve by substring")

# Two clubs share Jamsil; both must land on the same grid point.
if W.coords_for("kbo", "Jamsil") != W.coords_for("kbo", "JAMSIL Baseball"):
    failures.append("shared venue resolved to two different points")
else:
    print("PASS: a shared venue is one location")

# NPB keys on exact venue names emitted by npb_precompute.
if W.coords_for("npb", "Tokyo Dome") is None:
    failures.append("NPB venue lookup broke")
else:
    print("PASS: NPB venues resolve")

# Every KBO and NPB venue in intl_venues must have coordinates here, or
# a slate will silently lose weather for a stadium nobody noticed.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from engines import intl_venues as V
missing = [n for n in V.NPB_VENUES if n not in W.NPB_COORDS]
if missing:
    failures.append(f"NPB venues without coordinates: {missing}")
else:
    print("PASS: every NPB venue in intl_venues has coordinates")
missing_k = [needle for needle, _ in V.KBO_VENUE_PATTERNS
             if W.coords_for("kbo", needle) is None]
if missing_k:
    failures.append(f"KBO venue patterns without coordinates: {missing_k}")
else:
    print("PASS: every KBO venue pattern has coordinates")

# CC BY 4.0 requires attribution with a link wherever data is shown.
if "open-meteo.com" not in W.ATTRIBUTION or "<a " not in W.ATTRIBUTION:
    failures.append("attribution is missing or is not a link")
else:
    print("PASS: attribution carries a link")

# summarize() must survive an empty forecast rather than raising.
if "no forecast" not in W.summarize({}):
    failures.append("summarize({}) did not report an empty forecast")
else:
    print("PASS: an empty forecast summarizes cleanly")

# The heat flag reads the DAY's max, and reports temperature either way.
fake = {"Daegu": {"max_temp_c": 36.0, "heat_risk": True},
        "Jamsil": {"max_temp_c": 29.0, "heat_risk": False}}
line = W.summarize(fake)
if "36" not in line or "1 at or above" not in line:
    failures.append(f"summarize did not report max and count: {line}")
else:
    print("PASS: summary reports max temp and flagged count")


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

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nAll international weather checks passed.")
