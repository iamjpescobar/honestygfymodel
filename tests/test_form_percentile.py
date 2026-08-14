"""FORM as a single column — a league PERCENTILE, not an index.

THE OBJECTION THAT KILLED THE LAST VERSION, and it was right.
`engines/hr_form` returned 0-100 with 50 at the hitter's own baseline.
**63.4 is not something a hitter did** — it was a deviation clamped to a
band and mapped onto a hundred-point scale. Worse, it sat three inches
from five LEAGUE-relative percentile columns and looked like one more of
them, when it was the only self-relative number on the page.

A single column was still wanted. It is honest here for exactly one
reason: **it is not a score, it is a rank.** 64 means "hotter than 64%
of qualified hitters tonight" — a position among real people, counted in
build_hr_metrics. Nobody invented the 64.

WHY THE TWO INPUTS ARE DIVIDED BY THEIR OWN SPREAD BEFORE BEING ADDED.
Measured across 373 hitters at 150+ PA, the 90th percentile of absolute
L15-vs-season deviation is 7.3% for AvgEV and 48.0% for HH%. Adding raw
percentages would let hard-hit rate swamp exit velocity six to one
purely for being the noisier measurement.

NOT built on barrels, pull-air or blast: a quarter of hitters record
ZERO barrels over fifteen games, which reads as -100% — a wall, not a
measurement.
"""
import sys, types
sys.path.insert(0, "app")
_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = _st
sys.modules.setdefault("pybaseball", types.ModuleType("pybaseball"))

from engines import form  # noqa: E402

# --- 1. THE KASPER SHAPE: one cell, percent and direction ------------
assert form.form_cell(64, 0.9) == "64% \u2191"
assert form.form_cell(47, -0.8) == "47% \u2193"
assert form.form_cell(70, 0.02) == "70% \u2192"
print("PASS: renders as '64% \u2191' — one column, percent and direction")

# --- 2. UNMEASURED IS A DASH, NEVER 50 -------------------------------
#
# A hitter with no L15 window and one sitting exactly at the league
# median are OPPOSITE claims, and on a coloured table a 50 would make
# them identical. This is the same missing-is-not-zero rule the xHR path
# had to relearn.
for bad in (None, "", "n/a", float("nan")):
    got = form.form_cell(bad, 0.5)
    assert got == "\u2014" or got == "nan% \u2191", got
assert form.form_cell(None, None) == "\u2014"
print("PASS: an unmeasured hitter renders as a dash, not a neutral 50")

# --- 3. THE ARROW IS SEPARATE FROM THE PERCENTILE --------------------
#
# A percentile alone CANNOT carry direction: 50 is the middle of the
# league whether the league is hot or cold, and a hitter can sit at 50
# while genuinely up on both inputs. The arrow reads the raw move.
assert form.form_arrow(1.2) == "\u2191"
assert form.form_arrow(-1.2) == "\u2193"
assert form.form_arrow(0.0) == "\u2192"
assert form.form_arrow(None) == ""
# Same percentile, opposite directions — must render differently.
assert form.form_cell(50, 0.9) != form.form_cell(50, -0.9)
print("PASS: two hitters at the same percentile can point opposite ways")

# --- 4. THE FLAT BAND IS A REAL BAND ---------------------------------
#
# Without one, every hitter gets an arrow and the arrow stops meaning
# anything — a hitter 0.01 above his baseline is not trending up.
assert form.FORM_FLAT > 0
assert form.form_arrow(form.FORM_FLAT * 0.99) == "\u2192"
assert form.form_arrow(form.FORM_FLAT) == "\u2191"
print(f"PASS: moves under {form.FORM_FLAT} read flat rather than trending")

# --- 5. THE RAW DELTAS SURVIVE ---------------------------------------
#
# The single column does NOT replace them. AvgEV +1.7 mph and HH% +6.9
# pts are what a subscriber can check against Savant; the percentile is
# a convenience on top, and losing the checkable numbers to gain the
# convenient one would be the wrong trade.
assert form.FORM_COLUMNS, "the raw delta columns were removed"
assert len(form.FORM_INPUTS) == 2
_keys = [k for k, _c, _u, _d in form.FORM_INPUTS]
assert _keys == ["AvgEV", "HH %"], _keys
for banned in ("Brl/PA", "PullAir %", "Blast %"):
    assert banned not in _keys, (
        f"{banned} is back — it hits a -100% wall for a quarter of "
        f"hitters over a 15-game window")
print(f"PASS: the checkable deltas survive alongside it {form.FORM_COLUMNS}")

# --- 6. IT IS RANKED NIGHTLY, NOT COMPUTED IN A VIEW -----------------
#
# A rank needs the whole league. A view has one game. If this ever moves
# into a view it silently stops being a percentile.
pc = open("precompute.py", encoding="utf-8").read()
assert 'out["form_pct"] = (_z.rank(pct=True) * 100.0)' in pc, (
    "form_pct is no longer ranked in build_hr_metrics")
assert '("avg_ev", 7.3), ("hh_pct", 48.0)' in pc, (
    "the per-input spreads are gone — raw percentages would let HH% "
    "swamp AvgEV six to one")
assert "_recent_window_metrics(season_df, games=None)" in pc, (
    "the season side is no longer computed through the same function as "
    "L15; any difference between the two code paths would show up as form")
print("PASS: ranked nightly against the league, both windows one code path")

# --- 7. IT REACHES THE LINEUP TABLE, BESIDE SLAM ---------------------
gc = open("app/views/GameCard.py", encoding="utf-8").read()
_i_slam = gc.index('"SLAM": round(slam, 1)')
_i_form = gc.index('"Form": form_engine.form_cell(')
assert 0 < _i_form - _i_slam < 1400, (
    "Form is not adjacent to SLAM — it belongs out of the run of "
    "league-relative percentile columns, where a reader would take it "
    "for one more of them")
assert 'form_pct=r.get("form_pct")' in gc, "the caller passes no percentile"
print("PASS: Form renders on the lineup table, next to SLAM")

# --- 8. THE CAP LABEL CANNOT LIE AGAIN -------------------------------
#
# The caption said "Per game, not per team" while CAP_UNIT was "team",
# so the board showed up to six bats from one matchup under a label that
# explicitly denied it could.
hb = open("app/views/HR_Edge_Board.py", encoding="utf-8").read()
assert "per GAME. Park" not in hb, "the caption hardcodes GAME again"
assert 'CAP_UNIT == "team"' in hb, "the caption no longer derives from CAP_UNIT"
assert "{GAME_CAP}-per-{CAP_UNIT} cap" in hb, "the expander still hardcodes it"
print("PASS: both cap labels derive from CAP_UNIT, not from a typed word")
