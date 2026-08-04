"""Every graded board must have a SCHEDULED logger, not just a page.

wnba_props shipped with no calibration at all. It was logged from one
place — inside app/views/WNBA_Props.py — which only runs when a human
opens that page. So on any night nobody browsed it, the picks that board
would have made vanished unrecorded, and data/calibration.json contained
no wnba_props entries whatsoever while the MLB boards logged fine.

That is exactly the "no visitor, no picks" failure calibration_picks.py
exists to prevent. The board was configured for GRADING in
calibration_pipeline.BOARDS but had no BUILDER, and nothing connected
those two facts, so it failed silently for as long as it existed.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKS = (ROOT / "calibration_picks.py").read_text()
PIPELINE = (ROOT / "calibration_pipeline.py").read_text()

# --- 1. graded boards and logged boards must be the same set ---------
_graded = set(re.findall(r'^\s*"(\w+)":\s*\{"sport"', PIPELINE, re.M))
_builders = PICKS[PICKS.index("BUILDERS = {"):]
_builders = _builders[:_builders.index("}")]
_logged = set(re.findall(r'"(\w+)":', _builders))

assert _graded, "could not parse BOARDS out of calibration_pipeline"
missing = _graded - _logged
assert not missing, (
    f"boards {sorted(missing)} are configured for grading but have no builder "
    f"in calibration_picks.BUILDERS. They only get picks when someone opens "
    f"the page, so they silently never calibrate — which is how wnba_props "
    f"went its whole life with zero logged picks")
print(f"PASS: all {len(_graded)} graded boards have a scheduled builder")

extra = _logged - _graded
assert not extra, (
    f"builders {sorted(extra)} log picks that calibration_pipeline never "
    f"grades — those picks accumulate as permanently ungraded entries")
print("PASS: no builder logs picks that never get graded")

# --- 2. the WNBA builder must mirror the view's defaults -------------
_wnba = PICKS[PICKS.index("def _rows_wnba_props"):PICKS.index("BUILDERS = {")]
VIEW = (ROOT / "app" / "views" / "WNBA_Props.py").read_text()

assert '"Points"' in _wnba, "builder must use the view's default stat"
assert '"l10"' in _wnba, "builder must use the view's default window"
assert 'default="L10"' in VIEW, (
    "the view's default window changed — the builder still logs l10, so the "
    "record would grade a board the site never showed")
assert "[:10]" in _wnba and "top[:10]" in VIEW, (
    "builder and view disagree on how many picks the board makes")
print("PASS: builder mirrors the view's stat, window and pick count")

# --- 3. picks must carry what the grader needs -----------------------
# WNBA grades against a LINE, unlike MLB's binary threshold
# (BOARDS gives wnba_props threshold: None), so a pick without one can
# never be graded.
for field in ('"id"', '"name"', '"team"', '"stat"', '"line"'):
    assert field in _wnba, (
        f"WNBA picks must carry {field} — the pipeline grades these against "
        f"the pick's own line, not a fixed threshold, so a missing line "
        f"leaves the pick permanently ungradeable")
print("PASS: WNBA picks carry the line the grader needs")

# --- 4. the slate path must match where fetch_data extracts ----------
FETCH = (ROOT / "app" / "fetch_data.py").read_text()
assert "extracts to app/data" in FETCH or 'DEST = os.path.dirname' in FETCH
# The path moved again, and for a good reason: it now lives in
# app/engines/slate_guard.py, which is also the only place that checks
# the slate's DATE. Reading the file without that check is what let
# boards be built from games already played — see tests/test_slate_guard.
_slate = PICKS[PICKS.index("def _wnba_games"):PICKS.index("def _rows_wnba_props")]
assert 'load_slate("wnba")' in _slate, (
    "the builder no longer goes through slate_guard.load_slate — it would "
    "read the slate file without checking which night it was built for")
GUARD = (ROOT / "app" / "engines" / "slate_guard.py").read_text()
assert '"data"' in GUARD and '"games.json"' in GUARD, (
    "slate_guard reads from a path that isn't where fetch_data unpacks the "
    "archive — every league would silently return no games every run")
print("PASS: the slate is read through the date guard, from where "
      "fetch_data extracts it")

# --- 5. the workflow must fetch the slate BEFORE logging picks -------
# Compare actual STEP order, not raw text position — the filenames also
# appear in comments, and a comment above the fetch step would make a
# naive text comparison lie.
import yaml
_wf = yaml.safe_load((ROOT / ".github" / "workflows" / "slate-picks.yml").read_text())
_steps = [str(st.get("run", "")) for st in list(_wf["jobs"].values())[0]["steps"]]
_fetch_i = next(i for i, r in enumerate(_steps) if "fetch_data.py" in r)
_picks_i = next(i for i, r in enumerate(_steps) if "calibration_picks.py" in r)
assert _fetch_i < _picks_i, (
    "picks are logged before the nightly slate is fetched, so the WNBA "
    "builder would read a stale or missing games.json")
print("PASS: slate is fetched before picks are logged")
