"""
Diagnostic script — loads every page headlessly (no browser needed) and
prints any real Python exception each one hits. Run this from inside
the app/ folder:

    python test_pages.py

This won't catch things that only show up with real user interaction
(like clicking a specific dropdown value), but it will catch import
errors, crashes on initial load, and anything broken at the top level
of a page — which covers most "every page is an error" situations.
"""
import sys
import glob
import py_compile

from streamlit.testing.v1 import AppTest

PAGES = sorted(glob.glob("pages/*.py"))


def test_page(path, as_admin=True):
    # AppTest does NOT reliably catch compile-time SyntaxErrors (confirmed
    # in practice — a broken f-string once printed "OK" here despite a
    # visible compilation traceback in the log). Check compilation
    # explicitly first so that class of bug can never slip through again.
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"  SYNTAX ERROR: {e}")
        return False

    at = AppTest.from_file(path)
    at.session_state["authentication_status"] = True
    at.session_state["username"] = "admin" if as_admin else "demo_subscriber"
    at.session_state["name"] = "Admin" if as_admin else "Demo Subscriber"
    at.session_state["lc_role"] = "admin" if as_admin else "subscriber"
    try:
        at.run(timeout=60)
    except Exception as e:
        print(f"  RUNNER CRASHED: {e}")
        return False

    if at.exception:
        for e in at.exception:
            print(f"  EXCEPTION: {e}")
        return False

    print("  OK — no exceptions")
    return True


if __name__ == "__main__":
    print(f"Testing {len(PAGES)} pages...\n")
    results = {}
    for path in PAGES:
        print(f"--- {path} ---")
        results[path] = test_page(path)
        print()

    print("=" * 50)
    failed = [p for p, ok in results.items() if not ok]
    if failed:
        print(f"{len(failed)} page(s) with errors:")
        for p in failed:
            print(f"  - {p}")
        sys.exit(1)
    else:
        print("All pages loaded cleanly.")
