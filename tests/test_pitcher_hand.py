"""get_pitcher_hand must unpack _get_pitcher_df's (df, error) TUPLE.

This shipped broken: the function did `df = _get_pitcher_df(pid)` and then
`df.empty`, which raised AttributeError: 'tuple' object has no attribute
'empty' and took down the whole Game Card on load. Every other caller in
statcast_engine unpacks the pair; this one didn't, and no test called it.
"""
import sys
import types

import pandas as pd

st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for _n in ("statcast_batter", "statcast_pitcher", "playerid_lookup",
           "statcast_batter_percentile_ranks"):
    setattr(pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

from engines import statcast_engine as se

_DF = pd.DataFrame({"p_throws": ["L", "L", "R"], "pitch_type": ["FF"] * 3})

# --- 1. the tuple contract ------------------------------------------
se._get_pitcher_df = lambda pid, *a, **k: (_DF, None)
assert se.get_pitcher_hand(123) == "L", (
    "handedness must come off the dataframe inside the (df, error) tuple — "
    "most common value, so one mislabelled pitch can't flip a pitcher's hand")
assert se.hand_tag(123) == "LHP"
print("PASS: unpacks (df, error) and returns the modal hand")

# --- 2. every degraded path returns None/"" rather than raising ------
for label, stub in (
    ("empty dataframe", lambda pid, *a, **k: (pd.DataFrame(), None)),
    ("df is None", lambda pid, *a, **k: (None, "fetch failed")),
    ("no p_throws column", lambda pid, *a, **k: (pd.DataFrame({"x": [1]}), None)),
    ("all-NaN p_throws", lambda pid, *a, **k: (pd.DataFrame({"p_throws": [None]}), None)),
    ("fetch raises", lambda pid, *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))),
):
    se._get_pitcher_df = stub
    assert se.get_pitcher_hand(123) is None, f"{label} should yield None"
    assert se.hand_tag(123) == "", f"{label} should yield an empty tag"
print("PASS: every degraded path yields None/\"\" instead of raising")

# --- 3. no id at all -------------------------------------------------
se._get_pitcher_df = lambda pid, *a, **k: (_DF, None)
assert se.get_pitcher_hand(None) is None, "no probable posted => no hand"
assert se.hand_tag(None) == "", (
    "an unposted probable must render as a plain name, not crash the card")
print("PASS: a missing pitcher id is handled, not raised")

# --- 4. the tag is display-ready -------------------------------------
se._get_pitcher_df = lambda pid, *a, **k: (
    pd.DataFrame({"p_throws": ["R", "R"]}), None)
assert se.hand_tag(1) == "RHP"
print("PASS: tag renders as LHP/RHP")
