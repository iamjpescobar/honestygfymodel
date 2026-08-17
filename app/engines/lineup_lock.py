"""How reliably each bat actually starts — read, never built.

WHAT THIS IS FOR

The morning problem: MLB posts a lineup 1-3 hours before first pitch,
and slate breakdowns get recorded before that. Every morning lineup on
this site is the projected one (last game's real nine, IL-filtered),
and until now every row in it looked equally certain. About two of
those nine will be wrong by first pitch.

This attaches the one number that separates them: how often this bat
has actually started, out of his team's games in the window, and the
same split by the hand of the opposing starter — which is knowable in
the morning, because probables are announced a day ahead.

READ, NEVER BUILD. lineup_lock_precompute.py writes the file nightly.
On 2026-08-16 a convenience column took the Game Card down by calling
board builders during a render, and the rule that came out of it is
that anything decorating a page reads and does not compute. There is
no build path in this module, on purpose.

TIER CUT POINTS ARE PROVISIONAL. 100 / 66 / 34 come from the
distribution measured over 2026-08-12..16 (40% of bats started every
game, 28% two thirds or more, 24% between a third and two thirds), and
five days is a first read rather than a measurement.
lineup_lock_probe.py measures whether the rate PREDICTS tonight's
start. Until it has run, `measured()` returns False and every caller
labels the number as provisional.
"""
import json
from pathlib import Path

# Both roots, same split calibration.json and slate_guard document: the
# archive extracts under app/, while a CI-committed file arrives in the
# repo checkout. Reading one of them is how a correct file goes unread.
_PUBLISHED = Path(__file__).resolve().parent.parent / "data" / "mlb" / "lineup_lock.json"
_REPO = Path(__file__).resolve().parents[2] / "data" / "mlb" / "lineup_lock.json"

LOCK = 1.0          # started every game in the window
USUAL = 0.66        # started at least two thirds
FLUX = 0.34         # a third to two thirds — the coin flips

TIER_LOCK = "Lock"
TIER_USUAL = "Usual"
TIER_FLUX = "In question"
TIER_RARE = "Rare"
TIER_UNKNOWN = "—"


def _path():
    """Whichever copy exists, newest first. Returns None if neither."""
    live = [p for p in (_PUBLISHED, _REPO) if p.exists()]
    if not live:
        return None
    return max(live, key=lambda p: p.stat().st_mtime)


# PARSE ONCE, KEYED ON THE FILE ITSELF.
#
# The first version wrapped a read in st.cache_data and parsed the JSON
# on every call. Measured on a real-sized file (30 teams, ~1,000 bats,
# 110 KB): attaching one nine-man lineup cost 19 ms, because attach()
# asks nine times and each ask re-parsed the whole league.
#
# st.cache_data is the wrong tool one layer down — it serialises what it
# stores, so even a cached dict is re-unpickled per call and the 110 KB
# is paid again. A plain memo keyed on (path, mtime, size) is O(1) after
# the first read and re-reads the moment the nightly writes a new file.
# roster.py keeps a response memo below st.cache_data for the same
# reason.
#
# CALLERS MUST NOT MUTATE what load() returns — it is the shared parsed
# copy, not a per-caller one. Nothing in this module writes to it, and
# attach() copies the values it needs onto the batter rows.
_MEMO = {"key": None, "data": {}}


def clear_cache():
    """Drop the parsed copy. For tests, and for a manual data refresh."""
    _MEMO["key"] = None
    _MEMO["data"] = {}


def load():
    p = _path()
    if p is None:
        clear_cache()
        return {}
    try:
        stat = p.stat()
        key = (str(p), stat.st_mtime_ns, stat.st_size)
    except Exception:
        return {}
    if _MEMO["key"] == key:
        return _MEMO["data"]
    try:
        data = json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    _MEMO["key"], _MEMO["data"] = key, data
    return data


def available() -> bool:
    """True when there is real lock data to show.

    Every caller checks this. The alternative — rendering a column of
    dashes — reads as "these bats have no history" rather than "the
    nightly has not published", and those are opposite meanings."""
    return bool(load().get("teams"))


def measured() -> bool:
    """True once the probe has confirmed the window predicts anything.

    Ships False. A number on screen that has never been checked against
    an outcome is exactly what standing rule 1 exists to stop, so the
    caption says 'provisional' until this flips."""
    return bool(load().get("window_is_measured"))


def window_games():
    return load().get("window_games")


def generated_at():
    return load().get("generated_at_et")


def tier_of(rate):
    """Label for a start rate. None in, TIER_UNKNOWN out — a bat with no
    window is unmeasured, NOT a bat who never plays."""
    if rate is None:
        return TIER_UNKNOWN
    if rate >= LOCK:
        return TIER_LOCK
    if rate >= USUAL:
        return TIER_USUAL
    if rate >= FLUX:
        return TIER_FLUX
    return TIER_RARE


def start_rate(team_name, player_id, vs_hand=None):
    """(rate, starts, games, basis) for one bat, or (None, 0, 0, None).

    vs_hand narrows to games against that hand of starter. It FALLS BACK
    to the overall rate when the team has not faced that hand enough in
    the window, and says so through `basis` — a platoon bat who has not
    seen a lefty in two weeks has an unmeasured split, and reporting
    0-for-0 as 0% would call a healthy regular a bench player."""
    data = load()
    # ONE guard, in _lookup. This used to check `not team` here as well,
    # and the duplicate cost a negative control: breaking _lookup's copy
    # left this path green, because the test only ever called start_rate.
    # attach() goes through _lookup directly, so a rule enforced in two
    # places is a rule half-tested.
    return _lookup((data.get("teams") or {}).get(team_name), player_id, vs_hand)


def _lookup(team, player_id, vs_hand=None):
    """start_rate's body, against a team record already resolved."""
    if not team:
        return None, 0, 0, None
    rec = (team.get("players") or {}).get(str(player_id))
    if not rec:
        # He is on the roster and did not start in the window. That IS
        # measured — zero starts out of the team's games — and it is the
        # one case where zero is the honest answer rather than missing.
        return 0.0, 0, int(team.get("games") or 0), "window"
    if vs_hand in ("L", "R"):
        split = (rec.get("vs") or {}).get(vs_hand)
        if split and split.get("games"):
            return (float(split["rate"]), int(split["starts"]),
                    int(split["games"]), f"vs{vs_hand}")
    return (float(rec["rate"]), int(rec["starts"]), int(rec["games"]), "window")


def attach(batters, team_name, vs_hand=None):
    """Adds lock_rate / lock_starts / lock_games / lock_basis / lock_tier
    to each batter row in place, and returns the same list.

    In place and returning, because both call styles already exist in
    the views this feeds.

    Resolves the team ONCE for the whole lineup. Calling start_rate per
    bat is the obvious way to write this and it is nine dictionary
    walks where one will do — the same shape of waste as a per-row
    fetch inside a table loop."""
    data = load()
    team = (data.get("teams") or {}).get(team_name) or {}
    for b in batters or []:
        rate, starts, games, basis = _lookup(team, b.get("id"), vs_hand)
        b["lock_rate"] = rate
        b["lock_starts"] = starts
        b["lock_games"] = games
        b["lock_basis"] = basis
        b["lock_tier"] = tier_of(rate)
    return batters


def summarize(batters):
    """(locks, in_question, named) for a projected lineup.

    `named` is the bats a reader should say out loud on camera — the
    ones the projection is actually unsure about. Deliberately not a
    single confidence percentage: one number over nine rows hides WHICH
    two are soft, and which two is the entire useful part."""
    locks = in_q = 0
    named = []
    for b in batters or []:
        tier = b.get("lock_tier")
        if tier == TIER_LOCK:
            locks += 1
        elif tier in (TIER_FLUX, TIER_RARE):
            in_q += 1
            named.append(b.get("name") or "?")
    return locks, in_q, named


def caption(batters):
    """One honest sentence for the top of a projected lineup."""
    if not available():
        return None
    locks, in_q, named = summarize(batters)
    win = window_games()
    head = f"Projected lineup — {locks} lock{'' if locks == 1 else 's'}"
    if in_q:
        head += (f", {in_q} in question ({', '.join(named[:4])})"
                 if named else f", {in_q} in question")
    tail = (f" · start rates over the last {win} team games"
            if win else "")
    if not measured():
        tail += " · provisional, not yet checked against outcomes"
    return head + tail + "."
