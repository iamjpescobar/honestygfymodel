"""The arsenal a hitter faces TONIGHT, not the one from March.

THE PROBLEM. get_weak_spots read usage and damage off the SAME window,
which forces a bad trade either way:

  season only -> damage is well-sampled, USAGE IS STALE. A pitcher who
                 scrapped his curve in June still shows 16% curveballs
                 in August.
  recent only -> usage is current, DAMAGE COLLAPSES. The floor is 150
                 pitches and 35 batted balls per pitch type, and thirty
                 days clears that for a primary fastball and nothing
                 else.

THE FIX. They have different sample requirements, so they get different
windows: RANK BY RECENT USAGE, RATE ON SEASON DAMAGE. Usage is a
proportion and settles in ~450 pitches; damage is a rate over batted
balls and needs the year.

Both are published per pitch rather than one replacing the other,
because THE GAP IS ITSELF THE SIGNAL — a pitch at 7% on the season and
18% over the last month is a pitcher who changed something, and that is
worth more than either number alone.
"""
import sys, types
import pandas as pd

_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = _st
_pb = types.ModuleType("pybaseball")
for _n in ("statcast_pitcher", "statcast_batter", "playerid_lookup",
           "statcast_batter_percentile_ranks", "statcast"):
    setattr(_pb, _n, lambda *a, **k: None)
sys.modules["pybaseball"] = _pb
sys.path.insert(0, "app")

from engines import pitcher_weakspots as pw  # noqa: E402
from engines import weakspot_view as wv      # noqa: E402


def frame():
    """A pitcher who SWAPPED a pitch mid-season.

    March-June: heavy curveball, no sweeper.
    Last 30 days: curve gone, sweeper is now a main pitch.
    Season usage would rank the curve second and never show the sweeper.
    """
    rows = []
    old = pd.Timestamp("2026-05-01")
    new = pd.Timestamp("2026-08-10")
    for _ in range(600):
        rows.append(("FF", old))
    for _ in range(400):
        rows.append(("CU", old))     # the pitch he has since dropped
    for _ in range(300):
        rows.append(("FF", new))
    for _ in range(250):
        rows.append(("ST", new))     # the pitch he added
    for _ in range(50):
        rows.append(("CU", new))
    return pd.DataFrame({"pitch_type": [r[0] for r in rows],
                         "game_date": [r[1] for r in rows]})


df = frame()

# --- 1. RECENT USAGE DIFFERS FROM SEASON USAGE -----------------------
rec = pw._recent_usage(df, pw.USAGE_DAYS)
assert rec, "no recent usage computed at all"
assert rec["ST"] > rec["CU"], (
    f"the added sweeper ({rec.get('ST')}%) does not outrank the dropped "
    f"curve ({rec.get('CU')}%) in the recent window")
season_cu = 450 / len(df) * 100
assert rec["CU"] < season_cu / 2, (
    f"recent curve usage {rec['CU']}% is not materially below its season "
    f"{season_cu:.0f}% — the window is not isolating recent games")
print(f"PASS: recent window sees ST {rec['ST']}% / CU {rec['CU']}%, "
      f"season CU is {season_cu:.0f}%")

# --- 2. A THIN RECENT WINDOW RETURNS NOTHING, NOT A GUESS ------------
#
# Under ~50 pitches one appearance can put a pitch at 40%. Returning {}
# makes the caller fall back to season order; returning a confident wrong
# order would be worse than a stale right one.
thin = pd.DataFrame({"pitch_type": ["FF"] * 20,
                     "game_date": [pd.Timestamp("2026-08-10")] * 20})
assert pw._recent_usage(thin, pw.USAGE_DAYS) == {}, (
    "a 20-pitch window produced a usage split — one appearance would "
    "set the whole arsenal order")
# And a frame with no dates at all must not invent one.
assert pw._recent_usage(pd.DataFrame({"pitch_type": ["FF"] * 500}), 30) == {}
print("PASS: too-thin or dateless windows return nothing, not a guess")

# --- 3. THE TWO WINDOWS STAY SEPARATE --------------------------------
#
# The whole point. If USAGE_DAYS ever gets applied to the damage rate,
# every secondary pitch drops below its floor and the panel goes blank.
src = open("app/engines/pitcher_weakspots.py", encoding="utf-8").read()
assert "USAGE_DAYS" in src and "PITCH_MIN_BBE" in src
_i_recent = src.index("recent = _recent_usage(df, USAGE_DAYS)")
_i_xslg = src.index("xslg, bbe = _xslg_of(sub)")
assert "_xslg_of(sub)" in src, "damage is no longer computed per pitch"
assert "_recent_usage(sub" not in src, (
    "the damage bucket is being windowed too — season damage is what "
    "clears the 35-batted-ball floor")
print("PASS: usage is windowed, damage is not")

# --- 4. TOP THREE ARE MARKED, NOT TRUNCATED --------------------------
#
# A fourth pitch thrown 9% of the time still leaves the yard, and a
# pitch a pitcher has just ADDED appears at the bottom of this list
# before it appears anywhere else on the site.
assert pw.PRIMARY_PITCHES == 3
pitches = [{"code": c, "name": c, "usage": 10.0, "usage_recent": u,
            "xslg": 0.5, "bbe": 60, "primary": i < 3}
           for i, (c, u) in enumerate(
               [("FF", 40), ("SL", 25), ("CH", 15), ("CU", 12), ("ST", 8)])]
assert sum(1 for p in pitches if p["primary"]) == 3
svg = wv.arsenal_svg(pitches, min_usage=0)
assert svg.count("<circle") == 5, (
    f"only {svg.count('<circle')} pitches drawn — the secondary ones were "
    f"dropped rather than de-emphasised")
assert 'stroke-opacity="0.9"' in svg, "secondary pitches are not outlined"
assert 'opacity="0.78"' in svg, "primary pitches are not solid"
print("PASS: all 5 pitches render; 3 solid, the rest hollow")

# --- 5. THE PLOT USES RECENT USAGE FOR POSITION ----------------------
#
# A pitch he has dropped belongs at the left edge no matter what March
# says. Two pitches with identical season usage and different recent
# usage must land in different places.
same = [{"code": "A", "name": "A", "usage": 30.0, "usage_recent": 40.0,
         "xslg": 0.5, "bbe": 60, "primary": True},
        {"code": "B", "name": "B", "usage": 30.0, "usage_recent": 5.0,
         "xslg": 0.5, "bbe": 60, "primary": True}]
import re  # noqa: E402
xs = [int(m) for m in re.findall(r'<circle cx="(\d+)"', wv.arsenal_svg(same, min_usage=0))]
assert len(set(xs)) == 2, (
    f"both pitches plotted at x={xs} — identical SEASON usage put them in "
    f"the same place, so the chart is still reading the stale number")
print(f"PASS: equal season usage, different recent usage -> x={xs}")

# --- 6. DRIFT IS SHOWN, NOT THRESHOLDED ------------------------------
#
# No cut point is invented for "meaningfully changed". The number is
# printed and the reader judges — the same thing the site does anywhere
# a threshold has not been measured against the league.
moved = [{"code": "ST", "name": "Sweeper", "usage": 7.0, "usage_recent": 18.0,
          "usage_drift": 11.0, "xslg": 0.62, "bbe": 40, "primary": True}]
assert "+11 pts" in wv.arsenal_svg(moved, min_usage=0)
# Assert on the LABEL, not on the string "pts" — the axis caption
# explains what +/-pts means and would match a naive search, which would
# make this case pass for the wrong reason.
flat = [dict(moved[0], usage_drift=0.4)]
_flat_svg = wv.arsenal_svg(flat, min_usage=0)
assert "+0 pts" not in _flat_svg and "-0 pts" not in _flat_svg, (
    "a 0.4-point move was annotated; noise-level drift should stay silent")
assert "Sweeper 0.620" in _flat_svg, "the pitch label itself went missing"
print("PASS: real drift is labelled, noise-level drift is not")
