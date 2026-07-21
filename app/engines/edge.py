"""
The Matchup Edge layer — Phase 2 of the scoring system.

    HR Edge = HR Score (skill, 0-100)  +  matchup adjustments (max ±40)

The skill score stays pure ("how dangerous is this bat, period" — real
Savant percentiles of Barrel%, Hard-Hit%, and Exit Velocity). The
matchup layer adjusts it with three independent, capped, sample-floored
components — every one printed on the page so the WHY is always
visible:

1) BvP  (±15) — the batter's real CAREER line vs tonight's pitcher
   (MLB official vs-player split). Tiers:
       +15  PA >= 10 and SLG >= .600   (he owns him)
       +10  PA >=  8 and SLG >= .500
       -10  PA >= 10 and AVG <= .150
       -15  PA >= 12 and AVG <= .120   (career futility)
   Anything smaller-sample or in between: 0. The raw line is always
   attached either way.

2) ZONE FIT (±15) — does this pitcher live where this batter does
   damage? Overlap of the pitcher's real in-zone pitch distribution
   (zones 1-9, season, minimum 200 in-zone pitches) with the batter's
   real xSLG on contact per zone (season; zones need >= 15 pitches and
   >= 5 batted balls to count). The expected xSLG given WHERE this
   pitcher throws is compared to the batter's own overall xSLG on
   contact; the difference maps linearly (0.050 of xSLG = 3 points)
   and clamps at ±15. If the sampled zones cover less than half the
   pitcher's in-zone mix, the component is 0 ("insufficient overlap")
   rather than a guess.

3) BULLPEN (±10) — the late-game reality: after the starter leaves,
   the lineup faces his team's pen. Each team's bullpen profile is
   pooled from its real relievers' own Statcast rows (roster pitchers
   minus tonight's starter): total HR allowed over total estimated IP
   = pen HR/9, compared to the AVERAGE PEN ON TODAY'S SLATE (an
   apples-to-apples baseline computed from the same data, not an
   imported constant). One full HR/9 above slate average = +10,
   linear, clamped ±10. Pens with under 5 arms or 40 pooled IP of
   data: 0, labeled.

Nothing here is a probability. It's a transparent stack of real
measurements with declared weights — the weights are this app's
choice (40-point matchup ceiling, set deliberately), and every
component's contribution is shown, so a wrong-feeling Edge can be
audited line by line.

Caching: JSON-string layers (always pickle-serializable). The slate
bullpen baseline is the heavy one — first build of the day reads every
slate reliever's local parquet (~a few hundred fast local reads),
then it's cached for the day.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from engines.bvp import career_bvp
from engines.statcast_engine import (
    _get_batter_df, _get_pitcher_df, get_pitcher_advanced_splits,
)
from engines.weather_engine import get_todays_games_with_weather
from engines.roster import get_live_team_roster

EASTERN = ZoneInfo("America/New_York")

BVP_CAP, ZONE_CAP, PEN_CAP = 15, 15, 10
_ZONE_MIN_PITCHER = 200   # pitcher's in-zone pitches to profile him
_ZONE_MIN_P = 15          # batter pitches in a zone to count it
_ZONE_MIN_BBE = 5         # batter batted balls in a zone to count it
_ZONE_MIN_COVER = 0.5     # sampled zones must cover half his mix
_PEN_MIN_ARMS = 5
_PEN_MIN_IP = 40.0


# ------------------------------------------------------------------
# 1) BvP tiers
# ------------------------------------------------------------------
def bvp_component(batter_id, pitcher_id):
    """(adj, line_text). adj in {-15,-10,0,+10,+15} per the tiers."""
    if not batter_id or not pitcher_id:
        return 0, None
    d = career_bvp(batter_id, pitcher_id)
    if not d or not d.get("ab"):
        return 0, "no career history"
    avg, slg, pa = d.get("avg"), d.get("slg"), d.get("pa", 0)
    slg_txt = f"{slg:.3f}" if slg is not None else "\u2014"
    line = f'{d["h"]}-for-{d["ab"]}, {d["hr"]} HR, SLG {slg_txt} ({pa} PA)'
    if pa >= 10 and slg is not None and slg >= 0.600:
        return BVP_CAP, line
    if pa >= 8 and slg is not None and slg >= 0.500:
        return 10, line
    if pa >= 12 and avg is not None and avg <= 0.120:
        return -BVP_CAP, line
    if pa >= 10 and avg is not None and avg <= 0.150:
        return -10, line
    return 0, line


# ------------------------------------------------------------------
# 2) Zone fit
# ------------------------------------------------------------------
@st.cache_data(ttl=3600, max_entries=16, show_spinner=False)
def _pitcher_zone_mix_json(pitcher_id) -> str:
    """{zone: share} over zones 1-9, or {} if under sample."""
    try:
        df, _e = _get_pitcher_df(pitcher_id)
    except Exception:
        return json.dumps({})
    if df is None or df.empty or "zone" not in df.columns:
        return json.dumps({})
    z = pd.to_numeric(df["zone"], errors="coerce")
    inzone = z[(z >= 1) & (z <= 9)]
    total = int(len(inzone))
    if total < _ZONE_MIN_PITCHER:
        return json.dumps({})
    counts = inzone.value_counts()
    return json.dumps({str(int(k)): round(v / total, 4) for k, v in counts.items()})


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def _batter_zone_dmg_json(batter_id) -> str:
    """{"zones": {zone: xSLG-on-contact}, "overall": xSLG-on-contact}
    with per-zone sample floors applied."""
    try:
        df, _e = _get_batter_df(batter_id)
    except Exception:
        return json.dumps({})
    if df is None or df.empty or "zone" not in df.columns:
        return json.dumps({})
    z = pd.to_numeric(df["zone"], errors="coerce")
    xslg = pd.to_numeric(df.get("estimated_slg_using_speedangle"), errors="coerce")
    is_bbe = df["type"] == "X" if "type" in df.columns else pd.Series(False, index=df.index)
    overall = xslg[is_bbe].dropna()
    if overall.empty:
        return json.dumps({})
    zones = {}
    for zn in range(1, 10):
        mask = z == zn
        n = int(mask.sum())
        dmg = xslg[mask & is_bbe].dropna()
        if n >= _ZONE_MIN_P and len(dmg) >= _ZONE_MIN_BBE:
            zones[str(zn)] = round(float(dmg.mean()), 4)
    return json.dumps({"zones": zones, "overall": round(float(overall.mean()), 4)})


def zone_fit_component(batter_id, pitcher_id):
    """(adj, note). 0.050 xSLG of expected-vs-own-norm = 3 pts, ±15."""
    if not batter_id or not pitcher_id:
        return 0, None
    try:
        mix = json.loads(_pitcher_zone_mix_json(pitcher_id))
        dmg = json.loads(_batter_zone_dmg_json(batter_id))
    except Exception:
        return 0, None
    if not mix:
        return 0, "pitcher zone sample too small"
    zones, overall = dmg.get("zones") or {}, dmg.get("overall")
    if not zones or overall is None:
        return 0, "batter zone sample too small"
    fit, cover = 0.0, 0.0
    for zn, share in mix.items():
        if zn in zones:
            fit += share * zones[zn]
            cover += share
    if cover < _ZONE_MIN_COVER:
        return 0, f"insufficient overlap ({cover:.0%} of his mix sampled)"
    expected = fit / cover
    diff = expected - overall
    adj = int(max(-ZONE_CAP, min(ZONE_CAP, round(diff * 60))))
    note = (f"expected xSLG {expected:.3f} where he throws vs own norm {overall:.3f} "
            f"({cover:.0%} of mix sampled)")
    return adj, note


# ------------------------------------------------------------------
# 3) Bullpen (slate-relative)
# ------------------------------------------------------------------
@st.cache_data(ttl=21600, show_spinner=False)
def _pen_profile_json(team: str, starter_pid, date_str: str) -> str:
    """Pooled pen HR/9 from the team's real relievers (roster pitchers
    minus tonight's starter), each from his own Statcast rows."""
    arms, hr_total, ip_total = 0, 0, 0.0
    roster = get_live_team_roster(team) or []
    for p in roster:
        if not p.get("is_pitcher") or not p.get("id"):
            continue
        if starter_pid and p["id"] == starter_pid:
            continue
        sp = get_pitcher_advanced_splits(p["id"])
        ip = float(sp.get("IP") or 0.0)
        if ip <= 0:
            continue
        arms += 1
        hr_total += int(sp.get("HR") or 0)
        ip_total += ip
    if arms < _PEN_MIN_ARMS or ip_total < _PEN_MIN_IP:
        return json.dumps({"hr9": None, "arms": arms, "ip": round(ip_total, 1)})
    return json.dumps({"hr9": round(hr_total * 9.0 / ip_total, 2),
                       "arms": arms, "ip": round(ip_total, 1)})


@st.cache_data(ttl=21600, show_spinner=False)
def _slate_pen_avg_json(date_str: str) -> str:
    """Average pen HR/9 across every team on today's slate — the
    apples-to-apples baseline. Heavy on first build, cached all day."""
    games, _err = get_todays_games_with_weather()
    vals = []
    for g in games or []:
        for side in ("away", "home"):
            team = g.get(side)
            spid = g.get(f"{side}_pitcher_id")
            if not team:
                continue
            try:
                prof = json.loads(_pen_profile_json(team, spid, date_str))
            except Exception:
                continue
            if prof.get("hr9") is not None:
                vals.append(prof["hr9"])
    return json.dumps({"avg": round(sum(vals) / len(vals), 2) if vals else None,
                       "n": len(vals)})


def pen_context(pitcher_team: str, starter_pid):
    """(adj, note) for a lineup facing this team's pen tonight.
    +10 per full HR/9 above the slate-average pen, linear, ±10."""
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    try:
        prof = json.loads(_pen_profile_json(pitcher_team, starter_pid, date_str))
        base = json.loads(_slate_pen_avg_json(date_str))
    except Exception:
        return 0, None
    hr9, avg = prof.get("hr9"), base.get("avg")
    if hr9 is None:
        return 0, f"pen sample too small ({prof.get('arms', 0)} arms, {prof.get('ip', 0)} IP)"
    if avg is None:
        return 0, f"pen HR/9 {hr9} (slate baseline unavailable)"
    adj = int(max(-PEN_CAP, min(PEN_CAP, round((hr9 - avg) * 10))))
    return adj, (f"pen HR/9 {hr9} vs slate-average pen {avg} "
                 f"({prof['arms']} arms, {prof['ip']} IP)")


# ------------------------------------------------------------------
# Composition
# ------------------------------------------------------------------
def edge_components(batter_id, pitcher_id, base_score, pen_adj, pen_note):
    """Attachable dict for a lineup row. edge is None when the skill
    score is None (no Savant sample) — matchup can't rescue a bat we
    can't rate."""
    b_adj, b_line = bvp_component(batter_id, pitcher_id)
    z_adj, z_note = zone_fit_component(batter_id, pitcher_id)
    total = b_adj + z_adj + pen_adj
    edge = None
    if base_score is not None:
        edge = int(max(0, min(100, round(base_score + total))))
    return {"edge": edge, "mx": total,
            "bvp_adj": b_adj, "bvp_line": b_line,
            "zone_adj": z_adj, "zone_note": z_note,
            "pen_adj": pen_adj, "pen_note": pen_note}
