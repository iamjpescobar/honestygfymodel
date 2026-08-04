"""Guards the two things the home screen depends on.

1) THE WIRING. CI commits today's picks to data/calibration.json at the
   repo root; the app only ever read app/data/calibration.json, which is
   the nightly archive copy and does not change between 6 AM refreshes.
   Same filename, different file, and the failure was silent: today's
   board simply wasn't there, and the only reason the site ever showed
   one was log_picks() firing when a human opened that board's page.
   That is the "no visitor, no picks" hole calibration_picks.py exists
   to close, reopened on the reading side.

2) THE DISK-ONLY CONTRACT. Home is the landing page. Its entire premise
   is that the board CI already computed is on disk, so the page paints
   instead of spending tens of seconds rebuilding a board that would
   come out identical. One import of a fetching engine would quietly
   turn the landing page back into a minute of spinner, and nothing else
   in the suite would notice.
"""
import ast
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

failures = []

# ----------------------------------------------------------------------
# 1) The repo-root record is a source the app actually reads.
# ----------------------------------------------------------------------
from engines import calibration as cal  # noqa: E402

expected = ROOT / "data" / "calibration.json"
if cal._repo_path() != expected:
    failures.append(f"_repo_path() resolves {cal._repo_path()}, not {expected}")
else:
    print("PASS: _repo_path -> data/calibration.json (the file CI commits)")

# The pipeline and the CI logger must keep writing the file the app now
# reads. If either is ever repointed, this fails instead of the site
# quietly showing yesterday's board forever.
pipe_src = (ROOT / "calibration_pipeline.py").read_text()
picks_src = (ROOT / "calibration_picks.py").read_text()
if 'Path(__file__).resolve().parent / "data" / "calibration.json"' not in pipe_src:
    failures.append("calibration_pipeline no longer writes the repo-root record")
elif 'ROOT / "data" / "calibration.json"' not in picks_src:
    failures.append("calibration_picks no longer writes the repo-root record")
else:
    print("PASS: pipeline and slate-picks both still write that same file")

# ----------------------------------------------------------------------
# 1b) FILL-ONLY. The repo record supplies days nothing else has; it must
# never overwrite a day the pipeline or the local log already holds,
# because those are the ones carrying grades and hand-entered odds.
# ----------------------------------------------------------------------
tmp = Path(tempfile.mkdtemp())
(tmp / "pub.json").write_text(json.dumps({
    "daily13": {"2026-01-02": {"picks": [{"id": "1", "name": "Graded",
                                          "result": "hit"}], "graded": True}}}))
(tmp / "repo.json").write_text(json.dumps({
    "daily13": {
        # Same day the published record holds, but ungraded — must lose.
        "2026-01-02": {"picks": [{"id": "1", "name": "Ungraded",
                                  "result": None}], "graded": False},
        # A day nothing else holds — this is the whole point.
        "2026-01-03": {"picks": [{"id": "9", "name": "Today",
                                  "result": None}], "graded": False}}}))
(tmp / "local.json").write_text("{}")

_orig_pub, _orig_repo, _orig_log = cal._published_path, cal._repo_path, cal._LOG_PATH
cal._published_path = lambda: tmp / "pub.json"
cal._repo_path = lambda: tmp / "repo.json"
cal._LOG_PATH = tmp / "local.json"
merged = cal._load()
cal._published_path, cal._repo_path, cal._LOG_PATH = _orig_pub, _orig_repo, _orig_log

if merged.get("daily13", {}).get("2026-01-03", {}).get("picks"):
    print("PASS: repo record supplies a day the other sources don't have")
else:
    failures.append("repo record did not backfill a day missing from the others")

_kept = merged.get("daily13", {}).get("2026-01-02", {}).get("picks", [{}])[0]
if _kept.get("result") == "hit":
    print("PASS: repo record does not overwrite an already graded day")
else:
    failures.append("repo record clobbered a graded day — grades and odds "
                    "would be lost on every read")

# ----------------------------------------------------------------------
# 2) Home does no live work.
# ----------------------------------------------------------------------
HOME = ROOT / "app" / "views" / "Home.py"
home_src = HOME.read_text()
tree = ast.parse(home_src)

imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported.update(a.name.split(".")[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom):
        imported.add((node.module or "").split(".")[0])
        if (node.module or "").startswith("engines"):
            imported.add(node.module)

# Anything that reaches the network, or any engine that builds a board
# from scratch. The record on disk is the only permitted input.
BANNED = {"requests", "urllib", "http", "pybaseball", "baseball_scraper",
          "engines.daily_13", "engines.hr_edge_board", "engines.k_projection",
          "engines.player_of_the_day", "engines.wnba_props",
          "engines.wnba_defense", "engines.roster", "engines.statcast_engine",
          "engines.weather_engine"}
offenders = sorted(imported & BANNED)
if offenders:
    failures.append(f"Home.py imports live-fetch modules {offenders} — the "
                    f"landing page must read the published record only")
else:
    print("PASS: Home.py imports nothing that fetches or rebuilds a board")

# ----------------------------------------------------------------------
# 3) Home is registered, and it is the default landing page.
# ----------------------------------------------------------------------
app_src = (ROOT / "app" / "app.py").read_text()
if '("Home", "views/Home.py")' not in app_src:
    failures.append("Home is not registered in app.py's MLB page list")
elif app_src.index('("Home", "views/Home.py")') > app_src.index('("Game Card"'):
    failures.append("Home is not first in the page list — menu_titles[0] is "
                    "the default landing page, so a cold session would land "
                    "on a page that builds a board before it paints")
else:
    print("PASS: Home is registered and lands first")

# The jump buttons write the nav radio's widget key. That is only legal
# because app.py instantiates the radio AFTER the main column renders.
if 'st.session_state["lc_nav_radio"]' not in home_src:
    failures.append("Home lost its nav jump — the boards become unreachable "
                    "from the landing page")
elif app_src.index("with main_col:") > app_src.index("with right_col:"):
    # Source order of the two `with` blocks IS execution order, and the
    # radio (key="lc_nav_radio") is rendered inside the right one. Writing
    # a widget's key after Streamlit has instantiated it raises
    # StreamlitAPIException, so the page content must render first.
    failures.append("app.py now renders the right sidebar before the main "
                    "column; the nav radio would already exist by the time "
                    "Home runs, and setting lc_nav_radio would raise "
                    "StreamlitAPIException on every jump-button click")
else:
    print("PASS: main column renders before the nav radio, so Home may set it")

# ----------------------------------------------------------------------
if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nAll home-screen checks passed.")
