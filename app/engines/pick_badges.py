"""
Pick badges — the "why is this bat here" layer.

Every badge is a named threshold test over data this app already
computes. Nothing here invents a number: each badge fires only when
its stated condition is met, and the condition is printed alongside
it. The goal is that a subscriber can read WHY a bat ranks without
opening the Edge breakdown, and can disagree with the reasoning
because the reasoning is visible.

Badges:
  BLAST MATCH  - batter Blast% >= 10 AND pitcher Meatball% >= 12
                 (loud contact profile meets a pitcher who leaves
                 pitches over the plate)
  SPLIT FIT    - batter ISO vs this pitcher's handedness >= .200
  ZONE FIT     - Edge zone-fit component >= +5 (he does damage where
                 this pitcher lives)
  OWNS HIM     - Edge BvP component >= +10 (real career damage vs him)
  PEN LEAK     - Edge bullpen component >= +5 (the arms behind the
                 starter give up power)
  PARK BOOST   - park factor >= 105
  WIND BOOST   - official field-relative wind blowing out >= 8 mph

Thresholds live here as module constants so they're auditable and
changeable in one place.
"""

BLAST_RATE_MIN = 10.0
MEATBALL_MIN = 12.0
SPLIT_ISO_MIN = 0.200
ZONE_FIT_MIN = 5
BVP_OWNS_MIN = 10
PEN_LEAK_MIN = 5
PARK_BOOST_MIN = 105
WIND_OUT_MPH_MIN = 8


def _wind_out_mph(wind_str):
    """(is_out, mph) from MLB's field-relative wind string. Returns
    (False, 0) for forecast/compass wind — only official field-relative
    data can honestly claim 'out'."""
    if not wind_str:
        return False, 0
    w = str(wind_str).lower()
    if "out to" not in w:
        return False, 0
    import re
    m = re.search(r"(\d+)\s*mph", w)
    return True, int(m.group(1)) if m else 0


def compute_badges(row, profile, pitcher_splits, park_factor, wind_str):
    """Returns (badges, why_parts).

    badges:    [(label, reason_text), ...] in display order
    why_parts: short strings for the one-line "Why upside" summary
    """
    badges, why = [], []

    blast = profile.get("Blast %")
    meatball = (pitcher_splits or {}).get("Meatball%")
    if (blast is not None and meatball is not None
            and blast >= BLAST_RATE_MIN and meatball >= MEATBALL_MIN):
        badges.append(("\U0001F4A5 Blast Match",
                       f"{blast:.0f}% blast rate vs {meatball:.0f}% meatball pitcher"))
        why.append(f"{blast:.0f}% blast vs {meatball:.0f}% meatball")

    iso_split = row.get("iso_vs_hand")
    hand = row.get("opp_hand")
    if iso_split is not None and iso_split >= SPLIT_ISO_MIN:
        badges.append(("\U0001F4CA Split Fit",
                       f".{int(round(iso_split * 1000)):03d} ISO vs {hand or 'this hand'}"))
        why.append(f".{int(round(iso_split * 1000)):03d} ISO vs {hand or 'hand'}")

    z = row.get("zone_adj")
    if z is not None and z >= ZONE_FIT_MIN:
        badges.append(("\U0001F3AF Zone Fit", row.get("zone_note") or f"zone fit +{z}"))
        why.append(f"zone fit +{z}")

    b = row.get("bvp_adj")
    if b is not None and b >= BVP_OWNS_MIN:
        badges.append(("\U0001F512 Owns Him", row.get("bvp_line") or f"BvP +{b}"))
        why.append("career BvP edge")

    p = row.get("pen_adj")
    if p is not None and p >= PEN_LEAK_MIN:
        badges.append(("\U0001F513 Pen Leak", row.get("pen_note") or f"bullpen +{p}"))
        why.append("leaky bullpen late")

    if park_factor is not None:
        try:
            if float(park_factor) >= PARK_BOOST_MIN:
                badges.append(("\U0001F3DF\uFE0F Park Boost", f"park factor {park_factor}"))
                why.append(f"park {park_factor}")
        except Exception:
            pass

    is_out, mph = _wind_out_mph(wind_str)
    if is_out and mph >= WIND_OUT_MPH_MIN:
        badges.append(("\U0001F32C\uFE0F Wind Boost", f"wind out {mph} mph"))
        why.append(f"wind out {mph}")

    return badges, why


def render_badge_row(st, COLOR, badges, why, name, hr_score, edge):
    """Renders one bat's badge card. Kept in the engine so the Game
    Card and any future page render picks identically."""
    if not badges:
        return
    chips = "".join(
        f'<span style="display:inline-block; padding:2px 8px; margin:2px 4px 2px 0; '
        f'border-radius:4px; font-size:10px; font-weight:700; '
        f'background:{COLOR["gold"]}22; color:{COLOR["gold"]};" title="{reason}">{label}</span>'
        for label, reason in badges
    )
    why_txt = " \u00b7 ".join(why)
    st.markdown(
        f'<div style="padding:7px 10px; margin-bottom:6px; border-radius:8px; '
        f'border:1px solid {COLOR["text"]}1E;">'
        f'<div style="font-size:12.5px; font-weight:700; color:{COLOR["text"]};">{name}'
        f'<span style="margin-left:8px; font-size:11px; color:{COLOR["stat_high"]};">'
        f'HR Score {hr_score} \u2192 Edge {edge}</span></div>'
        f'<div style="margin-top:3px;">{chips}</div>'
        f'<div style="font-size:10.5px; color:{COLOR["text"]}; opacity:0.7; margin-top:3px;">'
        f'Why upside: {why_txt}</div></div>',
        unsafe_allow_html=True,
    )
