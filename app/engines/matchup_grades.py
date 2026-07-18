"""
MLB matchup grades — moneyline lean and over/under lean, graded.

HONESTY CONTRACT (read this before trusting a grade):
These are this app's OWN transparent composites — a checklist of real,
named signals, each computed from real data (this app's Statcast-derived
starter splits, the verified park factor, and MLB's posted weather).
They are NOT calibrated win probabilities and NOT predictions. Every
signal that fired is listed next to the grade so the reader can weigh
the evidence themselves. No starter data -> no grade, stated plainly.

MONEYLINE signals (each compares the two starters' real season splits;
a signal fires for the better side when the gap clears the threshold):
  WHIP gap        >= 0.15
  K% gap          >= 3.0 percentage points
  HR/9 gap        >= 0.40
  SLG-against gap >= 0.030
Grade by net signals for one side: 4=A, 3=B, 2=C, 1=C-, 0=no lean.

OVER/UNDER signals (each fires toward Over or Under):
  Park factor >= 102 (Over) / <= 98 (Under)      [verified parks only]
  Game-time temp >= 80F (Over) / <= 65F (Under)
  Starters' avg WHIP >= 1.30 (Over) / <= 1.15 (Under)
  Starters' avg HR/9 >= 1.20 (Over) / <= 0.90 (Under)
  Starters' avg SLG-against >= .420 (Over) / <= .380 (Under)
Grade by net signals: 4-5=A, 3=B, 2=C, 1=C-, 0=no lean.
Thresholds are this app's fixed heuristic anchors, documented here.
"""

import streamlit as st

from engines.statcast_engine import get_pitcher_advanced_splits

_GRADES = {4: "A", 3: "B", 2: "C", 1: "C-"}


def _grade(net):
    return _GRADES.get(min(net, 4), "A" if net > 4 else None)


@st.cache_data(ttl=3600, max_entries=16, show_spinner=False)
def grade_matchup(away_pitcher_id, home_pitcher_id, away_name, home_name,
                  park_factor=None, park_verified=False, temp=None,
                  window: str = "season"):
    """Returns {"ml": {...}|None, "ou": {...}|None, "error": str|None,
    "window": window}. window slices BOTH starters' splits to their
    last N games ("l25"/"l15"/"l10"/"l5") via the shared recency
    engine; "season" (default) is the exact behavior this checklist
    has always had. Same thresholds in every window — the window
    changes the EVIDENCE, never the bar it has to clear."""
    if not away_pitcher_id or not home_pitcher_id:
        return {"ml": None, "ou": None, "window": window,
                "error": "Starter not posted yet — no grade without both starters' real data."}

    a = get_pitcher_advanced_splits(away_pitcher_id, window=window)
    h = get_pitcher_advanced_splits(home_pitcher_id, window=window)
    if not a or not h:
        return {"ml": None, "ou": None, "window": window,
                "error": "Splits unavailable for one starter in this window — no grade."}

    def val(d, k):
        v = d.get(k)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # ---- Moneyline: head-to-head starter comparison ----
    ml_signals, a_pts, h_pts = [], 0, 0
    checks = [
        ("WHIP", "WHIP", 0.15, "lower"),
        ("K%", "K%", 3.0, "higher"),
        ("HR/9", "HR/9", 0.40, "lower"),
        ("SLG against", "SLG", 0.030, "lower"),
    ]
    for label, key, thresh, better in checks:
        av, hv = val(a, key), val(h, key)
        if av is None or hv is None:
            continue
        gap = abs(av - hv)
        if gap < thresh:
            continue
        a_better = av < hv if better == "lower" else av > hv
        who = away_name if a_better else home_name
        if a_better:
            a_pts += 1
        else:
            h_pts += 1
        ml_signals.append(f"{label}: edge {who} ({av:g} vs {hv:g})")

    ml = None
    net = abs(a_pts - h_pts)
    if net > 0:
        lean = away_name if a_pts > h_pts else home_name
        ml = {"lean": lean, "grade": _grade(net), "signals": ml_signals,
              "score": f"{max(a_pts, h_pts)}-{min(a_pts, h_pts)} signals"}
    elif ml_signals:
        ml = {"lean": None, "grade": None, "signals": ml_signals,
              "score": "signals split evenly — no lean"}

    # ---- Over/Under: environment + combined starter suppression ----
    over, under, ou_signals = 0, 0, []

    def avg2(k):
        av, hv = val(a, k), val(h, k)
        if av is None or hv is None:
            return None
        return (av + hv) / 2

    if park_verified and park_factor is not None:
        try:
            pf = float(park_factor)
            if pf >= 102:
                over += 1
                ou_signals.append(f"Park factor {pf:g} (hitter-friendly)")
            elif pf <= 98:
                under += 1
                ou_signals.append(f"Park factor {pf:g} (pitcher-friendly)")
        except (TypeError, ValueError):
            pass
    if temp is not None:
        try:
            tf = float(temp)
            if tf >= 80:
                over += 1
                ou_signals.append(f"Temp {tf:g}F (carry weather)")
            elif tf <= 65:
                under += 1
                ou_signals.append(f"Temp {tf:g}F (cold suppresses)")
        except (TypeError, ValueError):
            pass
    for label, key, ov_t, un_t in [
        ("Starters' avg WHIP", "WHIP", 1.30, 1.15),
        ("Starters' avg HR/9", "HR/9", 1.20, 0.90),
        ("Starters' avg SLG against", "SLG", 0.420, 0.380),
    ]:
        v = avg2(key)
        if v is None:
            continue
        if v >= ov_t:
            over += 1
            ou_signals.append(f"{label} {v:.3g} (high)")
        elif v <= un_t:
            under += 1
            ou_signals.append(f"{label} {v:.3g} (low)")

    ou = None
    net = abs(over - under)
    if net > 0:
        ou = {"lean": "Over" if over > under else "Under",
              "grade": _grade(net), "signals": ou_signals,
              "score": f"{max(over, under)}-{min(over, under)} signals"}
    elif ou_signals:
        ou = {"lean": None, "grade": None, "signals": ou_signals,
              "score": "signals split evenly — no lean"}

    return {"ml": ml, "ou": ou, "error": None, "window": window}