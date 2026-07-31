"""The bullpen edge must come from RELIEVERS, and vary by batter.

Two defects this covers.

The pen profile pooled "every roster pitcher except tonight's starter",
which swept in the other four men in the rotation. A starter carries five
or six times a reliever's innings, so pooled HR/IP was dominated by the
rotation — the number labelled "bullpen HR/9" was mostly other starters.

And the adjustment was team-level, identical for all nine hitters. That
throws away the whole late-game platoon angle: a lefty facing an
all-right-handed pen in the 7th is a real edge that one shared number
cannot express.
"""
import sys
import types

import pandas as pd

st = types.ModuleType("streamlit")
st.session_state = {}
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

from engines import statcast_engine as se


def _frame(first_abs):
    rows = []
    for g, fa in enumerate(first_abs):
        for k in range(4):
            rows.append({"game_pk": 1000 + g, "at_bat_number": fa + k * 4})
    return pd.DataFrame(rows)


# --- 1. role classification ------------------------------------------
for label, firsts, want in [
    ("everyday starter", [1, 2, 1, 1, 2], "SP"),
    ("late reliever", [24, 27, 22, 30, 26], "RP"),
    ("closer", [33, 31, 35, 34], "RP"),
    ("middle relief", [14, 17, 12, 19, 15], "RP"),
    ("starter with one relief cameo", [1, 1, 2, 1, 26], "SP"),
    ("reliever with one spot start", [25, 28, 1, 24, 27], "RP"),
]:
    se._get_pitcher_df = lambda pid, *a, **k: (_frame(firsts), None)
    got = se.get_pitcher_role(1)
    assert got == want, f"{label}: got {got}, want {want}"
print("PASS: starters and relievers separate cleanly by at_bat_number")

# A median, not a mean — one odd outing must not flip the label.
se._get_pitcher_df = lambda pid, *a, **k: (_frame([1, 1, 1, 1, 40]), None)
assert se.get_pitcher_role(1) == "SP", (
    "a single long relief appearance reclassified a starter — use the median, "
    "or one outing drags the whole label")
print("PASS: one outlier outing does not flip a role")

# --- 2. unknown roles are excluded, never guessed --------------------
for label, stub in [
    ("too few outings", lambda pid, *a, **k: (_frame([1, 1]), None)),
    ("empty frame", lambda pid, *a, **k: (pd.DataFrame(), None)),
    ("missing columns", lambda pid, *a, **k: (pd.DataFrame({"x": [1]}), None)),
    ("df is None", lambda pid, *a, **k: (None, "err")),
    ("fetch raises", lambda pid, *a, **k: (_ for _ in ()).throw(RuntimeError())),
]:
    se._get_pitcher_df = stub
    assert se.get_pitcher_role(1) is None, (
        f"{label}: returned a role it could not know. A misclassified starter "
        f"drags the pooled pen rate straight back toward the rotation")
print("PASS: undeterminable roles return None and get excluded")

# --- 3. the pen profile actually filters on role ---------------------
EDGE = (__import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "engines" / "edge.py").read_text()
_prof = EDGE[EDGE.index("def _pen_profile_json"):EDGE.index("def _slate_pen_avg_json")]
assert 'get_pitcher_role(' in _prof and 'role != "RP"' in _prof, (
    "the pen profile no longer filters by role — it is pooling the rotation "
    "back into the bullpen average")
assert "lhp_ip_share" in _prof, (
    "the pen's handedness mix is gone; without it the adjustment cannot be "
    "batter-specific")
print("PASS: pen profile filters to relievers and reports its handedness mix")

# --- 4. the adjustment is batter-aware, and degrades safely ----------
_ctx = EDGE[EDGE.index("def pen_context"):]
assert "batter_id=None" in _ctx, "pen_context must accept a batter"
assert "get_batter_iso_vs_hand" in _ctx, (
    "no platoon lookup — the pen adjustment is still one flat number for the "
    "entire lineup")
assert "if batter_id and share is not None" in _ctx, (
    "the batter branch must be optional so callers without a batter id, or "
    "hitters with no platoon sample, fall back to team-only rather than break")
print("PASS: adjustment is batter-aware and falls back cleanly")

# --- 5. every caller passes a batter ---------------------------------
import pathlib
for f in ("app/engines/hr_edge_board.py", "app/engines/player_of_the_day.py",
          "app/views/GameCard.py"):
    src = pathlib.Path(f).read_text()
    lines = src.split("\n")
    for i, line in enumerate(lines):
        if "pen_context(" in line and "def " not in line and "import" not in line:
            # Calls wrap across lines — read the whole call, not one line.
            call = " ".join(lines[i:i + 3])
            # A bare call whose result is discarded is a deliberate cache
            # warm-up (see GameCard) — it feeds nothing to the board, so
            # it doesn't need a batter.
            if "=" not in line.split("pen_context(")[0]:
                continue
            assert "batter_id" in call, (
                f"{f} calls pen_context without a batter — that hitter silently "
                f"reverts to the old lineup-wide number:\n    {line.strip()}")
print("PASS: all three call sites pass a batter id")
