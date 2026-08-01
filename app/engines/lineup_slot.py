"""
How many times he actually gets to swing.

Every other number on this site measures how good a hitter's swing is.
None of them measures how OFTEN he takes it — and that gap changes
answers, not just decimals.

A leadoff hitter comes to the plate meaningfully more often than a
9-hole hitter, every single game, and home run probability scales almost
linearly with plate appearances. So a model built purely on skill can
rank a 9-hole bat above a leadoff bat correctly on quality and still be
wrong about the actual question: who is most likely to go deep tonight.

MEASURED, NOT ASSUMED
---------------------
No table of "expected PA by slot" is hardcoded here. The nightly build
measures the one real quantity involved — how many plate appearances a
team actually gets in a game (see precompute.build_pa_per_game) — and
the per-slot split is then pure arithmetic, because a batting order
simply wraps around:

    slot i gets  (T - i + 1) / 9   plate appearances, on average

Deliberately NOT rounded up. In any single game a hitter gets a whole
number of trips, but the expectation across games is fractional, and
rounding destroys the very distinction this is measuring: at T = 38,
ceil() hands slots 2 through 9 an identical 4 PA and collapses eight
slots into one value. The fractional form keeps the gradient — 4.22 for
the 2-hole, 3.33 for the 9 — which is what actually separates them.

The figure tracks whatever the league is really doing; a low-scoring era
moves it on its own, with nothing to update by hand.

WHY IT'S CAPPED
---------------
Opportunity is real but it is not the whole story, and a hitter batting
ninth for a good reason shouldn't be dragged down twice — once by his
own weak skill metrics and again by his slot. The adjustment is bounded
like every other matchup component, so it reorders bats of similar
quality without overturning a genuine skill gap.
"""
import streamlit as st

# Bounded, like BvP, zone fit, bullpen and park. Opportunity between the
# best and worst slot is worth roughly 15-20% more chances, so a band of
# this size reflects it without letting slot dominate skill.
SLOT_CAP = 5.0

# Used only when the nightly measurement is unavailable. This is NOT a
# guessed league constant — it's a neutral value that makes the whole
# adjustment vanish rather than apply an invented one. See expected_pa.
_NEUTRAL = None


def _slot_from_batting_order(batting_order):
    """1-9 from MLB's battingOrder code, or None.

    MLB encodes the order as a three-digit number: 100 is first, 200
    second, through 900. A substitute entering that spot gets 101, 201
    and so on, so integer division by 100 recovers the slot for starters
    and substitutes alike.
    """
    if batting_order is None:
        return None
    try:
        slot = int(batting_order) // 100
    except (TypeError, ValueError):
        return None
    return slot if 1 <= slot <= 9 else None


def expected_pa(slot, pa_per_team_game):
    """Plate appearances this slot can expect, or None.

    Pure arithmetic on a measured input. Returns None when the league
    figure is unavailable, which makes the adjustment sit out rather
    than apply a fabricated one.
    """
    if slot is None or not pa_per_team_game:
        return None
    if not 1 <= slot <= 9:
        return None
    # Fractional on purpose — see the module docstring. Rounding up
    # collapses most of the order into one value.
    return round((pa_per_team_game - slot + 1) / 9.0, 3)


def slot_opportunity_adj(batting_order, pa_per_team_game):
    """(adj, note) — opportunity for this lineup slot.

    Scaled against the average slot rather than against slot 1, so the
    middle of the order sits near zero and the adjustment is genuinely
    two-sided: the top of the order gains, the bottom gives back.

    Returns (0, None) when the slot is unknown (an unconfirmed lineup has
    no batting order at all) or the league PA figure hasn't been built
    yet. Never invents an opportunity it can't measure.
    """
    slot = _slot_from_batting_order(batting_order)
    exp = expected_pa(slot, pa_per_team_game)
    if exp is None:
        return 0, None

    # Mean expectation across all nine slots — the neutral point.
    all_slots = [expected_pa(i, pa_per_team_game) for i in range(1, 10)]
    all_slots = [v for v in all_slots if v is not None]
    if not all_slots:
        return 0, None
    mean_pa = sum(all_slots) / len(all_slots)
    if mean_pa <= 0:
        return 0, None

    adj = (exp - mean_pa) / mean_pa * SLOT_CAP * 2.0
    adj = round(max(-SLOT_CAP, min(SLOT_CAP, adj)), 1)
    if abs(adj) < 0.5:
        return 0, None
    word = "extra look" if adj > 0 else "fewer looks"
    return adj, f"bats {slot}{_ordinal(slot)}, ~{exp:.1f} PA ({word}, {adj:+.1f})"


def _ordinal(n):
    return {1: "st", 2: "nd", 3: "rd"}.get(n if n < 20 else n % 10, "th")


@st.cache_data(ttl=21600, max_entries=1, show_spinner=False)
def league_pa_per_game():
    """Measured PA per team-game from the nightly manifest, or None."""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("pa_per_team_game")
    except Exception:
        return None

def pen_exposure(slot, pa_per_team_game, starter_ip):
    """Share of this slot's plate appearances that come against the PEN.

    The whole reason the bullpen matters differently by lineup position.
    A starter who averages 5.1 IP leaves roughly 3.2 innings to the pen,
    and the top of the order turns over more often in those innings than
    the bottom does — so the leadoff hitter carries meaningfully more pen
    exposure than the 8-hole, and a pen adjustment applied equally to
    both is wrong for both.

    Returns a fraction in [0, 1], or None when either input is missing.
    None means the caller sits the adjustment out rather than applying a
    fabricated one — same rule as expected_pa above.

    Deliberately simple: PAs are assumed to arrive at a steady rate
    through the game, so the pen's share of innings is the pen's share of
    plate appearances. That is an approximation, and it is the only one
    here; everything it consumes is measured.
    """
    pa = expected_pa(slot, pa_per_team_game)
    if pa is None or not starter_ip or starter_ip <= 0:
        return None
    game_ip = 9.0
    pen_ip = max(0.0, game_ip - float(starter_ip))
    if pen_ip <= 0:
        return 0.0
    return round(min(1.0, pen_ip / game_ip), 3)
