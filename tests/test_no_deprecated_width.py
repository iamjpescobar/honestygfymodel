"""
No `use_container_width` anywhere in the app.

WHY
---
Streamlit deprecated `use_container_width` in favour of
`width="stretch"` / `width="content"` and printed, on every page that
used it, "will be removed after 2025-12-31". requirements.txt pins
streamlit==1.59.2, which still accepts it, so nothing is broken TODAY —
but the first Streamlit bump that drops it turns eight call sites
(Home, HR Edge, Game Card, app.py's nav, three charts) into TypeErrors
at once, and app.py's nav is on every page. Same shape as the starlette
incident in requirements.txt: a dependency moving under code that did
nothing wrong.

HOW
---
Tokenize-based, so the name in a COMMENT or docstring never counts
(the 08-12 na_rep test passed for the wrong reason by matching a
comment). Only a real NAME token followed by `=` is a call keyword.

Plain script — exits non-zero on failure.
"""
import io
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "app"
BANNED = "use_container_width"


def offenders(source: str):
    hits = []
    toks = [t for t in tokenize.generate_tokens(io.StringIO(source).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                              tokenize.INDENT, tokenize.DEDENT)]
    for i, t in enumerate(toks[:-1]):
        if (t.type == tokenize.NAME and t.string == BANNED
                and toks[i + 1].type == tokenize.OP and toks[i + 1].string == "="):
            hits.append(t.start[0])
    return hits


failures = []

# Self-checks: the detector must see a real keyword and ignore prose,
# otherwise a green run below proves nothing (rule 4).
if offenders("st.button('x', use_container_width=True)\n") != [1]:
    failures.append("detector missed a real use_container_width= keyword")
if offenders("# use_container_width=True\nx = 'use_container_width=True'\n"):
    failures.append("detector counted a comment or string as a call")

files = sorted(ROOT.rglob("*.py"))
if len(files) < 50:
    failures.append(f"only {len(files)} files scanned under app/ — wrong root?")

for f in files:
    for line in offenders(f.read_text(encoding="utf-8")):
        failures.append(f"{f.relative_to(ROOT.parent)}:{line} uses {BANNED}= "
                        f"(use width='stretch' or width='content')")

for msg in failures:
    print("FAIL", msg)
print(f"scanned {len(files)} files — {'FAILING' if failures else 'clean'}")
sys.exit(1 if failures else 0)
