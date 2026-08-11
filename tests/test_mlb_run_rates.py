"""Tier 2 of the best-games ranking: real rates, or nothing.

WHY THIS EXISTS

`proj_total` was deliberately absent for weeks. `run_total` needs each
club's runs scored and allowed per game and nothing on disk carried them
for MLB, so tier 2 was wired, tested, and dark.

Four probe rounds later, `/api/v1/standings` does. Run 85313739682:

    standings regularSeason  200 | 30 entries | 30 w/stats | 30 w/runs
                                 e.g. Rays: 519 runs in 117 G

**Three of those four rounds went wrong in the PARSE, not the fetch.**
`teams/stats` returns one row and it looks like a club until you notice
it has no name — it is the league aggregate, and it survived two rounds
recorded as "PARTIAL: 1 of 30". Then the entries nest two levels down,
so counting the outer list gives 6, and 6-of-30 reads like a partial
failure rather than a parsing mistake.

So the parser is pure and tested offline against a payload matching the
real shape. A parser you cannot exercise without the network is one you
debug in production.

THE TWO WAYS A WRONG NUMBER GETS ONTO THE FRONT PAGE

1. **A ZERO WHERE A MEASUREMENT IS MISSING.** A club with `runsScored`
   absent is unmeasured, not a club that has scored no runs. A 0.00
   rs_pg drags the league average down AND makes that team the worst
   offense in baseball, and both errors are invisible on a card.

2. **A PARTIAL LEAGUE.** With 22 of 30 clubs, eight games get no
   projected total, tier 2 fires on some and not others, and the ranking
   silently mixes two different sorts — some games ranked on three tiers,
   some on two, with nothing on screen saying so.
"""
import ast
import os
import sys
import types

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "app"))

_st = types.ModuleType("streamlit")


def _memo(*a, **k):
    def deco(fn):
        return fn
    return a[0] if (a and callable(a[0]) and not k) else deco


_st.cache_data = _st.cache_resource = _memo
_st.session_state = {}
sys.modules.setdefault("streamlit", _st)

from engines.mlb_run_rates import parse_standings, fetch_team_run_rates  # noqa: E402
from engines.run_total import project_total, league_run_average  # noqa: E402

failures = []


def check(label, ok):
    if ok:
        print(f"PASS: {label}")
    else:
        failures.append(label)


def payload(clubs):
    """clubs = [(name, rs, ra, g), ...] -> a /standings-shaped payload,
    split across six division records like the real one."""
    recs, per = [], max(1, len(clubs) // 6 or 1)
    for i in range(0, len(clubs), per):
        recs.append({"division": {"id": 200 + i},
                     "teamRecords": [
                         {"team": {"name": n}, "runsScored": rs,
                          "runsAllowed": ra, "gamesPlayed": g}
                         for n, rs, ra, g in clubs[i:i + per]]})
    return {"copyright": "x", "records": recs}


THIRTY = [(f"Club {i}", 470 + i * 4, 500 - i * 2, 117 + i % 2)
          for i in range(30)]

# ----------------------------------------------------------------------
# 1. THE NESTING. Six division records holding thirty clubs.
# ----------------------------------------------------------------------
rates = parse_standings(payload(THIRTY))
check(f"thirty clubs come out of six division records (got {len(rates)})",
      len(rates) == 30)
check("divisions are never counted as clubs (6 != 30)", len(rates) != 6)

# The real club the probe named, with its real numbers.
r = parse_standings(payload([("Rays", 519, 498, 117)]))["Rays"]
check(f"runs are converted to a per-game rate (Rays {r['rs_pg']})",
      r["rs_pg"] == round(519 / 117, 3) and r["ra_pg"] == round(498 / 117, 3))

# ----------------------------------------------------------------------
# 2. MISSING IS NOT ZERO — the error that would be invisible on a card.
# ----------------------------------------------------------------------
half = parse_standings(payload([("A", None, 500, 118), ("B", 500, None, 118),
                                ("C", 500, 490, 118)]))
check("a club with no runsScored is DROPPED, not recorded as 0.00",
      "A" not in half and "B" not in half and "C" in half)
check("a club with no games played is dropped (no division by zero)",
      "D" not in parse_standings(payload([("D", 500, 490, 0)])))

# ----------------------------------------------------------------------
# 3. A PARTIAL LEAGUE IS REFUSED. Ranking half the slate on three tiers
#    and half on two, with nothing saying so, is worse than no tier 2.
# ----------------------------------------------------------------------
import engines.mlb_run_rates as mrr  # noqa: E402


class _Resp:
    """A stub matching what fetch_team_run_rates actually calls.

    It uses requests.GET and r.json(). `content` is provided as well so
    the stub keeps working if the fetch ever switches to decoding bytes
    the way engines/kbo_official does — a stub that does not match the
    interface silently falls through to a REAL request, and the assertion
    then passes on whatever error the network happens to give.
    """

    status_code = 200

    def __init__(self, p):
        self._p = p

    def json(self):
        return self._p

    @property
    def content(self):
        import json as _j
        return _j.dumps(self._p).encode("utf-8")


_real_get = mrr.requests.get
try:
    mrr.requests.get = lambda *a, **k: _Resp(payload(THIRTY[:22]))
    got, err = fetch_team_run_rates(2026)
    check(f"22 of 30 clubs is refused, with a reason (got {len(got)})",
          got == {} and err and "22" in err)

    mrr.requests.get = lambda *a, **k: _Resp(payload(THIRTY))
    got, err = fetch_team_run_rates(2026)
    check("a full league is accepted", len(got) == 30 and err is None)

    mrr.requests.get = lambda *a, **k: _Resp({"records": []})
    got, err = fetch_team_run_rates(2026)
    check("an empty payload returns a reason, not an exception",
          got == {} and err)

    def _boom(*a, **k):
        raise ConnectionError("down")

    mrr.requests.get = _boom
    got, err = fetch_team_run_rates(2026)
    check("a standings outage costs tier 2, not the day's picks",
          got == {} and "ConnectionError" in err)
finally:
    mrr.requests.get = _real_get

# ----------------------------------------------------------------------
# 4. THE RATES FEED run_total UNCHANGED. No second copy of the maths —
#    it is the same engine KBO and NPB use, and league_rs_pg is a
#    PARAMETER measured from these teams, not a frozen constant.
# ----------------------------------------------------------------------
rates = parse_standings(payload(THIRTY))
lg = league_run_average(rates)
check(f"the league average is measured from the clubs themselves ({lg})",
      lg is not None and 3.0 < lg < 6.0)

total, detail = project_total(rates["Club 0"], rates["Club 29"], league_rs_pg=lg)
check(f"a projected total comes out in a plausible MLB range ({total})",
      total is not None and 5.0 <= total <= 14.0)
check("the projection states its basis", "basis" in (detail or {}))

# A club with no rates yields None, not a guess — the caller writes no
# field, and best_games sorts unmeasured below measured.
none_total, why = project_total(None, rates["Club 0"], league_rs_pg=lg)
check("an unmeasured club yields None and a reason, never a number",
      none_total is None and "reason" in why)

# ----------------------------------------------------------------------
# 5. THE SLATE BUILDER WRITES IT, and writes ABSENCE as absence.
# ----------------------------------------------------------------------
src = open(os.path.join(ROOT, "calibration_picks.py"), encoding="utf-8").read()
tree = ast.parse(src)
fn = next((n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name == "_write_mlb_slate"), None)
check("_write_mlb_slate exists", fn is not None)
if fn:
    body = ast.dump(fn)
    check("it fetches the run rates", "fetch_team_run_rates" in body)
    check("it calls the shared projector, not its own maths",
          "project_total" in body)
    check("it measures the league average from those same clubs",
          "league_run_average" in body)
    check("proj_total is only assigned when a total came back",
          "proj_total" in body and "if _t is not None" in src)
    # ONE call for all thirty, not one per game. Inside the loop it would
    # be thirty requests a slate and a standings blip would cost half of
    # them.
    loop = next((n for n in ast.walk(fn) if isinstance(n, ast.For)), None)
    in_loop = ast.dump(loop) if loop else ""
    check("the fetch is OUTSIDE the per-game loop",
          "fetch_team_run_rates" not in in_loop)

check("no second definition of runs-per-game anywhere in the engine",
      "def project_total" not in
      open(os.path.join(ROOT, "app", "engines", "mlb_run_rates.py"),
           encoding="utf-8").read())

# ----------------------------------------------------------------------
# 6. THE TWO ENDPOINTS DISAGREE ABOUT WHAT A TEAM IS CALLED.
#
#   schedule   "Detroit Tigers"     standings   "Tigers"
#
# Measured on 2026-08-11: `home matched: False | away matched: False`
# for all fifteen games. Tier 2 wrote zero totals AND LOGGED NO ERROR,
# because the fetch succeeded and every lookup missed. That is the worst
# shape a bug can have — a feature silently absent from a working
# pipeline.
# ----------------------------------------------------------------------
from engines.mlb_run_rates import canonical  # noqa: E402

check("the schedule's full name resolves", canonical("Detroit Tigers") == "DET")
check("the standings' short name resolves to the SAME club",
      canonical("Tigers") == canonical("Detroit Tigers") == "DET")
check("case and whitespace do not matter",
      canonical("  cleveland guardians ") == "CLE")

# AMBIGUITY RESOLVES TO NOTHING. "Sox" is the last word of both Red Sox
# and White Sox. Picking one would put the wrong offense on a card and
# nothing on screen could contradict it.
check("an ambiguous suffix resolves to None, not a coin flip",
      canonical("Sox") is None)
check("but the unambiguous two-word forms both work",
      canonical("Red Sox") == "BOS" and canonical("White Sox") == "CWS")
check("an unknown name is None, never a raw-string fallback",
      canonical("Sheffield Wednesday") is None and canonical("") is None)

# Every short name the real endpoint returns must resolve. This is the
# list from the live payload, not an invented one.
_SHORTS = ["Angels", "Astros", "Athletics", "Blue Jays", "Braves", "Brewers",
           "Cardinals", "Cubs", "Diamondbacks", "Dodgers", "Giants",
           "Guardians", "Mariners", "Marlins", "Mets", "Nationals", "Orioles",
           "Padres", "Phillies", "Pirates", "Rangers", "Rays", "Red Sox",
           "Reds", "Rockies", "Royals", "Tigers", "Twins", "White Sox",
           "Yankees"]
_unresolved = [n for n in _SHORTS if not canonical(n)]
check(f"all 30 standings short names resolve (unresolved: {_unresolved})",
      not _unresolved)
check("and they resolve to 30 DISTINCT clubs, not fewer",
      len({canonical(n) for n in _SHORTS}) == 30)

# Records are reachable by BOTH vocabularies, and both keys point at ONE
# dict — otherwise the 30-club guard sees 60 and never fires.
_short_payload = {"records": [{"teamRecords": [
    {"team": {"name": "Tigers"}, "runsScored": 500, "runsAllowed": 480,
     "gamesPlayed": 118}]}]}
_r = parse_standings(_short_payload)
check("a record is reachable by the standings name", "Tigers" in _r)
check("and by the abbreviation the schedule reduces to", "DET" in _r)
check("both keys are the SAME record, not two copies",
      _r["Tigers"] is _r["DET"])

# The 30-club guard must count CLUBS, not keys.
_full = parse_standings(payload(THIRTY))
check("dual keying does not fool the partial-league guard",
      len({id(v) for v in _full.values()}) == 30)

import engines.mlb_run_rates as _ko2  # noqa: E402
# REAL team names, so dual keying actually happens. A fixture of
# "Club 0".."Club 21" is keyed ONCE each (canonical returns None), so
# len(rates) and the club count agree and the assertion cannot tell them
# apart — it passed against a guard counting keys. The fixture has to
# exercise the thing being asserted.
_REAL22 = [(n, 470, 500, 118) for n in _SHORTS[:22]]
_real3 = _ko2.requests.get
try:
    _ko2.requests.get = lambda *a, **k: _Resp(payload(_REAL22))
    _got, _err = _ko2.fetch_team_run_rates(2026)
    check(f"a 22-club league is refused even though it has 44 keys "
          f"({_err})",
          _got == {} and _err and "22" in _err)

    _REAL30 = [(n, 470, 500, 118) for n in _SHORTS]
    _ko2.requests.get = lambda *a, **k: _Resp(payload(_REAL30))
    _got, _err = _ko2.fetch_team_run_rates(2026)
    check("a full 30-club league with 60 keys is accepted",
          len({id(v) for v in _got.values()}) == 30 and _err is None)
finally:
    _ko2.requests.get = _real3

# THE REGRESSION, end to end: the exact matchup that failed in production.
_rates = parse_standings({"records": [{"teamRecords": [
    {"team": {"name": "Tigers"}, "runsScored": 520, "runsAllowed": 495,
     "gamesPlayed": 118},
    {"team": {"name": "Guardians"}, "runsScored": 470, "runsAllowed": 489,
     "gamesPlayed": 117}]}]})
_lg = league_run_average(_rates)
_t, _d = project_total(_rates.get(canonical("Detroit Tigers")),
                       _rates.get(canonical("Cleveland Guardians")),
                       league_rs_pg=_lg)
check(f"Cleveland Guardians @ Detroit Tigers now projects ({_t})",
      _t is not None and 5.0 <= _t <= 14.0)

# And the caller must actually use it — asserting on source, because the
# engine can be perfect while the lookup still passes a raw name.
_src = open(os.path.join(ROOT, "calibration_picks.py"), encoding="utf-8").read()
check("the slate builder reduces both names before the lookup",
      "canonical(home)" in _src and "canonical(g.get(\"away\"))" in _src)

if failures:
    print()
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(1)

print("\nThirty clubs or none. Half a league ranked on three tiers and half "
      "on two is worse than no tier at all.")
