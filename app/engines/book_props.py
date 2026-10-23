"""
The sportsbook's own player-prop lines and prices (10-23), from ESPN's
free core feed: sports.core.api.espn.com/v2/sports/{sport}/leagues/{lg}/
events/{id}/competitions/{id}/odds/{provider}/propBets. Measured by
prop_lines_probe.py on 10-23: one provider (100, DraftKings) for NFL,
NHL, NBA and MLB; 500-1,500 items an event (paged, limit 1000).

One item (the probe's sample):
  {"athlete": {"$ref": ".../athletes/3735?..."},
   "type": {"id": "1", "name": "Total Points"},
   "odds": {"american": {"value": "+105", "open": "+100"}, ...},
   "current": {"target": {"value": 0.5}}, "open": {"target": {"value": 0.5}},
   "lastUpdated": "2026-10-23T12:22Z"}
There is NO side field. An over / under market ("Total ...") comes as
TWO items with the same player, type and line, one per side; a
"... Milestones" market is one item per threshold (that many or more).
Which of a pair is the over is MEASURED, not assumed (side_check): the
milestone at line + 0.5 IS the over, so whichever of the pair prices
closer to it is the over.

Why this exists: the boards open each player on a line the MODEL picks
and the reader types the book's — "off by 2 and up". With the book's
line and price saved every run, the boards can open on the book's own
number, and every disagreement between the site and the book can be
graded (who was right) — the test the props have never had.

Pure — no requests (fetch_event takes a get function).
"""
import re

CORE = "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{lg}"
PROVIDER = "100"
ATHLETE = re.compile(r"/athletes/(\d+)")


def _num(x):
    try:
        return float(str(x).replace("+", ""))
    except (TypeError, ValueError):
        return None


def american(x):
    """'+105' -> 105, '-140' -> -140, 'EVEN' -> 100; None when absent."""
    if isinstance(x, str) and x.strip().upper() in ("EVEN", "EV"):
        return 100
    v = _num(x)
    return int(v) if v is not None and (v >= 100 or v <= -100) else None


def implied(a):
    """The price's own break-even chance (vig included)."""
    if a is None:
        return None
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def fetch_event(get, sport, lg, eid, provider=PROVIDER, limit=1000, max_pages=5):
    """Every propBets item for one event (all pages)."""
    base = (CORE.format(sport=sport, lg=lg)
            + f"/events/{eid}/competitions/{eid}/odds/{provider}/propBets")
    out = []
    for page in range(1, max_pages + 1):
        js = get(f"{base}?lang=en&region=us&limit={limit}&page={page}") or {}
        out += [x for x in js.get("items") or [] if isinstance(x, dict)]
        pc = js.get("pageCount")
        if not pc or page >= int(pc):
            break
    return out


def parse(items):
    """[{"pid", "type_id", "type", "line", "price", "open_price",
    "open_line", "updated", "k"}] — k is the item's place among the items
    with the same player, type and line (0, 1): the pair's order."""
    rows, seen = [], {}
    for it in items or []:
        m = ATHLETE.search(str(((it.get("athlete") or {}).get("$ref")) or ""))
        typ = it.get("type") or {}
        line = _num(((it.get("current") or {}).get("target") or {}).get("value"))
        am = ((it.get("odds") or {}).get("american") or {})
        key = (m.group(1) if m else None, str(typ.get("id")), line)
        k = seen.get(key, 0)
        seen[key] = k + 1
        rows.append({"pid": key[0], "type_id": key[1], "type": typ.get("name"), "line": line,
                     "price": american(am.get("value")), "open_price": american(am.get("open")),
                     "open_line": _num(((it.get("open") or {}).get("target") or {}).get("value")),
                     "updated": it.get("lastUpdated"), "k": k})
    return rows


def family(type_name):
    """'Total Shots on Goal' / 'Shots on Goal Milestones' -> 'shots on
    goal'; '(incl. overtime)' dropped. None for other shapes."""
    t = re.sub(r"\s*\(incl\. overtime\)", "", str(type_name or "")).strip().lower()
    if t.startswith("total ") and "milestone" not in t:
        return t[6:]
    if t.endswith(" milestones"):
        return t[:-11]
    return None


def side_check(rows):
    """{"pairs", "first_is_over", "second_is_over"}: for every over / under
    pair (k 0 and 1, same player / type / line) that has a milestone
    (same player and family, threshold line + 0.5), which of the pair
    prices closer to the milestone — that one is the over."""
    mil = {}
    for r in rows:
        f = family(r["type"])
        if f and "milestone" in str(r["type"]).lower() and r["price"] is not None \
                and r["line"] is not None:
            mil[(r["pid"], f, float(r["line"]))] = implied(r["price"])
    pairs = {}
    for r in rows:
        f = family(r["type"])
        if f and str(r["type"]).lower().startswith("total") and r["price"] is not None \
                and r["line"] is not None and r["k"] in (0, 1):
            pairs.setdefault((r["pid"], r["type_id"], r["line"], f), {})[r["k"]] = r["price"]
    out = {"pairs": 0, "first_is_over": 0, "second_is_over": 0}
    for (pid, _t, line, f), pr in pairs.items():
        if 0 not in pr or 1 not in pr:
            continue
        m = mil.get((pid, f, float(line) + 0.5))
        if m is None:
            continue
        out["pairs"] += 1
        d0, d1 = abs(implied(pr[0]) - m), abs(implied(pr[1]) - m)
        out["first_is_over" if d0 < d1 else "second_is_over"] += 1
    return out


def sides(rows, first_is_over):
    """{(pid, type, line): {"over": price, "under": price}} for over /
    under pairs, by the measured order; milestones as {"over": price}
    at line - 0.5 (3+ shots = over 2.5)."""
    out = {}
    for r in rows:
        if r["price"] is None or r["line"] is None or not r["pid"]:
            continue
        t = str(r["type"])
        if "milestone" in t.lower():
            key = (r["pid"], t, float(r["line"]) - 0.5)
            out.setdefault(key, {})["over"] = r["price"]
        elif r["k"] in (0, 1):
            side = ("over" if r["k"] == 0 else "under") if first_is_over else \
                ("under" if r["k"] == 0 else "over")
            out.setdefault((r["pid"], t, float(r["line"])), {})[side] = r["price"]
        else:
            continue
    return out


# Markets the site never prices (who scores FIRST / LAST, team totals,
# exact-score, longest play, period / game lines) are not kept: the record
# is committed every run, so it holds only what can be compared or graded.
SKIP_WORDS = ("first", "last ", "team", "exact", "longest", "moneyline", "spread",
              "period total", "double double", "triple double")


def keep(type_name):
    t = str(type_name or "").lower()
    return not any(w in t for w in SKIP_WORDS)


def compact(rows):
    """({type_id: name}, [[pid, type_id, line, k, price, first_price,
    open_price]]) — the day's file stores rows as short lists."""
    types, out = {}, []
    for r in rows:
        if not keep(r.get("type")):
            continue
        types[r["type_id"]] = r["type"]
        out.append([r["pid"], r["type_id"], r["line"], r["k"], r.get("price"),
                    r.get("first_price"), r.get("open_price")])
    return types, out


def expand(entry):
    """The rows of one saved event back as dicts."""
    types = entry.get("types") or {}
    return [{"pid": x[0], "type_id": x[1], "type": types.get(x[1]), "line": x[2], "k": x[3],
             "price": x[4], "first_price": x[5], "open_price": x[6]}
            for x in entry.get("rows") or []]


def merge_snapshot(old, event_rows, now):
    """The day's file: {event_id: {"first": iso, "last": iso, "types": {id:
    name}, "rows": [compact rows]}}
    — the FIRST prices seen are kept (open of our record) beside the
    latest (closest to the game), so a grade can use either."""
    out = dict(old or {})
    for eid, rows in (event_rows or {}).items():
        prev = out.get(eid) or {}
        prows = expand(prev)
        first = {(r["pid"], r["type_id"], r["line"], r["k"]): r.get("price") for r in prows}
        firsts = {(r["pid"], r["type_id"], r["line"], r["k"]): r.get("first_price")
                  for r in prows}
        new = []
        for r in rows:
            key = (r["pid"], r["type_id"], r["line"], r["k"])
            fp = firsts.get(key) if firsts.get(key) is not None else first.get(key)
            new.append(dict(r, first_price=fp if fp is not None else r.get("price")))
        types, rows_c = compact(new)
        out[eid] = {"first": prev.get("first") or now, "last": now, "types": types,
                    "rows": rows_c}
    return out
