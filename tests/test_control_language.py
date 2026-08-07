"""Every control on the site looks like every other control.

WHY THIS EXISTS

The pill treatment — quiet ghost option, filled accent when selected —
was written scoped to the league nav, where it obviously worked. Every
other segmented control and pill group on the site kept the older
bordered-grey style, so the SAME widget looked like two different things
depending which page you were on: Bats and Window on the Game Card, the
form window on WNBA, the prop tabs, every board's filters.

That is not a taste problem. A control's whole job is to answer "which
one is on", and when the answer is styled differently in two places the
reader has to re-learn the answer on every page.

The rule now lives unscoped in kc_theme, and the nav keeps only what is
genuinely nav-specific. This file pins that arrangement, because the
easy regression is someone adding a second scoped copy for one board and
starting the drift again.
"""
import os
import re
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

_stub = types.ModuleType("streamlit")
_out = []
_stub.markdown = lambda s, **k: _out.append(s)
_stub.session_state = {}
sys.modules["streamlit"] = _stub

import styles.kc_theme as kc  # noqa: E402
kc.inject_kc_theme()
CSS = "\n".join(_out)

failures = []


def check(label, ok):
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


BASE = CSS
# Selectors span several lines (comma-separated); collapse whitespace so
# a two-line selector matches as one string.
FLAT = re.sub(r"\s+", " ", BASE)


def rule_bodies(selector):
    """Every rule body in the sheet whose selector contains `selector`.

    Returns a list, not one match, on purpose. A selector legitimately
    appears more than once — the base rule plus a media-query override —
    and an earlier version of this test read whichever came first and
    reported the base rule missing when it was fine. Asking "does ANY
    rule for this selector set the pill radius" is the property; "does
    the first one" is an accident of ordering.
    """
    flat_sel = re.sub(r"\s+", " ", selector)
    return [m.group(1) for m in
            re.finditer(re.escape(flat_sel) + r"\s*\{([^}]*)\}", FLAT)]


def declares(selector, needle):
    return any(needle in body for body in rule_bodies(selector))


# ---- 1. the f-strings actually resolved -----------------------------
# Rule 3: the CSS blocks are f-strings and every literal brace must be
# doubled. A missed one either throws at import or leaks a placeholder
# into the page, and the page is where you'd notice it.
check("CSS was built", len(CSS) > 5000)
check("no unresolved {COLOR[...]} placeholder reached the page",
      "{COLOR" not in CSS)
check("no doubled braces leaked through", "{{" not in CSS)


# ---- 2. the control language is GLOBAL, not scoped -------------------
_group_rules = re.findall(
    r'([^{}]*div\[data-testid="stButtonGroup"\][^{}]*)\{', FLAT)
_unscoped = [r for r in _group_rules if "st-key-" not in r]
check(f"an unscoped rule styles every button group ({len(_unscoped)} found)",
      bool(_unscoped))

# The selected state must be defined once, globally — that is the state
# that carries the meaning.
check("the checked state is styled unscoped",
      any('aria-checked="true"' in r and "st-key-" not in r
          for r in _group_rules))

# Scoped overrides are allowed, but only for LAYOUT, never for the
# three colours that say what state a control is in. A per-board colour
# override is exactly how the drift started.
_scoped = [r for r in _group_rules if "st-key-" in r]
for r in _scoped:
    _body = FLAT[FLAT.index(r) + len(r):]
    _body = _body[:_body.index("}")]
    check(f"scoped rule sets no background colour: {r.strip()[:52]}",
          "background-color:" not in _body)


# ---- 3. plain buttons speak the same language ------------------------
def rule_body(selector):
    i = CSS.find(selector)
    if i < 0:
        return ""
    j = CSS.index("{", i)
    return CSS[j:CSS.index("}", j)]


_BTN = ".stButton > button, .stDownloadButton > button"
_GRP = 'div[data-testid="stButtonGroup"] button'
check("plain buttons use the pill radius",
      declares(_BTN, "border-radius: 999px"))
check("pill options use the pill radius",
      declares(_GRP, "border-radius: 999px"))
check("both default to transparent, not a filled grey slab",
      declares(_BTN, "background-color: transparent")
      and declares(_GRP, "background-color: transparent"))
check("a primary button fills with the same accent as a checked pill",
      declares('.stButton > button[kind="primary"]', kc.COLOR["stat_high"]))


# ---- 4. touch targets never shrink on small screens ------------------
# The mobile block used to SET stButtonGroup to 38px, which made the
# targets smaller on the one device where they matter most. Assert every
# min-height in the CSS clears 40px so that inversion cannot come back.
_heights = [int(m) for m in re.findall(r"min-height:\s*(\d+)px", CSS)]
_small = [h for h in _heights if h < 40]
check(f"no control is under 40px tall (found: {_small or 'none'})", not _small)


# ---- 5. every card selector is flat, wherever it is defined ----------
# THE FAILURE THIS CATCHES. Cards are drawn by three different
# selectors: `st-key-card_` (container cards, MLB views), `.pf-card`
# (raw HTML via card_open(), which is what KBO and NPB use), and a
# local override in Home.py. Flattening the first one left the other
# two in the previous generation of the design — so the international
# boards and the home page were the only pages still drawing panels,
# and nothing in the code said the three had to agree.
#
# They do have to agree: it is the same object to a reader. This
# asserts none of them paints a fill or a shadow, no matter which file
# defines it.
_HOME = open(os.path.join(ROOT, "app", "views", "Home.py"),
             encoding="utf-8").read()
_ALL_CSS = FLAT + " " + re.sub(r"\s+", " ", _HOME)

for _sel in ('div[class*="st-key-card_"]', ".pf-card {",
             "[class*='st-key-card_home_'] {"):
    _i = _ALL_CSS.find(_sel)
    check(f"{_sel} is defined somewhere", _i >= 0)
    if _i < 0:
        continue
    _body = _ALL_CSS[_ALL_CSS.index("{", _i):]
    _body = _body[:_body.index("}")]
    check(f"{_sel} paints no gradient", "linear-gradient" not in _body)
    check(f"{_sel} casts no shadow",
          "box-shadow: 0" not in _body and "box-shadow:0" not in _body)


# ---- 6. expanders speak the control language ------------------------
_exp = rule_bodies('div[data-testid="stExpander"]')
check("the expander shell is transparent",
      any("background: transparent" in b for b in _exp))
check("expander headers get a real touch target",
      declares('div[data-testid="stExpander"] summary, '
               'div[data-testid="stExpander"] details > summary',
               "min-height: 44px"))
# Open state must be visible. It keys off details[open], the browser's
# own flag, so it cannot drift with a Streamlit release the way an
# internal class name would (rule 9).
check("an open expander is marked, and by a standard flag not an "
      "internal class",
      "details[open]" in FLAT)

print("FAILING:" + (" " + ", ".join(failures) if failures else " none"))
sys.exit(1 if failures else 0)
