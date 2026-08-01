"""Column wiring for the Game Card tables.

Streamlit views can't be imported headlessly, so this reads the source
and asserts the contracts that break silently at runtime:
  - every column pulls a key the engine actually produces
  - every sort option has a handler (a missing one is a KeyError crash)
  - the pitcher card reads the "Allowed" aliases, not batter-side names
"""
import re, sys

gc = open("app/views/GameCard.py").read()
eng = open("app/engines/statcast_engine.py").read()

# Keys the batted-ball bundle actually returns.
ret = eng[eng.index('        "Brl %": round(barrels'):]
produced = set(re.findall(r'"([A-Za-z0-9/ %]+)":', ret[:ret.index("}")]))
produced |= set(re.findall(r'"([A-Za-z0-9/ %]+)":',
                eng[eng.index('"SweetSpot %": 0.0'):eng.index('"HRIntent": None,') + 20]))
produced |= {a for _, a in re.findall(r'\("([^"]+)", "([^"]+)"\)', eng)}
# Keys assigned directly rather than via the alias tuples, e.g.
# metrics["xHR Allowed"] = ...
produced |= set(re.findall(r'metrics\["([^"]+)"\]\s*=', eng))

NEW_BATTER = ["Brl/PA", "EV90", "MaxEV", "HRWindow %", "HRIntent"]
for key in NEW_BATTER:
    assert f'profile.get("{key}")' in gc, f'batter table never reads "{key}"'
    assert key in produced, f'"{key}" is read by the view but never produced'
print(f"PASS: batter table reads {len(NEW_BATTER)} new keys, all engine-produced")

# Sort dropdown vs handler map — a mismatch is a hard KeyError on click.
opts = re.findall(r'"([^"]+)"', re.search(r'"Sort by", \[(.*?)\],\s*\n\s*key=', gc, re.S).group(1))
keymap = re.search(r'sort_key_map = \{(.*?)\n                \}', gc, re.S).group(1)
handlers = set(re.findall(r'"([^"]+)":', keymap))
missing = [o for o in opts if o not in handlers]
assert not missing, f"sort options with no handler (KeyError on select): {missing}"
print(f"PASS: all {len(opts)} sort options have handlers")

for col in ("Brl/PA", "EV90", "HRWindow%", "HRIntent"):
    assert col in opts, f'"{col}" not sortable'
print("PASS: the new HR axes are sortable")

# None-safety: these metrics are None (not 0) for unmeasurable bats, and
# None breaks sorted(). Every new handler must coalesce.
for col in ("Brl/PA", "EV90", "HRWindow %", "HRIntent"):
    h = re.search(r'"[^"]*":\s*lambda r: windowed_profile_cache\[r\["name"\]\]\.get\("'
                  + re.escape(col) + r'"\)([^,\n]*)', keymap)
    assert h and "or 0" in h.group(1), f'"{col}" sort handler lacks a None guard'
print("PASS: every new sort handler guards against None")

# Pitcher card must read the Allowed aliases, never the batter-side keys.
card = gc[gc.index("HR VULNERABILITY (ALLOWED)"):]
card = card[:card.index("st.caption")]
for key in ("Brl % Allowed", "HH % Allowed", "FB % Allowed",
            "HRWindow % Allowed", "EV90 Allowed", "xHR Allowed"):
    assert f'pitcher_data.get("{key}")' in gc, f'pitcher card never reads "{key}"'
    assert key in produced, f'"{key}" read but never aliased in the engine'
print("PASS: pitcher card reads 6 Allowed aliases, all engine-produced")

# Allowed metrics are BAD when high — the card must be favor_low.
vuln = gc[gc.index("HR VULNERABILITY (ALLOWED)"):]
# Terminator is the render_html_table key, not width="stretch": this card
# moved off st.dataframe so its label column could be sticky. Slicing on a
# marker the block no longer contains ran past into the lineup table and
# picked up ITS favor_high, which is a false alarm, not a real regression.
vuln = vuln[:vuln.index('key="hr_vuln"')]
assert "favor_low=" in vuln and "favor_high=" not in vuln, \
    "allowed contact coloured as if high were good for the pitcher"
print("PASS: HR vulnerability card colours high-as-bad")

# New columns must be styled in the lineup table too.
fav = re.search(r'favor_high=\["SLAM".*?\],', gc, re.S).group(0)
for col in ("Brl/PA", "EV90", "HRWindow%", "HRIntent"):
    assert col in fav, f'"{col}" missing from the lineup favor_high list'
print("PASS: new lineup columns are styled")

# --- Formatting -------------------------------------------------------
# style_stat_table applies a global .format(precision=2). Any column
# without an explicit format string falls through to it and renders with
# the wrong number of decimals next to its neighbours — 104.00 beside
# 104.0. These assert every displayed numeric column is covered.
lineup_fmt = re.search(r'styled = styled\.format\(\{(.*?)\}, na_rep=', gc, re.S).group(1)
formatted = set(re.findall(r'"([^"]+)":', lineup_fmt))

row = re.search(r'return \{\s*\n\s*"Player".*?\n\s{20}\}', gc, re.S).group(0)
declared = re.findall(r'"([^"]+)":', row)
NON_NUMERIC = {"Player", "Bats", "Matchup", "Edge", "EdgeLabel", "EdgeTier", "Confidence"}
missing = [c for c in declared if c not in NON_NUMERIC and c not in formatted]
assert not missing, f"numeric lineup columns with no format string: {missing}"
print(f"PASS: all {len(formatted)} numeric lineup columns have explicit formats")

for col in ("Brl/PA", "EV90", "MaxEV", "HRWindow%", "HRIntent"):
    assert col in formatted, f'"{col}" would render at the global precision'
print("PASS: the five new batter columns are formatted like their neighbours")

# Scope the search to the vulnerability card. The targets tables now
# also use gradient=True).format(...), so an unanchored search matched
# the first one instead and reported the wrong block as unformatted.
_vuln_seg = gc[gc.index("HR VULNERABILITY (ALLOWED)"):]
vuln_fmt = re.search(r'gradient=True\)\.format\(\{(.*?)\}, na_rep=', _vuln_seg, re.S).group(1)
vuln_formatted = set(re.findall(r'"([^"]+)":', vuln_fmt))
vuln_cols = set(re.findall(r'"([^"]+)": pitcher_data\.get', gc))
missing_v = [c for c in vuln_cols if c not in vuln_formatted]
assert not missing_v, f"vulnerability columns with no format: {missing_v}"
print(f"PASS: all {len(vuln_cols)} HR vulnerability columns are formatted")

assert '"xHR Gap": "{:+.1f}"' in gc, "xHR Gap should show its sign — the sign IS the signal"
print("PASS: xHR Gap renders signed (+/-), since direction is the whole read")

# --- HR Edge Board view ------------------------------------------------
# Same class of silent breakage as the Game Card: a view that can't be
# imported headlessly, where a bad theme key or an unformatted column
# only shows up when a user opens the page.
import sys as _sys, types as _types
_st = _types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
_st.cache_data = _c
_sys.modules.setdefault("streamlit", _st)
_sys.path.insert(0, "app")
from styles.kc_theme import COLOR as _COLOR

hb = open("app/views/HR_Edge_Board.py").read()

bad_keys = [k for k in set(re.findall(r'COLOR\["(\w+)"\]', hb)) if k not in _COLOR]
assert not bad_keys, f"HR Edge Board uses nonexistent theme keys (KeyError on load): {bad_keys}"
print("PASS: HR Edge Board theme keys all resolve")

hb_fmt = re.search(r'\)\.format\(\{(.*?)\}, na_rep=', hb, re.S).group(1)
hb_formatted = set(re.findall(r'"([^"]+)":', hb_fmt))
hb_cols = set(re.findall(r'"([^"]+)": r\.get', hb))
NUMERIC = {"HR Edge", "HR Score", "Matchup", "Context"}
missing_hb = [c for c in NUMERIC if c not in hb_formatted]
assert not missing_hb, f"unformatted numeric columns: {missing_hb}"
print(f"PASS: all {len(NUMERIC)} numeric HR Edge Board columns are formatted")

assert '"Matchup": "{:+.1f}"' in hb and '"Context": "{:+.1f}"' in hb, \
    "adjustment columns should be signed — direction is the read"
print("PASS: Matchup and Context render signed")

# The page must be reachable, or it's dead code.
app = open("app/app.py").read()
assert '"views/HR_Edge_Board.py"' in app, "HR Edge Board is not registered in app.py"
print("PASS: HR Edge Board is registered in the nav")

# --- unmeasurable scores must read N/A, never 0 -----------------------
# When Baseball Savant is unreachable, every HR/Hit/K Score is None. The
# targets tables were passing those through _score_num, which substitutes
# 0 — so a hitter nobody could measure rendered as the worst on the board,
# while the warning banner directly above promised "N/A" and the Stack
# Pick card beside them correctly showed N/A. Three parts of one screen
# disagreeing, with the wrong one being the most prominent.
tt = gc[gc.index("def _targets_table"):]
tt = tt[:tt.index("top_row1, top_row2")]
assert "_score_num(" not in tt, (
    "_targets_table must not substitute 0 — its own docstring says that's "
    "only safe when N/A text appears alongside, and here the number IS the "
    "only signal")
assert "label: r[sort_field]" in tt, "None must survive into the frame as NaN"
print("PASS: targets tables keep None rather than substituting 0")

for lbl in ("HR Score", "Hit Score", "K Score"):
    # These moved from a literal "{:.0f}" to score_bar(), which draws the
    # value as a filled bar. The REQUIREMENT is unchanged and is what
    # this checks: an unmeasurable score must render as N/A, never as an
    # empty bar — a zero-width bar reads as a real score of zero, which
    # is the worst possible rendering of "we don't know".
    assert f'"{lbl}": score_bar(' in gc, \
        f"{lbl} table no longer renders its score as a bar"
    assert f'{{"{lbl}": score_bar' in gc and 'na_rep="N/A"' in gc, \
        f"{lbl} table doesn't render NaN as N/A"
print("PASS: all three targets tables render unmeasurable scores as N/A")

# _score_num itself is still fine where a real numeric is required
# (progress bars), so long as N/A text sits beside it.
assert "def _score_num" in gc and "def _score_display" in gc
print("PASS: _score_num retained for genuinely numeric contexts")
