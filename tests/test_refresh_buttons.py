"""
Every page in the nav has a refresh (10-22) — the "Sync latest" button
(engines/live_sync.sync_latest_button) right under its header, so a page
opened before the nightly finished can pull the new build without a
redeploy.

Plain script — exits non-zero on failure. Reads app/app.py's nav and the
view files' syntax trees. No network.

Negative control, confirmed red by exit code when written (rule 4):
  - the button call removed from NBA_First_Basket.py
    -> "NBA_First_Basket.py has a refresh" fails
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
# Pages with their own refresh, or nothing a data build changes
OWN = {"Live.py": "its own Refresh (live scores, every 60 s)",
       "Bet_Log.py": "your own saved bets, not the data build",
       "Home.py": "the landing page", "0_Debug_Roster.py": "admin debug",
       "Calibration.py": "admin, grades on demand"}

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


nav = sorted(set(re.findall(r'"views/([A-Za-z0-9_]+\.py)"', (APP / "app.py").read_text())))
check("the nav lists pages", len(nav) > 20)
for v in nav:
    if v in OWN:
        continue
    src = (APP / "views" / v).read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "sync_latest_button"]
    imported = any(isinstance(n, ast.ImportFrom) and n.module == "engines.live_sync"
                   and any(a.name == "sync_latest_button" for a in n.names)
                   for n in ast.walk(tree))
    keys = [kw.value.value for c in calls for kw in c.keywords
            if kw.arg == "key" and isinstance(kw.value, ast.Constant)]
    check(f"{v} has a refresh", bool(calls) and imported and bool(keys))

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nevery page has a refresh")
