"""
MLB Park Factors — real, complete data pulled directly from Baseball
Savant's own Park Factors leaderboard
(baseballsavant.mlb.com/leaderboard/statcast-park-factors), read off
screenshots of the live page since it renders via JavaScript and has
no simple CSV export.

IMPORTANT — this is the OVERALL park factor (wOBA-based, "index_wOBA"),
NOT a home-run-specific number. Baseball Savant's HR-specific factor
lives behind a stat picker on that same page that couldn't be reached
programmatically or reliably clicked into during this build. Rather
than mislabel a real overall-offense number as HR-specific — which
would be wrong for a park like Fenway (great for hitting overall,
unremarkable for homers specifically) — this is presented honestly as
what it actually is: real, general offensive favorability, not a
pure home-run number.

100 = league average. 113 means ~13% more offense than a neutral park.
2024-2026 rolling window, "Both" handedness split, as shown on
Savant's own page at the time this was gathered.

Athletics/Sutter Health Park is the one team missing a real number —
it fell off the bottom of the screenshots gathered and was never
independently re-verified, so it stays honestly unverified rather
than guessed.
"""

PARK_FACTORS = {
    "Colorado Rockies": {"venue": "Coors Field", "park_factor": 113, "verified": True},
    "Arizona Diamondbacks": {"venue": "Chase Field", "park_factor": 103, "verified": True},
    "Baltimore Orioles": {"venue": "Oriole Park at Camden Yards", "park_factor": 103, "verified": True},
    "Minnesota Twins": {"venue": "Target Field", "park_factor": 103, "verified": True},
    "Cincinnati Reds": {"venue": "Great American Ball Park", "park_factor": 102, "verified": True},
    "Boston Red Sox": {"venue": "Fenway Park", "park_factor": 102, "verified": True},
    "Philadelphia Phillies": {"venue": "Citizens Bank Park", "park_factor": 102, "verified": True},
    "Washington Nationals": {"venue": "Nationals Park", "park_factor": 102, "verified": True},
    "Los Angeles Dodgers": {"venue": "Dodger Stadium", "park_factor": 101, "verified": True},
    "Toronto Blue Jays": {"venue": "Rogers Centre", "park_factor": 101, "verified": True},
    "New York Yankees": {"venue": "Yankee Stadium", "park_factor": 101, "verified": True},
    "Kansas City Royals": {"venue": "Kauffman Stadium", "park_factor": 101, "verified": True},
    "Houston Astros": {"venue": "Daikin Park", "park_factor": 100, "verified": True},
    "Los Angeles Angels": {"venue": "Angel Stadium", "park_factor": 100, "verified": True},
    "Pittsburgh Pirates": {"venue": "PNC Park", "park_factor": 100, "verified": True},
    "Miami Marlins": {"venue": "loanDepot park", "park_factor": 100, "verified": True},
    "Detroit Tigers": {"venue": "Comerica Park", "park_factor": 100, "verified": True},
    "New York Mets": {"venue": "Citi Field", "park_factor": 99, "verified": True},
    "Atlanta Braves": {"venue": "Truist Park", "park_factor": 99, "verified": True},
    "Cleveland Guardians": {"venue": "Progressive Field", "park_factor": 98, "verified": True},
    "Chicago White Sox": {"venue": "Rate Field", "park_factor": 98, "verified": True},
    "St. Louis Cardinals": {"venue": "Busch Stadium", "park_factor": 97, "verified": True},
    "Milwaukee Brewers": {"venue": "American Family Field", "park_factor": 97, "verified": True},
    "Tampa Bay Rays": {"venue": "Tropicana Field", "park_factor": 97, "verified": True},
    "San Diego Padres": {"venue": "Petco Park", "park_factor": 97, "verified": True},
    "San Francisco Giants": {"venue": "Oracle Park", "park_factor": 97, "verified": True},
    "Chicago Cubs": {"venue": "Wrigley Field", "park_factor": 96, "verified": True},
    "Texas Rangers": {"venue": "Globe Life Field", "park_factor": 93, "verified": True},
    "Seattle Mariners": {"venue": "T-Mobile Park", "park_factor": 91, "verified": True},
}

_DEFAULT = {"venue": "Unknown Venue", "park_factor": None, "verified": False}


def get_park_factor(home_team: str) -> dict:
    """Returns real park factor info for a team's home park. Always
    check `verified` before displaying `park_factor` — it's None for
    Athletics/Sutter Health Park, the one team without a re-verified
    real number, rather than a guess."""
    return PARK_FACTORS.get(home_team, _DEFAULT)
