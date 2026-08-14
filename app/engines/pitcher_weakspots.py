"""
Pitcher weak spots — where a starter actually gets hurt.

The Edge layer answers "which batters should I target." This answers
"where is this guy beatable," which is what makes the first answer
trustworthy instead of merely correlated.

Four reads, each with its own sample floor, because every one of these
splits the same season into smaller buckets and a rate off a thin
bucket is noise wearing a number's clothes:

1) PITCH TYPE (floor: 150 pitches AND 35 batted balls)
   xSLG allowed per offering. Often the sharpest signal available: a
   starter whose slider is untouchable but whose changeup gets crushed
   is a completely different at-bat depending on what he leans on. The
   floor is set where a mid-rotation starter's top 2-3 offerings
   qualify by midseason and his rarely-used fourth pitch doesn't —
   which is correct, since a pitch thrown 8% of the time isn't the
   edge anyway.

2) ZONE BANDS (floor: 40 pitches AND 12 batted balls per zone)
   Computed on all nine Statcast zones but REPORTED as three-zone
   bands (up / middle / down). Bands triple the effective sample and
   match how hitters actually think — "he's beatable up" is a real
   read; "he's beatable in zone 2 specifically" is usually noise.

3) TIMES THROUGH THE ORDER (floor: 60 batted balls per pass)
   The third time through a lineup, most starters decline — and unlike
   lineup-slot splits, this is a property of the PITCHER, so it
   travels to tonight's game. Computed from at_bat_number, which
   resets per game, by counting his own batters faced.

4) TOP vs BOTTOM OF ORDER (floor: 50 batted balls per half) —
   DISPLAY ONLY, never scored. Slots 1-4 vs 6-9. This is included
   because it captures something semi-real (how he handles quality of
   competition) but it is CONFOUNDED: a spike against the top half
   mostly reflects that better hitters bat there, not a repeatable
   weakness. Nine-slot splits are deliberately not built at all —
   they measure who he happened to face, not anything that predicts
   tonight.

Everything below a floor is returned with its sample and a reason,
never a number, so the page can gray it out instead of implying a
read that isn't there.
"""
import json

import pandas as pd
import streamlit as st

from engines.statcast_engine import _get_pitcher_df
from engines.recency_windows import apply_window

# ---- sample floors ----
PITCH_MIN_PITCHES = 150
PITCH_MIN_BBE = 35
ZONE_MIN_PITCHES = 40
ZONE_MIN_BBE = 12
TTO_MIN_BBE = 60
HALF_MIN_BBE = 50
# One batting slot gets ~1/4 the sample of a half, so the floor is set
# lower — but still high enough that a flagged "weak slot" is real and
# not three good hitters he happened to face twice. Below this, the
# slot's line is shown with its sample but never flagged/colored.
SLOT_MIN_BBE = 18

# league-ish reference points for coloring (xSLG on contact)
# MEASURED 2026-08-13 — 5,032 buckets across 451 pitchers, every bucket
# the panel actually draws (mlb_weakspot_probe.py):
#
#     10th   25th   median   75th   90th
#    0.394  0.453   0.523   0.598  0.675
#
# The old pair was 0.550 / 0.380, chosen by eye. At 0.550 the panel
# flagged **40.2%** of buckets as "hitters do real damage" — a phrase
# that should mark the dangerous QUARTER, not two buckets in five. A
# panel where nearly half the bars are red says nothing about WHERE a
# pitcher gets hurt, which is its entire job.
#
# xSLG measured ON CONTACT excludes strikeouts, so it sits far above the
# per-plate-appearance xSLG people quote. 0.550 was near the middle of
# this distribution, not near its top.
#
# Set to the 75th and 25th: the top quarter is genuinely dangerous, the
# bottom quarter is genuinely where he wins, and the middle half reads
# as middling because it IS middling.
#
# Fifth scale on this site set by eye. The other four — Clears%, FB95%,
# HRWindow% and an EV floor — were all measured and all wrong, three of
# them unreachable at one end. Re-measure with the probe every few
# weeks; the distribution drifts.
XSLG_HOT = 0.598     # 75th percentile — hitters do real damage here
XSLG_COLD = 0.453    # 25th percentile — he wins here

_ZONE_BANDS = {"Up": (1, 2, 3), "Middle": (4, 5, 6), "Down": (7, 8, 9)}

_PITCH_NAMES = {
    "FF": "4-Seam", "FA": "Fastball", "SI": "Sinker", "FC": "Cutter",
    "SL": "Slider", "ST": "Sweeper", "CU": "Curveball", "KC": "Knuckle Curve",
    "CS": "Slow Curve", "CH": "Changeup", "FS": "Splitter", "FO": "Forkball",
    "KN": "Knuckleball", "SV": "Slurve", "EP": "Eephus",
}


def _xslg_of(sub):
    """(xSLG on contact, batted-ball count) for a slice.

    Falls back to REAL SLG-on-contact from outcomes when Statcast's
    estimated column isn't in the data (some bulk pulls drop it — the
    same gap that zeroed SLAM). Keeps the weak-spot reads populated
    with a real number instead of collapsing to empty."""
    if sub.empty:
        return None, 0
    bbe = sub[sub["type"] == "X"] if "type" in sub.columns else sub
    if bbe.empty:
        return None, 0
    if "estimated_slg_using_speedangle" in bbe.columns:
        vals = pd.to_numeric(bbe["estimated_slg_using_speedangle"], errors="coerce").dropna()
        if not vals.empty:
            return round(float(vals.mean()), 3), int(len(vals))
    # Fallback: real total bases per batted ball in play, from events.
    if "events" in bbe.columns:
        ev = bbe["events"].dropna()
        n = int(len(ev))
        if n > 0:
            tb = (int((ev == "single").sum()) + 2 * int((ev == "double").sum())
                  + 3 * int((ev == "triple").sum()) + 4 * int((ev == "home_run").sum()))
            return round(tb / n, 3), n
    return None, 0


@st.cache_data(ttl=3600, max_entries=16, show_spinner=False)
def weak_spots_json(pitcher_id, window: str = "season") -> str:
    """All four reads for one pitcher. JSON string (pickle-safe)."""
    try:
        df, err = _get_pitcher_df(pitcher_id)
    except Exception as e:
        return json.dumps({"error": f"Could not load pitch data ({e})"})
    if df is None or df.empty:
        return json.dumps({"error": err or "No pitch data on file for this pitcher."})
    if window != "season":
        df = apply_window(df, window, "games")
    if df.empty:
        return json.dumps({"error": "No pitches in this window."})

    out = {"error": None, "window": window, "total_pitches": int(len(df))}

    # ---- 1) pitch type ----
    pitches = []
    if "pitch_type" in df.columns:
        for pt, sub in df.groupby("pitch_type"):
            if not pt or str(pt).lower() == "nan":
                continue
            n_pitches = int(len(sub))
            xslg, bbe = _xslg_of(sub)
            usage = round(n_pitches / len(df) * 100, 1)
            entry = {"code": str(pt), "name": _PITCH_NAMES.get(str(pt), str(pt)),
                     "pitches": n_pitches, "bbe": bbe, "usage": usage}
            if n_pitches >= PITCH_MIN_PITCHES and bbe >= PITCH_MIN_BBE and xslg is not None:
                entry["xslg"] = xslg
            else:
                entry["xslg"] = None
                entry["reason"] = (f"{n_pitches} pitches / {bbe} batted balls "
                                   f"\u2014 below the {PITCH_MIN_PITCHES}/{PITCH_MIN_BBE} floor")
            pitches.append(entry)
        pitches.sort(key=lambda p: -p["usage"])
    out["pitches"] = pitches

    # ---- 2) zone bands ----
    bands = []
    if "zone" in df.columns:
        z = pd.to_numeric(df["zone"], errors="coerce")
        for label, zs in _ZONE_BANDS.items():
            sub = df[z.isin(zs)]
            n_pitches = int(len(sub))
            xslg, bbe = _xslg_of(sub)
            # band floors scale with the three zones inside them
            need_p, need_b = ZONE_MIN_PITCHES * 3, ZONE_MIN_BBE * 3
            entry = {"band": label, "pitches": n_pitches, "bbe": bbe}
            if n_pitches >= need_p and bbe >= need_b and xslg is not None:
                entry["xslg"] = xslg
            else:
                entry["xslg"] = None
                entry["reason"] = (f"{n_pitches} pitches / {bbe} batted balls "
                                   f"\u2014 below the {need_p}/{need_b} band floor")
            bands.append(entry)
    out["bands"] = bands

    # ---- 3) times through the order ----
    tto = []
    if {"game_pk", "at_bat_number"}.issubset(df.columns):
        # Within each game, this pitcher's Nth batter faced tells us
        # which pass he's on: 1-9 is first time, 10-18 second, etc.
        pa = df[["game_pk", "at_bat_number"]].drop_duplicates().sort_values(
            ["game_pk", "at_bat_number"])
        pa["seq"] = pa.groupby("game_pk").cumcount()
        pa["tto"] = (pa["seq"] // 9 + 1).clip(upper=4)
        merged = df.merge(pa[["game_pk", "at_bat_number", "tto"]],
                          on=["game_pk", "at_bat_number"], how="left")
        for pass_n in (1, 2, 3):
            sub = merged[merged["tto"] == pass_n]
            xslg, bbe = _xslg_of(sub)
            entry = {"pass": pass_n, "bbe": bbe}
            if bbe >= TTO_MIN_BBE and xslg is not None:
                entry["xslg"] = xslg
            else:
                entry["xslg"] = None
                entry["reason"] = f"{bbe} batted balls \u2014 below the {TTO_MIN_BBE} floor"
            tto.append(entry)
    out["tto"] = tto

    # ---- 4) top vs bottom half (display only) ----
    halves = []
    if {"game_pk", "at_bat_number"}.issubset(df.columns):
        pa = df[["game_pk", "at_bat_number"]].drop_duplicates().sort_values(
            ["game_pk", "at_bat_number"])
        pa["seq"] = pa.groupby("game_pk").cumcount()
        pa["slot"] = pa["seq"] % 9 + 1
        merged = df.merge(pa[["game_pk", "at_bat_number", "slot"]],
                          on=["game_pk", "at_bat_number"], how="left")
        for label, slots in (("Top (1-4)", (1, 2, 3, 4)), ("Bottom (6-9)", (6, 7, 8, 9))):
            sub = merged[merged["slot"].isin(slots)]
            xslg, bbe = _xslg_of(sub)
            entry = {"half": label, "bbe": bbe}
            if bbe >= HALF_MIN_BBE and xslg is not None:
                entry["xslg"] = xslg
            else:
                entry["xslg"] = None
                entry["reason"] = f"{bbe} batted balls \u2014 below the {HALF_MIN_BBE} floor"
            halves.append(entry)
    out["halves"] = halves

    # ---- 5) per batting-order slot (1-9) ----
    # The individual-slot version of (4). Deliberately guarded: a single
    # slot has a modest sample, so a slot is only flagged as a real weak
    # spot when it clears SLOT_MIN_BBE. Below that, the line is returned
    # with its sample and a reason so the page shows it grayed rather
    # than implying a weakness that's really just noise. This is what
    # lets the Game Card align "which slots he's weak on" to the actual
    # hitters batting there tonight.
    slots_out = []
    if {"game_pk", "at_bat_number"}.issubset(df.columns):
        pa = df[["game_pk", "at_bat_number"]].drop_duplicates().sort_values(
            ["game_pk", "at_bat_number"])
        pa["seq"] = pa.groupby("game_pk").cumcount()
        pa["slot"] = pa["seq"] % 9 + 1
        merged = df.merge(pa[["game_pk", "at_bat_number", "slot"]],
                          on=["game_pk", "at_bat_number"], how="left")
        for slot_n in range(1, 10):
            sub = merged[merged["slot"] == slot_n]
            xslg, bbe = _xslg_of(sub)
            entry = {"slot": slot_n, "bbe": bbe}
            if bbe >= SLOT_MIN_BBE and xslg is not None:
                entry["xslg"] = xslg
            else:
                entry["xslg"] = None
                entry["reason"] = f"{bbe} batted balls \u2014 below the {SLOT_MIN_BBE} floor"
            slots_out.append(entry)
    out["slots"] = slots_out

    return json.dumps(out)


def get_weak_spots(pitcher_id, window: str = "season"):
    try:
        return json.loads(weak_spots_json(pitcher_id, window))
    except Exception as e:
        return {"error": f"Weak-spot cache error: {e}"}


def zone_band_xslg(pitcher_id, window: str = "season"):
    """{band: xSLG allowed} for the bands that cleared their floor —
    used by the Edge zone-fit component for two-sided overlap."""
    data = get_weak_spots(pitcher_id, window)
    if data.get("error"):
        return {}
    return {b["band"]: b["xslg"] for b in data.get("bands", []) if b.get("xslg") is not None}
