"""
Grade the site against DraftKings (10-24, engines/book_grade step 2-3).

Every nightly run: for each league, every saved day file in
data/props/<league>/ with the site's captured chances ("ours") for an
event that is not graded yet -> ESPN's summary; when the game is final,
its box score grades every captured line the book priced on both sides,
and the rows are appended to data/props/graded/<league>.json (the event
is marked "graded" in its day file so it is never graded twice). Then
the scorecard (per league and stat: the site's Brier vs the book's, a
paired verdict, the flagged plays' record at the book's own prices) is
written to data/props/scorecard.json and printed as [verify] lines.

Committed with the book's lines (the nightly's "Commit the book's prop
lines" step adds data/props). Never fails the nightly.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import book_grade as bg  # noqa: E402

PROPS = ROOT / "data" / "props"
LEAGUES = ("nhl", "nba", "nfl")


def _final(summary):
    comp = (((summary or {}).get("header") or {}).get("competitions") or [{}])[0] or {}
    t = ((comp.get("status") or {}).get("type") or {})
    return bool(t.get("completed")) or str(t.get("state")) == "post"


def grade_league(league, fetch_summary, today_iso, props=PROPS):
    """(new graded rows, events graded, events waiting)."""
    gpath = Path(props) / "graded" / f"{league}.json"
    graded = json.loads(gpath.read_text()) if gpath.exists() else []
    new, done, waiting = [], 0, 0
    for path in sorted((Path(props) / league).glob("*.json")):
        day = path.stem
        if day > today_iso:
            continue
        js = json.loads(path.read_text())
        changed = False
        for eid, entry in js.items():
            if not entry.get("ours") or entry.get("graded") is not None:
                continue
            try:
                summ = fetch_summary(league, eid)
            except Exception as exc:  # noqa: BLE001
                print(f"  {league}: summary {eid} failed: {exc}")
                waiting += 1
                continue
            if not _final(summ):
                waiting += 1
                continue
            rows = bg.grade_event(entry, bg.ACTUALS[league](summ, eid))
            new += [[day, eid] + r for r in rows]
            entry["graded"] = len(rows)
            changed = True
            done += 1
        if changed:
            path.write_text(json.dumps(js, separators=(",", ":")))
    if new:
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text(json.dumps(graded + new, separators=(",", ":")))
    return new, done, waiting


def main():
    from zoneinfo import ZoneInfo
    from engines import espn_feed as ef
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    card = {}
    for lg in LEAGUES:
        try:
            new, done, waiting = grade_league(lg, ef.fetch_summary, today)
            print(f"  [verify] SITE vs DRAFTKINGS {lg}: graded {done} games ({len(new)} lines) "
                  f"this run; {waiting} not final yet")
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::grading {lg} failed: {type(exc).__name__}: {exc}")
        gpath = PROPS / "graded" / f"{lg}.json"
        rows = json.loads(gpath.read_text()) if gpath.exists() else []
        card[lg] = bg.scorecard(rows)
        for st, x in card[lg].items():
            v, f = x["verdict"] or {}, x["flagged"]
            print(f"  [verify] SITE vs DRAFTKINGS {lg} {st:12s} n={x['n']} site {x['brier_site']} "
                  f"vs book {x['brier_book']} -> {v.get('verdict')} (z={v.get('z')}); flagged "
                  f"{f['n']} plays, {f['hits']} hit, {f['units']:+} units (roi {f['roi']})")
    PROPS.mkdir(parents=True, exist_ok=True)
    (PROPS / "scorecard.json").write_text(json.dumps({"as_of": today, "leagues": card},
                                                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
