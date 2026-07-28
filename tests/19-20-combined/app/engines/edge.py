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
_ZONE_HH_MIN_BBE = 10     # batted balls in a zone before hard-hit% counts
_ZONE_HH_THRESHOLD = 45.0 # hard-hit% that marks a zone as a damage zone
_ZONE_HH_BONUS_CAP = 4    # most the hard-hit layer can add or remove
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
@st.cache_data(ttl=3600, max_entries=180, show_spinner=False)
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


@st.cache_data(ttl=3600, max_entries=450, show_spinner=False)
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
    ev = pd.to_numeric(df.get("launch_speed"), errors="coerce")
    zones, zones_hh = {}, {}
    for zn in range(1, 10):
        mask = z == zn
        n = int(mask.sum())
        dmg = xslg[mask & is_bbe].dropna()
        if n >= _ZONE_MIN_P and len(dmg) >= _ZONE_MIN_BBE:
            zones[str(zn)] = round(float(dmg.mean()), 4)
        # Zone hard-hit carries its own (stricter) floor — a hard-hit
        # rate needs more batted balls than an xSLG average before it
        # means anything.
        ev_z = ev[mask & is_bbe].dropna()
        if len(ev_z) >= _ZONE_HH_MIN_BBE:
            zones_hh[str(zn)] = round(float((ev_z >= 95).mean() * 100), 1)
    return json.dumps({"zones": zones, "zones_hh": zones_hh,
                       "overall": round(float(overall.mean()), 4)})


def zone_fit_component(batter_id, pitcher_id):
    """(adj, note). 0.050 xSLG of expected-vs-own-norm = 3 pts, ±15.

    Two-sided since the weak-spot build: the original version asked
    only "does this pitcher throw where the batter does damage." That
    ignored half the information sitting in the same data — whether
    the pitcher actually GETS HURT there. A batter who mashes up in
    the zone against a pitcher who lives up but dominates up is a
    worse spot than the one-sided read suggests. The pitcher-side
    layer is capped small (±5) because band-level xSLG allowed is a
    coarser read than the batter's own per-zone damage."""
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

    # Contact-quality layer: weight his HARD-HIT rate by the same
    # pitcher mix. This separates two bats with identical expected
    # xSLG — one squaring balls up where this guy lives, the other
    # getting weak contact that happens to fall in. Capped small
    # (±4) because it's a refinement of the xSLG read, not a rival
    # to it, and only applied when enough zones cleared the stricter
    # hard-hit floor.
    zones_hh = dmg.get("zones_hh") or {}
    hh_fit, hh_cover = 0.0, 0.0
    for zn, share in mix.items():
        if zn in zones_hh:
            hh_fit += share * zones_hh[zn]
            hh_cover += share
    # ---- pitcher-side: where does HE get hurt? ----
    # Weighted by the same mix, so this asks: in the bands he actually
    # lives in, do hitters do damage against him? Capped ±5.
    try:
        from engines.pitcher_weakspots import zone_band_xslg
        bands = zone_band_xslg(pitcher_id)
    except Exception:
        bands = {}
    if bands:
        _BAND_OF = {1: "Up", 2: "Up", 3: "Up", 4: "Middle", 5: "Middle",
                    6: "Middle", 7: "Down", 8: "Down", 9: "Down"}
        band_fit, band_cover = 0.0, 0.0
        for zn, share in mix.items():
            band = _BAND_OF.get(int(zn))
            if band and band in bands:
                band_fit += share * bands[band]
                band_cover += share
        if band_cover >= _ZONE_MIN_COVER:
            hurt = band_fit / band_cover
            # .450 is roughly a neutral xSLG allowed on contact; every
            # .060 above or below it moves one point, capped ±5.
            hurt_adj = int(max(-5, min(5, round((hurt - 0.450) / 0.060))))
            if hurt_adj:
                adj = int(max(-ZONE_CAP, min(ZONE_CAP, adj + hurt_adj)))
                note += (f" \u00b7 he allows {hurt:.3f} xSLG in those bands "
                         f"({hurt_adj:+d})")

    if hh_cover >= _ZONE_MIN_COVER:
        expected_hh = hh_fit / hh_cover
        hh_diff = expected_hh - _ZONE_HH_THRESHOLD
        hh_adj = int(max(-_ZONE_HH_BONUS_CAP,
                         min(_ZONE_HH_BONUS_CAP, round(hh_diff / 5.0))))
        if hh_adj:
            adj = int(max(-ZONE_CAP, min(ZONE_CAP, adj + hh_adj)))
            note += (f" \u00b7 hard-hit {expected_hh:.0f}% there "
                     f"vs {_ZONE_HH_THRESHOLD:.0f}% bar ({hh_adj:+d})")
    return adj, note


# ------------------------------------------------------------------
# 3) Bullpen (slate-relative)
# ------------------------------------------------------------------
@st.cache_data(ttl=21600, max_entries=60, show_spinner=False)
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


@st.cache_data(ttl=21600, max_entries=4, show_spinner=False)
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
def edge_components(batter_id, pitcher_id, base_score, pen_adj, pen_note,
                    *, home_team=None, bats=None, temp=None, roof_closed=False,
                    wind=None):
    """Attachable dict for a lineup row. edge is None when the skill
    score is None (no Savant sample) — matchup can't rescue a bat we
    can't rate.

    CONTEXT (home_team / bats / temp) is optional and keyword-only so
    existing callers keep working unchanged and simply get no context
    adjustment rather than a wrong one.

    `bats` must be the EFFECTIVE hand for tonight — the side a switch
    hitter will actually bat from against this pitcher, not "S". The
    caller owns that resolution because only it knows the pitcher's
    throwing hand. Passing "S" yields no park adjustment rather than a
    coin-flip guess, which matters most for exactly the hitters whose
    park splits differ most.

    Park is deliberately NOT in HR Score: the xHR grid behind the skill
    number pools all 30 parks so a hitter's rating doesn't change when he
    travels. Tonight's building belongs here, in the matchup layer,
    beside BvP and bullpen — putting it in both would count it twice.
    """
    b_adj, b_line = bvp_component(batter_id, pitcher_id)
    z_adj, z_note = zone_fit_component(batter_id, pitcher_id)
    ctx_adj, ctx_notes = 0.0, []
    if home_team or temp or wind:
        # Imported here rather than at module scope: hr_context reads a
        # nightly parquet through streamlit's cache, and edge.py is
        # imported by non-Streamlit paths (calibration_picks.py) where a
        # hard dependency would be an unnecessary import cost.
        from engines.hr_context import context_hr_adj
        ctx_adj, ctx_notes = context_hr_adj(home_team, bats, temp,
                                            roof_closed=roof_closed,
                                            wind_str=wind)
    total = b_adj + z_adj + pen_adj + ctx_adj
    edge = None
    if base_score is not None:
        edge = int(max(0, min(100, round(base_score + total))))
    return {"edge": edge, "mx": round(total, 1),
            "bvp_adj": b_adj, "bvp_line": b_line,
            "zone_adj": z_adj, "zone_note": z_note,
            "pen_adj": pen_adj, "pen_note": pen_note,
            "ctx_adj": ctx_adj, "ctx_notes": ctx_notes}
