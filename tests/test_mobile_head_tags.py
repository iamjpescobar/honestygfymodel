"""The home-screen tag installer must be inert on failure and idempotent.

It writes into Streamlit's own index.html because Streamlit exposes no API
for <head> tags. That means it touches a file outside this repo, on a path
that a Streamlit upgrade could restructure — so the one thing that must
never happen is it taking the app down. Every failure path here has to be
silent, and repeat runs must not stack duplicate tags into the document.
"""
import base64
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "app" / "app.py").read_text()

# Pull the installer out by text: importing app.py would boot the whole
# Streamlit app, auth screen and all.
_start = SRC.index("def _install_mobile_head_tags")
_end = SRC.index("try:\n    _install_mobile_head_tags()")
_ns = {"Path": Path, "__file__": str(ROOT / "app" / "app.py")}


def _fresh_streamlit():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "static").mkdir()
    (tmp / "static" / "index.html").write_text(
        "<!doctype html><html><head><title>Streamlit</title></head>"
        "<body></body></html>", encoding="utf-8")
    mod = types.ModuleType("streamlit")
    mod.__file__ = str(tmp / "__init__.py")
    sys.modules["streamlit"] = mod
    exec(compile(SRC[_start:_end], "installer", "exec"), _ns)
    return tmp, _ns["_install_mobile_head_tags"]


ICON = ROOT / "app" / "static" / "loscappers-icon-180.png"
assert ICON.exists(), (
    f"{ICON} is missing — the installer silently does nothing without it, so "
    f"the icon would just never appear with no error anywhere")

# --- 1. tags land inside <head> --------------------------------------
tmp, install = _fresh_streamlit()
install()
html = (tmp / "static" / "index.html").read_text()
assert "lc-mobile-tags" in html, "marker missing — nothing was written"
assert html.index("lc-mobile-tags") < html.index("</head>"), (
    "tags must be inside <head>; iOS ignores an apple-touch-icon in the body")
for tag in ("apple-touch-icon", "apple-mobile-web-app-capable",
            "apple-mobile-web-app-status-bar-style", "theme-color",
            "apple-mobile-web-app-title"):
    assert tag in html, f"{tag} missing"
print("PASS: all head tags inserted before </head>")

# --- 2. idempotent ----------------------------------------------------
before = (tmp / "static" / "index.html").read_text()
install()
install()
after = (tmp / "static" / "index.html").read_text()
assert after == before, (
    "index.html changed on a repeat run — the app reruns constantly, so a "
    "non-idempotent patch would grow the document without bound")
# Two apple-touch-icon links are emitted on purpose (a bare one and a
# sizes="180x180" one); what matters is that repeat runs don't add more.
assert after.count("lc-mobile-tags") == 1
print("PASS: repeat runs leave the document untouched")

# --- 3. the icon is a SERVED URL, never a data: URI -------------------
# iOS Safari ignores a data: URI in apple-touch-icon and silently falls
# back to a letter tile — which is exactly what the first version did.
assert 'href="/app/static/loscappers-icon-180.png"' in after, (
    "apple-touch-icon must point at the static-served path")
assert "data:image/png;base64" not in after, (
    "a data: URI is ignored by iOS for apple-touch-icon — the icon has to "
    "be fetchable at a real URL")
print("PASS: icon is referenced by URL, not an inline data URI")

# That URL only resolves if Streamlit's static serving is switched on.
cfg = (ROOT / "app" / ".streamlit" / "config.toml").read_text()
assert "enableStaticServing = true" in cfg, (
    "enableStaticServing is off, so /app/static/... 404s and the icon "
    "silently never loads")
print("PASS: static serving is enabled, so the URL resolves")

# And the manifest must reference a file that exists.
import json
mf = json.loads((ROOT / "app" / "static" / "manifest.json").read_text())
for entry in mf["icons"]:
    src = entry["src"]
    assert src.startswith("/app/static/"), f"{src} won't resolve under Streamlit"
    assert (ROOT / "app" / src.split("/app/", 1)[1]).exists(), (
        f"manifest points at {src}, which does not exist in the repo")
print("PASS: manifest icons resolve to files that exist")

# --- 4. every failure path is silent ---------------------------------
(tmp / "static" / "index.html").unlink()
install()
print("PASS: missing index.html does not raise")

shutil.rmtree(tmp, ignore_errors=True)
install()
print("PASS: missing streamlit static dir does not raise")

# --- 5. app.py actually calls it, and guards the call ----------------
assert "_install_mobile_head_tags()" in SRC
_call = SRC[SRC.index("try:\n    _install_mobile_head_tags()"):]
assert _call.startswith("try:"), "the call must be wrapped in try/except"
assert "except Exception" in _call[:200], (
    "an unguarded call would let a cosmetic icon crash the whole app on boot")
print("PASS: app.py calls the installer inside a try/except")
