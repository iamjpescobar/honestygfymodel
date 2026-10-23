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
        rows.append({"ref": (it.get("athlete") or {}).get("$ref"),
                     "pid": key[0], "type_id": key[1], "type": typ.get("name"), "line": line,
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


def merge_snapshot(old, event_rows, now, names=None):
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
        nm = dict(prev.get("names") or {})
        nm.update((names or {}).get(eid) or {})
        if nm:
            out[eid]["names"] = nm
    return out


# ----------------------------------------------------------------------
# READING THE RECORD ON THE PAGES (10-23, step 2)
# ----------------------------------------------------------------------
# Which member of a pair is the over — MEASURED on the first real run
# (10-23 nightly, side_check against the milestones): NHL 100 of 103,
# NBA 604 of 615, MLB 83 of 83 pairs priced the FIRST item like the
# over (the stray ~2% are alt-ladder prices a few cents apart). NFL's
# main totals carry a line and no price.
FIRST_IS_OVER = True

# our stat key -> (the book's total, the book's ladder "N or more"), by
# league; names compared after norm() (lower case, "(incl. overtime)"
# dropped). Several spellings where the feed has shown more than one.
MARKETS = {
    "nhl": {"sog": (("total shots on goal",), ("shots on goal milestones",)),
            "pts": (("total points",), ("points milestones",)),
            "a": (("total assists",), ("assists milestones",)),
            "g": ((), ("goals milestones",)),
            "sv": (("total saves",), ("goalkeeper saves milestones",))},
    "nba": {"pts": (("total points",), ("points milestones",)),
            "reb": (("total rebounds",), ("rebounds milestones",)),
            "ast": (("total assists",), ("assists milestones",)),
            "tpm": (("total 3-point field goals",), ("3-point field goals milestones",)),
            "pra": (("total points, rebounds, and assists",),
                    ("points + assists + rebounds milestones",)),
            "pr": (("total points and rebounds",), ("points + rebounds milestones",)),
            "pa": (("total points and assists",), ("points + assists milestones",)),
            "ra": (("total assists and rebounds",), ("rebounds + assists milestones",)),
            "q1pts": (("1st quarter total points",), ("points milestones - 1st quarter",))},
    "nfl": {"pass_yds": (("total passing yards",), ("passing yards milestones",)),
            "pass_att": (("total passing attempts", "total pass attempts"),
                         ("passing attempts milestones",)),
            "pass_cmp": (("total pass completions", "total passing completions",
                          "total completions"),
                         ("passing completions milestones",)),
            "rush_yds": (("total rushing yards",), ("rushing yards milestones",)),
            "carries": (("total carries", "total rushing attempts"),
                        ("rushing attempts milestones",)),
            "rec_yds": (("total receiving yards",), ("receiving yards milestones",)),
            "rec": (("total receptions",), ("receptions milestones",)),
            "pass_td": (("total passing touchdowns",), ("passing touchdown milestones",)),
            "pass_int": (("total passing interceptions",), ("interceptions thrown milestones",)),
            "scrim_yds": (("total rushing + receiving yards", "total rushing plus receiving yards"),
                          ("rushing + receiving yards milestones",)),
            "q1_rec_yds": (("1st quarter total receiving yards",),
                           ("receiving yards milestones - 1st quarter",)),
            "h1_rec_yds": (("1st half total receiving yards",),
                           ("receiving yards milestones - 1st half",)),
            "q1_rush_yds": (("1st quarter total rushing yards",),
                            ("rushing yards milestones - 1st quarter",)),
            "h1_rush_yds": (("1st half total rushing yards",),
                            ("rushing yards milestones - 1st half",)),
            "q1_pass_yds": (("1st quarter total passing yards",),
                            ("passing yards milestones - 1st quarter",)),
            "h1_pass_yds": (("1st half total passing yards",),
                            ("passing yards milestones - 1st half",))},
}
# MLB (10-23): batters and starters share stat keys (k, h ...) but not
# the book's markets, so the starters have their own map. Walks are left
# OUT on purpose: the site's walks include hit-by-pitch, the book's do
# not — not the same bet, so no line is shown for them.
MARKETS["mlb"] = {"h": (("total hits",), ("hits milestones",)),
                  "tb": (("total bases",), ("total bases milestones",)),
                  "hr": ((), ("home runs milestones",)),
                  "k": ((), ("strikeouts (batter) milestones",)),
                  "s": (("total singles hit",), ("singles milestones",)),
                  "d": (("total doubles hit",), ("doubles milestones",)),
                  "rbi": (("total rbis",), ("rbis milestones",))}
MARKETS["mlb_p"] = {"k": (("total strikeouts",), ("strikeouts thrown milestones",)),
                    "h": (("total hits allowed",), ("hits allowed milestones",))}
# one-sided "yes" markets: the price IS the over at this line
YES = {"nhl": {"g": (("anytime goalscorer", 0.5), ("to score 2+ goals", 1.5),
                     ("to score 3+ goals", 2.5))},
       "nfl": {"td": (("anytime touchdown scorer", 0.5),
                      ("player to score 2 or more touchdowns", 1.5))}}


def norm(type_name):
    return re.sub(r"\s*\(incl\. overtime\)", "", str(type_name or "")).strip().lower()


def name_key(name):
    """'Vladimir Guerrero Jr.' -> 'vladimir guerrero'; accents dropped."""
    import unicodedata
    n = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    n = re.sub(r"[^a-z ]", "", n.lower().replace("-", " ").replace(".", " "))
    return re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", re.sub(r"\s+", " ", n).strip())


def board(day_files):
    """{pid: {norm type: {"lines": {line: {"over", "under"}}, "first":
    {line: {"over", "under"}}}}} from the day files' latest rows (one or
    more {event_id: entry} dicts)."""
    out = {}
    for f in day_files or []:
        for _eid, entry in (f or {}).items():
            for r in expand(entry):
                if not r["pid"] or r["line"] is None or r["k"] not in (0, 1):
                    continue
                t = norm(r["type"])
                ladder = t.endswith("milestones") or "milestones -" in t
                slot = out.setdefault(str(r["pid"]), {}).setdefault(t, {"lines": {}, "first": {}})
                if ladder:
                    ln, side = float(r["line"]) - 0.5, "over"
                elif r["k"] == 0:
                    ln, side = float(r["line"]), "over" if FIRST_IS_OVER else "under"
                else:
                    ln, side = float(r["line"]), "under" if FIRST_IS_OVER else "over"
                slot["lines"].setdefault(ln, {})[side] = r["price"]
                nm = (entry.get("names") or {}).get(str(r["pid"]))
                if nm:
                    out.setdefault("_names", {})[name_key(nm)] = str(r["pid"])
                slot["first"].setdefault(ln, {})[side] = r.get("first_price")
                if r["price"] is None:
                    slot["lines"][ln].setdefault("no_price", True)
    return out


def athlete_names(get, rows, known=None):
    """{pid: name} for the rows' players not already in `known`, read from
    the feed's athlete records (MLB: ESPN's ids are not MLBAM's, so the
    pages match MLB players by NAME)."""
    out = {}
    for r in rows:
        pid = r.get("pid")
        if not pid or pid in out or pid in (known or {}):
            continue
        try:
            a = get(r["ref"]) if r.get("ref") else None
        except Exception:  # noqa: BLE001
            a = None
        nm = (a or {}).get("displayName") or (a or {}).get("fullName")
        if nm:
            out[pid] = nm
    return out


def lookup(bd, league, pid, stat):
    """{"line": the book's main line, "over", "under", "ladder": {line:
    over price}} for one player and stat, or None. The main line is the
    total's (two-sided); a one-sided market gives its own line."""
    p = (bd or {}).get(str(pid))
    if not p:
        return None
    tot, lad = (MARKETS.get(league) or {}).get(stat, ((), ()))
    out = {"line": None, "over": None, "under": None, "ladder": {}}
    for t in tot:
        x = p.get(t)
        if x and x["lines"]:
            ln = sorted(x["lines"], key=lambda k: (x["lines"][k].get("over") is None, k))[0]
            out.update(line=ln, over=x["lines"][ln].get("over"),
                       under=x["lines"][ln].get("under"))
            break
    for t in lad:
        for ln, v in ((p.get(t) or {}).get("lines") or {}).items():
            if v.get("over") is not None:
                out["ladder"][ln] = v["over"]
    for t, ln in ((YES.get(league) or {}).get(stat) or ()):
        x = (p.get(t) or {}).get("lines") or {}
        v = x.get(ln) or next(iter(x.values()), None) if x else None
        if v and v.get("over") is not None:
            out["ladder"].setdefault(ln, v["over"])
    if out["line"] is None and out["ladder"]:
        # no total: the ladder rung nearest even money stands in as the line
        ln = min(out["ladder"], key=lambda k: abs(implied(out["ladder"][k]) - 0.5))
        out.update(line=ln, over=out["ladder"][ln])
    if out["line"] is None:
        return None
    if out["over"] is None and out["line"] in out["ladder"]:
        out["over"] = out["ladder"][out["line"]]
    return out


def price_at(bk, line, side):
    """The book's price for this side at this line (main line or a ladder
    rung for the over), or None."""
    if not bk or line is None:
        return None
    if bk.get("line") is not None and abs(float(line) - float(bk["line"])) < 1e-9:
        return bk.get("over" if side == "Over" else "under")
    if side == "Over":
        return (bk.get("ladder") or {}).get(float(line))
    return None


def load_board(league, roots, today_iso):
    """(board, as_of) from data/props/<league>/<today>.json and the next
    day's under any of `roots` (the published data and the repo's)."""
    from datetime import date, timedelta
    from pathlib import Path
    import json
    d0 = date.fromisoformat(today_iso)
    files, as_of = [], None
    for k in range(0, 3 if league == "nfl" else 2):
        name = f"{(d0 + timedelta(days=k)).isoformat()}.json"
        for root in roots:
            p = Path(root) / "props" / league / name
            if p.exists():
                try:
                    js = json.loads(p.read_text())
                except Exception:  # noqa: BLE001
                    continue
                files.append(js)
                for e in js.values():
                    as_of = max(as_of or "", e.get("last") or "")
                break
    return board(files), as_of
