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

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall book prop line checks passed")
