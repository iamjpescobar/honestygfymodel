"""A failed lookup and a bench night are not the same result.

WHAT WENT WRONG. `_mlb_line` returned None both when the API never
answered and when it answered and the player wasn't in the log. grade()
treated both as "unknown", held the pick open three days, then closed it
"dnp". So a timeout, a rate limit and a genuine bench night all became
the same permanent record.

16 of 221 Daily 13 picks (7.2%) closed that way — and at least one,
James McCann, was in the lineup and hit a home run on a day his pick
shows as ungraded. HR Edge and Player of the Day have ZERO DNPs across
96 picks, which is what a board that only ever picks starters looks
like.

TWO CAUSES, both fixed here:

  1. `_mlb_line` read `stats[0]` and ignored every other entry. A player
     who changes teams mid-season can come back as more than one, so all
     his games after the move were invisible.

  2. There was no way to say "the API answered, he wasn't there."
     DID_NOT_PLAY is that answer, and it closes the pick immediately
     instead of waiting three days for a timeout to look identical.
"""
import sys, types, json

for mod, attrs in (("requests", {}), ("pandas", {})):
    if mod not in sys.modules:
        try:
            __import__(mod)
        except ImportError:
            sys.modules[mod] = types.ModuleType(mod)
sys.path.insert(0, ".")
import calibration_pipeline as cp  # noqa: E402

DATE = "2026-08-12"


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def line_for(payload, boom=False):
    def _get(url, **kw):
        if boom:
            raise TimeoutError("the API did not answer")
        return _Resp(payload)
    real, cp.requests.get = cp.requests.get, _get
    try:
        return cp._mlb_line(12345, DATE)
    finally:
        cp.requests.get = real


def split(date, hits=0, hr=0):
    return {"date": date, "stat": {"hits": hits, "homeRuns": hr,
                                   "doubles": 0, "triples": 0}}


# --- 1. A TRADED PLAYER'S GAMES ARE NOT IN stats[0] ------------------
#
# The case that cost McCann his grade. Pre-trade games in the first
# entry, post-trade in the second. Reading only the first finds nothing
# and the pick eventually closes as a DNP for a man who homered.
traded = {"stats": [
    {"splits": [split("2026-07-01", hits=1)]},          # old team
    {"splits": [split(DATE, hits=2, hr=1)]},            # new team
]}
got = line_for(traded)
assert got not in (None, cp.DID_NOT_PLAY), (
    "a traded player's post-move game log was not found — only stats[0] "
    "is being read")
assert got["homeRuns"] == 1 and got["hits"] == 2, got
print("PASS: games in a second stats entry are found (the traded-player case)")

# --- 2. THE API ANSWERED AND HE WASN'T THERE -------------------------
absent = {"stats": [{"splits": [split("2026-08-09", hits=1)]}]}
assert line_for(absent) is cp.DID_NOT_PLAY, (
    "a real bench night did not report DID_NOT_PLAY, so it will be held "
    "open for three days as if the lookup had failed")
print("PASS: an answered lookup with no line for that date is DID_NOT_PLAY")

# --- 3. THE API DID NOT ANSWER ---------------------------------------
#
# Must stay None. Closing this as a DNP is how a network blip becomes a
# permanent, wrong record entry.
assert line_for({}, boom=True) is None, (
    "a failed request reported an outcome — a timeout is not evidence "
    "about whether he played")
print("PASS: a failed request returns None, never a result")

# --- 4. THE THREE ARE DISTINGUISHABLE --------------------------------
assert cp.DID_NOT_PLAY is not None
found = line_for({"stats": [{"splits": [split(DATE, hits=1)]}]})
assert isinstance(found, dict)
assert len({id(found), id(cp.DID_NOT_PLAY), id(None)}) == 3
print("PASS: found / did-not-play / no-answer are three distinct returns")

# --- 5. grade() CLOSES A REAL DNP IMMEDIATELY ------------------------
src = open("calibration_pipeline.py", encoding="utf-8").read()
assert "if line is DID_NOT_PLAY:" in src, (
    "grade() no longer handles the sentinel — a bench night will be held "
    "open for three days again")
assert "dnp_reason" in src, (
    "a dnp closed with no API answer is no longer flagged, so a "
    "collection failure is invisible in the record again")
print("PASS: grade() closes a real DNP at once and flags a silent one")

# --- 6. DAILY 13 FALLS BACK TO A LINEUP, NOT A ROSTER ----------------
d13 = open("app/engines/daily_13.py", encoding="utf-8").read()
assert "get_last_starting_lineup(team)" in d13, (
    "Daily 13 is back on the 26-man roster fallback — it will spend "
    "slots on bench bats who never enter the game")
_i = d13.index("get_last_starting_lineup(team)")
assert "get_live_team_roster" in d13[_i:_i + 600], (
    "the roster last-resort was removed; a team with no posted lineup "
    "at all would now produce no pool")
print("PASS: Daily 13 falls back to the last lineup, roster only as last resort")
