"""The nightly bullpen snapshot must not survive a trade.

bullpen_profiles.json is the only nightly artifact keyed by TEAM instead
of by player id. Every other table — the per-player parquets,
pitcher_roles, hr_metrics, Savant percentiles — travels with the player,
so a trade cannot misfile it. A team's stored reliever list can go wrong
the moment a deal is announced and stays wrong until the next 10:00 UTC
build.

On the trade deadline that is dozens of arms at once, hours before first
pitch. Without this check a Game Card would pool pen HR/9 from pitchers
who are no longer on that staff, while the arm the lineup will actually
face is missing from the pool — and every number would look measured,
because every number WOULD be measured. Just for the wrong club.

Both directions have to fire. A team that only RECEIVED players has no
departures at all, so departure detection alone would miss it entirely.

And it has to fail OPEN: an empty roster read means "couldn't check", not
"everybody left". A timed-out statsapi request must not throw the whole
slate onto the slow live path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import engines.edge as edge  # noqa: E402

STORED = {"relievers": [{"id": "111", "hr": 3, "ip": 40.0, "hand": "R"},
                        {"id": "222", "hr": 5, "ip": 35.0, "hand": "L"},
                        {"id": "333", "hr": 2, "ip": 28.0, "hand": "R"}],
          "unknown_role": 0}

CASES = [
    # label,                       live roster ids,        roles,        stale?
    ("roster unchanged",           {"111", "222", "333"},  {},            False),
    ("reliever traded AWAY",       {"111", "333"},         {},            True),
    ("reliever ACQUIRED",          {"111", "222", "333", "999"},
                                                           {"999": "RP"}, True),
    ("acquired a STARTER",         {"111", "222", "333", "888"},
                                                           {"888": "SP"}, False),
    ("callup below outing floor",  {"111", "222", "333", "777"},
                                                           {},            False),
    ("roster read failed",         set(),                  {},            False),
]

failures = []
_real_ids, _real_role = edge.get_active_player_ids, edge.get_pitcher_role

for label, live, roles, expect in CASES:
    edge.get_active_player_ids = lambda _t, _l=live: _l
    edge.get_pitcher_role = lambda pid, _r=roles: _r.get(str(pid))

    got = edge._pen_snapshot_is_stale("Some Team", STORED)
    ok = got is expect
    print(f"{'PASS' if ok else 'FAIL'}: {label:28} stale={got!r:6} expected={expect!r}")
    if not ok:
        failures.append(f"{label}: got stale={got!r}, expected {expect!r}")

edge.get_active_player_ids, edge.get_pitcher_role = _real_ids, _real_role

# ----------------------------------------------------------------------
# The flag must be OFF by default. The slate-wide baseline averages ~30
# pens and calls this for every team; verifying each one would put ~30
# sequential roster calls back on the first page load, which is the exact
# cost build_bullpen_profiles exists to remove.
# ----------------------------------------------------------------------
import inspect  # noqa: E402

for fn_name in ("_pen_from_precomputed", "_pen_profile_json"):
    fn = getattr(edge, fn_name)
    fn = getattr(fn, "__wrapped__", fn)
    sig = inspect.signature(fn)
    param = sig.parameters.get("verify_roster")
    if param is None:
        failures.append(f"{fn_name} lost its verify_roster parameter")
    elif param.default is not False:
        failures.append(f"{fn_name} verify_roster defaults to {param.default!r}, "
                        f"not False — the slate baseline would start making "
                        f"~30 roster calls on first load")
    else:
        print(f"PASS: {fn_name} verify_roster defaults off")

# And the one call site that SHOULD verify still does.
src = (ROOT / "app" / "engines" / "edge.py").read_text()
if "verify_roster=True" not in src:
    failures.append("pen_context no longer verifies the displayed team's roster")
else:
    print("PASS: pen_context verifies the displayed matchup")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    print("=" * 68)
    sys.exit(1)

print("\nPASS: traded arms invalidate the snapshot, and the check fails open.")
