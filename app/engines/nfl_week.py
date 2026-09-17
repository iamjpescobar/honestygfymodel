"""NFL week math, the week-aware slate guard, and the Mismatch Finder.

WHY THIS IS NOT IN slate_guard

slate_guard answers "is this file for TODAY?" by comparing one date. A
football slate is a RANGE — Tuesday through Monday — and a Sunday game
read on Wednesday is still this week's game. Registering NFL there would
mean stamping a single fake date on a week, which is a right-looking
number under a wrong label (standing rule 9). So the NFL file is stamped
with week_start_et / week_end_et, and this module applies the same rule
slate_guard applies — a stale slate is NOT a slate — to the range.

Pure functions only apart from load_week's file read. No streamlit, no
requests, so the tests and nfl_precompute can import it freely.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# 2026 kickoff: Wednesday Sept 9 (Patriots at Seahawks). Verified against
# the NFL's published schedule on 2026-09-15. Week 1 therefore runs from
# Tuesday Sept 8 to Monday Sept 14, and every later week is the next
# seven days — Thanksgiving, Christmas and the Week 18 Saturday games all
# still fall inside their own Tuesday-to-Monday window.
SEASON_START = date(2026, 9, 9)
WEEK1_TUESDAY = date(2026, 9, 8)
SEASON_WEEKS = 18

_PUBLISHED = Path(__file__).resolve().parent.parent / "data"
_REPO = Path(__file__).resolve().parents[2] / "data"


def week_of(d):
    """Regular-season week number for a date, or None before week 1.

    Returns numbers past 18 as-is so a caller can tell "the regular
    season is over" apart from "not started".
    """
    if d < WEEK1_TUESDAY:
        return None
    return (d - WEEK1_TUESDAY).days // 7 + 1


def week_window(week):
    """(tuesday, monday) for a week number."""
    start = WEEK1_TUESDAY + timedelta(days=7 * (week - 1))
    return start, start + timedelta(days=6)


def tv_window(kick_et):
    """The slot a game belongs to, from its Eastern kickoff.

    Sunday is split at the hours the league actually uses: the
    international morning games (9:30), the early window (1:00), the
    late window (4:05/4:25) and the night game (8:20).
    """
    wd, hr = kick_et.weekday(), kick_et.hour
    if wd == 6:
        if hr < 12:
            return "Sunday Morning"
        if hr < 16:
            return "Sunday Early"
        if hr < 19:
            return "Sunday Late"
        return "Sunday Night"
    return {0: "Monday Night", 1: "Tuesday", 2: "Wednesday",
            3: "Thursday Night", 4: "Friday", 5: "Saturday"}[wd]


WINDOW_ORDER = ["Tuesday", "Wednesday", "Thursday Night", "Friday",
                "Saturday", "Sunday Morning", "Sunday Early",
                "Sunday Late", "Sunday Night", "Monday Night"]


def _read_all():
    best = None
    for root in (_PUBLISHED, _REPO):
        try:
            p = json.loads((root / "nfl" / "games.json").read_text()) or {}
        except Exception:
            continue
        if best is None or (p.get("week_end_et") or "") > (best.get("week_end_et") or ""):
            best = p
    return best


def load_week(today=None, _payload=None):
    """(payload, state) where state is one of:

      "current"  — the file's week contains today;
      "stale"    — the file's week ended before today (games shown: NONE);
      "offseason"— the file says preseason/postseason;
      "missing"  — nothing readable on disk.

    A stale week returns payload with games=[] — same contract as
    slate_guard.load_slate: a caller that ignores the state still cannot
    present last week's games as this week's.
    """
    today = today or datetime.now(EASTERN).date()
    p = _payload if _payload is not None else _read_all()
    if not p:
        return None, "missing"
    if p.get("phase") in ("preseason", "postseason"):
        return p, "offseason"
    try:
        end = date.fromisoformat(p.get("week_end_et") or "")
    except ValueError:
        return dict(p, games=[]), "missing"
    if end < today:
        return dict(p, games=[]), "stale"
    return p, "current"


def staleness_note(payload, state, today=None):
    today = today or datetime.now(EASTERN).date()
    if state == "missing":
        return ("No NFL week on disk yet. Nothing is shown rather than "
                "inventing a slate — the nightly build publishes it.")
    if state == "stale":
        return (f"The NFL file on disk is week {payload.get('week')} "
                f"(ended {payload.get('week_end_et')}). The nightly build "
                f"hasn't published week {week_of(today)} yet, so last "
                f"week's games aren't shown as this week's.")
    if state == "offseason":
        if payload.get("phase") == "preseason":
            return f"The regular season opens {payload.get('season_start')}."
        return ("The regular season is over. Playoff coverage isn't built, "
                "so nothing is shown rather than a partial board.")
    return ""


# ----------------------------------------------------------------------
# Mismatch Finder
# ----------------------------------------------------------------------
# (label, offense stat, defense-allowed stat on the OTHER team)
# Rank 1 = best at that thing for the team that owns the number, so a
# strong unit has a SMALL rank and a leaky defense has a LARGE one.
UNIT_PAIRS = [
    ("Pass game", "pass_ypg", "pass_allowed"),
    ("Run game", "rush_ypg", "rush_allowed"),
    ("Scoring", "pf_pg", "pa_pg"),
    ("3rd down", "third_pct", "third_allowed_pct"),
    ("Red zone", "rz_td_pct", "rz_td_allowed_pct"),
    ("Pass rush", "sacks_pg", "sacked_pg"),   # defense's sacks vs the other line
]


def mismatches(games):
    """Every unit-vs-unit matchup on the slate, biggest gap first.

    edge = defender_rank - attacker_rank. A #3 pass offense into the #30
    pass defense is +27. Only pairs where BOTH ranks exist are returned;
    a missing rank is never treated as last place.

    "Pass rush" reads the other way round on purpose: the attacker is the
    defense that gets home (sacks_pg) and the defender is the offensive
    line that allows it (sacked_pg, rank 1 = fewest allowed).
    """
    rows = []
    for g in games or []:
        for side, other in (("away", "home"), ("home", "away")):
            me = g.get(f"{side}_profile") or {}
            op = g.get(f"{other}_profile") or {}
            mr, orr = me.get("ranks") or {}, op.get("ranks") or {}
            for label, a_stat, d_stat in UNIT_PAIRS:
                ar, dr = mr.get(a_stat), orr.get(d_stat)
                if ar is None or dr is None:
                    continue
                rows.append({
                    "game": f'{g.get("away_abbr") or g.get("away")} @ '
                            f'{g.get("home_abbr") or g.get("home")}',
                    "window": g.get("window") or "",
                    "team": g.get(side), "abbr": g.get(f"{side}_abbr") or "",
                    "vs": g.get(other), "vs_abbr": g.get(f"{other}_abbr") or "",
                    "unit": label,
                    "att_value": me.get(a_stat), "att_rank": ar,
                    "def_value": op.get(d_stat), "def_rank": dr,
                    "edge": dr - ar,
                    "gp": min(me.get("gp") or 0, op.get("gp") or 0),
                    "status": g.get("status"),
                })
    rows.sort(key=lambda r: (-r["edge"], r["att_rank"]))
    return rows


def rank_label(rank, of):
    if rank is None:
        return "\u2014"
    return f"#{rank}" + (f" of {of}" if of else "")


def edge_tier(edge, n_teams=32):
    """A word for a rank gap, scaled to how many teams are ranked.

    Thresholds are fractions of the league, NOT fitted to outcomes —
    they describe how far apart two ranks are, nothing more.
    """
    n = max(int(n_teams or 32), 2)
    if edge >= 0.6 * n:
        return "Glaring"
    if edge >= 0.35 * n:
        return "Strong"
    if edge >= 0.15 * n:
        return "Lean"
    if edge <= -0.35 * n:
        return "Uphill"
    return "Even"


PROP_COLUMNS = {
    "QB": [("pass_yds", "Pass Yds"), ("pass_att", "Att"), ("pass_cmp", "Cmp"),
           ("pass_td", "TD"), ("pass_int", "INT"), ("rush_yds", "Rush Yds")],
    "RB": [("rush_yds", "Rush Yds"), ("rush_att", "Car"), ("rush_td", "Rush TD"),
           ("rece_rec", "Rec"), ("rece_yds", "Rec Yds"), ("rece_tgt", "Tgt")],
    "REC": [("rece_yds", "Rec Yds"), ("rece_rec", "Rec"), ("rece_tgt", "Tgt"),
            ("rece_td", "Rec TD"), ("rece_long", "Long")],
}

# What the OPPOSING defense allows for each role's headline stat.
ROLE_DEFENSE = {"QB": "pass_allowed", "RB": "rush_allowed", "REC": "pass_allowed"}


def prop_rows(games, role, window="season"):
    """Flat rows for the Prop Lab: one per player of `role` on the slate.

    window: "season" | "l3" | "last" — which of the three lines to show.
    """
    suffix = {"season": "", "l3": "_l3", "last": "_last"}.get(window, "")
    cols = PROP_COLUMNS[role]
    out = []
    for g in games or []:
        for side, other in (("away", "home"), ("home", "away")):
            opp = g.get(f"{other}_profile") or {}
            dstat = ROLE_DEFENSE[role]
            for p in g.get(f"{side}_players") or []:
                if p.get("role") != role:
                    continue
                row = {"Player": p.get("name"), "Team": g.get(f"{side}_abbr") or g.get(side),
                       "Opp": g.get(f"{other}_abbr") or g.get(other),
                       "Pos": p.get("pos") or "", "Status": p.get("status") or "",
                       "GP": p.get("gp")}
                for key, label in cols:
                    row[label] = p.get(f"{key}{suffix}")
                row["Opp allows"] = opp.get(dstat)
                row["Opp rank"] = (opp.get("ranks") or {}).get(dstat)
                out.append(row)
    lead = cols[0][1]
    out.sort(key=lambda r: -(r.get(lead) if r.get(lead) is not None else -1))
    return out
