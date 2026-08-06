"""KBO and NPB must show the same weather signal, or neither should.

WHY THIS TEST EXISTS

He bets the two markets together. A risk marker that appears on one
board and not the other is worse than no marker at all, because a
missing badge is unreadable: on the board that has the feature it means
"no risk", and on the board that doesn't it means "nobody looked". The
reader cannot tell which without knowing the codebase.

That is exactly the state the app shipped in. `intl_weather` carried
NPB_COORDS for all twelve parks from the day it was written and nothing
ever called them, so KBO computed temperature, heat risk and
precipitation while NPB computed none of it — and NEITHER board
displayed any of it. KBO rendered the CC BY attribution for figures
that never appeared on screen.

So this pins three things:
  1. both pipelines attach the same weather keys to a shipped game
  2. both views render badges through the SAME engine helper, so the
     wording and thresholds cannot drift apart
  3. the licence attribution appears on both boards, because the moment
     a board displays Open-Meteo figures it owes the credit

Plain script, like everything in tests/ — exits non-zero on failure.
No network.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from engines.intl_weather import (  # noqa: E402
    NPB_HOME_VENUE, HOME_VENUE, NPB_COORDS, KBO_COORDS,
    venue_for_game, weather_badges,
)
from engines.intl_venues import roof  # noqa: E402

failures = []


def check(label, ok):
    if not ok:
        failures.append(label)


# ---- 1. both pipelines attach the same keys -------------------------
WX_KEYS = ("temp_c", "max_temp_c", "precip_prob", "weather_attribution")
kbo_src = (ROOT / "kbo_precompute.py").read_text(encoding="utf-8")
npb_src = (ROOT / "npb_precompute.py").read_text(encoding="utf-8")

for key in WX_KEYS:
    check(f"kbo pipeline sets {key}", f'"{key}"' in kbo_src)
    check(f"npb pipeline sets {key}", f'"{key}"' in npb_src)

# THE KEYS MUST SURVIVE SERIALISATION, not just exist in memory.
#
# The first live run logged "KBO: 2 of 50 upcoming games at or above the
# heat-cancellation threshold" and then shipped an archive with no
# weather in it at all: games_out is a curated dict, and nobody added
# the forecast keys to it, so the board rendered no badge while NPB's
# rendered fine. The log said it worked. The reader saw nothing.
#
# So assert on the SHIPPED entry, which is what the view actually reads.
for name, src in (("kbo", kbo_src), ("npb", npb_src)):
    for key in ("temp_c", "max_temp_c", "precip_prob", "heat_risk",
                "weather_attribution"):
        check(f"{name} SHIPS {key} on the slate entry",
              f'"{key}": g.get(' in src or f'"{key}": bool(g.get(' in src)

check("npb imports the shared forecast engine",
      "engines.intl_weather" in npb_src)
check("npb forecasts through venue_for_game",
      "_venue_for(" in npb_src)

# ---- 2. every home club resolves to a park the engine can locate ----
# A club missing here forecasts nothing, silently, for every home game.
for club, venue in NPB_HOME_VENUE.items():
    check(f"NPB {club} -> known coords",
          venue in NPB_COORDS)
for club, venue in HOME_VENUE.items():
    check(f"KBO {club} -> known coords", venue in KBO_COORDS)

check("all twelve NPB clubs are mapped", len(NPB_HOME_VENUE) == 12)
check("every NPB park is reachable", len(NPB_COORDS) == 12)

# A scraped venue must WIN over the club fallback — neutral-site games
# are rare but real, and defaulting to the home park would forecast the
# wrong city with full confidence.
check("real venue beats the fallback",
      venue_for_game("Koshien Stadium", "Yomiuri Giants") == "Koshien Stadium")
check("TBD falls back to the home park",
      venue_for_game("TBD", "Yomiuri Giants") == "Tokyo Dome")
check("unknown club stays empty rather than guessing",
      venue_for_game("TBD", "Some Other Club") == "")

# ---- 3. the badge rules, shared by both boards ----------------------
heat = weather_badges(
    {"stadium": "Daegu", "temp_c": 33, "max_temp_c": 36.2,
     "heat_risk": True, "precip_prob": 5}, "kbo", roof)
check("heat risk leads and quotes the day's max",
      heat and heat[0][0] == "HEAT RISK 36\u00b0C" and heat[0][1] == "bad")

wet = weather_badges(
    {"stadium": "Yokohama Stadium", "temp_c": 27, "precip_prob": 70},
    "npb", roof)
check("open park shows rain risk",
      any(t.startswith("RAIN RISK") and tone == "bad" for t, tone in wet))

# A dome cannot be rained out. Showing 80% under a roof would be the
# forecast crying wolf — intl_venues owns that judgement.
domed = weather_badges(
    {"stadium": "Tokyo Dome", "temp_c": 26, "precip_prob": 80}, "npb", roof)
check("roof suppresses the rain figure",
      not any("RAIN" in t for t, _ in domed))
check("roof is stated rather than left blank",
      any(t == "ROOFED" for t, _ in domed))

# Nothing known must render as NOTHING — never a 0% or an em dash that
# reads like a measurement.
check("no data yields no badges",
      weather_badges({"stadium": "Koshien Stadium"}, "npb", roof) == [])

# ---- 4. the views cannot drift apart --------------------------------
kbo_view = (ROOT / "app" / "views" / "KBO.py").read_text(encoding="utf-8")
npb_view = (ROOT / "app" / "views" / "NPB.py").read_text(encoding="utf-8")

for name, src in (("KBO", kbo_view), ("NPB", npb_view)):
    check(f"{name} renders badges via the shared helper",
          "_weather_badges(" in src)
    # Thresholds and wording live in the engine. A view spelling its own
    # "RAIN RISK" would be the start of exactly the drift this prevents.
    check(f"{name} does not hardcode a threshold",
          not re.search(r'RAIN RISK|HEAT RISK|>= ?50|precip_prob\s*>', src))
    # CC BY 4.0: the credit must appear wherever the data does.
    check(f"{name} carries the Open-Meteo attribution",
          "_WX_ATTRIBUTION" in src and src.count("_WX_ATTRIBUTION") >= 2)

# ---- 5. the three failures the first live run exposed ---------------
# Every one of these logged "no coordinates" and forecast nothing, on a
# green pipeline, because a lookup missed quietly.

# (a) A capital letter decided whether a game got a forecast:
#     kbo_precompute emits "Kia Tigers", the map said "KIA Tigers".
check("club lookup is case-insensitive",
      venue_for_game("TBD", "Kia Tigers", "kbo") == "Gwangju"
      and venue_for_game("TBD", "KIA Tigers", "kbo") == "Gwangju")

# Every name the KBO pipeline can emit must resolve. This is the check
# that would have caught (a) before it shipped.
_kbo_src = (ROOT / "kbo_precompute.py").read_text(encoding="utf-8")
_m = re.search(r"^TEAMS\s*=\s*\{(.*?)\n\}", _kbo_src, re.S | re.M)
_emitted = set(re.findall(r':\s*"([^"]+)"', _m.group(1))) if _m else set()
check("every KBO club the pipeline emits has a home park",
      _emitted and all(venue_for_game("TBD", n, "kbo") for n in _emitted))

# (b) npb.jp emits both the short and the full park name; STADIUMS held
#     only the prefix, so the full form fell through as raw Japanese.
sys.path.insert(0, str(ROOT))
import npb_precompute as _npb  # noqa: E402
from engines.intl_weather import coords_for  # noqa: E402

for raw in ("\u30d0\u30f3\u30c6\u30ea\u30f3\u30c9\u30fc\u30e0",
            "\u30de\u30c4\u30c0\u30b9\u30bf\u30b8\u30a2\u30e0",
            "\u6a2a \u6d5c", "\u6771\u4eac\u30c9\u30fc\u30e0"):
    check(f"NPB venue {raw} resolves to coordinates",
          bool(coords_for("npb", _npb._en_stadium(raw))))

# (c) An unrecognised venue string used to WIN over the club fallback
#     just for being non-empty, then forecast nothing.
check("an unlocatable venue falls back to the home park",
      venue_for_game("\u8b0e\u306e\u7403\u5834", "Hanshin Tigers", "npb")
      == "Koshien Stadium")
check("unknown club AND unknown venue still returns nothing",
      venue_for_game("\u8b0e\u306e\u7403\u5834", "Nobody FC", "npb") == "")

# Both pipelines must pass their league through, or (c) cannot fire.
check("kbo passes its league to venue_for_game",
      '_venue_for(g.get("stadium"), g.get("home"), "kbo")' in _kbo_src)
check("npb passes its league to venue_for_game",
      '_venue_for(g.get("stadium"), g.get("home"), "npb")' in npb_src)

if failures:
    print("FAIL:", "; ".join(failures))
    sys.exit(1)
print("PASS: KBO and NPB share one weather engine, one wording, one credit")
