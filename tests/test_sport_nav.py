"""
A sport's page nav (10-24) — one wrapped bar of pills, every label on one
line. It was a column per page (st.columns(len(titles))), which crushed
NHL's 16 labels into letter-per-line slivers on an iPad (Izzy's
screenshot: "this format here bother me make it beautiful").

Plain script — exits non-zero on failure. Reads app.py and the theme.
Measured in a headless browser before writing this: Streamlit's pills
sit in an INNER flex row that is a one-line scroller (display flex,
nowrap, overflow-x auto); that row is the one the theme wraps.

Negative controls, confirmed red by exit code when written (rule 4):
  - the nav put back to one st.columns per page
    -> "the page nav is one pill group, not a column per page" fails
  - the wrap rule aimed at the outer group instead of the pill row
    -> "the pill row itself wraps, labels stay on one line" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
theme = (ROOT / "app" / "styles" / "kc_theme.py").read_text(encoding="utf-8")
check("the page nav is one pill group, not a column per page",
      'st.pills("Pages", _titles' in app and "st.columns(len(_titles))" not in app
      and 'key=f"{_key}_pills_{_active}"' in app)
i = theme.find('div[class*="st-key-lc_sub_"] div[data-testid="stButtonGroup"] div:has(> button)')
blk = theme[i:theme.find("}}", i)] if i >= 0 else ""
check("the pill row itself wraps, labels stay on one line",
      "flex-wrap: wrap !important" in blk and "overflow: visible !important" in blk
      and 'div[class*="st-key-lc_sub_"] div[data-testid="stButtonGroup"] button' in theme
      and "white-space: nowrap !important" in theme)
check("UFC is in the sport switcher", '"NFL", "UFC"]' in theme)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall sport nav checks passed")
