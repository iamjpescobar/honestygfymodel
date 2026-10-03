"""
A day with no WNBA games is an off day, not an outage.

THE 10-03 FAILURE, replayed. The late refresh (intl-late-refresh.yml)
asked ESPN for a day with no WNBA games and got, from its run log:

    site.api:     200 but no events
    cdn.espn:     JSONDecodeError Expecting value: line 1 column 1
    site.web.api: 200 but not a scoreboard payload

fetch_scoreboard(require_events=True) counted the honest empty answer as
a failure, raised "every ESPN scoreboard source failed", and the WNBA
step's red took the whole refresh job red although NPB and KBO had
succeeded.

Plain script — exits non-zero on failure. Negative controls, confirmed
red by exit code when written (rule 4):
  - wnba_precompute calling fetch_scoreboard again -> section 3 fails
  - fetch_today accepting an empty answer when NO host returned a real
    scoreboard -> "a real outage still raises" fails
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import espn_wnba as ew  # noqa: E402

failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


def fake(responses):
    """get_json stand-in keyed on a URL fragment. NOT the hostname: the
    source named "site.api" is served from site.web.api.espn.com (see
    SCOREBOARD_SOURCES), so the first draft of this fixture routed by
    host and handed every source the wrong answer."""
    def get(url, _attempts=2):
        for host, resp in responses.items():
            if host in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise RuntimeError(url)
    return get


saved = ew.get_json
try:
    # ------------------------------------------- 1. the logged off day
    ew._PREFERRED_SOURCE = None
    ew.get_json = fake({
        "/apis/site/v2/": {"events": []},
        "cdn.espn.com/core": ValueError("Expecting value: line 1 column 1 (char 0)"),
        "/scoreboard/header": {"sports": [{"leagues": [{"name": "WNBA"}]}]},
    })
    try:
        data, src, off = ew.fetch_today("20261003")
        check("the 10-03 responses are an off day, not a crash", off is True)
        check("...answered by the host that returned a real scoreboard",
              src == "site.api" and data.get("events") == [])
    except RuntimeError as exc:
        check(f"the 10-03 responses are an off day, not a crash ({exc})", False)

    # ------------------------------------------- 2. a game day / outage
    ew._PREFERRED_SOURCE = None
    ew.get_json = fake({
        "/apis/site/v2/": {"events": []},
        # A real full-shape event (with competitions): a bare {"id"} is
        # dropped by _normalize_header_events as unparseable, correctly.
        "cdn.espn.com/core": {"content": {"sbData": {"events": [
            {"id": "1", "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"displayName": "Liberty"}},
                {"homeAway": "away", "team": {"displayName": "Aces"}}]}]}]}}},
        "/scoreboard/header": {"sports": []},
    })
    data, src, off = ew.fetch_today("20261003")
    check("a host with games still wins over one answering [] (game day)",
          off is False and src == "cdn.espn" and data["events"])

    ew._PREFERRED_SOURCE = None
    ew.get_json = fake({
        "/apis/site/v2/": RuntimeError("HTTP 403"),
        "cdn.espn.com/core": ValueError("Expecting value"),
        "/scoreboard/header": {"nope": 1},
    })
    try:
        ew.fetch_today("20261003")
        check("a real outage still raises", False)
    except RuntimeError as exc:
        check("a real outage still raises, naming every host",
              all(h in str(exc) for h in ("site.api", "cdn.espn", "site.web.api")))
finally:
    ew.get_json = saved
    ew._PREFERRED_SOURCE = None

# ------------------------------- 3. the pipeline uses the off-day path
tree = ast.parse((ROOT / "wnba_precompute.py").read_text())
main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
first_fetch = next((c for c in ast.walk(main) if isinstance(c, ast.Call)
                    and getattr(c.func, "id", "") in ("fetch_today", "fetch_scoreboard")), None)
check("wnba_precompute.main fetches tonight through fetch_today",
      first_fetch is not None and first_fetch.func.id == "fetch_today")

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
