"""ESPN's WNBA scoreboard has exactly ONE reader in this repo.

WHY THIS TEST EXISTS

The mirror chain was built in wnba_precompute.py after ESPN started
403-ing one API path from cloud IP ranges. app/views/WNBA.py kept its own
private copy — a single hardcoded URL aimed at the blocked host — and
because _live_overrides() swallows failures by design, the live-score
overlay and its 75-second auto-refresh were both dead for weeks without
one visible symptom.

Duplication is what made a silent failure possible, so the duplication is
what this test forbids. It runs no network calls: it reads the files and
exercises the normalizer on a payload of the shape the probe measured.

Plain script, like everything in tests/ — exits non-zero on failure.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from engines import espn_wnba  # noqa: E402

failures = []


def check(label, ok):
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------- 1
# The engine is the one that holds the chain.
check("engine exports the mirror list",
      len(getattr(espn_wnba, "SCOREBOARD_SOURCES", [])) >= 3)
for _name in ("fetch_scoreboard", "live_scores", "get_json",
              "_normalize_header_events", "STATUS_MAP", "BASE", "UA"):
    check(f"engine exports {_name}", hasattr(espn_wnba, _name))

# BASE must NOT be the host measured as blocked from cloud ranges. It is
# allowed to appear inside SCOREBOARD_SOURCES as the first mirror to try,
# because a mirror that fails costs one request and a fallback.
check("engine BASE is not the blocked host",
      "site.api.espn.com" not in espn_wnba.BASE)


# ---------------------------------------------------------------- 2
# NO VIEW MAY HOLD AN ESPN URL. This is the actual regression.
for path in sorted((ROOT / "app" / "views").glob("*.py")):
    text = path.read_text(encoding="utf-8")
    check(f"{path.name} holds no ESPN URL",
          "espn.com" not in text.replace("espn_wnba", ""))

_wnba_view = (ROOT / "app" / "views" / "WNBA.py").read_text(encoding="utf-8")
check("WNBA view imports the engine",
      "from engines.espn_wnba import live_scores" in _wnba_view)


# ---------------------------------------------------------------- 3
# The pipeline must not have grown a second copy back.
_pc = (ROOT / "wnba_precompute.py").read_text(encoding="utf-8")
check("pipeline imports the engine",
      "from engines.espn_wnba import" in _pc)
for _dup in ("SCOREBOARD_SOURCES = [", "def fetch_scoreboard(",
             "def get_json(", "def _normalize_header_events("):
    check(f"pipeline does not redefine {_dup.strip()!r}", _dup not in _pc)


# ---------------------------------------------------------------- 4
# The normalizer, on the shape wnba_scoreboard_probe measured against
# 2026-08-03: no `competitions`, competitors flat on the event, team
# fields flattened onto the competitor, status under `fullStatus`.
_header = {
    "events": [{
        "id": "401800001",
        "date": "2026-08-03T23:00Z",
        "location": "Barclays Center",
        "fullStatus": {"type": {"name": "STATUS_IN_PROGRESS",
                                "shortDetail": "Q3 4:12"}},
        "competitors": [
            {"homeAway": "home", "score": "58", "id": "9",
             "displayName": "New York Liberty", "records": "20-8"},
            {"homeAway": "away", "score": "51", "id": "5",
             "displayName": "Las Vegas Aces",
             "records": [{"name": "overall", "summary": "18-10"}]},
        ],
    }]
}
_norm = espn_wnba._normalize_header_events(_header)
_ev = _norm["events"][0]
check("normalizer builds a competitions block", bool(_ev.get("competitions")))
_comp = (_ev.get("competitions") or [{}])[0]
_sides = {c.get("homeAway"): c for c in _comp.get("competitors", [])}
check("normalizer keeps both sides", set(_sides) == {"home", "away"})
check("normalizer nests team fields",
      (_sides.get("home", {}).get("team") or {}).get("displayName")
      == "New York Liberty")
check("normalizer keeps the venue",
      (_comp.get("venue") or {}).get("fullName") == "Barclays Center")
# A bare "20-8" string used to be iterated as characters by _record().
check("normalizer boxes a string record",
      isinstance(_sides.get("home", {}).get("records"), list))

# A payload that ALREADY has competitions must come back untouched, so
# site.api keeps working unchanged if ESPN ever unblocks it.
_full = {"events": [{"id": "1", "competitions": [{"competitors": []}]}]}
check("normalizer passes through a full payload",
      espn_wnba._normalize_header_events(_full) is _full)


# ---------------------------------------------------------------- 5
# live_scores never raises and never invents a scoreline.
_saved = espn_wnba.fetch_scoreboard
try:
    espn_wnba.fetch_scoreboard = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("every ESPN scoreboard source failed"))
    check("live_scores returns {} when every mirror fails",
          espn_wnba.live_scores("20260803") == {})

    espn_wnba.fetch_scoreboard = lambda *a, **k: (
        espn_wnba._normalize_header_events(json.loads(json.dumps(_header))),
        "site.web.api")
    _live = espn_wnba.live_scores("20260803")
    _key = ("Las Vegas Aces", "New York Liberty")
    check("live_scores keys on (away, home) display names", _key in _live)
    check("live_scores maps the status",
          (_live.get(_key) or {}).get("status") == "in progress")
    check("live_scores publishes a scoreline for a live game",
          (_live.get(_key) or {}).get("scoreline")
          == "Las Vegas Aces 51 - 58 New York Liberty")

    # A scheduled game must not get "0 - 0", which reads as a tip-off
    # that has already happened.
    _sched = json.loads(json.dumps(_header))
    _sched["events"][0]["fullStatus"] = {"type": {"name": "STATUS_SCHEDULED"}}
    for _c in _sched["events"][0]["competitors"]:
        _c["score"] = "0"
    _live2 = espn_wnba.live_scores("20260803")
    espn_wnba.fetch_scoreboard = lambda *a, **k: (
        espn_wnba._normalize_header_events(_sched), "site.web.api")
    _live2 = espn_wnba.live_scores("20260803")
    check("no scoreline before tip-off",
          "scoreline" not in (_live2.get(_key) or {}))
finally:
    espn_wnba.fetch_scoreboard = _saved


if failures:
    print("FAIL:", "; ".join(failures))
    sys.exit(1)
print("PASS: espn_wnba is the single source for ESPN WNBA scoreboards")
