"""
Site vs DraftKings (10-24) — engines/book_grade: the site's chance
captured beside the book's lines (exactly as the Bet Finder prices it),
the grade against the box score with the book's cut removed, and the
scorecard; book_props_snapshot saving the capture, book_props_grade.py
grading final games once each, the nightly step.

Plain script — exits non-zero on failure. Book items in the core feed's
shape, an NBA games.json row ({"pid", "mu"}), a box score as
{pid: {stat: value}} (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - devig returning the over's break-even (cut left in)
    -> "the book's chance is its two prices with the cut removed" fails
  - grade_event grading a player with no box line as a zero
    -> "a player who did not play is not graded" fails
  - grade_league grading an event twice
    -> "a final game is graded once" fails
  - a ladder-only price graded with the cut left in
    -> "a one-sided price is graded apart, at the measured cut" fails
  - market_status giving a verdict under MIN_GRADED lines
    -> "no verdict before 300 graded lines" fails
  - the Bet Finder not capping a no-edge market
    -> "a market with no edge proven is capped at THIN" fails
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import bet_finder as bf  # noqa: E402
from engines import book_grade as bg  # noqa: E402
from engines import book_props as bp  # noqa: E402
from engines import nba_model as nm  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def item(pid, tid, name, line, price):
    return {"athlete": {"$ref": f"http://x/athletes/{pid}?a"}, "type": {"id": tid, "name": name},
            "odds": {"american": {"value": price, "open": price}},
            "current": {"target": {"value": line}}, "lastUpdated": "T"}


ITEMS = [item(11, "1", "Total Points", 24.5, "-110"), item(11, "1", "Total Points", 24.5, "-110"),
         item(11, "9", "Points Milestones", 30, "+260"),
         item(12, "1", "Total Points", 9.5, "+120"), item(12, "1", "Total Points", 9.5, "-150"),
         item(13, "1", "Total Points", 14.5, "-120"), item(13, "1", "Total Points", 14.5, "-105")]
snap = bp.merge_snapshot({}, {"e1": bp.parse(ITEMS)}, "T1")
BD = bp.board([snap])
PAY = {"model": {"sizes": {}, "test": {}},
       "games": [{"event_id": "e1", "status": "scheduled",
                  "home_props": [{"pid": "11", "mu": {"pts": 26.0}},
                                 {"pid": "12", "mu": {"pts": 8.0}},
                                 {"pid": "13", "mu": {"pts": 15.0}}], "away_props": []}]}
ours = bg.capture("nba", PAY, BD)
row11 = {"_pmfs": nm.player_pmfs({"pts": 26.0}, {})}
want = bf.chance_at(row11, "pts", 24.5, "Over", (), nm.calibration(PAY["model"]))[0]
got = {(r[0], r[2]): r[4] for r in ours["e1"] if r[1] == "pts"}
check("the site's chance is captured at the book's line and its ladder rungs, as the Bet Finder "
      "prices it", abs(got[("11", 24.5)] - want) < 1e-3 and ("11", 29.5) in got
      and ("12", 9.5) in got and len(ours["e1"]) >= 4)
check("the book's chance is its two prices with the cut removed",
      abs(bg.devig(-110, -110) - 0.5) < 1e-9 and abs(bg.devig(120, -150) - 0.4310) < 1e-3
      and bg.devig(150, None) is None)
entry = dict(snap["e1"], ours=ours["e1"])
G = bg.grade_event(entry, {"11": {"pts": 31}, "12": {"pts": 9}})
gp = {(r[0], r[2]): r for r in G}
check("each captured line graded on the box: over hit or not, the site's chance and the book's",
      gp[("11", 24.5)][5] == 1 and gp[("12", 9.5)][5] == 0
      and abs(gp[("11", 24.5)][4] - 0.5) < 1e-9 and ("11", 29.5) not in gp)
check("a player who did not play is not graded (missing is never zero)",
      not any(r[0] == "13" for r in G))
lad = bp.merge_snapshot({}, {"e2": bp.parse([item(21, "9", "Receiving Yards Milestones", 75,
                                                    "+150")])}, "T")
G2 = bg.grade_event(dict(lad["e2"], ours=[["21", "rec_yds", 74.5, 0.45, 0.45]]),
                    {"21": {"rec_yds": 80}})
check("a one-sided price is graded apart, at the measured cut (rec_yds* at 0.40 / 1.07)",
      len(G2) == 1 and G2[0][1] == "rec_yds*" and abs(G2[0][4] - 0.4 / 1.07) < 1e-3)
rows = [["d", "e", "p", "pts", 24.5, 0.60, 0.50, 1, -110, -110]] * 30 + \
       [["d", "e", "p", "pts", 24.5, 0.60, 0.50, 0, -110, -110]] * 10 + \
       [["d", "e", "q", "pts", 9.5, 0.50, 0.505, 0, 120, -150]] * 5
SC = bg.scorecard(rows)["pts"]
check("the scorecard: n, both Briers, a verdict, flagged plays at the book's price",
      SC["n"] == 45 and SC["brier_site"] < SC["brier_book"] and SC["flagged"]["n"] == 40
      and SC["flagged"]["hits"] == 30 and abs(SC["flagged"]["units"] - (30 * 100 / 110 - 10)) < 0.01
      and SC["verdict"]["verdict"] in ("beats", "thin"))

# --- the grader script, with a fake feed ---------------------------------------------------------
import book_props_grade as bpg  # noqa: E402
calls = []


def fsum(league, eid):
    calls.append(eid)
    return {"header": {"competitions": [{"status": {"type": {"completed": eid == "e1"}}}]}}


bg.ACTUALS["nba"] = lambda s, e: {"11": {"pts": 31}, "12": {"pts": 9}}
with tempfile.TemporaryDirectory() as td:
    d = Path(td) / "nba"
    d.mkdir(parents=True)
    (d / "2026-10-24.json").write_text(json.dumps(
        {"e1": entry, "e9": dict(entry)}))
    n1, done1, wait1 = bpg.grade_league("nba", fsum, "2026-10-24", props=td)
    n2, done2, _w = bpg.grade_league("nba", fsum, "2026-10-24", props=td)
    gr = json.loads((Path(td) / "graded" / "nba.json").read_text())
check("a final game is graded once; one not final waits",
      done1 == 1 and wait1 == 1 and done2 == 0 and len(gr) == len(n1) > 0 and not n2
      and gr[0][:2] == ["2026-10-24", "e1"])
src = (ROOT / "book_props_snapshot.py").read_text(encoding="utf-8")
wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the snapshot saves the site's chances beside the lines; the nightly grades every run",
      "ours = bg.capture(league, pl, bp.board(files))" in src
      and "python book_props_grade.py ||" in wf
      and wf.index("python book_props_grade.py") < wf.index("git add data/props"))
m = bp.merge_snapshot({"e1": entry}, {"e1": bp.parse(ITEMS)}, "T2")
check("a later snapshot keeps the captured chances", m["e1"].get("ours") == entry["ours"])

# --- what the pages say -----------------------------------------------------------------------
def _sc(n, verdict):
    return {"n": n, "verdict": {"verdict": verdict, "z": 2.5}}


CARD = {"leagues": {"nba": {"pts": _sc(400, "beats"), "reb": _sc(400, "thin"),
                            "ast": _sc(120, "beats")}, "nfl": {"rec_yds*": _sc(350, "fails")}}}
check("no verdict before 300 graded lines; then beats or no edge proven",
      bg.market_status(CARD, "nba", "ast")["status"] == "grading"
      and bg.market_status(CARD, "nba", "pts")["status"] == "beats"
      and bg.market_status(CARD, "nba", "reb")["status"] == "no_edge"
      and bg.market_status(CARD, "nfl", "rec_yds") == {"status": "no_edge", "n": 350, "z": 2.5,
                                                       "key": "rec_yds*"}
      and bg.market_status(None, "nhl", "sog")["status"] == "grading" and bg.MIN_GRADED == 300)
bfp = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("a market with no edge proven is capped at THIN on the Bet Finder, and labelled",
      'if _mk["status"] == "no_edge":' in bfp and "_sup = dict(_sup or {}, untested=True)" in bfp
      and "NO EDGE PROVEN vs DraftKings" in bfp and "BEATS DRAFTKINGS" in bfp)
app_ = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("the Site vs DraftKings page is in every sport's nav",
      app_.count('("Site vs DraftKings", "views/Site_vs_Book.py")') == 4)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall site vs DraftKings checks passed")
