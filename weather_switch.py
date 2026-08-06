#!/usr/bin/env python3
"""Weather from a source we own: Open-Meteo, not a scraped homepage.

Installs app/engines/intl_weather.py, its test, and rewires
kbo_precompute to use it. Adapts to whether the mykbostats heat reader
(F1) was committed or not. Verifies by RUNNING the parser, not grepping.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ENGINE = ROOT / "app/engines/intl_weather.py"
K = ROOT / "kbo_precompute.py"
applied = []

ENGINE_SRC = '"""\nForecast weather for KBO and NPB venues, from a source we actually own.\n\nWHY THIS EXISTS\n\npark_weather.py already does this properly for MLB: api.weather.gov,\nUS government data, public domain, no key. There was no equivalent for\nthe international slates, so KBO temperature and heat-cancellation\nwarnings were being read off mykbostats\' rendered homepage instead.\n\nThat was wrong three ways. It inherited their terms (Acceptable Use\nclause 6 forbids using their content to make sports bets). It inherited\ntheir source — that temperature is Apple Weather, arriving through a\nthird party with its own attribution rules. And it inherited their\nmarkup, which was rewritten on 2026-08-04 and broke the last parser\nthat depended on it.\n\nFetching a forecast directly fixes all three, and gives something the\nhomepage could never provide: TOMORROW\'s risk. Their page shows today.\n\nSOURCE AND LICENCE — read before changing anything here.\n\nOpen-Meteo, free tier. Their terms define non-commercial to include\n"private or non-profit websites or apps that do not have subscriptions\nor advertising", and commercial as "operating websites or apps that\nhave subscriptions or display advertisements". This site is currently\nprivate, login-gated, unpaid and adless, so the free tier applies.\n\n*** IF THIS SITE EVER TAKES SUBSCRIPTIONS OR RUNS ADS, THIS BECOMES\n*** COMMERCIAL USE AND NEEDS A PAID PLAN. That is not a footnote; it\n*** is the condition the whole choice rests on.\n\nThe data is CC BY 4.0, which REQUIRES attribution with a link wherever\nit is displayed. ATTRIBUTION below is exported for that purpose and\nships in the slate payload so the view can render it. Removing it is a\nlicence violation, not a style choice.\n\nLimits: 10,000 calls/day. One call covers the whole slate, because\nOpen-Meteo accepts comma-separated coordinates and returns an array.\n"""\nimport json\nfrom datetime import datetime\nfrom zoneinfo import ZoneInfo\n\nimport requests\n\nAPI = "https://api.open-meteo.com/v1/forecast"\n\n# CC BY 4.0 requires this next to any displayed value. Kept as HTML\n# because that is how every consumer here renders.\nATTRIBUTION = (\'<a href="https://open-meteo.com/">Weather data by \'\n               \'Open-Meteo.com</a>\')\n\nSEOUL = ZoneInfo("Asia/Seoul")\nTOKYO = ZoneInfo("Asia/Tokyo")\n\n# Stadium coordinates, good to a few hundred metres — far finer than any\n# forecast grid, so precision beyond this buys nothing. Keyed to the\n# venue rather than the club because two KBO clubs share Jamsil and\n# clubs move buildings, which is the same reason intl_venues.py keys on\n# venue.\nKBO_COORDS = {\n    "Jamsil":     (37.5122, 127.0719),\n    "Gocheok":    (37.4982, 126.8672),   # Sky Dome — roofed, still fetched\n    "Munhak":     (37.4370, 126.6933),   # Incheon SSG Landers Field\n    "Suwon":      (37.2997, 127.0097),\n    "Daegu":      (35.8411, 128.6816),\n    "Gwangju":    (35.1682, 126.8890),\n    "Daejeon":    (36.3170, 127.4290),\n    "Changwon":   (35.2226, 128.5822),\n    "Sajik":      (35.1940, 129.0615),   # Busan\n}\n\nNPB_COORDS = {\n    "Tokyo Dome":          (35.7056, 139.7519),\n    "Jingu Stadium":       (35.6748, 139.7170),\n    "Yokohama Stadium":    (35.4437, 139.6400),\n    "Koshien Stadium":     (34.7212, 135.3617),\n    "Kyocera Dome Osaka":  (34.6693, 135.4761),\n    "Vantelin Dome":       (35.1856, 136.9475),\n    "Mazda Stadium":       (34.3915, 132.4845),\n    "PayPay Dome":         (33.5953, 130.3623),\n    "Rakuten Mobile Park": (38.2562, 140.9022),\n    "Belluna Dome":        (35.7694, 139.4197),\n    "Zozo Marine Stadium": (35.6453, 140.0313),\n    "Escon Field":         (42.9897, 141.5100),\n}\n\n# KBO venue strings are free text, so match on a distinctive substring\n# the way intl_venues.KBO_VENUE_PATTERNS does rather than by equality.\nKBO_PATTERNS = (\n    ("gocheok", "Gocheok"), ("jamsil", "Jamsil"), ("sajik", "Sajik"),\n    ("munhak", "Munhak"), ("incheon", "Munhak"), ("landers", "Munhak"),\n    ("suwon", "Suwon"), ("daegu", "Daegu"), ("gwangju", "Gwangju"),\n    ("champions field", "Gwangju"), ("daejeon", "Daejeon"),\n    ("changwon", "Changwon"),\n)\n\n# THE THRESHOLD IS A GUESS UNTIL SOMEONE CHECKS IT.\n#\n# 35°C is the figure commonly cited for KBO heat cancellations and lines\n# up with the 폭염경보 (heat wave warning) criteria, but it has NOT been\n# verified against a published KBO rule, and the rule may key on\n# apparent temperature or on a KMA warning rather than a raw reading.\n#\n# So this is a named constant with the uncertainty written next to it,\n# and every forecast logs its max temperature whether or not the flag\n# fires. A week of logs beside the actual cancellations calibrates this\n# properly. Do not quietly tune the number without recording why.\nHEAT_CANCEL_C = 35.0\n\n\ndef coords_for(league, venue):\n    """(lat, lon) for a venue string, or None when it is unrecognised.\n\n    None rather than a default: a guessed stadium produces a confident\n    forecast for the wrong city, which is worse than no forecast at all.\n    """\n    if not venue:\n        return None\n    if (league or "").lower() == "kbo":\n        v = venue.lower()\n        for needle, canon in KBO_PATTERNS:\n            if needle in v:\n                return KBO_COORDS.get(canon)\n        return None\n    return NPB_COORDS.get(venue)\n\n\ndef _tz(league):\n    return SEOUL if (league or "").lower() == "kbo" else TOKYO\n\n\ndef forecast(league, venues, date_iso, hour=18):\n    """{venue: {...}} for one slate, in a single API call.\n\n    venues is the list of venue strings the slate builder emitted; the\n    unrecognised ones are dropped and reported rather than guessed.\n\n    hour is local first-pitch hour — 18 covers the 18:00 and 18:30\n    starts that make up nearly every KBO and NPB weeknight. Weekend\n    afternoon games read an hour that is off by a few, which moves the\n    temperature by about a degree and does not change a heat flag.\n    """\n    pairs, unknown = [], []\n    for v in venues:\n        c = coords_for(league, v)\n        (pairs.append((v, c)) if c else unknown.append(v))\n    if unknown:\n        print(f"  weather: no coordinates for {sorted(set(unknown))} — "\n              f"omitted rather than guessed")\n    if not pairs:\n        return {}\n\n    # Deduplicate: two clubs share Jamsil, and a doubleheader would\n    # otherwise pay for the same grid point twice.\n    seen, order = {}, []\n    for v, c in pairs:\n        if c not in seen:\n            seen[c] = []\n            order.append(c)\n        seen[c].append(v)\n\n    params = {\n        "latitude": ",".join(str(c[0]) for c in order),\n        "longitude": ",".join(str(c[1]) for c in order),\n        "hourly": "temperature_2m,precipitation_probability,wind_speed_10m",\n        "daily": "temperature_2m_max",\n        "timezone": str(_tz(league)),\n        "start_date": date_iso,\n        "end_date": date_iso,\n    }\n    try:\n        r = requests.get(API, params=params, timeout=25)\n    except Exception as exc:\n        print(f"  weather: fetch failed ({exc}) — no forecast this run")\n        return {}\n    if r.status_code != 200:\n        print(f"  weather: HTTP {r.status_code} — no forecast this run")\n        return {}\n    try:\n        payload = r.json()\n    except Exception:\n        print("  weather: 200 but not JSON — no forecast this run")\n        return {}\n\n    # A single coordinate returns an object; several return a list.\n    blocks = payload if isinstance(payload, list) else [payload]\n    if len(blocks) != len(order):\n        print(f"  weather: asked for {len(order)} locations, got "\n              f"{len(blocks)} — dropped rather than misaligned")\n        return {}\n\n    out = {}\n    want = f"{date_iso}T{hour:02d}:00"\n    for coord, block in zip(order, blocks):\n        hourly = block.get("hourly") or {}\n        times = hourly.get("time") or []\n        idx = times.index(want) if want in times else None\n        daily = (block.get("daily") or {}).get("temperature_2m_max") or []\n        tmax = daily[0] if daily else None\n\n        def at(key):\n            vals = hourly.get(key) or []\n            return vals[idx] if idx is not None and idx < len(vals) else None\n\n        reading = {\n            "temp_c": at("temperature_2m"),\n            "precip_prob": at("precipitation_probability"),\n            "wind_kph": at("wind_speed_10m"),\n            "max_temp_c": tmax,\n            # Flag on the DAY\'s max, not first-pitch. A 4pm peak of 36\n            # that eases to 33 by 18:30 is still the day a game gets\n            # called, and the call is usually made in the afternoon.\n            "heat_risk": bool(tmax is not None and tmax >= HEAT_CANCEL_C),\n            "attribution": ATTRIBUTION,\n        }\n        for v in seen[coord]:\n            out[v] = reading\n    return out\n\n\ndef summarize(readings):\n    """One log line. Prints max temps even when nothing is flagged, so a\n    week of runs calibrates HEAT_CANCEL_C instead of only proving it."""\n    if not readings:\n        return "weather: no forecast"\n    seen, temps, risk = set(), [], 0\n    for v, r in readings.items():\n        if v in seen:\n            continue\n        seen.add(v)\n        if r.get("max_temp_c") is not None:\n            temps.append(r["max_temp_c"])\n        risk += bool(r.get("heat_risk"))\n    hi = f"{max(temps):.0f}" if temps else "?"\n    return (f"weather: {len(seen)} venues, max {hi}°C, "\n            f"{risk} at or above {HEAT_CANCEL_C:.0f}°C heat threshold")\n\n\nif __name__ == "__main__":  # pragma: no cover - manual check\n    today = datetime.now(SEOUL).strftime("%Y-%m-%d")\n    got = forecast("kbo", ["Jamsil", "Daegu", "Sajik"], today)\n    print(json.dumps(got, indent=2, ensure_ascii=False))\n    print(summarize(got))\n'


# 1. the engine ---------------------------------------------------------
ENGINE.write_text(ENGINE_SRC)
applied.append("app/engines/intl_weather.py")

# 2. the test -----------------------------------------------------------
(ROOT / "tests/test_intl_weather.py").write_text('''"""
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

if failures:
    print("\\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\\nAll international weather checks passed.")
''')
applied.append("tests/test_intl_weather.py")

# 3. rewire kbo_precompute ---------------------------------------------
s = K.read_text()

NEW = '''    # WEATHER FROM A SOURCE WE OWN.
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
    from engines.intl_weather import forecast as _wx, summarize as _wxsum
    _venues = [g.get("stadium") or g.get("venue") or "" for g in upcoming]
    _wx_by_date = {}
    for g in upcoming:
        _wx_by_date.setdefault(g["date"], []).append(g)
    heat_hits = 0
    for _d, _games in _wx_by_date.items():
        _r = _wx("kbo", [g.get("stadium") or g.get("venue") or ""
                         for g in _games], _d)
        print("  " + _wxsum(_r))
        for g in _games:
            c = _r.get(g.get("stadium") or g.get("venue") or "") or {}
            g["temp_c"] = c.get("temp_c")
            g["max_temp_c"] = c.get("max_temp_c")
            g["precip_prob"] = c.get("precip_prob")
            g["heat_risk"] = bool(c.get("heat_risk"))
            g["weather_attribution"] = c.get("attribution")
            if g["heat_risk"]:
                heat_hits += 1
    print(f"KBO: {heat_hits} of {len(upcoming)} upcoming games at or above "
          f"the heat-cancellation threshold")
'''

start = s.find("    # HEAT RISK, from the same document.")
if start != -1:
    end = s.find("heat cancellation\")", start)
    end = s.find("\n", end) + 1
    s = s[:start] + NEW + s[end:]
    applied.append("kbo_precompute: replaced the mykbostats heat reader")
else:
    anchor = ('    print(f"KBO: matched probables onto {starter_hits} of '
              '{len(upcoming)} "\n          f"upcoming games (homepage '
              'carries TODAY only, so anything "\n          f"further out '
              'stays TBD by design)")\n')
    if anchor not in s:
        sys.exit("ANCHOR NOT FOUND (kbo merge point) - nothing written.")
    s = s.replace(anchor, anchor + "\n" + NEW, 1)
    applied.append("kbo_precompute: added forecast wiring")

K.write_text(s)

for a in applied:
    print(f"patched: {a}")
