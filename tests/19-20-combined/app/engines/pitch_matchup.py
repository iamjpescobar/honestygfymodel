"""
Pitch-type home-run matchup — the interaction, not the raw rate.

WHY NOT "PITCHER'S HR RATE BY PITCH TYPE"
-----------------------------------------
That was the obvious version and it doesn't work. A starter throws maybe
250 sliders in a season and gives up two home runs on them. That's a rate
of 0.8% built on two events — the difference between two and four homers
is a coin flip, and the resulting number would swing wildly while looking
precise. Ranking pitchers on it would be ranking noise.

WHAT ACTUALLY CARRIES SIGNAL
----------------------------
Three quantities, each measured on a sample large enough to mean
something, multiplied together:

  1. PITCH MIX — how often this pitcher throws each pitch type.
     Hundreds of pitches per type. Very stable, and it's a choice the
     pitcher makes rather than an outcome he suffers.

  2. LEAGUE HR RATE BY PITCH TYPE — how often a given pitch type gets
     hit out, across the entire league. Tens of thousands of pitches per
     type. Effectively exact.

  3. THIS HITTER'S DAMAGE ON THAT PITCH TYPE — his own barrel rate
     against sliders, changeups, four-seamers. Smaller, so it is
     regressed toward the league rate by sample size.

Multiply them and you get: how dangerous is THIS hitter against the mix
THIS pitcher actually throws. That is a matchup, and none of the three
inputs is a two-event coin flip.

The pitcher's own HR-per-pitch-type never enters. His contribution is
his mix — which is real, stable, and his decision.
"""
import streamlit as st
import pandas as pd
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_LEAGUE_PATH = _DATA_DIR / "pitch_type_hr.parquet"

# Regression constant for a hitter's barrel rate against one pitch type.
# Per-pitch-type samples are a fraction of his overall workload, so this
# is deliberately heavy: without it, "he's 3-for-8 on curveballs" reads
# as a matchup edge.
K_HITTER_PITCH = 60          # batted balls against that pitch type
# Bounded like every other matchup component in engines/edge.py.
PITCH_MATCH_CAP = 8.0


@st.cache_data(ttl=21600, max_entries=1, show_spinner=False)
def _league_pitch_hr():
    """{pitch_type: league HR-per-batted-ball} or None if unavailable."""
    if not _LEAGUE_PATH.exists():
        return None
    try:
        t = pd.read_parquet(_LEAGUE_PATH)
        return {str(r.pitch_type): float(r.hr_rate) for r in t.itertuples(index=False)}
    except Exception:
        return None


def pitch_matchup_adj(batter_id, arsenal, batter_vs_pitch=None):
    """(adj, note) — this hitter against this pitcher's actual mix.

    arsenal: {pitch_type: usage_percent} from get_pitcher_statcast.
    batter_vs_pitch: optional {pitch_type: {"barrels": n, "bbe": n}} for
        the hitter. When absent the hitter term drops out and the result
        reflects the pitcher's mix against league-average damage — still
        real information (some arsenals are more homer-prone than others)
        without pretending to know something about this hitter.

    Returns (0, None) whenever the league table is missing or the arsenal
    is unusable. Never a fabricated number.
    """
    league = _league_pitch_hr()
    if not league or not arsenal:
        return 0, None

    total_usage = sum(v for v in arsenal.values() if v)
    if not total_usage:
        return 0, None

    league_overall = sum(league.values()) / len(league)
    expected, covered = 0.0, 0.0

    for pitch, usage in arsenal.items():
        rate = league.get(str(pitch))
        if rate is None or not usage:
            continue
        share = usage / total_usage

        # Hitter's own damage on this pitch, regressed hard toward league.
        mult = 1.0
        if batter_vs_pitch:
            hv = batter_vs_pitch.get(str(pitch)) or {}
            bbe = hv.get("bbe") or 0
            barrels = hv.get("barrels") or 0
            if bbe > 0:
                league_brl = hv.get("league_brl", 0.065)   # measured, passed in
                own = (barrels + K_HITTER_PITCH * league_brl) / (bbe + K_HITTER_PITCH)
                mult = own / league_brl if league_brl else 1.0

        expected += share * rate * mult
        covered += share

    if covered < 0.5:
        # Less than half the arsenal is identifiable — the number would
        # describe a pitcher we can't actually see.
        return 0, None

    baseline = league_overall * covered
    if baseline <= 0:
        return 0, None

    # Ratio to a league-average arsenal, scaled into edge points.
    ratio = expected / baseline
    adj = round(max(-PITCH_MATCH_CAP, min(PITCH_MATCH_CAP, (ratio - 1.0) * 20.0)), 1)
    if abs(adj) < 0.5:
        return 0, None
    word = "homer-prone mix" if adj > 0 else "mix suppresses HR"
    return adj, f"{word} ({adj:+.1f}, {covered*100:.0f}% of arsenal read)"
