"""
The book's prop lines (10-23) — engines/book_props (parse ESPN's core
propBets items, measure which of an over / under pair is the over,
merge runs into the day's record) and book_props_snapshot.py with its
nightly steps.

Plain script — exits non-zero on failure. Items in the shape the probe
printed on 10-23 (athlete.$ref, type {id, name}, odds.american {value,
open}, current / open target value, lastUpdated; no side field) (rule 5).
No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - side_check calling the pair member FARTHER from the milestone the over
    -> "the over is the one priced like the milestone" fails
  - keep() keeping every market
    -> "markets the site never prices ... are not kept" fails
  - merge_snapshot overwriting the first price with the latest
    -> "the first price seen is kept beside the latest" fails
  - fetch_event reading page 1 only
    -> "every page of an event is read" fails
Step 2 (10-23, the pages read the record), each red:
  - board() taking the SECOND member of a pair as the over
    -> "the measured order: the first of a pair is the over" fails
  - price_at giving the main line's price at a moved line
    -> "a moved line gets the ladder's price or none" fails
MLB by name (10-23), each red:
  - name_key keeping "Jr."
    -> "MLB players are matched by name across the two id systems" fails
  - walks mapped for MLB (the site's include HBP, the book's do not)
    -> "MLB walks get no book line (not the same bet)" fails
"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import book_props as bp  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def item(pid, tid, name, line, price, open_price=None):
    return {"athlete": {"$ref": f"http://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/"
                                f"seasons/2027/athletes/{pid}?lang=en"},
            "type": {"id": tid, "name": name},
            "odds": {"american": {"value": price, "open": open_price or price}},
            "current": {"target": {"value": line}}, "open": {"target": {"value": line}},
            "lastUpdated": "2026-10-23T12:22Z"}


# the feed lists the UNDER first in this fake world: the milestone (2+ points
# at -140) prices like the second member, so the second is the over
ITEMS = [item(3735, "1", "Total Points", 0.5, "+105", "+100"),
         item(3735, "1", "Total Points", 0.5, "-140", "-135"),
         item(3735, "9", "Points Milestones", 1, "-135"),
         item(77, "1", "Total Points", 0.5, "+150"),
         item(77, "1", "Total Points", 0.5, "-190"),
         item(77, "9", "Points Milestones", 1, "-185"),
         item(77, "4", "Total Shots on Goal (incl. overtime)", 2.5, "+120"),
         item(77, "4", "Total Shots on Goal (incl. overtime)", 2.5, "-150"),
         item(77, "5", "Shots on Goal Milestones", 3, "-145"),
         item(77, "7", "Anytime Goalscorer", 0.5, "+210"),
         {"type": {"id": "8", "name": "Total Passing Yards (incl. overtime)"},
          "athlete": {"$ref": ".../athletes/8439?x"}, "current": {"target": {"value": 233.5}}}]
R = bp.parse(ITEMS)
check("an item reads as player, type, line, price (with the open), pair order k",
      R[0] == dict(R[0], pid="3735", type_id="1", type="Total Points", line=0.5, price=105,
                   open_price=100, k=0) and R[1]["k"] == 1 and R[1]["price"] == -140)
check("a prop with no price is kept, price None (missing is not zero)",
      R[-1]["price"] is None and R[-1]["line"] == 233.5 and R[-1]["pid"] == "8439")
check("prices: +105 -> 105, -140 -> -140, EVEN -> 100; break-even chances",
      bp.american("EVEN") == 100 and abs(bp.implied(-140) - 0.5833) < 1e-3
      and abs(bp.implied(150) - 0.4) < 1e-9 and bp.american("1.5") is None)
check("the families pair a total with its milestones",
      bp.family("Total Shots on Goal (incl. overtime)") == "shots on goal"
      and bp.family("Shots on Goal Milestones") == "shots on goal"
      and bp.family("Anytime Goalscorer") is None)
sc = bp.side_check(R)
check("the over is the one priced like the milestone (measured, not assumed)",
      sc == {"pairs": 3, "first_is_over": 0, "second_is_over": 3})
S = bp.sides(R, first_is_over=False)
check("sides by the measured order; a milestone of 3+ is the over at 2.5",
      S[("3735", "Total Points", 0.5)] == {"over": -140, "under": 105}
      and S[("77", "Shots on Goal Milestones", 2.5)] == {"over": -145})
m1 = bp.merge_snapshot({}, {"e1": R[:2]}, "T1")
R2 = [dict(r, price=r["price"] - 10) for r in R[:2]]
m2 = bp.merge_snapshot(m1, {"e1": R2}, "T2")
e2 = bp.expand(m2["e1"])
check("the first price seen is kept beside the latest",
      m2["e1"]["first"] == "T1" and m2["e1"]["last"] == "T2"
      and e2[0]["price"] == 95 and e2[0]["first_price"] == 105 and e2[0]["type"] == "Total Points")
_t, _rows = bp.compact(bp.parse([item(1, "30", "First Goalscorer", 0.5, "+900"),
                                 item(1, "31", "Team Total Goals (Excl OT)", 2.5, "-110")] + ITEMS))
check("markets the site never prices (first / last scorer, team totals ...) are not kept",
      "30" not in _t and "31" not in _t and len(_rows) == len(ITEMS))
pages = []


def get(url):
    pages.append(url)
    p = int(url.split("page=")[1])
    return {"pageCount": 2, "items": ITEMS[:5] if p == 1 else ITEMS[5:]}


got = bp.fetch_event(get, "hockey", "nhl", "401892564")
check("every page of an event is read",
      len(got) == len(ITEMS) and len(pages) == 2
      and "/events/401892564/competitions/401892564/odds/100/propBets" in pages[0])

# --- the snapshot script, with a fake feed ----------------------------------------------------
import book_props_snapshot as bps  # noqa: E402


def sb(league, d):
    return {"events": [{"id": d[-2:], "shortName": "MTL @ CHI", "status": {"type": {"state": "pre"}}},
                       {"id": "8", "shortName": "done", "status": {"type": {"state": "post"}}}]}, "x"


with tempfile.TemporaryDirectory() as td:
    out = bps.run_league("nhl", date(2026, 10, 23), lambda u: {"items": ITEMS}, sb,
                         ("hockey", "nhl"), out_dir=td, now="T1", sleep=0)
    files = sorted(p.name for p in (Path(td) / "nhl").glob("*.json"))
    js = json.loads((Path(td) / "nhl" / "2026-10-23.json").read_text())
check("the snapshot saves upcoming games only, one file a day, and prints the side check",
      out["events"] == 2 and files == ["2026-10-23.json", "2026-10-24.json"] and set(js) == {"23"}
      and out["side"]["second_is_over"] == 3)
wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the nightly snapshots and commits the record in its own steps",
      "python book_props_snapshot.py ||" in wf and "git add data/props" in wf
      and wf.index("python book_props_snapshot.py") < wf.index("Fetch and package real Statcast"))

# --- step 2: the pages read the record -------------------------------------------------------
# the real feed lists the OVER first (measured 10-23: NHL 100 / 103, NBA 604 / 615, MLB 83 / 83)
REAL = [item(5, "4", "Total Shots on Goal", 2.5, "+115"), item(5, "4", "Total Shots on Goal",
                                                               2.5, "-155"),
        item(5, "5", "Shots on Goal Milestones", 2, "-240"),
        item(5, "5", "Shots on Goal Milestones", 3, "+115"),
        item(5, "5", "Shots on Goal Milestones", 4, "+285"),
        item(5, "7", "Anytime Goalscorer", 0.5, "+210"),
        {"type": {"id": "8", "name": "Total Receiving Yards (incl. overtime)"},
         "athlete": {"$ref": ".../athletes/6?x"}, "current": {"target": {"value": 64.5}}},
        item(6, "9", "Receiving Yards Milestones", 75, "+180")]
snap = bp.merge_snapshot({}, {"e": bp.parse(REAL)}, "2026-10-23T22:00Z")
BD = bp.board([snap])
k5 = bp.lookup(BD, "nhl", "5", "sog")
check("the measured order: the first of a pair is the over",
      bp.FIRST_IS_OVER and k5["line"] == 2.5 and k5["over"] == 115 and k5["under"] == -155)
check("the ladder: 3+ shots is the over at 2.5, 4+ at 3.5; a yes-market at its own line",
      k5["ladder"] == {1.5: -240, 2.5: 115, 3.5: 285}
      and bp.lookup(BD, "nhl", "5", "g") == {"line": 0.5, "over": 210, "under": None,
                                              "ladder": {0.5: 210}})
k6 = bp.lookup(BD, "nfl", "6", "rec_yds")
check("an NFL total with no price keeps the line, prices come only from the ladder",
      k6["line"] == 64.5 and k6["over"] is None and k6["ladder"] == {74.5: 180})
check("a moved line gets the ladder's price or none (never the main line's price)",
      bp.price_at(k5, 2.5, "Over") == 115 and bp.price_at(k5, 2.5, "Under") == -155
      and bp.price_at(k5, 3.5, "Over") == 285 and bp.price_at(k5, 3.5, "Under") is None
      and bp.price_at(k5, 9.5, "Over") is None)
with tempfile.TemporaryDirectory() as td:
    (Path(td) / "props" / "nhl").mkdir(parents=True)
    (Path(td) / "props" / "nhl" / "2026-10-23.json").write_text(json.dumps(snap))
    lb, asof = bp.load_board("nhl", [Path(td) / "nope", td], "2026-10-23")
check("the page loads today's record from whichever data root has it, with its time",
      asof == "2026-10-23T22:00Z" and bp.lookup(lb, "nhl", "5", "sog")["line"] == 2.5)
bfp = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("the Bet Finder opens each row on DraftKings' line and price, and re-prices a moved line",
      "_attach_book(groups, sport.lower())" in bfp and '"DraftKings"' in bfp
      and "return float(_bk(r)[\"line\"])" in bfp
      and "_yp = _bp.price_at(_bk(r), ln, side)" in bfp and "j = bf.judge(ch, _yp, _stk, _os," in bfp)

# --- MLB: matched by name ------------------------------------------------------------------
def mitem(pid, tid, name, line, price):
    x = item(pid, tid, name, line, price)
    x["athlete"]["$ref"] = f"http://x/v2/sports/baseball/leagues/mlb/seasons/2026/athletes/{pid}?a"
    return x


MI = [mitem(33372, "46", "Total Strikeouts", 5.5, "+129"), mitem(33372, "46", "Total Strikeouts",
                                                                 5.5, "-165"),
      mitem(901, "1", "Total Hits", 0.5, "-200"), mitem(901, "1", "Total Hits", 0.5, "+150"),
      mitem(901, "2", "Total Walks (Batter)", 0.5, "+180"),
      mitem(901, "2", "Total Walks (Batter)", 0.5, "-240")]
mrows = bp.parse(MI)
looked = []


def aget(url):
    looked.append(url)
    return {"displayName": {"33372": "Freddy Peralta", "901": "Vladimir Guerrero Jr."}[
        url.split("athletes/")[1].split("?")[0]]}


nm = bp.athlete_names(aget, mrows)
msnap = bp.merge_snapshot({}, {"g": mrows}, "T", {"g": nm})
MB = bp.board([msnap])
vg = MB["_names"].get(bp.name_key("Vladimir Guerrero"))
check("MLB players are matched by name across the two id systems (one athlete call each)",
      len(looked) == 2 and vg == "901" and MB["_names"][bp.name_key("Freddy Peralta")] == "33372"
      and bp.lookup(MB, "mlb", vg, "h")["over"] == -200
      and bp.lookup(MB, "mlb_p", "33372", "k") == {"line": 5.5, "over": 129, "under": -165,
                                                  "ladder": {}})
check("MLB walks get no book line (not the same bet: the site's include hit-by-pitch)",
      "bb" not in bp.MARKETS["mlb"] and "bb" not in bp.MARKETS["mlb_p"]
      and bp.lookup(MB, "mlb", vg, "bb") is None)
check("a second run keeps the names it already has (no repeat calls)",
      bp.athlete_names(aget, mrows, known=nm) == {} and len(looked) == 2
      and bp.merge_snapshot(msnap, {"g": mrows}, "T2")["g"]["names"] == nm)
check("the Bet Finder matches MLB rows by name, starters on their own markets",
      "names.get(bp.name_key(r.get(\"Batter\") or r.get(\"Pitcher\")))" in bfp
      and 'lg = "mlb_p"' in bfp and '("NHL", "NBA", "NFL", "MLB")' in bfp)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall book prop line checks passed")
