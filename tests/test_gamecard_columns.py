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
vuln = vuln[:vuln.index("width=\"stretch\"")]
assert "favor_low=" in vuln and "favor_high=" not in vuln, \
    "allowed contact coloured as if high were good for the pitcher"
print("PASS: HR vulnerability card colours high-as-bad")

# New columns must be styled in the lineup table too.
fav = re.search(r'favor_high=\["SLAM".*?\],', gc, re.S).group(0)
for col in ("Brl/PA", "EV90", "HRWindow%", "HRIntent"):
    assert col in fav, f'"{col}" missing from the lineup favor_high list'
print("PASS: new lineup columns are styled")
