"""NFL and NHL are wired end to end — and say so consistently.

The site has already shipped a switcher caption that contradicted the
code twenty lines above it. This pins the four places that must agree
when a league goes live: the nav (app.py), the switcher caption, the
pages themselves (no coming-soon stub left behind), and the nightly
(a fetch step AND an archive-verifier entry — a fetch nobody verifies
is how WNBA once vanished from production without a red run).
"""
import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


app_src = (ROOT / "app" / "app.py").read_text()
tree = ast.parse(app_src)
subpages = None
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SPORT_SUBPAGES"
                                            for t in node.targets):
        subpages = ast.literal_eval(node.value)
check("SPORT_SUBPAGES is a literal", isinstance(subpages, dict))
subpages = subpages or {}
for lg, want in (("NFL", {"views/NFL.py", "views/NFL_Mismatch.py",
                          "views/NFL_Props.py", "views/NFL_Projections.py"}),
                 ("NHL", {"views/NHL.py", "views/NHL_Crease.py", "views/NHL_Shots.py"})):
    paths = {p for _t, p in subpages.get(lg, [])}
    check(f"{lg} has its three pages in the nav", paths == want)
    for p in paths:
        check(f"{p} exists", (ROOT / "app" / p).exists())

theme = (ROOT / "app" / "styles" / "kc_theme.py").read_text()
cap = re.search(r"f'(MLB[^']*live[^']*)</div>'", theme)
check("switcher caption found", bool(cap))
if cap:
    live, _, soon = cap.group(1).partition("live")
    check("caption lists NFL and NHL as live", "NFL" in live and "NHL" in live)
    check("caption no longer lists NFL/NHL as soon", "NFL" not in soon and "NHL" not in soon)
    check("caption still lists NBA as soon", "NBA" in soon)

for v in ("NFL", "NFL_Mismatch", "NFL_Props", "NFL_Projections", "NHL",
          "NHL_Crease", "NHL_Shots"):
    code = "\n".join(l.split("#")[0] for l in
                     (ROOT / "app" / "views" / f"{v}.py").read_text().splitlines())
    check(f"{v} is not a coming-soon stub", "coming_soon_page(" not in code)
    # st.stop() inside a view ends the WHOLE app run, so the right-hand
    # sidebar (account card, Sign out) rendered after it never appears.
    check(f"{v} never calls st.stop()", "st.stop(" not in code)
# EVERY DENSE BOARD EXPLAINS ITSELF. These pages carry ranks running in
# two directions, rates per attempt, and a probability resting on a named
# assumption. A reader who cannot tell those apart either misreads the
# board or ignores it.
for v in ("NFL", "NFL_Mismatch", "NFL_Props", "NFL_Projections",
          "NHL_Crease", "NHL_Shots"):
    check(f"{v} carries a how-to-read panel",
          "how_to_read(" in (ROOT / "app" / "views" / f"{v}.py").read_text())

# The live-overlay rule lives in the ENGINE, where it can be tested. It
# was one untestable line in the view, and it was wrong.
nfl_view = (ROOT / "app" / "views" / "NFL.py").read_text()
check("NFL view uses nfl_week.live_days", "live_days(games" in nfl_view)

# The projection log is a record for grading. A log the nightly writes
# and never commits is a log that does not exist.
_wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text()
check("the nightly commits the NFL projection log",
      "data/nfl/projections" in _wf and "git add data/nfl/projections" in _wf)

check("NBA is still the honest coming-soon page",
      "coming_soon_page(" in (ROOT / "app" / "views" / "NBA.py").read_text())

wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text()
steps = yaml.safe_load(wf)["jobs"]["build-data"]["steps"]
runs = [s.get("run", "") for s in steps]
for script in ("nfl_precompute.py", "nhl_precompute.py"):
    hit = [r for r in runs if script in r]
    check(f"nightly runs {script}", bool(hit))
    check(f"{script} step is tolerant (one league down keeps the rest)",
          bool(hit) and "|| echo" in hit[0])
    idx = next((i for i, r in enumerate(runs) if script in r), 99)
    pub = next((i for i, s in enumerate(steps) if "Fetch and package" in s.get("name", "")), -1)
    check(f"{script} runs BEFORE the archive is packaged", idx < pub)
check("archive verifier expects data/nfl/games.json", '"data/nfl/games.json"' in wf)
check("archive verifier expects data/nhl/games.json", '"data/nhl/games.json"' in wf)

probe = yaml.safe_load((ROOT / ".github" / "workflows" / "nfl-nhl-probe.yml").read_text())
_on = probe.get("on", probe.get(True))
check("probe workflow is manual-only", set(_on) == {"workflow_dispatch"})
check("probe script exists", (ROOT / "nfl_nhl_probe.py").exists())

if failures:
    print(f"\n{len(failures)} FAILED")
    raise SystemExit(1)
print("\nNFL/NHL wiring checks passed.")
