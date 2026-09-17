"""NHL season phase, the Crease Report and the Shots Lab.

Pure helpers — no streamlit, no requests. The slate itself goes through
slate_guard ("nhl" is registered there with Eastern dating), because
hockey IS a nightly slate and the per-date guard fits it exactly.

DATES, verified against the NHL's own announcements on 2026-09-15:
  preseason   Sat Sept 19 – Sat Sept 26 (65 games, max four per club)
  opening     Tue Sept 29 (84-game season, first under the new CBA)

PRESEASON IS REAL BUT IT IS NOT RESEARCH. Split squads, AHL call-ups
and third-string goalies make exhibition box scores the wrong sample
for a regular-season prop, so the pipeline parses them (that is how the
parser gets verified before opening night) and counts them NOWHERE.
"""
from datetime import date

PRESEASON_START = date(2026, 9, 19)
REGULAR_SEASON_START = date(2026, 9, 29)
SEASON_GAMES = 84


def phase(d):
    if d < PRESEASON_START:
        return "offseason"
    if d < REGULAR_SEASON_START:
        return "preseason"
    return "regular"


def days_until_opening(d):
    return max((REGULAR_SEASON_START - d).days, 0)


def countdown_text(d):
    n = days_until_opening(d)
    if n == 0:
        return "Opening night is tonight."
    if n == 1:
        return "Opening night is tomorrow."
    return f"{n} days to opening night ({REGULAR_SEASON_START:%a %b} {REGULAR_SEASON_START.day})."


def fmt_svp(v):
    """.912 style — how hockey prints save percentage."""
    if v is None:
        return "\u2014"
    return f"{v:.3f}".lstrip("0")


def crease_rows(goalies, teams_tonight=None):
    """Goalie table rows, most starts first.

    teams_tonight: optional set of team names — when given, only those
    goalies are returned (the tonight-only filter on the page).
    """
    rows = []
    for g in (goalies or {}).values():
        if teams_tonight and g.get("team") not in teams_tonight:
            continue
        rows.append({
            "Goalie": g.get("name"), "Team": g.get("abbr") or g.get("team"),
            "GP": g.get("gp"), "Starts": g.get("starts"),
            "Crease share": g.get("crease_share"),
            "SV%": g.get("sv_pct"), "GAA": g.get("gaa"),
            "L5 SV%": g.get("l5_sv_pct"), "SA/60": g.get("sa_per60"),
            "Last start": g.get("last_start"),
        })
    rows.sort(key=lambda r: (-(r["Starts"] or 0), -(r["SV%"] or 0)))
    return rows


# (key in the skater summary, column label)
SHOT_COLUMNS = {
    "season": [("sog", "SOG/G"), ("pts", "P/G"), ("g", "G/G"), ("a", "A/G"),
               ("toi", "TOI"), ("hits", "HIT/G"), ("blk", "BLK/G")],
    "l5": [("l5_sog", "SOG/G"), ("l5_pts", "P/G"), ("l5_g", "G/G"),
           ("l5_a", "A/G"), ("l5_toi", "TOI"), ("l5_hits", "HIT/G"), ("l5_blk", "BLK/G")],
    "l10": [("l10_sog", "SOG/G"), ("l10_pts", "P/G"), ("l10_g", "G/G"),
            ("l10_a", "A/G"), ("l10_toi", "TOI"), ("l10_hits", "HIT/G"), ("l10_blk", "BLK/G")],
}

# Hit rates are COUNTS over games played — "3 of his 10 games had 3+
# shots" — not a probability model. The page says so.
HIT_RATES = [("sog2_rate", "2+ SOG %"), ("sog3_rate", "3+ SOG %"),
             ("pt1_rate", "1+ PT %")]


def shots_rows(games, window="season", min_gp=1):
    """Tonight's skaters, one row each, sorted by shots per game."""
    cols = SHOT_COLUMNS.get(window, SHOT_COLUMNS["season"])
    out = []
    for g in games or []:
        for side, other in (("away", "home"), ("home", "away")):
            opp = g.get(f"{other}_profile") or {}
            for p in g.get(f"{side}_skaters") or []:
                if (p.get("gp") or 0) < min_gp:
                    continue
                row = {"Skater": p.get("name"), "Pos": p.get("pos") or "",
                       "Team": g.get(f"{side}_abbr") or g.get(side),
                       "Opp": g.get(f"{other}_abbr") or g.get(other),
                       "GP": p.get("gp")}
                for key, label in cols:
                    row[label] = p.get(key)
                for key, label in HIT_RATES:
                    row[label] = p.get(key)
                row["Opp SA/G"] = opp.get("sa_pg")
                out.append(row)
    out.sort(key=lambda r: -(r.get("SOG/G") if r.get("SOG/G") is not None else -1))
    return out


def tape_rows(away_prof, home_prof):
    """(label, away, home, higher_is_better) for the tale-of-the-tape."""
    a, h = away_prof or {}, home_prof or {}
    spec = [
        ("Record (W-L-OTL)", "record", None),
        ("Points %", "pts_pct", True),
        ("Goals for / G", "gf_pg", True),
        ("Goals against / G", "ga_pg", False),
        ("Shots for / G", "sf_pg", True),
        ("Shots against / G", "sa_pg", False),
        ("Shot share %", "sf_pct", True),
        ("Power play %", "pp_pct", True),
        ("Penalty kill %", "pk_pct", True),
        ("Avg game total", "avg_total", None),
        ("Last 10", "l10", None),
    ]
    return [(lab, a.get(k), h.get(k), hb) for lab, k, hb in spec]
