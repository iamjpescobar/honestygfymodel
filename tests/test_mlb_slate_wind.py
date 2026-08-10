"""The MLB slate resolves wind in BOTH formats, not just one.

WHY THIS EXISTS

There are two wind engines in this repo and they are not
interchangeable:

    engines/wind_engine.wind_hr_adj          compass     "12 mph SW"
        Resolves against the park's real CF bearing. What the National
        Weather Service gives.

    engines/player_of_the_day._wind_hr_adj   field-relative
        "8 mph Out To CF" — MLB's own format, already stated relative to
        the field.

`calibration_picks._write_mlb_slate()` called only the FIRST, on a
string that is usually the SECOND's. And `_parse_wind` returns None for
field-relative input ON PURPOSE — its docstring says so and names the
other function — so the failure was completely silent: `wind_adj` 0,
`wind_note` None, no exception, no log line, on exactly the runs (5 and
7 PM ET) where MLB has actually posted a wind.

Measured against the real formats before the fix:

    "8 mph Out To CF"     -> (0, None)
    "15 mph Out To CF"    -> (0, None)
    "15 mph In From CF"   -> (0, None)
    "8 mph L To R"        -> (0, None)

Tier 3 of the best-games ranking lost its wind signal entirely, while
the park factor kept contributing — so the swing was real but partial,
and `why_first` called it a "weather and park swing" on the strength of
a park factor alone. A right number under a wrong label.

WHAT THIS CHECKS

The router, not the engines. Each engine is correct on its own input;
the bug was a caller that knew about one of them. So: a field-relative
string must produce a non-zero adjustment, a compass string must still
work, a roofed park must stay zero, and an unresolvable string must
return no note rather than a guess.

Asserted against the source of `_write_mlb_slate` plus a re-run of the
same routing logic, because the function itself needs network. That is
the same posture `test_calibration_picks` already takes.
"""
import ast
import os
import sys
import types

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "app"))

# Minimal streamlit shim — both engines carry @st.cache_data.
_st = types.ModuleType("streamlit")


def _memo(*a, **k):
    def deco(fn):
        return fn
    return a[0] if (a and callable(a[0]) and not k) else deco


_st.cache_data = _st.cache_resource = _memo
_st.session_state = {}
_st.secrets = {}
for _n in ("markdown", "caption", "stop", "write", "info", "warning", "error"):
    setattr(_st, _n, lambda *a, **k: None)
sys.modules.setdefault("streamlit", _st)

from engines.wind_engine import wind_hr_adj  # noqa: E402
from engines.player_of_the_day import _wind_hr_adj as field_wind  # noqa: E402
from engines.team_abbreviations import team_abbr  # noqa: E402

failures = []


def check(label, ok):
    if ok:
        print(f"PASS: {label}")
    else:
        failures.append(label)


def route(wind, roofed=False, home="Chicago Cubs"):
    """The routing _write_mlb_slate performs, mirrored."""
    adj, note = field_wind(wind)
    if roofed:
        return 0, None
    if not note:
        adj, note = wind_hr_adj(team_abbr(home), wind, roof_closed=roofed)
    return adj, note


# --- MLB's own format must resolve. This is the whole bug. ------------
for s, sign in (("8 mph Out To CF", 1), ("15 mph Out To CF", 1),
                ("15 mph In From CF", -1)):
    adj, note = route(s)
    check(f"MLB field-relative resolves: {s!r}",
          note is not None and adj * sign > 0)

# A crosswind is genuinely neutral — zero here is a measurement, not a
# miss, and must not be "fixed" into a number.
check("a field-relative crosswind stays neutral",
      route("8 mph L To R") == (0, None))

# --- the compass path must not have regressed ------------------------
adj, note = route("12 mph SW")
check("NWS compass wind still resolves", note is not None and adj != 0)

# --- a closed roof is zero regardless of what the string says --------
check("a roofed park ignores any wind string",
      route("15 mph Out To CF", roofed=True) == (0, None))

# --- absent input is absent, not zero-with-a-story -------------------
check("no wind string yields no note", route(None) == (0, None))
check("'Calm' yields no note", route("Calm") == (0, None))

# --- THE ROUTER MUST BE IN THE SLATE BUILDER, not just in this file --
#
# Everything above re-implements the routing. That proves the engines
# behave, and proves nothing about the caller — which is precisely the
# gap that let this ship. So: assert _write_mlb_slate actually reaches
# for both engines.
src = open(os.path.join(ROOT, "calibration_picks.py"), encoding="utf-8").read()
tree = ast.parse(src)
fn = next((n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name == "_write_mlb_slate"), None)
check("_write_mlb_slate exists", fn is not None)
if fn:
    body = ast.dump(fn)
    check("the slate builder imports the compass engine",
          "wind_hr_adj" in body)
    check("the slate builder ALSO imports the field-relative engine",
          "_field_wind_adj" in body or "player_of_the_day" in body)
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check("both engines are actually CALLED, not merely imported",
          "wind_hr_adj" in called and "_field_wind_adj" in called)

if failures:
    print()
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(1)

print("\nMLB posts wind one way and the forecast another; the slate reads both.")
