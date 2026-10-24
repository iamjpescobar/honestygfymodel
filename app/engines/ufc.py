"""
UFC (10-24) — the card and DraftKings' own chances for every fight.

Measured by ufc_probe.py on 10-24 (UFC 333): ESPN's MMA scoreboard (site.
web.api) lists the next card, one competition per fight; ESPN's core feed
carries DraftKings (provider 100) per fight: each fighter's moneyline,
total rounds (O/U 2.5, both prices), the round spread, and the method-of-
victory prices per fighter (KO/TKO/DQ, submission, points) under
"open" / "close"; propBets carry "Fight To Go The Distance" (two prices).
ufcstats.com does not answer from Actions (a 3 KB stub, no events).

THIS STEP IS THE BOOK'S NUMBERS, NOT A MODEL. Every chance here is
DraftKings' price with its cut removed (each market's break-even
chances scaled to add to 1). The site's own fighter model needs the
backfill and its test against these moneylines first (rule 1) — until
then the UFC page says so in plain words.

Which fighter is "away": the core feed's awayAthleteOdds / homeAthlete-
Odds; on the 10-24 card the scoreboard's FIRST competitor was the away
side in every fight, and the odds' "details" ("D. Santos -115") names
the favourite — pair() checks that and swaps the sides when the named
favourite is the other fighter, so a price is never shown under the
wrong man.

Pure apart from the get function passed in.
"""
import re

SITE = ("https://site.web.api.espn.com/apis/site/v2/sports/mma/ufc",
        "https://site.api.espn.com/apis/site/v2/sports/mma/ufc")
CORE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"
PROVIDER = "100"
METHODS = (("koTkoDq", "KO / TKO"), ("submission", "Submission"), ("points", "Decision"))


def _am(x):
    try:
        v = float(str(x).replace("+", ""))
    except (TypeError, ValueError):
        if isinstance(x, str) and x.strip().upper() in ("EVEN", "EV"):
            return 100
        return None
    return int(v) if v >= 100 or v <= -100 else None


def implied(a):
    if a is None:
        return None
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def no_vig(prices):
    """Break-even chances scaled to add to 1 (None when any is missing)."""
    ps = [implied(_am(p)) for p in prices]
    if not ps or any(p is None for p in ps) or sum(ps) <= 0:
        return None
    s = sum(ps)
    return [p / s for p in ps]


def scoreboard(get, day=None):
    """(payload, host) for the next card (or `day`, YYYYMMDD)."""
    for base in SITE:
        try:
            js = get(f"{base}/scoreboard" + (f"?dates={day}" if day else ""))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(js, dict) and "events" in js:
            return js, base
    return None, None


def _fighter(c):
    a = c.get("athlete") or {}
    rec = next((r.get("summary") for r in c.get("records") or [] if isinstance(r, dict)), None)
    return {"id": str(a.get("id") or c.get("id") or ""), "name": a.get("displayName")
            or a.get("fullName") or "?", "short": a.get("shortName"),
            "record": rec, "winner": c.get("winner"),
            "flag": ((a.get("flag") or {}).get("href"))}


def card(js):
    """{"event_id", "name", "date", "fights": [{"id", "weight", "status",
    "a", "b"}]} — fights in the scoreboard's order (main event usually
    last); a is the first competitor."""
    ev = ((js or {}).get("events") or [None])[0]
    if not ev:
        return None
    fights = []
    for c in ev.get("competitions") or []:
        comps = c.get("competitors") or []
        if len(comps) < 2:
            continue
        st = ((c.get("status") or {}).get("type") or {})
        fights.append({"id": str(c.get("id")), "weight": (c.get("type") or {}).get("abbreviation"),
                       "date": c.get("date"), "status": st.get("state"),
                       "done": bool(st.get("completed")), "detail": st.get("detail"),
                       "a": _fighter(comps[0]), "b": _fighter(comps[1])})
    return {"event_id": str(ev.get("id")), "name": ev.get("name"), "date": ev.get("date"),
            "fights": fights}


def _last(name):
    return re.sub(r"[^a-z]", "", str(name or "").split()[-1].lower()) if name else ""


def pair(fight, odds_item):
    """{"a", "b"} side odds dicts for the fight's a / b fighters, from the
    core odds item (away = a unless "details" names b as the favourite
    while saying away is the favourite, or the reverse)."""
    away = odds_item.get("awayAthleteOdds") or {}
    home = odds_item.get("homeAthleteOdds") or {}
    det = str(odds_item.get("details") or "")
    fav = det.split(" ")[0:2]
    fav_last = _last(" ".join(fav[1:]) if len(fav) > 1 else det) if det else ""
    a_last, b_last = _last(fight["a"]["name"]), _last(fight["b"]["name"])
    away_fav = bool(away.get("favorite"))
    swap = False
    if fav_last and (a_last.startswith(fav_last[:5]) or b_last.startswith(fav_last[:5])):
        a_is_fav = a_last.startswith(fav_last[:5])
        swap = a_is_fav != away_fav
    return ({"a": home, "b": away} if swap else {"a": away, "b": home}), swap


def _method(side):
    for when in ("close", "open"):
        vm = ((side.get(when) or {}).get("victoryMethod")) or {}
        if vm:
            out = {}
            for k, _l in METHODS:
                v = vm.get(k)
                v = (v.get("american") if isinstance(v, dict) else v)
                out[k] = _am(v)
            if any(x is not None for x in out.values()):
                return out
    return None


def fight_odds(fight, odds_item, distance=None):
    """The book's chances for one fight, cut removed: {"ml": {a, b} prices,
    "win": {a, b}, "rounds": {line, over, under, p_over}, "method": {a:
    {koTkoDq, submission, points}, b: {...}} (the six outcomes scaled
    together), "distance": {yes, no, p_yes}}."""
    sides, swapped = pair(fight, odds_item or {})
    ml = {k: _am(sides[k].get("moneyLine")) for k in ("a", "b")}
    out = {"ml": ml, "swapped": swapped, "win": None, "rounds": None, "method": None,
           "distance": None}
    w = no_vig([ml["a"], ml["b"]])
    if w:
        out["win"] = {"a": w[0], "b": w[1]}
    ou = (odds_item or {}).get("overUnder")
    if ou is not None:
        o, u = _am((odds_item or {}).get("overOdds")), _am((odds_item or {}).get("underOdds"))
        nv = no_vig([o, u])
        out["rounds"] = {"line": ou, "over": o, "under": u, "p_over": nv[0] if nv else None}
    ma, mb = _method(sides["a"]), _method(sides["b"])
    if ma and mb:
        keys = [k for k, _l in METHODS]
        nv = no_vig([ma[k] for k in keys] + [mb[k] for k in keys])
        if nv:
            out["method"] = {"a": dict(zip(keys, nv[:3])), "b": dict(zip(keys, nv[3:])),
                             "prices": {"a": ma, "b": mb}}
    if distance and len(distance) == 2:
        nv = no_vig(distance)
        if nv:
            # the YES price is the longer one far more often than not, but
            # order is not trusted: "goes the distance" must agree with the
            # decision share of the method market when there is one
            yes, no_ = distance
            p_yes = nv[0]
            if out["method"]:
                dec = out["method"]["a"]["points"] + out["method"]["b"]["points"]
                if abs((1 - p_yes) - dec) < abs(p_yes - dec):
                    yes, no_, p_yes = distance[1], distance[0], nv[1]
            elif out["rounds"] and out["rounds"].get("p_over") is not None \
                    and float(out["rounds"]["line"]) < 3:
                # going the distance needs the fight past the round line too:
                # P(distance) cannot be above P(over the round line)
                if p_yes > out["rounds"]["p_over"] + 0.02 >= 1 - p_yes:
                    yes, no_, p_yes = distance[1], distance[0], nv[1]
            out["distance"] = {"yes": _am(yes), "no": _am(no_), "p_yes": p_yes}
    return out


def fetch_fight_odds(get, event_id, fight_id):
    """(DraftKings' odds item, distance prices [p, p]) for one fight."""
    base = f"{CORE}/events/{event_id}/competitions/{fight_id}/odds"
    od = get(f"{base}?lang=en&region=us") or {}
    item = next((i for i in od.get("items") or []
                 if str((i.get("provider") or {}).get("id")) == PROVIDER), None)
    dist = None
    try:
        pb = get(f"{base}/{PROVIDER}/propBets?lang=en&region=us&limit=200") or {}
        ds = [((x.get("odds") or {}).get("american") or {}).get("value")
              for x in pb.get("items") or []
              if "distance" in str((x.get("type") or {}).get("name")).lower()]
        dist = ds[:2] if len(ds) >= 2 else None
    except Exception:  # noqa: BLE001
        pass
    return item, dist


def build(get, day=None):
    """The card with every fight's book chances (fights without odds kept,
    marked)."""
    js, _host = scoreboard(get, day)
    c = card(js)
    if not c:
        return None
    for f in c["fights"]:
        try:
            item, dist = fetch_fight_odds(get, c["event_id"], f["id"])
        except Exception:  # noqa: BLE001
            item, dist = None, None
        f["odds"] = fight_odds(f, item, dist) if item else None
    return c
