"""
Forecast weather for KBO and NPB venues, from a source we actually own.

WHY THIS EXISTS

park_weather.py already does this properly for MLB: api.weather.gov,
US government data, public domain, no key. There was no equivalent for
the international slates, so KBO temperature and heat-cancellation
warnings were being read off mykbostats' rendered homepage instead.

That was wrong three ways. It inherited their terms (Acceptable Use
clause 6 forbids using their content to make sports bets). It inherited
their source — that temperature is Apple Weather, arriving through a
third party with its own attribution rules. And it inherited their
markup, which was rewritten on 2026-08-04 and broke the last parser
that depended on it.

Fetching a forecast directly fixes all three, and gives something the
homepage could never provide: TOMORROW's risk. Their page shows today.

SOURCE AND LICENCE — read before changing anything here.

Open-Meteo, free tier. Their terms define non-commercial to include
"private or non-profit websites or apps that do not have subscriptions
or advertising", and commercial as "operating websites or apps that
have subscriptions or display advertisements". This site is currently
private, login-gated, unpaid and adless, so the free tier applies.

*** IF THIS SITE EVER TAKES SUBSCRIPTIONS OR RUNS ADS, THIS BECOMES
*** COMMERCIAL USE AND NEEDS A PAID PLAN. That is not a footnote; it
*** is the condition the whole choice rests on.

The data is CC BY 4.0, which REQUIRES attribution with a link wherever
it is displayed. ATTRIBUTION below is exported for that purpose and
ships in the slate payload so the view can render it. Removing it is a
licence violation, not a style choice.

Limits: 10,000 calls/day. One call covers the whole slate, because
Open-Meteo accepts comma-separated coordinates and returns an array.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

API = "https://api.open-meteo.com/v1/forecast"

# CC BY 4.0 requires this next to any displayed value. Kept as HTML
# because that is how every consumer here renders.
ATTRIBUTION = ('<a href="https://open-meteo.com/">Weather data by '
               'Open-Meteo.com</a>')

SEOUL = ZoneInfo("Asia/Seoul")
TOKYO = ZoneInfo("Asia/Tokyo")

# Stadium coordinates, good to a few hundred metres — far finer than any
# forecast grid, so precision beyond this buys nothing. Keyed to the
# venue rather than the club because two KBO clubs share Jamsil and
# clubs move buildings, which is the same reason intl_venues.py keys on
# venue.
KBO_COORDS = {
    "Jamsil":     (37.5122, 127.0719),
    "Gocheok":    (37.4982, 126.8672),   # Sky Dome — roofed, still fetched
    "Munhak":     (37.4370, 126.6933),   # Incheon SSG Landers Field
    "Suwon":      (37.2997, 127.0097),
    "Daegu":      (35.8411, 128.6816),
    "Gwangju":    (35.1682, 126.8890),
    "Daejeon":    (36.3170, 127.4290),
    "Changwon":   (35.2226, 128.5822),
    "Sajik":      (35.1940, 129.0615),   # Busan
}

NPB_COORDS = {
    "Tokyo Dome":          (35.7056, 139.7519),
    "Jingu Stadium":       (35.6748, 139.7170),
    "Yokohama Stadium":    (35.4437, 139.6400),
    "Koshien Stadium":     (34.7212, 135.3617),
    "Kyocera Dome Osaka":  (34.6693, 135.4761),
    "Vantelin Dome":       (35.1856, 136.9475),
    "Mazda Stadium":       (34.3915, 132.4845),
    "PayPay Dome":         (33.5953, 130.3623),
    "Rakuten Mobile Park": (38.2562, 140.9022),
    "Belluna Dome":        (35.7694, 139.4197),
    "Zozo Marine Stadium": (35.6453, 140.0313),
    "Escon Field":         (42.9897, 141.5100),
}

# KBO venue strings are free text, so match on a distinctive substring
# the way intl_venues.KBO_VENUE_PATTERNS does rather than by equality.
KBO_PATTERNS = (
    ("gocheok", "Gocheok"), ("jamsil", "Jamsil"), ("sajik", "Sajik"),
    ("munhak", "Munhak"), ("incheon", "Munhak"), ("landers", "Munhak"),
    ("suwon", "Suwon"), ("daegu", "Daegu"), ("gwangju", "Gwangju"),
    ("champions field", "Gwangju"), ("daejeon", "Daejeon"),
    ("changwon", "Changwon"),
)

# THE THRESHOLD IS A GUESS UNTIL SOMEONE CHECKS IT.
#
# 35°C is the figure commonly cited for KBO heat cancellations and lines
# up with the 폭염경보 (heat wave warning) criteria, but it has NOT been
# verified against a published KBO rule, and the rule may key on
# apparent temperature or on a KMA warning rather than a raw reading.
#
# So this is a named constant with the uncertainty written next to it,
# and every forecast logs its max temperature whether or not the flag
# fires. A week of logs beside the actual cancellations calibrates this
# properly. Do not quietly tune the number without recording why.
HEAT_CANCEL_C = 35.0


def coords_for(league, venue):
    """(lat, lon) for a venue string, or None when it is unrecognised.

    None rather than a default: a guessed stadium produces a confident
    forecast for the wrong city, which is worse than no forecast at all.
    """
    if not venue:
        return None
    if (league or "").lower() == "kbo":
        v = venue.lower()
        for needle, canon in KBO_PATTERNS:
            if needle in v:
                return KBO_COORDS.get(canon)
        return None
    return NPB_COORDS.get(venue)


def _tz(league):
    return SEOUL if (league or "").lower() == "kbo" else TOKYO


def forecast(league, venues, date_iso, hour=18):
    """{venue: {...}} for one slate, in a single API call.

    venues is the list of venue strings the slate builder emitted; the
    unrecognised ones are dropped and reported rather than guessed.

    hour is local first-pitch hour — 18 covers the 18:00 and 18:30
    starts that make up nearly every KBO and NPB weeknight. Weekend
    afternoon games read an hour that is off by a few, which moves the
    temperature by about a degree and does not change a heat flag.
    """
    pairs, unknown = [], []
    for v in venues:
        c = coords_for(league, v)
        (pairs.append((v, c)) if c else unknown.append(v))
    if unknown:
        print(f"  weather: no coordinates for {sorted(set(unknown))} — "
              f"omitted rather than guessed")
    if not pairs:
        return {}

    # Deduplicate: two clubs share Jamsil, and a doubleheader would
    # otherwise pay for the same grid point twice.
    seen, order = {}, []
    for v, c in pairs:
        if c not in seen:
            seen[c] = []
            order.append(c)
        seen[c].append(v)

    params = {
        "latitude": ",".join(str(c[0]) for c in order),
        "longitude": ",".join(str(c[1]) for c in order),
        "hourly": "temperature_2m,precipitation_probability,wind_speed_10m",
        "daily": "temperature_2m_max",
        "timezone": str(_tz(league)),
        "start_date": date_iso,
        "end_date": date_iso,
    }
    try:
        r = requests.get(API, params=params, timeout=25)
    except Exception as exc:
        print(f"  weather: fetch failed ({exc}) — no forecast this run")
        return {}
    if r.status_code != 200:
        print(f"  weather: HTTP {r.status_code} — no forecast this run")
        return {}
    try:
        payload = r.json()
    except Exception:
        print("  weather: 200 but not JSON — no forecast this run")
        return {}

    # A single coordinate returns an object; several return a list.
    blocks = payload if isinstance(payload, list) else [payload]
    if len(blocks) != len(order):
        print(f"  weather: asked for {len(order)} locations, got "
              f"{len(blocks)} — dropped rather than misaligned")
        return {}

    out = {}
    want = f"{date_iso}T{hour:02d}:00"
    for coord, block in zip(order, blocks):
        hourly = block.get("hourly") or {}
        times = hourly.get("time") or []
        idx = times.index(want) if want in times else None
        daily = (block.get("daily") or {}).get("temperature_2m_max") or []
        tmax = daily[0] if daily else None

        def at(key):
            vals = hourly.get(key) or []
            return vals[idx] if idx is not None and idx < len(vals) else None

        reading = {
            "temp_c": at("temperature_2m"),
            "precip_prob": at("precipitation_probability"),
            "wind_kph": at("wind_speed_10m"),
            "max_temp_c": tmax,
            # Flag on the DAY's max, not first-pitch. A 4pm peak of 36
            # that eases to 33 by 18:30 is still the day a game gets
            # called, and the call is usually made in the afternoon.
            "heat_risk": bool(tmax is not None and tmax >= HEAT_CANCEL_C),
            "attribution": ATTRIBUTION,
        }
        for v in seen[coord]:
            out[v] = reading
    return out


def summarize(readings):
    """One log line. Prints max temps even when nothing is flagged, so a
    week of runs calibrates HEAT_CANCEL_C instead of only proving it."""
    if not readings:
        return "weather: no forecast"
    seen, temps, risk = set(), [], 0
    for v, r in readings.items():
        if v in seen:
            continue
        seen.add(v)
        if r.get("max_temp_c") is not None:
            temps.append(r["max_temp_c"])
        risk += bool(r.get("heat_risk"))
    hi = f"{max(temps):.0f}" if temps else "?"
    return (f"weather: {len(seen)} venues, max {hi}°C, "
            f"{risk} at or above {HEAT_CANCEL_C:.0f}°C heat threshold")


if __name__ == "__main__":  # pragma: no cover - manual check
    today = datetime.now(SEOUL).strftime("%Y-%m-%d")
    got = forecast("kbo", ["Jamsil", "Daegu", "Sajik"], today)
    print(json.dumps(got, indent=2, ensure_ascii=False))
    print(summarize(got))
