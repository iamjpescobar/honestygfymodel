"""Projected run totals for KBO and NPB.

Arithmetic on four measured quantities: each side's runs scored and
allowed per game, the league baseline, and the announced starter's ERA.
Deliberately NOT a moneyline — that needs a fitted run-margin-to-win-
probability relationship, which requires graded history this site
doesn't have yet.
"""
import re, sys, types

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, "app")

from engines.run_total import (project_total, expected_runs,
                               starter_adjustment, league_run_average,
                               STARTER_CAP, MIN_TOTAL, MAX_TOTAL)

# --- the pairing identity ---------------------------------------------
# A team facing an exactly league-average staff scores its own average.
assert expected_runs(5.0, 4.5, 4.5) == 5.0
# 20% stingier opponent -> 20% fewer runs.
assert abs(expected_runs(5.0, 3.6, 4.5) - 4.0) < 1e-9
print("PASS: pairing identity — average opponent returns the team's own average")

assert expected_runs(None, 4.5, 4.5) is None
assert expected_runs(5.0, None, 4.5) is None
assert expected_runs(5.0, 4.5, None) is None
assert expected_runs("x", 4.5, 4.5) is None
print("PASS: any missing input -> None (no league-average substitution)")

# --- totals ------------------------------------------------------------
strong = {"rs_pg": 5.5, "ra_pg": 3.8}
weak = {"rs_pg": 3.6, "ra_pg": 5.4}
t_mismatch, d = project_total(strong, weak, 4.5)
t_even, _ = project_total({"rs_pg": 4.5, "ra_pg": 4.5},
                          {"rs_pg": 4.5, "ra_pg": 4.5}, 4.5)
assert t_even == 9.0, t_even
assert d["home_exp"] > d["away_exp"], d
print(f"PASS: two average teams project {t_even}; mismatch splits "
      f"{d['home_exp']}/{d['away_exp']}")

# KBO field names must work as well as NPB's.
kbo_shape = {"runs_per_game": 4.5, "runs_allowed_per_game": 4.5}
assert project_total(kbo_shape, kbo_shape, 4.5)[0] == 9.0
print("PASS: both KBO and NPB field names accepted by one engine")

# --- starters ----------------------------------------------------------
ace_adj = starter_adjustment(2.00, 4.50)
bad_adj = starter_adjustment(7.00, 4.50)
assert ace_adj < 0 < bad_adj
assert abs(ace_adj) <= STARTER_CAP and abs(bad_adj) <= STARTER_CAP
print(f"PASS: ace {ace_adj}, replacement {bad_adj}, both within +/-{STARTER_CAP}")

assert starter_adjustment(None, 4.5) == 0.0
assert starter_adjustment(2.0, None) == 0.0
print("PASS: unknown starter or league ERA -> no adjustment")

with_ace, _ = project_total(strong, weak, 4.5, league_era=4.5,
                            away_starter_era=2.0)
assert with_ace < t_mismatch, (with_ace, t_mismatch)
print(f"PASS: an ace starting drops the total {t_mismatch} -> {with_ace}")

# --- guards -------------------------------------------------------------
absurd, why = project_total({"rs_pg": 40.0, "ra_pg": 40.0},
                            {"rs_pg": 40.0, "ra_pg": 40.0}, 4.5)
assert absurd is None and "outside the plausible range" in why["reason"]
print("PASS: implausible totals rejected rather than displayed")

missing, why2 = project_total({"rs_pg": None}, weak, 4.5)
assert missing is None and "not enough real run data" in why2["reason"]
print("PASS: incomplete data -> no projection, with a reason")

assert league_run_average({"a": {"rs_pg": 4.0}, "b": {"rs_pg": 5.0}}) == 4.5
assert league_run_average({}) is None
print("PASS: league baseline measured from teams on file, None when empty")

# --- explicitly not a moneyline ----------------------------------------
# Check for CODE that produces a probability, not the word appearing in
# prose — the module docstring explains at length why it isn't a
# moneyline, and an earlier version of this test matched that explanation
# and failed against correct code.
import ast
tree = ast.parse(open("app/engines/run_total.py").read())
defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
for banned in ("win_prob", "moneyline", "win_probability", "implied_odds",
               "to_american", "fair_odds"):
    assert banned not in defined, f"{banned}() defined — that needs fitted history"
src = open("app/engines/run_total.py").read()
assert "NOT a moneyline" in src, "the omission should be stated, not silent"
print("PASS: no win probability produced (needs calibration that doesn't exist)")

# --- both views wired ---------------------------------------------------
for view in ("app/views/KBO.py", "app/views/NPB.py"):
    v = open(view).read()
    assert "_project_total(" in v, f"{view} doesn't project a total"
    assert "PROJECTED TOTAL" in v, f"{view} doesn't display it"
    # Baseline must be measured, not a literal.
    assert "_LEAGUE_RS" in v
    i_def = v.index("_LEAGUE_RS =")
    i_use = v.index("            _LEAGUE_RS,")
    assert i_def < i_use, f"{view}: baseline used before it's defined"
    print(f"PASS: {view.split('/')[-1]} projects and displays a measured total")