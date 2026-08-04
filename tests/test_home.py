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

# Home is a TOP-LEVEL VIEW, not one of baseball's pages. It reports every
# board on the site, WNBA included, so living in the MLB nav made it
# unreachable from every other sport.
if '("Home", "views/Home.py")' in app_src:
    failures.append("Home is back in the MLB page list — it belongs above "
                    "the sport switcher, not inside one sport's nav")
elif 'st.session_state.setdefault("lc_view", "home")' not in app_src:
    failures.append("a new session no longer defaults to the Home view")
elif 'if st.session_state.get("lc_view") == "home":' not in app_src:
    failures.append("app.py has no Home branch — the view is unreachable")
else:
    print("PASS: Home is a top-level view and is where a new session lands")

# A sport click must leave Home, and the check has to sit ABOVE the
# switcher: Streamlit syncs the widget key before the script runs, and
# sport_switcher writes lc_sport then reruns, so the two disagree on
# exactly one run — the click. Checking afterwards always misses it.
if 'st.session_state["lc_view"] = "sport"' not in app_src:
    failures.append("nothing leaves the Home view when a sport is clicked — "
                    "the switcher would appear dead from Home")
elif app_src.index('st.session_state["lc_view"] = "sport"') > \
        app_src.index("sport_switcher(active=selected_sport)"):
    failures.append("the sport-click check runs after sport_switcher has "
                    "already synced lc_sport_seg and lc_sport, so it can "
                    "never fire")
else:
    print("PASS: a sport click leaves Home, detected before the switcher syncs")

# ----------------------------------------------------------------------
# HOME MUST HAVE A WAY OUT. This shipped broken once: the button only
# ever set lc_view="home", and clicking the already-selected sport is a
# no-op in sport_switcher (it reruns only when the sport CHANGES). A new
# session landed on Home and could reach five of the ten destinations.
# ----------------------------------------------------------------------
if 'Back to {selected_sport}' not in app_src:
    failures.append("the Home button no longer flips to a Back control — "
                    "clicking the already-active sport is a no-op, so Home "
                    "becomes a room with no door")
elif "_home_nav" not in app_src or "render_right_sidebar(nav_titles=_home_nav" not in app_src:
    failures.append("Home no longer passes a nav to the sidebar — the admin "
                    "diagnostics have no other route in")
elif 'if _nav is not None and _nav != st.session_state.get("lc_active_page"):' not in app_src:
    failures.append("a nav click from Home does not leave the Home view, so "
                    "the sidebar would appear dead")
elif 'st.session_state["lc_nav_radio"] = None' not in app_src:
    failures.append("Home no longer clears the nav selection, so the active "
                    "rail would sit on a page the user is not on")
# The nav used to be an st.radio, and this guard checked `index=_idx ...
# else None` — a radio always selects SOMETHING, so passing index=None was
# the only way to show no active page on Home. The nav is buttons now and
# there is no index to pass, so that string check could never pass again.
#
# The BUG it guards against is unchanged and still worth guarding: on
# Home, no page is current, and the rail must not light up the first one.
# With buttons that is expressed by rendering the active row only on an
# exact match, and by handing `active_page` straight through instead of
# defaulting it. Both are checked below, which is a stricter test than
# the old one — it reads the actual condition rather than the presence of
# a keyword argument.
elif "if _title == active_page:" not in app_src:
    failures.append("the nav no longer marks the active row by exact match, "
                    "so it may highlight a page the user is not on")
elif 'st.session_state["lc_active_page"] = active_page' not in app_src:
    failures.append("the nav defaults lc_active_page instead of passing it "
                    "through, so Home (which has no active page) would "
                    "highlight the first entry")
else:
    print("PASS: Home has a Back control, the page nav, and both exits work")
    print("PASS: the nav shows no active page on Home")

# The nav is st.button now, not st.radio. A radio needs a value for every
# render and silently selects index 0 when handed none, which is exactly
# the failure the block above exists to prevent — so a revert to st.radio
# should fail loudly here rather than quietly re-highlighting page one.
if "st.radio(" in app_src:
    failures.append("app.py is back on st.radio for navigation — a radio "
                    "always has a selection, so Home would light up the "
                    "first page again")
else:
    print("PASS: navigation is buttons, which can show no selection at all")

# ----------------------------------------------------------------------
# EVERY PAGE MUST BE REACHABLE FROM HOME.
#
# This used to be checked indirectly, by asserting that Home rendered the
# sport's whole page nav in the sidebar. That nav was nine parts
# duplication by the time Home grew Today cards and an Explore grid, and
# it is gone — so the old check would now pass or fail for reasons
# unrelated to the thing it cared about.
#
# The concern behind it is still real and this tests it directly: walk
# the actual page list and confirm each non-admin entry has a route from
# Home's body. Delete an Explore card without adding another way in and
# this fails, which the old string check could never have caught.
# ----------------------------------------------------------------------
import ast as _ast

_nav_titles = []
for _n in _ast.parse(app_src).body:
    if isinstance(_n, _ast.FunctionDef) and _n.name == "build_mlb_pages":
        for _c in _ast.walk(_n):
            if (isinstance(_c, _ast.Tuple) and len(_c.elts) == 2
                    and isinstance(_c.elts[0], _ast.Constant)):
                _nav_titles.append(_c.elts[0].value)

if not _nav_titles:
    failures.append("could not read build_mlb_pages — the reachability "
                    "check below is not running")
else:
    # A title counts as reachable if Home names it anywhere: BOARD_PAGE
    # and WNBA_PAGE map a board to its page for the Today-card titles,
    # EXPLORE lists the rest, and Results arrives via its own _goto.
    _unreachable = [t for t in _nav_titles
                    if "(Admin)" not in t and f'"{t}"' not in home_src]
    if _unreachable:
        failures.append("no route from Home to: " + ", ".join(_unreachable)
                        + " — every non-admin page needs a card, a board "
                          "title, or a link on the landing screen")
    else:
        print(f"PASS: all {len(_nav_titles)} MLB pages are reachable "
              f"(admin ones via the sidebar, the rest via Home's own cards)")

# The jump buttons write lc_nav_radio. That key kept its name through the
# radio-to-button change so every existing reader keeps working, but it is
# now a plain session value rather than a widget key — which means writing
# it from Home is no longer order-dependent. The ordering check below is
# kept anyway: it is still true, still cheap, and still the thing that
# would break first if the layout were reshuffled.
if 'st.session_state["lc_nav_radio"]' not in home_src:
    failures.append("Home lost its nav jump — the boards become unreachable "
                    "from the landing page")
elif "lc_sport_seg" in home_src.split("CURRENT_SPORT")[-1].replace(
        'st.session_state.get("lc_sport_seg")', ""):
    failures.append("Home writes lc_sport_seg — that widget is instantiated "
                    "by app.py above the main column, so setting it raises "
                    "StreamlitAPIException")
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

# ----------------------------------------------------------------------
# NO FABRICATED FRESHNESS.
#
# data_timestamp() printed datetime.now() under the words "Data
# refreshed", on every page, always the current second — so a three-day-
# old archive read as fresh and the one control a subscriber has for
# judging staleness was the one thing guaranteed not to reflect it. It
# must read the nightly's own manifest instead.
# ----------------------------------------------------------------------
theme_src = (ROOT / "app" / "styles" / "kc_theme.py").read_text()
_ts = theme_src[theme_src.index("def data_timestamp"):]
_ts = _ts[:_ts.index("\ndef ")] if "\ndef " in _ts else _ts
if "generated_at_utc" not in _ts or "manifest.json" not in _ts:
    failures.append("data_timestamp no longer reads the nightly manifest — it "
                    "would be reporting the clock as the data's age")
elif "no data manifest on disk" not in _ts:
    # The property that matters isn't "never calls now()" — computing an
    # age needs the clock. It's that a MISSING manifest says so, instead
    # of quietly substituting the current time and calling it fresh.
    failures.append("data_timestamp has no honest fallback for a missing "
                    "manifest — it would go back to displaying the clock as "
                    "the data's age")
else:
    print("PASS: the freshness stamp reports the DATA's age, not the clock")

# Home must not invent a slate. A missing games.json means the nightly
# hasn't shipped it, which is not the same fact as "no games tonight".
if "def _slate_counts" not in home_src:
    failures.append("Home lost _slate_counts")
elif "if games:" not in home_src:
    failures.append("Home would show a league with zero games as if the slate "
                    "were empty, when the file is simply absent")
else:
    print("PASS: an unshipped slate is omitted, not shown as an empty one")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nAll home-screen checks passed.")
