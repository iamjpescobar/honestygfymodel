"""Slate-wide HR Edge board.

The board used to live inside GameCard.py and rank ONE game's bats
against ONE pitcher, so the "top 5 HR Edge" logged for calibration was
whichever game card was open. These assert the board actually spans the
slate, that each side faces the correct opposing starter, and that
switch hitters resolve before park factors are applied.
"""
import sys, types
import pandas as pd

st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
          "statcast_batter_percentile_ranks", "statcast"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

import engines.hr_edge_board as board

# --- effective handedness (park splits depend on getting this right) ---
assert board._effective_hand("S", "R") == "L"
assert board._effective_hand("S", "L") == "R"
assert board._effective_hand("R", "L") == "R"
assert board._effective_hand("L", "R") == "L"
assert board._effective_hand("S", None) is None, "unknown pitcher hand must not be guessed"
assert board._effective_hand("", "R") is None
print("PASS: switch hitters flip against the pitcher; unknown hand yields None")

# --- slate-wide assembly ----------------------------------------------
GAMES = [
    {"game_pk": 1, "away": "Yankees", "home": "Red Sox", "weather_temp": "80 degrees",
     "away_pitcher_id": 10, "home_pitcher_id": 20,
     "away_pitcher": "AP", "home_pitcher": "HP"},
    {"game_pk": 2, "away": "Dodgers", "home": "Giants", "weather_temp": "60 degrees",
     "away_pitcher_id": 30, "home_pitcher_id": 40,
     "away_pitcher": "DP", "home_pitcher": "GP"},
]
board.get_todays_games_with_weather = lambda: (GAMES, None)
board.load_percentile_ranks = lambda: (pd.DataFrame(), None)
board.get_confirmed_lineup = lambda pk, side: (
    [{"name": f"{side}{pk}-{i}", "id": pk * 100 + i * 10 + (0 if side == "away" else 5),
      "bats": "S" if i == 0 else "R", "is_pitcher": False} for i in range(3)], True)
# REAL shape: (lineup, game_date, confirmed) — a 3-tuple, not a list.
board.get_last_starting_lineup = lambda t: ([], None, False)
board.get_batter_profile_windowed = lambda pid, **kw: {"Brl %": 10.0}
board.get_pitcher_statcast = lambda pid: {"p_throws": "R"}
board.pen_context = lambda team, pid: (0, None)

seen_pitchers = []
def fake_rank(profiles, savant):
    return [{"name": p["name"], "id": p["id"], "bats": p["bats"],
             "hr_score": 50 + (p["id"] % 7)} for p in profiles]
def fake_edge(bid, pid, base, pen, note, **kw):
    seen_pitchers.append((bid, pid))
    return {"edge": base, "mx": 0, "ctx_adj": 0, "ctx_notes": [],
            "_bats_passed": kw.get("bats")}
board.rank_batters = fake_rank
board.edge_components = fake_edge

rows, meta = board.get_hr_edge_board(_date_str="2026-07-27")

assert meta["games"] == 2
teams = {r["team"] for r in rows}
assert teams == {"Yankees", "Red Sox", "Dodgers", "Giants"}, teams
print(f"PASS: board spans all 4 teams across {meta['games']} games ({len(rows)} bats)")

# Each side must face the OPPOSING starter, not its own. Away batter ids
# in game 1 end in 0 (100/110/120), home ids end in 5 (105/115/125) — an
# earlier version of this test filtered on a range that caught both and
# reported a failure the code hadn't made.
pairs = dict(seen_pitchers)
away_g1 = {pairs[b] for b in (100, 110, 120)}
home_g1 = {pairs[b] for b in (105, 115, 125)}
assert away_g1 == {20}, f"Yankees hitters faced {away_g1}, expected Red Sox starter 20"
assert home_g1 == {10}, f"Red Sox hitters faced {home_g1}, expected Yankees starter 10"
away_g2 = {pairs[b] for b in (200, 210, 220)}
assert away_g2 == {40}, f"Dodgers hitters faced {away_g2}, expected Giants starter 40"
print("PASS: every lineup matched against the OPPOSING probable, both games")

assert all(rows[i]["edge"] >= rows[i+1]["edge"] for i in range(len(rows)-1))
print("PASS: rows sorted by edge descending")

# Switch hitters must be resolved BEFORE park factors see them.
passed = {r["_bats_passed"] for r in rows}
assert "S" not in passed, "a raw 'S' reached edge_components"
print(f"PASS: no raw 'S' passed downstream (hands seen: {sorted(x for x in passed if x)})")

# --- unrateable bats are dropped, not sorted to the bottom -------------
board.edge_components = lambda bid, pid, base, pen, note, **kw: {
    "edge": None, "mx": 0, "ctx_adj": 0, "ctx_notes": []}
rows2, _ = board.get_hr_edge_board(_date_str="x")
assert rows2 == [], "bats with no Savant sample should be dropped, not ranked"
print("PASS: unrateable bats dropped rather than ranked as if evaluated")
board.edge_components = fake_edge

# --- confirmed_only ----------------------------------------------------
board.get_confirmed_lineup = lambda pk, side: ([], False)
board.get_last_starting_lineup = lambda t: (
    [{"name": "Fallback", "id": 999, "bats": "R", "is_pitcher": False}],
    "2026-07-26", True)
rows3, meta3 = board.get_hr_edge_board(_date_str="x", confirmed_only=True)
assert rows3 == [] and meta3["skipped"], "projected lineups leaked into a confirmed-only board"
print("PASS: confirmed_only excludes projected lineups and records why")

rows4, _ = board.get_hr_edge_board(_date_str="x", confirmed_only=False)
assert len(rows4) == 4 and all(r["confirmed"] is False for r in rows4)
print("PASS: confirmed_only=False allows fallbacks but flags them as unconfirmed")

# --- no games -----------------------------------------------------------
board.get_todays_games_with_weather = lambda: ([], "no slate")
rows5, meta5 = board.get_hr_edge_board(_date_str="x")
assert rows5 == [] and meta5["error"]
print("PASS: empty slate returns cleanly with an error note")

# --- fallback path uses the real 3-tuple shape ------------------------
# This is what crashed the live page: get_last_starting_lineup returns
# (lineup, game_date, confirmed) and was unpacked as a bare list.
board.get_todays_games_with_weather = lambda: (GAMES, None)
board.get_confirmed_lineup = lambda pk, side: ([], False)
board.get_last_starting_lineup = lambda t: (
    [{"name": f"{t}-1", "id": 777, "bats": "R", "is_pitcher": False},
     {"name": f"{t}-P", "id": 778, "bats": "R", "is_pitcher": True}],
    "2026-07-26", True)
rows6, _ = board.get_hr_edge_board(_date_str="x", confirmed_only=False)
assert rows6, "fallback lineup produced no rows"
assert all(r["confirmed"] is False for r in rows6)
assert not any("-P" in (r.get("name") or "") for r in rows6), "pitcher leaked into the board"
print(f"PASS: fallback 3-tuple unpacks, pitchers filtered out ({len(rows6)} bats)")

# No completed game to fall back to -> empty, not a crash.
board.get_last_starting_lineup = lambda t: ([], None, False)
rows7, meta7 = board.get_hr_edge_board(_date_str="x", confirmed_only=False)
assert rows7 == [] and meta7["skipped"]
print("PASS: no fallback lineup available -> empty board, reason recorded")
