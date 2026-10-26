"""
Finished games fetched once (10-26) — engines/espn_feed.fetch_summary's
cache, the nightly's cache step, NPB's fail-fast, and the day-file keep.

Measured on the 10-26 10 AM nightly (35 min): NHL 9.1 min (every final of
the season re-downloaded every run, ~250 now, ~1,400 by April); NPB 5.1
min (npb.jp never answers from GitHub's runners: ~14 requests x a 25 s
timeout).

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - the cache serving a final fetched only 2 hours after it started
    -> "a final fetched before stat corrections settle is fetched again" fails
  - the cache keeping games that are not final -> "a game in progress is never kept" fails
  - prune dropping a 20-day-old file still waiting to be graded
    -> "a file still waiting to be graded is kept until 30 days" fails
"""
import json
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import espn_feed as ef  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def summ(state, start="2026-10-20T23:00Z", tag="x"):
    return {"header": {"competitions": [{"date": start, "status": {"type": {
        "state": state, "completed": state == "post"}}}]}, "tag": tag}


calls = []


def fake(tag, state="post"):
    def g(url):
        calls.append(url)
        return summ(state, tag=tag)
    return g


tmp = tempfile.mkdtemp()
late = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)      # 37 h after the start
ef.fetch_summary("nhl", "1", _get=fake("first"), _cache=tmp, _now=late)
calls.clear()
got = ef.fetch_summary("nhl", "1", _get=fake("second"), _cache=tmp)
check("a settled final is served from the cache, no fetch", got["tag"] == "first" and not calls)

early = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)      # 2 h after the start
ef.fetch_summary("nhl", "2", _get=fake("early"), _cache=tmp, _now=early)
calls.clear()
got = ef.fetch_summary("nhl", "2", _get=fake("corrected"), _cache=tmp, _now=late)
check("a final fetched before stat corrections settle is fetched again (and re-kept)",
      got["tag"] == "corrected" and len(calls) == 1)
calls.clear()
check("...then served from the cache", ef.fetch_summary("nhl", "2", _get=fake("z"), _cache=tmp)
      ["tag"] == "corrected" and not calls)

ef.fetch_summary("nhl", "3", _get=fake("live", "in"), _cache=tmp, _now=late)
check("a game in progress is never kept", not (Path(tmp) / "nhl" / "3.json.gz").exists())
(Path(tmp) / "nhl" / "4.json.gz").write_bytes(b"not gzip")
calls.clear()
check("a broken cache file is just a miss", ef.fetch_summary("nhl", "4", _get=fake("ok"),
                                                              _cache=tmp)["tag"] == "ok" and calls)

import os  # noqa: E402
os.environ["ESPN_SUMMARY_CACHE"] = tmp
_real = ef.get_json
ef.get_json = fake("FAKE")
ef.fetch_summary("nba", "9")
ef.get_json = _real
check("a swapped-in fake fetcher never writes the shared cache",
      not (Path(tmp) / "nba" / "9.json.gz").exists())
del os.environ["ESPN_SUMMARY_CACHE"]

wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the nightly carries the folder between runs and prints unbuffered",
      "ESPN_SUMMARY_CACHE: .cache/espn-summaries" in wf and "uses: actions/cache@" in wf
      and "continue-on-error: true" in wf and 'PYTHONUNBUFFERED: "1"' in wf
      and ".cache/" in (ROOT / ".gitignore").read_text())

# --- NPB fails fast ------------------------------------------------------------------------
import npb_precompute as npb  # noqa: E402
import requests  # noqa: E402
n = {"c": 0}
_rg = requests.get


def _down(*a, **k):
    n["c"] += 1
    raise requests.ConnectTimeout("no route")


requests.get = _down
npb._NPB_DOWN["down"] = False
for m in range(3, 11):
    npb.fetch_month(2026, m)
requests.get = _rg
check("npb.jp unreachable: one connection attempt, the rest skip at once",
      n["c"] == 1 and npb._NPB_DOWN["down"])
npb._NPB_DOWN["down"] = False

# --- day files kept 14 days, 30 at most -----------------------------------------------------
import book_props_snapshot as bps  # noqa: E402
out = Path(tempfile.mkdtemp())
(out / "nba").mkdir()
(out / "graded").mkdir()
today = date(2026, 11, 20)
files = {"2026-11-15": {"e": {"ours": [1], "graded": None}},          # 5 days: keep
         "2026-11-01": {"e": {"ours": [1], "graded": 12}},            # 19 days, graded: drop
         "2026-10-31": {"e": {"ours": [1], "graded": None}},          # 20 days, waiting: keep
         "2026-10-15": {"e": {"ours": [1], "graded": None}},          # 36 days: drop
         "2026-10-30": {"e": {"rows": []}}}                           # 21 days, nothing to grade
for d, js in files.items():
    (out / "nba" / f"{d}.json").write_text(json.dumps(js))
(out / "graded" / "nba.json").write_text("[]")
gone = bps.prune(out, today)
left = sorted(p.stem for p in (out / "nba").glob("*.json"))
check("a file still waiting to be graded is kept until 30 days; graded / empty ones go at 14",
      left == ["2026-10-31", "2026-11-15"] and (out / "graded" / "nba.json").exists())

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall cache / speed checks passed")
