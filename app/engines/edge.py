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
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from engines.bvp import career_bvp
from engines.statcast_engine import (
    _get_batter_df, _get_pitcher_df, get_pitcher_advanced_splits,
    get_pitcher_role, get_pitcher_hand, get_batter_iso_vs_hand,
)
from engines.weather_engine import get_todays_games_with_weather
from engines.roster import get_live_team_roster, get_active_player_ids

EASTERN = ZoneInfo("America/New_York")

BVP_CAP, ZONE_CAP, PEN_CAP = 15, 15, 10

# PLATOON — the batter's ISO against the STARTER's hand.
#
# pen_context has priced the bullpen's hand mix since it was written.
# The starting pitcher, whom a hitter faces two or three times, had no
# platoon term at all, so a hitter with a .300 ISO against right-handers
# was scored on his blended .205 when he faced a righty.
#
# MEASURED 2026-08-12, 340 batters clearing 40 AB against BOTH hands:
#
#   |ISO vs RHP - ISO vs LHP|   median 0.058 · 75th 0.094
#                               90th 0.138 · max 0.300
#   188 of 340 (55%) gap >= 0.050 · 78 (23%) >= 0.100
#
# League median ISO is about .150, so the MEDIAN hitter's gap is roughly
# 39% of a typical ISO and the 90th nearly doubles it. This is one of
# the largest single effects in the data, and the board selects from the
# tail, which is exactly where splits live.
#
# The signed median is +0.012 — essentially zero, because righties and
# lefties cancel. That is the sanity check that says this measures a
# platoon split and not a systematic bias.
#
# BAND: a hitter's ISO against one hand sits half the gap from his
# neutral, so the 90th-percentile gap of 0.138 is a ~46% swing off a
# .150 neutral. 0.45 maps that to the full cap: about one hitter in ten
# reaches an extreme, which is what an extreme should mean. It also
# lands beside pen_context's 0.40 rather than contradicting it.
PLATOON_CAP = 8
PLATOON_BAND = 0.45

# Both sides must clear get_batter_iso_vs_hand's own 40-AB floor, which
# is why only 340 of 1,390 batters qualify. That is not a gap to paper
# over: a hitter measured against one hand has ONE NUMBER, not a split,
# and inventing the other side is how a thin sample becomes a confident
# adjustment. The term stays silent for him.
_ZONE_MIN_PITCHER = 200   # pitcher's in-zone pitches to profile him
_ZONE_MIN_P = 15          # batter pitches in a zone to count it
_ZONE_MIN_BBE = 5         # batter batted balls in a zone to count it
_ZONE_MIN_COVER = 0.5     # sampled zones must cover half his mix
_ZONE_HH_MIN_BBE = 10     # batted balls in a zone before hard-hit% counts
_ZONE_HH_THRESHOLD = 45.0 # hard-hit% that marks a zone as a damage zone
_ZONE_HH_BONUS_CAP = 4    # most the hard-hit layer can add or remove
_PEN_MIN_ARMS = 5
_PEN_MIN_IP = 40.0

# Ships in the nightly data package, same directory as the parquets and
# manifest (see fetch_data.py / precompute.build_bullpen_profiles).
_PEN_PATH = Path(__file__).resolve().parents[1] / "data" / "statcast" / "bullpen_profiles.json"


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
@st.cache_data(ttl=21600, max_entries=1, show_spinner=False)
def _precomputed_pens():
    """{team: {"relievers":[{id,hr,ip,hand}], "unknown_role":n}} or None.

    Built nightly by precompute.build_bullpen_profiles from the same
    Statcast rows and the same active rosters the live path below reads —
    it is the identical calculation, moved off the user's first page load.
    None when the file isn't in this deploy's data package (an app running
    before the first nightly that includes it), which is why every caller
    below keeps its live path intact.
    """
    path = _PEN_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _pen_snapshot_is_stale(team: str, entry: dict) -> bool:
    """True when this team's stored pen no longer matches its real roster.

    bullpen_profiles.json is the ONE nightly artifact keyed by TEAM
    rather than by player id. Everything else — the per-player parquets,
    pitcher_roles, hr_metrics, the Savant percentiles — travels with the
    player, so a trade cannot misfile it. A team's stored reliever LIST
    can go wrong the moment a deal is announced, and stays wrong until
    the next 10:00 UTC build.

    On a normal day that is a non-event. On the deadline it is dozens of
    arms changing clubs at once, hours before first pitch, and the pen
    HR/9 on a Game Card would be pooled from men who are no longer on
    that staff — while the newly acquired arm the lineup will actually
    face is missing from it.

    Two signals, both from data already on hand:

      DEPARTURE — a stored reliever is no longer on the active roster.
      ARRIVAL   — a pitcher IS on the roster, pitcher_roles (which is
                  keyed by player id, so it is never stale) classifies
                  him RP, and the stored pen doesn't have him.

    The arrival test is what catches a team that only received players.
    Departures alone would miss them entirely.

    FAILS OPEN. An empty roster read means "couldn't check", not
    "everybody left" — same rule get_active_player_ids documents. A
    timed-out request must not throw the slate onto the slow path.
    """
    live_ids = get_active_player_ids(team) or set()
    if not live_ids:
        return False
    stored = {str(r.get("id")) for r in (entry.get("relievers") or []) if r.get("id")}
    if not stored:
        return False
    if stored - live_ids:
        return True
    for pid in live_ids - stored:
        # Pitchers under the outing floor are legitimately absent from
        # the snapshot, and get_pitcher_role returns None for them — so
        # this only fires on an arm with a real, established RP role.
        if get_pitcher_role(pid) == "RP":
            return True
    return False


def _pen_from_precomputed(team: str, starter_pid,
                          verify_roster: bool = False) -> str | None:
    """Pooled pen line for this team from the nightly file, or None.

    Tonight's starter is still excluded here rather than baked in at
    build time: role classification puts an opener in the RP bucket, and
    on the night he opens he is not part of the pen the lineup faces
    late. Pooling the stored arms is arithmetic on a ~8-item list, so
    doing it per request costs nothing and keeps this exactly equal to
    the live path.
    """
    pens = _precomputed_pens()
    if not pens:
        return None
    entry = pens.get(team)
    if not entry:
        return None
    # Only the team actually on screen is verified. The slate-wide
    # baseline deliberately does not: it averages ~30 pens, one traded
    # arm barely moves it, and checking every team would put the ~30
    # sequential roster calls back on the first page load — the exact
    # cost the nightly build exists to remove.
    if verify_roster and _pen_snapshot_is_stale(team, entry):
        return None
    arms, hr_total, ip_total, lhp_ip = 0, 0, 0.0, 0.0
    for r in entry.get("relievers") or []:
        if starter_pid and str(r.get("id")) == str(starter_pid):
            continue
        ip = float(r.get("ip") or 0.0)
        if ip <= 0:
            continue
        arms += 1
        hr_total += int(r.get("hr") or 0)
        ip_total += ip
        if r.get("hand") == "L":
            lhp_ip += ip
    if arms < _PEN_MIN_ARMS or ip_total < _PEN_MIN_IP:
        return json.dumps({"hr9": None, "arms": arms, "ip": round(ip_total, 1),
                           "lhp_ip_share": None,
                           "unknown_role": entry.get("unknown_role", 0)})
    return json.dumps({"hr9": round(hr_total * 9.0 / ip_total, 2),
                       "arms": arms, "ip": round(ip_total, 1),
                       "lhp_ip_share": round(lhp_ip / ip_total, 3),
                       "unknown_role": entry.get("unknown_role", 0)})


@st.cache_data(ttl=21600, max_entries=60, show_spinner=False)
def _pen_profile_json(team: str, starter_pid, date_str: str,
                      verify_roster: bool = False, roster_key: str = "") -> str:
    """Pooled pen HR/9 from the team's ACTUAL RELIEVERS, plus the
    handedness mix of those innings.

    This used to be "every roster pitcher except tonight's starter",
    which quietly included the other four men in the rotation. A starter
    carries five or six times a reliever's innings, so pooling HR and IP
    let the rotation dominate the result — the number labelled "bullpen
    HR/9" was mostly other starters' HR/9, and it was the same for every
    hitter in the lineup.

    get_pitcher_role() separates them from at_bat_number, so this is now
    genuinely the arms that finish the game. Pitchers whose role can't be
    determined are EXCLUDED rather than guessed at: a misclassified
    starter would drag the pooled rate straight back toward the rotation.

    Also returns lhp_ip_share — the fraction of pen innings thrown by
    lefties. That's what makes the adjustment batter-specific downstream:
    a lefty bat facing an all-right-handed pen is a real edge that a
    single team-level number cannot express.
    """
    # PRECOMPUTED FIRST. This is the whole point of the nightly build:
    # the live path below is one HTTPS roster call plus a role lookup, a
    # full splits derive and a hand lookup for every arm on the roster,
    # and _slate_pen_avg_json runs it for all ~30 teams on the slate
    # before the first Game Card can render. Reading the local file
    # instead turns that from ~30 seconds into microseconds.
    #
    # Falls through to the live build on any miss — a team absent from
    # the file, a deploy predating the first nightly that includes it —
    # so behaviour is unchanged when the data isn't there.
    _pre = _pen_from_precomputed(team, starter_pid, verify_roster)
    if _pre is not None:
        return _pre

    arms, hr_total, ip_total, lhp_ip = 0, 0, 0.0, 0.0
    skipped_unknown = 0
    roster = get_live_team_roster(team) or []
    for p in roster:
        if not p.get("is_pitcher") or not p.get("id"):
            continue
        if starter_pid and p["id"] == starter_pid:
            continue
        # ACTIVE 26 ONLY. get_live_team_roster deliberately returns the
        # union of the active roster and the 40-man, so IL and optioned
        # players still resolve elsewhere in the app. But a 40-man carries
        # around twenty pitchers, so pooling all of them produced a
        # "bullpen" of twelve-plus arms — real relievers, but including
        # ones in Triple-A or on the IL who cannot pitch tonight. Their
        # innings still moved the average.
        #
        # p["active"] is False for exactly those. Missing key is treated
        # as active so an older cached roster shape degrades to the
        # previous behaviour rather than emptying the pen.
        if p.get("active") is False:
            continue
        role = get_pitcher_role(p["id"])
        if role != "RP":
            # "SP" is the rotation; None means not enough outings to
            # judge. Neither belongs in a bullpen average.
            if role is None:
                skipped_unknown += 1
            continue
        sp = get_pitcher_advanced_splits(p["id"])
        ip = float(sp.get("IP") or 0.0)
        if ip <= 0:
            continue
        arms += 1
        hr_total += int(sp.get("HR") or 0)
        ip_total += ip
        if get_pitcher_hand(p["id"]) == "L":
            lhp_ip += ip
    if arms < _PEN_MIN_ARMS or ip_total < _PEN_MIN_IP:
        return json.dumps({"hr9": None, "arms": arms, "ip": round(ip_total, 1),
                           "lhp_ip_share": None, "unknown_role": skipped_unknown})
    return json.dumps({"hr9": round(hr_total * 9.0 / ip_total, 2),
                       "arms": arms, "ip": round(ip_total, 1),
                       "lhp_ip_share": round(lhp_ip / ip_total, 3),
                       "unknown_role": skipped_unknown})


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


def pen_context(pitcher_team: str, starter_pid, batter_id=None):
    """(adj, note) for a hitter facing this team's pen tonight.

    Two parts:

      TEAM  — how homer-prone this pen is against the slate-average pen.
              +10 per full HR/9 above it, linear.
      HITTER— how this particular batter hits the HAND the pen actually
              throws with. Optional: pass batter_id to get it.

    The second part is the point. Research done on the starter expires
    the moment he's pulled, and roughly a third of a hitter's plate
    appearances come after that. A single team-level number applied
    identically to all nine hitters can't tell you that the lefty batting
    third will see an all-right-handed pen in the 7th while the righty
    behind him won't care. Blending the batter's own platoon split
    against the pen's handedness mix is what carries your matchup work
    into the late innings instead of ending it in the 6th.

    Falls back to exactly the old team-only behaviour when batter_id is
    absent or the batter has no usable platoon sample — the adjustment
    degrades, it doesn't invent.
    """
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    # roster_key is a CACHE KEY, not an argument the body reads.
    #
    # _pen_profile_json is cached for six hours, so the staleness check
    # inside it only runs on a miss. Without this, a deal announced after
    # the day's first Game Card render would sit behind a warm cache
    # entry until the ttl expired — the check would be correct and simply
    # never get asked. Folding the roster into the key means any change
    # to who is on the staff produces a new entry and re-runs the check.
    #
    # get_active_player_ids is cached for five minutes and the Game Card
    # has already called it for this team by now, so this is a dict
    # lookup in practice.
    roster_key = ",".join(sorted(get_active_player_ids(pitcher_team) or ()))
    try:
        prof = json.loads(_pen_profile_json(pitcher_team, starter_pid, date_str,
                                            verify_roster=True,
                                            roster_key=roster_key))
        base = json.loads(_slate_pen_avg_json(date_str))
    except Exception:
        return 0, None
    hr9, avg = prof.get("hr9"), base.get("avg")
    if hr9 is None:
        return 0, (f"pen sample too small ({prof.get('arms', 0)} relievers, "
                   f"{prof.get('ip', 0)} IP)")
    if avg is None:
        return 0, f"pen HR/9 {hr9} (slate baseline unavailable)"

    team_adj = (hr9 - avg) * 10.0
    note = (f"pen HR/9 {hr9} vs slate-average pen {avg} "
            f"({prof['arms']} relievers, {prof['ip']} IP)")

    share = prof.get("lhp_ip_share")
    if batter_id and share is not None:
        iso_l = get_batter_iso_vs_hand(batter_id, "L")
        iso_r = get_batter_iso_vs_hand(batter_id, "R")
        if iso_l is not None and iso_r is not None:
            # ISO the batter can expect from the pen's actual hand mix,
            # against his own overall ISO across both hands. A pen that
            # is 85% right-handed barely moves a hitter with no platoon
            # split and moves a strong-split hitter a lot.
            mixed = share * iso_l + (1 - share) * iso_r
            neutral = (iso_l + iso_r) / 2.0
            if neutral > 0:
                # ±40% ISO swing maps to the full cap; clamped so a tiny
                # platoon sample can't dominate the team signal.
                platoon = max(-1.0, min(1.0, (mixed - neutral) / (0.40 * neutral)))
                team_adj += platoon * PEN_CAP * 0.5
                note += (f" · pen is {round(share * 100)}% LHP, batter ISO "
                         f"{mixed:.3f} vs that mix ({neutral:.3f} neutral)")

    return int(max(-PEN_CAP, min(PEN_CAP, round(team_adj)))), note


# ------------------------------------------------------------------
# Composition
# ------------------------------------------------------------------
def platoon_context(batter_id, p_throws):
    """(adj, note) for the batter's split against the STARTER's hand.

    Returns (0, None) whenever the split is not measurable on both
    sides — see PLATOON_CAP above for why a one-sided sample is not a
    split.
    """
    if not batter_id or p_throws not in ("L", "R"):
        return 0, None
    iso_l = get_batter_iso_vs_hand(batter_id, "L")
    iso_r = get_batter_iso_vs_hand(batter_id, "R")
    if iso_l is None or iso_r is None:
        return 0, None
    neutral = (iso_l + iso_r) / 2.0
    if neutral <= 0:
        return 0, None
    facing = iso_l if p_throws == "L" else iso_r
    swing = (facing - neutral) / (PLATOON_BAND * neutral)
    adj = max(-1.0, min(1.0, swing)) * PLATOON_CAP
    note = (f"ISO {facing:.3f} vs {p_throws}HP against {neutral:.3f} "
            f"neutral (L {iso_l:.3f} / R {iso_r:.3f})")
    return int(round(adj)), note


def edge_components(batter_id, pitcher_id, base_score, pen_adj, pen_note,
                    *, home_team=None, bats=None, temp=None, roof_closed=False,
                    wind=None, arsenal=None, batter_vs_pitch=None,
                    batting_order=None):
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
    # PITCH-TYPE MATCHUP. Never uses the pitcher's own HR rate per pitch
    # type — that's ~2 events over ~250 sliders. Uses his MIX (stable,
    # and his choice) against measured league rates, optionally weighted
    # by this hitter's damage on those pitches.
    #
    # batter_vs_pitch is optional by design. With it, the full
    # interaction. Without it, the mix term alone — still real (some
    # arsenals are more homer-prone than others) and cheap enough for a
    # slate-wide board, where fetching per-pitch profiles for ~270
    # batters would not be.
    pm_adj, pm_note = 0.0, None
    if arsenal:
        from engines.pitch_matchup import pitch_matchup_adj
        pm_adj, pm_note = pitch_matchup_adj(batter_id, arsenal,
                                            batter_vs_pitch=batter_vs_pitch)

    # LINEUP SLOT — opportunity, not skill.
    #
    # Every other component here asks how good this bat is. This one asks
    # how many times he gets to swing, which is the difference between
    # ranking hitters and predicting home runs. Sits out entirely when the
    # lineup isn't confirmed, since an unposted lineup has no batting
    # order to read.
    slot_adj, slot_note = 0.0, None
    if batting_order is not None:
        from engines.lineup_slot import slot_opportunity_adj, league_pa_per_game
        slot_adj, slot_note = slot_opportunity_adj(batting_order,
                                                   league_pa_per_game())

    # THE STARTER'S HAND. pen_context already prices the bullpen's mix;
    # this is the arm the hitter faces two or three times. get_pitcher_hand
    # is the same lookup the arsenal and zone terms use, so a pitcher
    # whose hand is unknown gets no platoon adjustment rather than a
    # guessed one.
    plat_adj, plat_note = platoon_context(batter_id, get_pitcher_hand(pitcher_id))

    total = b_adj + z_adj + pen_adj + ctx_adj + pm_adj + slot_adj + plat_adj
    edge = edge_raw = None
    if base_score is not None:
        # THE UNROUNDED, UNCLAMPED VALUE, carried for SORTING ONLY.
        #
        # `edge` is an integer clamped to 0-100. On a full slate that is
        # ~270 bats sharing 101 possible values, so ties are everywhere —
        # and a stable sort resolves them by whatever order the caller
        # happened to build its rows in, which on the slate board is
        # game order, then away before home, then lineup order. A
        # ranking that falls back to the schedule is the alphabetical
        # problem wearing a different costume.
        #
        # Teammates tie far more often than strangers do, because they
        # share ctx_adj EXACTLY — same park, same temperature, same wind,
        # same opposing arsenal. So tied teammates land adjacent, which
        # is part of why one lineup can appear to take over the top of
        # the board.
        #
        # The clamp compounds it: the adjustments span +/-75 (bvp 15,
        # zone 15, pen 10, park 10, temp 4, pitch 8, slot 5, platoon 8),
        # so a strong
        # bat in a strong spot pins at 100 and real separation at the
        # very top is erased. Sorting on this value keeps the separation
        # while the displayed number stays the honest bounded one.
        edge_raw = round(base_score + total, 4)
        edge = int(max(0, min(100, round(edge_raw))))
    return {"edge": edge, "edge_raw": edge_raw, "mx": round(total, 1),
            "bvp_adj": b_adj, "bvp_line": b_line,
            "zone_adj": z_adj, "zone_note": z_note,
            "pen_adj": pen_adj, "pen_note": pen_note,
            "ctx_adj": ctx_adj, "ctx_notes": ctx_notes,
            "pitch_adj": pm_adj, "pitch_note": pm_note,
            "slot_adj": slot_adj, "slot_note": slot_note,
            "platoon_adj": plat_adj, "platoon_note": plat_note}
