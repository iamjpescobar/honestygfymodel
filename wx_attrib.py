#!/usr/bin/env python3
"""Render the Open-Meteo attribution the CC BY 4.0 licence requires."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
V = ROOT / "app/views/KBO.py"
s = V.read_text()

OLD = ('    st.caption(f"Slate data as of {generated_at} KST \\u2014 '
       'refreshed by the nightly pipeline.")')
NEW = ('''    st.caption(f"Slate data as of {generated_at} KST \\u2014 '''
       '''refreshed by the nightly pipeline.")

    # LICENCE CONDITION, not decoration.
    #
    # Temperature and the heat-cancellation flag come from Open-Meteo,
    # whose data is CC BY 4.0. That licence requires attribution with a
    # link wherever the data is displayed. It is rendered here rather
    # than per-game so it appears once even on a slate where no figure
    # happens to print, and it reads from the engine constant so it
    # cannot drift from the source it credits.
    #
    # Removing this is a licence violation. If the weather source ever
    # changes, change ATTRIBUTION in engines/intl_weather.py, not here.
    st.markdown(
        f'<div style="font-size:var(--lc-text-tiny); '
        f'color:{COLOR["text_faint"]}; margin-top:var(--lc-space-hair);">'
        f'{_WX_ATTRIBUTION}</div>',
        unsafe_allow_html=True,
    )''')

if "_WX_ATTRIBUTION" in s:
    sys.exit("Already applied - nothing written.")
if OLD not in s:
    sys.exit("ANCHOR NOT FOUND (slate caption) - nothing written.")
if s.count(OLD) != 1:
    sys.exit("ANCHOR NOT UNIQUE - nothing written.")
s = s.replace(OLD, NEW, 1)

# Import beside the other engine imports.
imp = "from engines.intl_weather import ATTRIBUTION as _WX_ATTRIBUTION\n"
lines = s.split("\n")
last = max(i for i, ln in enumerate(lines) if ln.startswith("from engines"))
lines.insert(last + 1, imp.rstrip("\n"))
s = "\n".join(lines)
V.write_text(s)

_v = V.read_text()
checks = {
    "import added": "from engines.intl_weather import ATTRIBUTION" in _v,
    "rendered once": _v.count("_WX_ATTRIBUTION}</div>") == 1,
    "links to open-meteo via engine": "ATTRIBUTION as _WX_ATTRIBUTION" in _v,
}
try:
    import ast
    ast.parse(_v)
    checks["KBO.py parses"] = True
except SyntaxError as exc:
    checks["KBO.py parses"] = False
    print(f"  !! {exc}")

print("patched: KBO.py weather attribution\n")
for k, ok in checks.items():
    print(f"  {'OK  ' if ok else 'FAIL'} {k}")
print("done" if all(checks.values()) else "INCOMPLETE - tell Claude")
