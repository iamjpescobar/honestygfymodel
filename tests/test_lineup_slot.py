"""Lineup-slot opportunity — how often he gets to swing.

Every other metric measures how good the swing is. This one measures how
many times he takes it. A leadoff bat comes up meaningfully more often
than a 9-hole bat, and HR probability scales almost linearly with plate
appearances, so a purely skill-based model can rank a 9-hole hitter above
a leadoff hitter correctly on quality and still be wrong about who is
likeliest to go deep tonight.
"""
import sys, types, tempfile, json
from pathlib import Path

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks", "statcast"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

from engines.lineup_slot import (
    _slot_from_batting_order, expected_pa, slot_opportunity_adj, SLOT_CAP)

# --- MLB's 3-digit batting order code ---------------------------------
assert _slot_from_batting_order(100) == 1
assert _slot_from_batting_order(900) == 9
# Substitutes entering a spot get 101, 201, ... — same slot.
assert _slot_from_batting_order(401) == 4
assert _slot_from_batting_order(None) is None
assert _slot_from_batting_order(0) is None
assert _slot_from_batting_order("bad") is None
print("PASS: batting order code decodes to 1-9, substitutes included")

# --- expected PA is arithmetic on a MEASURED input --------------------
PA = 38.0
exp = [expected_pa(i, PA) for i in range(1, 10)]
assert exp == sorted(exp, reverse=True), exp
assert exp[0] > exp[-1], exp
# Every slot must be DISTINCT. An earlier version used ceil(), which at
# T=38 gave slots 2-9 an identical 4 PA and collapsed eight slots into
# one value — destroying the gradient this exists to measure.
assert len(set(exp)) == 9, f"slots collapsed into {len(set(exp))} values: {exp}"
print(f"PASS: expected PA descends by slot — leadoff {exp[0]}, 9th {exp[-1]}")

# No measured figure means NO adjustment, never an invented one.
assert expected_pa(1, None) is None
assert slot_opportunity_adj(100, None) == (0, None)
print("PASS: without the measured PA figure the adjustment sits out")

# --- the adjustment ---------------------------------------------------
lead, lead_note = slot_opportunity_adj(100, PA)
ninth, ninth_note = slot_opportunity_adj(900, PA)
assert lead > 0 > ninth, (lead, ninth)
assert abs(lead) <= SLOT_CAP and abs(ninth) <= SLOT_CAP
print(f"PASS: leadoff {lead:+} vs 9-hole {ninth:+} (capped at {SLOT_CAP})")
assert "PA" in lead_note and "1st" in lead_note, lead_note
print(f"PASS: note explains itself: {lead_note!r}")

# Middle of the order sits near neutral — the scale is two-sided.
mid, _ = slot_opportunity_adj(500, PA)
assert abs(mid) < abs(lead), (mid, lead)
print(f"PASS: 5-hole {mid:+} sits between the extremes")

# Unknown slot (unconfirmed lineup has no batting order) -> nothing.
assert slot_opportunity_adj(None, PA) == (0, None)
print("PASS: no batting order -> no adjustment (unconfirmed lineup)")

# --- it must actually reach the score ---------------------------------
import engines.edge as edge
edge.bvp_component = lambda b, p: (0, None)
edge.zone_fit_component = lambda b, p: (0, None)
import engines.lineup_slot as ls
ls.league_pa_per_game = lambda: PA

top = edge.edge_components(1, 2, 50, 0, None, batting_order=100)
bot = edge.edge_components(1, 2, 50, 0, None, batting_order=900)
assert top["edge"] > bot["edge"], (top["edge"], bot["edge"])
assert top["slot_note"] and bot["slot_note"]
print(f"PASS: same skill, different slot -> {top['edge']} vs {bot['edge']}")

none_row = edge.edge_components(1, 2, 50, 0, None)
assert none_row["slot_adj"] == 0 and none_row["edge"] == 50
print("PASS: callers passing no batting order are unaffected")

# --- measured, not hardcoded ------------------------------------------
src = open("app/engines/lineup_slot.py").read()
import re
# No table of per-slot PA values baked in.
assert not re.search(r"\{\s*1:\s*[45]\.", src), "a hardcoded PA-by-slot table is present"
assert "build_pa_per_game" in src, "should reference the measured source"
pre = open("precompute.py").read()
assert "def build_pa_per_game" in pre
assert '"pa_per_team_game"' in pre, "measurement not published to the manifest"
print("PASS: PA per game is measured nightly, not hardcoded")

# --- Game Card: batting order carried and displayed --------------------
gc = open("app/views/GameCard.py").read()
assert '"battingOrder": b.get("battingOrder")' in gc, "order not carried into profiles"
assert 'batting_order=r.get("battingOrder")' in gc, "order not passed to edge_components"
assert '"Batting Order"' in gc, "no batting-order sort option"
assert gc.index('"Batting Order", "SLAM"') > 0, "batting order should be the default sort"
km = re.search(r'sort_key_map = \{(.*?)\n                \}', gc, re.S).group(1)
assert '"Batting Order":' in km, "sort option has no handler (KeyError on select)"
print("PASS: Game Card carries, scores, displays and sorts by batting order")
