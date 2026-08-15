"""Two rendered tables must never claim the same CSS selectors.

THE BUG THIS PINS. pandas builds Styler selectors from table_uuid:

    #T_{uuid}_row0_col10 { background-image: ... }

render_html_table used f"lc{key}" with key defaulting to "". Every
caller that passed no key emitted CSS under identical selectors, and two
such tables on one page have equal specificity — so the LAST one
rendered won for all of them.

It presented as "the WNBA colours are inverted". They were not inverted.
Each team's grid was wearing the colours computed for a different
team's numbers, which is why no value-based theory fit: 56.7 FG%
rendering poor while 30.0 rendered elite is not an inversion, it is two
tables' CSS colliding. The team table renders inside two nested loops
(per prop tab, per side) under one hardcoded key, and GameCard had nine
keyless tables on a single page.

The grader was never at fault. Given the exact 14-row frame, the Styler
produces elite for the maximum and poor for the minimum — correct at
both ends. Only the selectors collided.
"""
import sys, types, re
import pandas as pd

st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
st.markdown = lambda *a, **k: None
sys.modules["streamlit"] = st
sys.path.insert(0, "app")

from styles.table_style import style_stat_table, render_html_table  # noqa: E402


def uuids(styler, key=""):
    """The set of table_uuids render_html_table hands pandas."""
    captured = []

    def _capture(html, **kw):
        captured.append(html)

    real, st.markdown = st.markdown, _capture
    try:
        render_html_table(styler, key=key)
    finally:
        st.markdown = real
    return set(re.findall(r"#T_(\w+?)_row\d+_col\d+", "".join(captured)))


def _re_ok(uid):
    """CSS identifiers: letters, digits, hyphen, underscore only."""
    return re.fullmatch(r"[A-Za-z0-9_-]+", uid) is not None


def frame(vals):
    return pd.DataFrame({"Player": [f"p{i}" for i in range(len(vals))],
                         "MIN": vals})


a = style_stat_table(frame([28.5, 20.0, 10.2]), favor_high=["MIN"], gradient=True)
b = style_stat_table(frame([5.0, 6.0, 7.0]), favor_high=["MIN"], gradient=True)

# --- 1. NO KEY AT ALL — the default case, and the one that broke ------
ua, ub = uuids(a), uuids(b)
assert ua and ub, "no selectors captured — the parse above is wrong, not the code"
assert not (ua & ub), (
    f"two keyless tables share selectors {ua & ub} — the second one's CSS "
    f"will repaint the first")
print(f"PASS: two keyless tables get distinct uuids ({ua.pop()} vs {ub.pop()})")

# --- 2. THE SAME KEY TWICE ---------------------------------------------
#
# The WNBA call site passed one hardcoded key from inside two nested
# loops. A caller reusing a key must still get unique selectors —
# uniqueness cannot depend on every future caller inventing a new name.
ua, ub = uuids(a, key="wnba_636"), uuids(b, key="wnba_636")
assert not (ua & ub), f"the same key twice collided: {ua & ub}"
print("PASS: the same key rendered twice still yields distinct uuids")

# --- 3. The key still appears, for readability -------------------------
assert any("wnba_636" in u for u in ub), (
    "the key vanished from the uuid — selectors become unreadable in devtools")
print("PASS: the key survives in the uuid as a label")

# --- 4. THE GRADER ITSELF IS CORRECT -----------------------------------
#
# Kept as the control. If this ever goes red the diagnosis above was
# wrong and the fix is in the wrong file.
css = a.to_html(table_uuid="ctl").split("</style>")[0]
blocks = [x for x in css.split("}") if "{" in x]


def fill(row, col):
    for blk in blocks:
        head, body = blk.split("{", 1)
        if f"#T_ctl_row{row}_col{col}" in head:
            m = re.search(r"rgba\((\d+,\d+,\d+)", body)
            if m:
                return m.group(1)
    return None


ELITE, POOR = "59,184,255", "214,48,74"
assert fill(0, 1) == ELITE, f"max value did not grade elite: {fill(0, 1)}"
assert fill(2, 1) == POOR, f"min value did not grade poor: {fill(2, 1)}"
print("PASS: the grader puts the maximum at elite and the minimum at poor")


# --- 5. A KEY WITH CSS-UNSAFE CHARACTERS MUST NOT KILL THE STYLING ---
#
# THE BUG THIS SHIPPED WITH. pandas puts table_uuid straight into the
# selector: #T_{uuid}_row0_col4. A key of "wnba_Pts+Reb_away" yields
# #T_lcwnba_Pts+Reb_away_7_row0_col4, and "+" is not valid in a CSS
# identifier — the browser discards the WHOLE RULE and the table renders
# with no colour at all. Silent, total, and it looks like a data problem.
#
# The WNBA tab labels are Points, Rebounds, Assists, Threes, PRA,
# Pts+Reb, Pts+Ast, Reb+Ast, Stocks, Volume. The three that lost colour
# were exactly the three containing a "+".
for bad in ("wnba_Pts+Reb_away", "a b", "x/y", "p%q", "n(1)", "d.e"):
    got = uuids(a, key=bad)
    assert got, f"no selectors emitted for key {bad!r}"
    for u in got:
        assert _re_ok(u), (
            f"key {bad!r} produced uuid {u!r} — a CSS identifier may only "
            f"contain letters, digits, hyphen and underscore, and an "
            f"invalid one silently voids every rule for that table")
print("PASS: unsafe key characters are sanitised, selectors stay valid")

# --- 6. Sanitising must not reintroduce collisions -------------------
#
# "Pts+Reb" and "Pts Reb" both sanitise to "Pts_Reb". The counter is
# what keeps them apart — this is the case that proves sanitising did
# not undo case 1.
u1, u2 = uuids(a, key="Pts+Reb"), uuids(b, key="Pts Reb")
assert not (u1 & u2), f"two keys that sanitise alike collided: {u1 & u2}"
print("PASS: keys that sanitise to the same string still get distinct uuids")


# --- 7. A WIDE TABLE GETS TIGHTER CELLS, AT ANY SCREEN WIDTH ---------
#
# The stylesheet's only density rule was @media (max-width: 900px), so a
# twenty-five-column lineup table on a wide tablet got the same roomy
# padding as a five-column reference table and ran off the right edge
# with columns to spare. It read as CROPPED rather than scrollable.
#
# Density has to follow the TABLE's width, not the viewport's, and CSS
# cannot count columns — so render_html_table adds the class.
_seen = []
_real_md = st.markdown
st.markdown = lambda h, **kw: _seen.append(h)
try:
    for _n in (20, 5):
        _df = pd.DataFrame({f"c{_i}": [1.0] for _i in range(_n)})
        render_html_table(style_stat_table(_df, favor_high=[]), key=f"k{_n}")
finally:
    st.markdown = _real_md

_wraps = [h for h in _seen if 'class="lc-tbl-wrap' in h]
assert len(_wraps) == 2, len(_wraps)
assert "lc-tbl-dense" in _wraps[0], (
    "a 20-column table did not get the dense class — it will overflow "
    "with columns to spare")
assert "lc-tbl-dense" not in _wraps[1], (
    "a 5-column table was made dense; tight padding on a narrow table "
    "buys nothing and costs legibility")
print("PASS: 20 columns render dense, 5 columns stay roomy")

# --- 8. The dense rule exists in the stylesheet ----------------------
_css = open("app/styles/table_style.py", encoding="utf-8").read()
assert ".lc-tbl-wrap.lc-tbl-dense th" in _css, "the dense class has no CSS"
assert "background-attachment: local" in _css, (
    "the scroll-edge shading is gone — a table that continues past the "
    "viewport looks cropped rather than scrollable")
print("PASS: dense padding and the scroll-edge hint are both in the CSS")
