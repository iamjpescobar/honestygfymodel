"""MLB active-roster filtering on stale fallback lineups.

get_last_starting_lineup searches back FOURTEEN days for the most recent
completed game, and the Game Card falls back to it whenever today's
lineup hasn't posted — which is exactly when you're looking at the page,
the morning before lineups drop. A player who went on the IL nine days
ago is still in that lineup and gets scored like anyone else: HR Score,
matchup, park, wind. Every number right except whether he's playing.
"""
import sys, types
import pandas as pd

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
          "statcast_batter_percentile_ranks", "statcast"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

import engines.roster as roster

# --- active flag comes from the roster call already being made ---------
src = open("app/engines/roster.py").read()
assert "active_pids" in src, "active roster membership is not tracked"
assert '"active": is_active' in src, "players don't carry an active flag"
assert "def get_active_player_ids" in src
print("PASS: roster tracks active-26 membership from the existing call")

# --- get_active_player_ids -------------------------------------------
roster.get_live_team_roster = lambda team: [
    {"id": "1", "name": "Healthy", "is_pitcher": False, "active": True},
    {"id": "2", "name": "OnTheIL", "is_pitcher": False, "active": False},
    {"id": "3", "name": "Optioned", "is_pitcher": False, "active": False},
]
ids = roster.get_active_player_ids("Yankees")
assert ids == {"1"}, ids
print(f"PASS: only active-26 ids returned ({ids}) — IL and optioned excluded")

roster.get_live_team_roster = lambda team: []
assert roster.get_active_player_ids("Yankees") == set()
def _boom(team): raise RuntimeError("API down")
roster.get_live_team_roster = _boom
assert roster.get_active_player_ids("Yankees") == set(), "must not propagate"
print("PASS: unreachable roster returns an empty set, not an exception")

# --- the slate board fallback drops IL players ------------------------
import engines.hr_edge_board as board
board.get_confirmed_lineup = lambda pk, side: ([], False)
board.get_last_starting_lineup = lambda t: (
    [{"id": "1", "name": "Healthy", "is_pitcher": False},
     {"id": "2", "name": "OnTheIL", "is_pitcher": False},
     {"id": "9", "name": "Starter", "is_pitcher": True}],
    "2026-07-18", True)
board.get_active_player_ids = lambda t: {"1"}

batters, confirmed = board._lineup_for(1, "away", "Yankees")
names = [b["name"] for b in batters]
assert names == ["Healthy"], names
assert confirmed is False
print(f"PASS: 10-day-old lineup filtered -> {names} (IL player and pitcher dropped)")

# --- fails OPEN when the roster is unknown ----------------------------
board.get_active_player_ids = lambda t: set()
batters2, _ = board._lineup_for(1, "away", "Yankees")
assert len(batters2) == 2, (
    "an empty active set means UNKNOWN, not 'nobody is active' — the board "
    "must not empty itself because one request timed out")
print("PASS: unreadable roster falls back to showing the lineup, not blanking it")

# --- the Game Card does the same and says so --------------------------
gc = open("app/views/GameCard.py").read()
assert "get_active_player_ids" in gc, "Game Card doesn't check the active roster"
assert "no longer on" in gc, "Game Card should name who it removed and why"
i_active = gc.index("_active = get_active_player_ids(opposing_team)")
i_else = gc.index("batters = _raw")
assert i_active < i_else, "fail-open branch must come after the check"
print("PASS: Game Card filters the stale lineup and names who it dropped")
