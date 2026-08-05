"""The roster payload's REPORTED status must survive into the slate.

WHY THIS TEST EXISTS

fetch_team_roster() used to keep {name, pos} and drop everything else in
the response -- jersey, status, injuries[], experience. The app then had
to infer "OUT 4d" from days-since-played, not because the fact was
unavailable but because it had been discarded one function earlier.
wnba_roster_probe (run 84109530071, slate 2026-08-03) measured what is
actually in that payload: status on 14 of 14 athletes per team, jersey on
13 of 14, injuries[] on the 1-4 per team who have one, and NO `active`
and NO `starter` fields at all.

So this pins two things: the parsing survives the shapes ESPN sends, and
the app never lets an inferred label outrank a reported one.

Plain script, like everything in tests/ -- exits non-zero on failure.
No network.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import wnba_precompute as wp  # noqa: E402

failures = []


def check(label, ok):
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------- shapes
# The probe did not print status's inner shape, so both are accepted.
check("status from a dict", wp._status_text({"id": "1", "name": "Active"}) == "Active")
check("status from a bare string", wp._status_text("Day-To-Day") == "Day-To-Day")
check("status falls back through keys",
      wp._status_text({"abbreviation": "OUT"}) == "OUT")
check("status of nothing is None", wp._status_text(None) is None)
check("status of an empty string is None", wp._status_text("   ") is None)

# The exact injury entry the probe printed.
check("injury read from the roster payload",
      wp._injury_note({"injuries": [{"status": "Out",
                                     "date": "2026-07-15T23:46Z"}]})
      == ("Out", "2026-07-15T23:46Z"))
check("no injuries array is not an injury",
      wp._injury_note({"id": "1"}) == (None, None))
check("an empty injuries array is not an injury",
      wp._injury_note({"injuries": []}) == (None, None))
check("a junk injuries entry is survived",
      wp._injury_note({"injuries": ["oops", {"date": "x"}]}) == (None, None))

# ---------------------------------------------------------------- source
_pc = (ROOT / "wnba_precompute.py").read_text(encoding="utf-8")
for _field in ("jersey", "roster_status", "injury_status", "injury_date", "exp"):
    check(f"roster keeps {_field}", f'"{_field}":' in _pc)
    check(f"slate row carries {_field}", f'row["{_field}"] = _ri.get' in _pc)

# `active` and `starter` are NOT on this payload. Anything reading them
# from the roster would be silently always-empty, which is the failure
# mode this whole area already has a history of.
check("does not read a starter flag off the roster",
      '_ri.get("starter")' not in _pc)

# ---------------------------------------------------------------- app
_view = (ROOT / "app" / "views" / "WNBA.py").read_text(encoding="utf-8")
_status_expr = _view[_view.index('"Status": (p.get('):]
_status_expr = _status_expr[:_status_expr.index('"Role"')]
# Order matters: both reported source must be consulted before the
# days-since-played guess is allowed to speak.
check("reported statuses come first",
      _status_expr.index('today_status') < _status_expr.index("OUT {_days}d")
      and _status_expr.index('injury_status') < _status_expr.index("OUT {_days}d"))
# The guess keeps its day count, which is what makes it visibly a guess.
check("the inference stays labelled", "OUT {_days}d" in _status_expr)

if failures:
    print("FAIL:", "; ".join(failures))
    sys.exit(1)
print("PASS: reported roster status reaches the slate and outranks the guess")
