#!/usr/bin/env python3
"""Put app/ on sys.path so kbo_precompute can import the weather engine.

Verifies by RUNNING the import the way the workflow does, not by
grepping — the bug this fixes shipped past a compile check and a green
test suite because nothing ever executed main().
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
K = ROOT / "kbo_precompute.py"
s = K.read_text()

if "sys.path.insert" in s:
    sys.exit("Already has a sys.path insert - inspect by hand, nothing written.")

# The import currently sits inside main(), which is where it exploded.
# Hoist it to module scope beside a path insert, the same shape
# wnba_precompute.py uses, so the failure would have been at import
# time and impossible to miss rather than 800 lines into a run.
OLD_INLINE = ("    from engines.intl_weather import forecast as _wx, "
              "summarize as _wxsum\n")
if OLD_INLINE not in s:
    sys.exit("ANCHOR NOT FOUND (inline weather import) - nothing written.")
s = s.replace(OLD_INLINE, "", 1)

anchor = "OUT = Path(\"build_data\") / \"data\" / \"kbo\""
if anchor not in s:
    sys.exit("ANCHOR NOT FOUND (OUT) - nothing written.")

block = '''# app/ is not on sys.path for a script run from the repo root, and this
# file had never needed it until the weather engine arrived. The import
# was inside main(), so it survived a compile check AND a green test
# suite and only failed 800 lines into a live run — after the fetch, in
# a step nothing else could see. Hoisted here beside the path insert,
# the same shape wnba_precompute.py uses, so a bad import is now an
# immediate ImportError instead of a late one.
sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from engines.intl_weather import (  # noqa: E402
    forecast as _wx,
    summarize as _wxsum,
)

'''
s = s.replace(anchor, block + anchor, 1)

if "import sys" not in s.split("def ")[0]:
    s = s.replace("from pathlib import Path", "import sys\nfrom pathlib import Path", 1)

K.write_text(s)
print("patched: kbo_precompute sys.path + hoisted weather import\n")

# RUN the import the way the workflow does: python from the repo root.
r = subprocess.run([sys.executable, "-c",
                    "import kbo_precompute as k; "
                    "print('imported OK'); "
                    "print('has _wx:', hasattr(k, '_wx')); "
                    "print('has _wxsum:', hasattr(k, '_wxsum'))"],
                   cwd=str(ROOT), capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip()[-600:])
ok = "imported OK" in r.stdout and "has _wx: True" in r.stdout
print("\n  " + ("OK   kbo_precompute imports from the repo root"
                if ok else "FAIL kbo_precompute still cannot import"))
print("done" if ok else "INCOMPLETE - tell Claude")
