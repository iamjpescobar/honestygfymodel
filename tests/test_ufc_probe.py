"""
UFC probe (10-24) — ufc_probe.py reads the next UFC card from ESPN's MMA
scoreboard, each fight's odds providers and DraftKings' prop types from
the core feed, and prints them. Print only.

Plain script — exits non-zero on failure. A fake feed in ESPN's shape
(events[].competitions[] = fights, competitors[].athlete.displayName;
core odds items / propBets items) (rule 5). No network.

Negative control, confirmed red by exit code when written (rule 4):
  - card_info reading the LAST event instead of the next one
    -> "the probe reads the next card and its fights" fails
"""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
import ufc_probe as up  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def fighter(n):
    return {"athlete": {"id": n, "displayName": n}}


SB = {"events": [{"id": "600", "name": "UFC Fight Night", "date": "2026-10-24",
                  "competitions": [{"id": "11", "competitors": [fighter("A"), fighter("B")]},
                                   {"id": "12", "competitors": [fighter("C"), fighter("D")]}]},
                 {"id": "601", "name": "UFC 330", "competitions": []}]}
eid, name, _d, fights = up.card_info(SB)
check("the probe reads the next card and its fights",
      eid == "600" and fights == [("11", "A", "B"), ("12", "C", "D")])
urls = []


def get(url):
    urls.append(url)
    if url.split("?")[0].endswith("/odds"):
        return {"items": [{"provider": {"id": "100", "name": "DraftKings"},
                           "moneyline": {"home": {"close": {"odds": "-150"}}}}]}
    if "/propBets" in url:
        return {"items": [{"type": {"name": "Method of Victory"}},
                          {"type": {"name": "Total Rounds"}}]}
    return {}


buf = io.StringIO()
with redirect_stdout(buf):
    n, types = up.probe_odds(get, "600", fights, k=2)
check("each fight's odds providers and DraftKings' prop types are counted",
      n == 4 and types == {"Method of Victory": 2, "Total Rounds": 2}
      and any("/events/600/competitions/12/odds/100/propBets" in u for u in urls)
      and "UFC fight A vs B" in buf.getvalue())
wf = (ROOT / ".github" / "workflows" / "ufc-probe.yml").read_text(encoding="utf-8")
check("its workflow is manual and touches nothing",
      "workflow_dispatch" in wf and "python ufc_probe.py" in wf and "git push" not in wf)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall UFC probe checks passed")
