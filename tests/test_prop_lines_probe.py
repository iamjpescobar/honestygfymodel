"""
Prop lines probe (10-23) — prop_lines_probe.py asks ESPN's core feed for
one upcoming event per league, its odds providers and each provider's
propBets, and prints counts, types and raw samples. Print only.

Plain script — exits non-zero on failure. A fake feed in the core API's
shape ({"items": [{"provider": {"id", "name"}}]}, propBets {"count",
"items": [{"type": {"name"}, ...}]}) (rule 5). No network.

Negative control, confirmed red by exit code when written (rule 4):
  - upcoming_event taking a FINAL game
    -> "the probe asks about a game that has not been played" fails
"""
import io
import sys
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
import prop_lines_probe as plp  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def sb(league, d):
    return {"events": [{"id": "1", "shortName": "A @ B", "status": {"type": {"state": "post"}}},
                       {"id": "2", "shortName": "C @ D", "status": {"type": {"state": "pre"}}}]}, "x"


eid, lab = plp.upcoming_event("nhl", date(2026, 10, 23), sb)
check("the probe asks about a game that has not been played", eid == "2" and "C @ D" in lab)
urls = []


def get(url):
    urls.append(url)
    if url.split("?")[0].endswith("/odds"):
        return {"items": [{"provider": {"id": "58", "name": "ESPN BET"}}]}
    if "/propBets" in url:
        return {"count": 3, "items": [{"type": {"name": "Total Shots"}, "athlete": {"$ref": "a"},
                                       "odds": {"over": {"american": "-120"}}},
                                      {"type": {"name": "Total Shots"}},
                                      {"type": {"name": "Anytime Goal"}}]}
    return {}


buf = io.StringIO()
with redirect_stdout(buf):
    r = plp.probe("nhl", "2", get, ("hockey", "nhl"))
txt = buf.getvalue()
check("providers and each provider's prop items are counted by type, with raw samples",
      r["providers"] == [("58", "ESPN BET")] and r["props"]["58"]["n"] == 3
      and r["props"]["58"]["types"] == {"Total Shots": 2, "Anytime Goal": 1}
      and "PROPS nhl sample" in txt and "-120" in txt)
check("the core feed's paths: event / competition / odds / provider / propBets",
      any("/events/2/competitions/2/odds/58/propBets" in u for u in urls)
      and all("sports.core.api.espn.com/v2/sports/hockey/leagues/nhl" in u for u in urls))
wf = (ROOT / ".github" / "workflows" / "prop-lines-probe.yml").read_text(encoding="utf-8")
check("its workflow is manual and touches nothing",
      "workflow_dispatch" in wf and "python prop_lines_probe.py" in wf
      and "git push" not in wf and "contents: write" not in wf)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall prop lines probe checks passed")
