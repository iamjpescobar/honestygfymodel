"""Verify the new metrics against hand-built batted-ball data."""
import sys, types
import numpy as np, pandas as pd

# stub streamlit so the engine imports without it installed
st = types.ModuleType("streamlit")
def _cache(**kw):
    def deco(f): return f
    return deco
st.cache_data = _cache
sys.modules["streamlit"] = st
pb = types.ModuleType("pybaseball")
for n in ("statcast_batter","statcast_pitcher","playerid_lookup"):
    setattr(pb, n, lambda *a, **k: None)
sys.modules["pybaseball"] = pb
sys.path.insert(0, "app")

from engines.statcast_engine import _compute_batted_ball_metrics, _HR_LA_MIN, _HR_LA_MAX

def row(ev, la, bb, ev_events="field_out"):
    return {"type":"X","events":ev_events,"description":"hit_into_play","bb_type":bb,
            "launch_speed":ev,"launch_angle":la,"launch_speed_angle":4,
            "hc_x":100.0,"hc_y":100.0,"stand":"R","bat_speed":72.0,"release_speed":93.0}

# 4 in the HR window (20,25,35,40), 4 outside (8,15,45,50)
rows = [row(100, a, "fly_ball") for a in (20,25,35,40,8,15,45,50)]
df = pd.DataFrame(rows)
m = _compute_batted_ball_metrics(df)

assert m["HRWindow %"] == 50.0, m["HRWindow %"]
print(f"PASS: HR window {_HR_LA_MIN}-{_HR_LA_MAX} -> {m['HRWindow %']}% (4 of 8)")

# a 15-degree liner is NOT in the window (the old 8-32 band would have counted it)
assert _compute_batted_ball_metrics(pd.DataFrame([row(112,15,"line_drive")]))["HRWindow %"] == 0.0
assert _compute_batted_ball_metrics(pd.DataFrame([row(112,15,"line_drive")]))["SweetSpot %"] == 100.0
print("PASS: 15-deg liner excluded from HR window but still counts as sweet spot")

# EV90 vs Max EV separation
evs = [80,85,90,95,100,105,108,110,112,119]
df2 = pd.DataFrame([row(e, 28, "fly_ball") for e in evs])
m2 = _compute_batted_ball_metrics(df2)
assert m2["MaxEV"] == 119.0, m2["MaxEV"]
assert m2["EV90"] == round(float(np.percentile(evs, 90)), 1), m2["EV90"]
assert m2["EV90"] < m2["MaxEV"], "EV90 should sit below the single hardest ball"
print(f"PASS: EV90 {m2['EV90']} vs MaxEV {m2['MaxEV']} — outlier does not drive the scored value")

# Brl/PA folds in strikeouts; Brl% does not
bbe = [ {**row(101, 28, "fly_ball"), "launch_speed_angle": 6} for _ in range(10) ]
ks  = [ {"type":"S","events":"strikeout","description":"swinging_strike","bb_type":None,
         "launch_speed":np.nan,"launch_angle":np.nan,"launch_speed_angle":np.nan,
         "hc_x":np.nan,"hc_y":np.nan,"stand":"R","bat_speed":np.nan,"release_speed":93.0}
        for _ in range(30) ]
m3 = _compute_batted_ball_metrics(pd.DataFrame(bbe + ks))
assert m3["Brl %"] == 100.0, m3["Brl %"]
assert m3["PA"] == 40, m3["PA"]
assert m3["Brl/PA"] == 25.0, m3["Brl/PA"]
print(f"PASS: Brl% {m3['Brl %']}% (per BBE) vs Brl/PA {m3['Brl/PA']}% — strikeouts counted")

# HR Intent is present and bounded
assert m["HRIntent"] is not None and 0 <= m["HRIntent"] <= 100, m["HRIntent"]
print(f"PASS: HR Intent computes ({m['HRIntent']}) and stays on a 0-100 scale")

# empty frame must not crash and must not fabricate values
e = _compute_batted_ball_metrics(pd.DataFrame())
assert e["EV90"] is None and e["MaxEV"] is None and e["HRIntent"] is None
print("PASS: empty input returns None, not a fabricated zero")
