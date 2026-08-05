"""
Roof status for KBO and NPB venues — the cheapest postponement signal
there is.

WHY THIS EXISTS

KBO and NPB only learn about a postponement AFTER it is announced:
kbo_precompute regex-matches "postponed/cancelled" off the schedule
page, npb_precompute reads a status field. Both look backwards. Neither
league has any weather data at all, so a subscriber betting a rain-risk
game had nothing on the site telling him so, and voids were the result.

The forecast half of that problem needs a weather provider this site
does not have and cannot currently pay for. This file is the half that
needs no provider at all: a game under a fixed roof CANNOT be rained
out. That is not a forecast or a model — it is a fact about a building,
it does not go stale between seasons, and it covers half the NPB slate.

WHAT IS DELIBERATELY NOT HERE

No coordinates. The obvious next step is a precipitation forecast per
venue, which needs latitude and longitude, and inventing those to
several decimal places would be exactly the kind of confident-looking
fabrication the rest of this codebase refuses. They get added alongside
a real forecast source, verified at the same time, or not at all.

ROOF CATEGORIES

    "dome"        Fixed roof. Rain is irrelevant. Certainty.
    "retractable" Roof that closes. In practice these games are not
                  rained out either, but the roof is a decision someone
                  makes rather than a property of the building, so it is
                  labelled separately rather than merged into "dome".
    "open"        Open air. Rain-out is possible; this file has nothing
                  further to say about how likely.

Anything not listed resolves to None — unknown, which must read
differently from "open". Same rule park_factors.py follows for its
unverified entries: a missing number stays missing rather than being
guessed into place.
"""

# Keyed on the stadium strings the slate builders actually emit — see
# STADIUMS in npb_precompute.py and the venue field in kbo_precompute.py.
# Matching on the venue rather than the club matters: two KBO clubs share
# Jamsil, and clubs move buildings.
NPB_VENUES = {
    "Tokyo Dome":         "dome",
    "Vantelin Dome":      "dome",
    "Kyocera Dome Osaka": "dome",
    "PayPay Dome":        "dome",
    # Belluna is roofed but its sides are open, so wind and blown-in rain
    # still reach the field. Rain-outs there are effectively unheard of,
    # which is why it counts as a dome for VOID purposes — the only
    # question this file answers — while the note below says what it
    # actually is rather than implying a sealed building.
    "Belluna Dome":       "dome",
    "Escon Field":        "retractable",
    "Jingu Stadium":      "open",
    "Koshien Stadium":    "open",
    "Yokohama Stadium":   "open",
    "Mazda Stadium":      "open",
    "Rakuten Mobile Park": "open",
    "Zozo Marine Stadium": "open",
}

# KBO venue strings come off MyKBOStats' venue div, which is free text
# rather than a fixed vocabulary, so these are matched case-insensitively
# on a distinctive substring instead of by exact equality.
KBO_VENUE_PATTERNS = (
    ("gocheok", "dome"),      # Gocheok Sky Dome — the only one in the league
    ("jamsil", "open"),
    ("sajik", "open"),
    ("incheon", "open"),
    ("landers", "open"),
    ("suwon", "open"),
    ("daegu", "open"),
    ("gwangju", "open"),
    ("champions field", "open"),
    ("daejeon", "open"),
    ("changwon", "open"),
)

_NOTES = {
    "Belluna Dome": "roofed, open sides — wind still plays, but not rained out",
    "Escon Field": "retractable roof — closed in bad weather",
}


def roof(league: str, stadium: str):
    """'dome' | 'retractable' | 'open' | None for a venue string.

    None means the venue is not in the table — unknown, NOT open air. A
    stadium this file has never heard of is usually a neutral-site or
    newly opened park, and calling it open air would invent the exact
    risk assessment the caller asked about.
    """
    if not stadium:
        return None
    s = str(stadium).strip()
    if league.lower() == "npb":
        return NPB_VENUES.get(s)
    if league.lower() == "kbo":
        low = s.lower()
        for needle, kind in KBO_VENUE_PATTERNS:
            if needle in low:
                return kind
        return None
    return None


def rainout_possible(league: str, stadium: str):
    """True / False / None — can this game be rained out?

    False is a real, certain answer and the whole point of the file.
    None is "we don't know", and the caller must render those two
    differently: "cannot be postponed for weather" and "we have no idea"
    are opposite statements.
    """
    r = roof(league, stadium)
    if r is None:
        return None
    return r == "open"


def roof_note(league: str, stadium: str):
    """A short phrase for the UI, or '' when there is nothing to say."""
    r = roof(league, stadium)
    if r is None:
        return ""
    if r == "open":
        return "open air"
    return _NOTES.get(str(stadium).strip(),
                      "domed — cannot be rained out")


def coverage(league: str):
    """(n_covered, n_listed) — how much of a league this table knows.

    Exposed so a test can assert the tables stay complete as venues
    change, rather than silently degrading to None for a club that moved.
    """
    if league.lower() == "npb":
        return len(NPB_VENUES), len(NPB_VENUES)
    if league.lower() == "kbo":
        return len(KBO_VENUE_PATTERNS), len(KBO_VENUE_PATTERNS)
    return 0, 0
