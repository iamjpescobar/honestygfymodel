"""
Milestone watch (10-14) — who is close to a round career or season number
(a 300th goal, 10,000 passing yards, 3,000 hits), what he needs tonight,
and the model's chance he gets it.

WHERE THE CAREER NUMBER COMES FROM
----------------------------------
career now = career BEFORE this season  +  this season so far.

  - Before this season: ESPN's per-season career table for NHL and NFL
    players (fetched ONCE per player per season and committed, see
    PriorCareer below); MLB's stats API career line, read live (one call
    for a whole lineup).
  - This season: the nightly's own box scores — the same lines every
    model on the site is built on, so the count moves the morning after
    every game.

Splitting it that way means the slow fetch happens once a season and the
number is never a game behind. A season ESPN lists twice (a traded
player's two teams plus a combined row) is read once (season_value).
A stat ESPN does not carry for a player is MISSING, never zero — he is
simply not on the watch for it (rule 6).

WHAT COUNTS AS "CLOSE"
----------------------
REACH: the most a player can plausibly need in one game for each stat —
2 goals, 3 points, 400 passing yards, 2 home runs. Further away than that
is not tonight's story.

THE CHANCE
----------
Read by the page from the same distribution every board prices (the
skater's / player's pmfs; for MLB the batter's market chances), DELIVERED
through the stat's tested curve where one exists. A milestone is not an
edge: books shade the props people love to bet. The chance is what the
model says; the price check is still the Bet Finder's.

Pure — no streamlit, no requests.
"""

def _ladder(first, step, top, extra=()):
    return sorted(set(list(extra) + list(range(first, top + 1, step))))


# (stat, label, noun for "300th ___", marks). Round numbers people
# actually talk about; every step is a real broadcast graphic.
CAREER = {
    "nhl": (
        ("g", "Goals", "career goal", _ladder(100, 100, 1000, extra=(50,))),
        ("a", "Assists", "career assist", _ladder(100, 100, 2000)),
        ("pts", "Points", "career point", _ladder(100, 100, 3000)),
        ("gp", "Games played", "career game", (500, 1000, 1500)),
    ),
    "nfl": (
        ("pass_yds", "Passing yards", "career passing yards", _ladder(5000, 5000, 90000)),
        ("pass_td", "Passing TDs", "career passing TD", _ladder(25, 25, 650)),
        ("rush_yds", "Rushing yards", "career rushing yards", _ladder(1000, 1000, 20000)),
        ("rec_yds", "Receiving yards", "career receiving yards", _ladder(1000, 1000, 25000)),
        ("rec", "Receptions", "career catch", _ladder(100, 100, 1600)),
        ("td", "Rush + rec TDs", "career rush/rec TD", _ladder(25, 25, 225)),
    ),
    "nba": (
        ("pts", "Points", "career point", _ladder(5000, 1000, 45000, extra=(1000, 2500))),
        ("reb", "Rebounds", "career rebound", _ladder(1000, 1000, 16000)),
        ("ast", "Assists", "career assist", _ladder(1000, 1000, 16000)),
        ("tpm", "3-pointers made", "career three", _ladder(250, 250, 4500)),
        ("gp", "Games played", "career game", (500, 1000, 1500)),
    ),
    "mlb": (
        ("hr", "Home runs", "career home run", _ladder(100, 50, 800)),
        ("h", "Hits", "career hit", _ladder(500, 500, 4500)),
        ("rbi", "RBI", "career RBI", _ladder(500, 250, 2500)),
        ("sb", "Stolen bases", "career steal", _ladder(100, 100, 1000)),
    ),
}
SEASON = {
    "nhl": (
        ("g", "Goals", "goal of the season", (20, 30, 40, 50, 60, 70)),
        ("pts", "Points", "point of the season", (50, 75, 100, 125, 150)),
    ),
    "nfl": (
        ("pass_yds", "Passing yards", "passing yards this season", (3000, 4000, 5000)),
        ("pass_td", "Passing TDs", "passing TD of the season", (20, 30, 40, 50)),
        ("rush_yds", "Rushing yards", "rushing yards this season", (1000, 1500, 2000)),
        ("rec_yds", "Receiving yards", "receiving yards this season", (1000, 1500, 2000)),
        ("rec", "Receptions", "catch of the season", (100, 125, 150)),
        ("td", "Rush + rec TDs", "rush/rec TD of the season", (10, 15, 20, 25)),
    ),
    "nba": (
        ("pts", "Points", "point of the season", (1000, 1500, 2000)),
        ("reb", "Rebounds", "rebound of the season", (500, 750, 1000)),
        ("ast", "Assists", "assist of the season", (500, 750)),
        ("tpm", "3-pointers made", "three of the season", (200, 250, 300)),
    ),
    "mlb": (),
}
# The most a player can plausibly need in ONE game to count as "close".
REACH = {"g": 2, "a": 2, "pts": 3, "gp": 1,
         "pass_yds": 400, "pass_td": 4, "rush_yds": 175, "rec_yds": 175, "rec": 12, "td": 3,
         "hr": 2, "h": 3, "rbi": 4, "sb": 2}
# Basketball counts are bigger: "pts" is 3 in hockey, 45 here.
REACH_BY = {"nba": {"pts": 45, "reb": 18, "ast": 15, "tpm": 7, "gp": 1}}


def reach(sport, stat):
    return (REACH_BY.get(sport) or {}).get(stat, REACH.get(stat, 0))


# Yardage reads "300 yards", counts read "2".
YARDS = {"pass_yds", "rush_yds", "rec_yds"}


def ordinal(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n:,}{suf}"


def next_mark(total, marks):
    """The first mark ABOVE total (a player sitting on 300 is chasing 400)."""
    if total is None:
        return None
    for m in marks:
        if m > total:
            return m
    return None


def describe(stat, mark, noun):
    if stat in YARDS:
        return f"{mark:,} {noun}"
    return f"{ordinal(mark)} {noun}"


def needs(career=None, season=None, sport="nhl"):
    """Every milestone within REACH: [{"stat", "label", "scope", "mark",
    "have", "need", "what"}], nearest first. career / season: {stat: total}
    (a stat missing from either is skipped, never read as zero)."""
    out = []
    for scope, table, nums in (("career", CAREER.get(sport) or (), career or {}),
                               ("season", SEASON.get(sport) or (), season or {})):
        for stat, label, noun, marks in table:
            have = nums.get(stat)
            if have is None:
                continue
            mark = next_mark(have, marks)
            if mark is None:
                continue
            need = mark - have
            if need <= 0 or need > reach(sport, stat):
                continue
            out.append({"stat": stat, "label": label, "scope": scope, "mark": mark,
                        "have": have, "need": need, "what": describe(stat, mark, noun)})
    # The one item per stat that matters most: a career mark beats a
    # season mark for the same stat on the same night.
    out.sort(key=lambda x: (x["need"] / max(1, reach(sport, x["stat"])), x["scope"] != "career"))
    return out


def crossed(before, after, sport="nhl"):
    """Marks passed between two totals: [(scope, stat, mark, what)]."""
    out = []
    for scope, table in (("career", CAREER.get(sport) or ()), ("season", SEASON.get(sport) or ())):
        b, a = (before or {}).get(scope) or {}, (after or {}).get(scope) or {}
        for stat, _label, noun, marks in table:
            x, y = b.get(stat), a.get(stat)
            if x is None or y is None or y <= x:
                continue
            for m in marks:
                if x < m <= y:
                    out.append((scope, stat, m, describe(stat, m, noun)))
    return out


def short(item):
    """'2 from his 300th career goal' — the line a board prints."""
    n = item["need"]
    unit = "yds" if item["stat"] in YARDS else ""
    return f"{n:,}{(' ' + unit) if unit else ''} from his {item['what']}"


# ----------------------------------------------------------------------
# This season, from the nightly's own box scores
# ----------------------------------------------------------------------
def nhl_season(lines):
    """{g, a, pts, gp} from one skater's regular-season box lines."""
    lines = [ln for ln in lines or [] if ln]
    if not lines:
        return {"g": 0, "a": 0, "pts": 0, "gp": 0}
    g = sum(ln.get("g") or 0 for ln in lines)
    a = sum(ln.get("a") or 0 for ln in lines)
    return {"g": int(g), "a": int(a), "pts": int(g + a), "gp": len(lines)}


def nfl_season(games):
    """{pass_yds, pass_td, rush_yds, rec_yds, rec, td} from one player's
    box lines this season (the nightly's logs[pid]["games"].values())."""
    out = {k: 0 for k in ("pass_yds", "pass_td", "rush_yds", "rec_yds", "rec", "td")}
    for gm in games or []:
        ps, ru, re_ = gm.get("passing") or {}, gm.get("rushing") or {}, gm.get("receiving") or {}
        out["pass_yds"] += ps.get("yds") or 0
        out["pass_td"] += ps.get("td") or 0
        out["rush_yds"] += ru.get("yds") or 0
        out["rec_yds"] += re_.get("yds") or 0
        out["rec"] += re_.get("rec") or 0
        out["td"] += (ru.get("td") or 0) + (re_.get("td") or 0)
    return {k: int(v) for k, v in out.items()}


def nba_season(games):
    """{pts, reb, ast, tpm, gp} from one player's regular-season game
    tuples this season (engines/nba_model.IDX)."""
    games = [g for g in games or [] if g and g[3]]
    out = {"pts": 0, "reb": 0, "ast": 0, "tpm": 0, "gp": len(games)}
    for g in games:
        for k, i in (("pts", 4), ("reb", 5), ("ast", 6), ("tpm", 7)):
            out[k] += int(g[i] or 0)
    return out


def add(prior, season):
    """career now = prior + this season, stat by stat; a stat the prior
    table lacks stays missing."""
    return {k: int(v + (season or {}).get(k, 0)) for k, v in (prior or {}).items()
            if v is not None}


# ----------------------------------------------------------------------
# ESPN's per-season career table (site.web.api common/v3 .../stats)
# ----------------------------------------------------------------------
# our stat -> ESPN stat names (first one present wins); derived sums below
ESPN_NAMES = {
    "nhl": {"g": ("goals",), "a": ("assists",), "pts": ("points",),
            "gp": ("gamesPlayed", "games")},
    "nfl": {"pass_yds": ("passingYards",), "pass_td": ("passingTouchdowns",),
            "rush_yds": ("rushingYards",), "rec_yds": ("receivingYards",),
            "rec": ("receptions",), "rush_td": ("rushingTouchdowns",),
            "rec_td": ("receivingTouchdowns",)},
}
DERIVED = {"nhl": {"pts": ("g", "a")}, "nfl": {"td": ("rush_td", "rec_td")}}
ESPN_NAMES["nba"] = {"pts": ("points",), "reb": ("totalRebounds", "rebounds"),
                     "ast": ("assists",),
                     "tpm": ("threePointFieldGoalsMade",
                             "threePointFieldGoalsMade-threePointFieldGoalsAttempted"),
                     "gp": ("gamesPlayed",)}
_SKIP_CATS = ("average", "avg", "per")


def _num(x):
    t = str(x).replace(",", "")
    try:
        return float(t)
    except (TypeError, ValueError):
        # "made-attempted" cells (basketball threes): the made part
        head = t.split("-")[0] if "-" in t[1:] else None
        try:
            return float(head) if head else None
        except ValueError:
            return None


def season_label(row):
    s = (row or {}).get("season") or {}
    if isinstance(s, dict):
        return str(s.get("displayName") or s.get("year") or "")
    return str(s or "")


def season_value(vals):
    """One season's number from its rows: a traded player's per-team rows
    are summed, unless one row already IS their sum (ESPN's combined row),
    which is then taken alone."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    if len(vals) > 1:
        tot = sum(vals)
        for v in vals:
            if abs(2 * v - tot) < 0.5:
                return v
        return tot
    return vals[0]


def is_current_season(label, sport, start_year):
    """Is this ESPN season label the one being played now? NFL labels a
    season by its start year ("2026"). NHL, as the 10-14 nightly's probe
    showed, by two-digit years ("26-27"); "2026-27" and the end year
    ("2027") are accepted too."""
    lab = str(label or "").strip()
    if sport == "nfl":
        return lab == str(start_year)
    a, b = str(start_year), str(start_year + 1)
    return lab in (f"{a[2:]}-{b[2:]}", f"{a}-{b[2:]}", f"{a}-{b}", b)


def parse_espn_career(data, sport, start_year):
    """{"prior": {stat: total before this season}, "seasons": n,
    "labels": [...], "current_seen": bool} from ESPN's per-season table,
    or None when no wanted stat could be read."""
    names = ESPN_NAMES.get(sport) or {}
    by_stat = {}            # stat -> {season label -> {category -> [row values]}}
    labels = set()
    cats = (data or {}).get("categories") if isinstance(data, dict) else None
    for cat in cats or []:
        if not isinstance(cat, dict):
            continue
        cname = str(cat.get("name") or cat.get("displayName") or "").lower()
        if any(w in cname for w in _SKIP_CATS):
            continue
        keys = [str(k) for k in cat.get("names") or []]
        for ours, theirs in names.items():
            idx = next((keys.index(t) for t in theirs if t in keys), None)
            if idx is None:
                continue
            for row in cat.get("statistics") or []:
                stats = (row or {}).get("stats") or []
                lab = season_label(row)
                if not lab or idx >= len(stats):
                    continue
                labels.add(lab)
                (by_stat.setdefault(ours, {}).setdefault(lab, {})
                 .setdefault(cname, []).append(_num(stats[idx])))
    if not by_stat:
        # ESPN answered with its table and nothing in it: a player with no
        # NHL / NFL games before this season. His career is this season.
        if isinstance(cats, list) and isinstance(data, dict) and "categories" in data:
            return {"prior": {k: 0 for k, *_ in CAREER.get(sport) or ()}, "seasons": 0,
                    "labels": [], "current_seen": False}
        return None
    prior, current_seen = {}, False
    for ours, seasons in by_stat.items():
        tot, got = 0.0, False
        for lab, per_cat in seasons.items():
            if is_current_season(lab, sport, start_year):
                current_seen = True
                continue
            # the same stat in two categories (games played) is one
            # number, not two: the largest category's season value
            vals = [season_value(v) for v in per_cat.values()]
            vals = [v for v in vals if v is not None]
            if vals:
                tot += max(vals)
                got = True
        if got:
            prior[ours] = int(round(tot))
        elif not [lab for lab in seasons if not is_current_season(lab, sport, start_year)]:
            prior[ours] = 0          # a rookie: every row is this season's
    for ours, parts in (DERIVED.get(sport) or {}).items():
        if ours not in prior and all(p in prior for p in parts):
            prior[ours] = sum(prior[p] for p in parts)
    for helper in ("rush_td", "rec_td"):
        prior.pop(helper, None)
    return {"prior": prior, "seasons": len(labels), "labels": sorted(labels),
            "current_seen": current_seen}


# MLB's stats API career line (people?personIds=..&hydrate=stats(group=
# [hitting],type=[career])) — regular season only, current to last night.
MLB_NAMES = {"hr": "homeRuns", "h": "hits", "rbi": "rbi", "sb": "stolenBases"}


def parse_mlb_careers(resp):
    """{pid: {hr, h, rbi, sb}} from one bulk people call; a player without
    a hitting career line is left out (missing, not zero)."""
    out = {}
    for person in (resp or {}).get("people") or []:
        if not isinstance(person, dict) or not person.get("id"):
            continue
        for blk in person.get("stats") or []:
            grp = str(((blk or {}).get("group") or {}).get("displayName") or "").lower()
            typ = str(((blk or {}).get("type") or {}).get("displayName") or "").lower()
            if grp != "hitting" or typ != "career":
                continue
            splits = blk.get("splits") or []
            stat = (splits[0] or {}).get("stat") if splits else None
            if not isinstance(stat, dict):
                continue
            vals = {k: _num(stat.get(v)) for k, v in MLB_NAMES.items()}
            vals = {k: int(v) for k, v in vals.items() if v is not None}
            if vals:
                out[str(person["id"])] = vals
    return out


def season_start_year(d, sport):
    """The season a date belongs to, by its START year."""
    cut = 8 if sport == "nfl" else 9
    return d.year if d.month >= cut else d.year - 1


# ----------------------------------------------------------------------
# The committed prior-career file
# ----------------------------------------------------------------------
# The file's format per sport. Bumped when a file on disk is known wrong,
# so the next nightly starts it over: NHL 2 (10-14) — format 1 read
# ESPN's "26-27" row as a past season and counted this season twice.
FORMAT = {"nhl": 2, "nfl": 1, "nba": 1}


class PriorCareer:
    """data/<sport>/career_prior.json: {"season": start_year, "format": n,
    "players": {pid: {"name", "prior": {stat: n}}}}. A player is fetched
    once per season; a file from another season or format is started over."""

    def __init__(self, data, start_year, fmt=1):
        data = data if isinstance(data, dict) else {}
        same = data.get("season") == start_year and (data.get("format") or 1) == fmt
        self.season = start_year
        self.format = fmt
        self.players = dict(data.get("players") or {}) if same else {}
        self.fetched = 0
        self.failed = 0

    def missing(self, pids):
        return [p for p in pids if str(p) not in self.players]

    # More "no earlier seasons" than this among 20+ new players means the
    # feed's shape changed, not a wave of rookies: the night's fetch is
    # thrown away rather than publishing veterans' careers as zero.
    MAX_ROOKIE_SHARE = 0.35

    def fill(self, pids, names, fetch, sport, cap=300, sleep=None):
        """Fetch up to `cap` missing players (fetch(pid) -> ESPN payload).
        A failed or unreadable player is retried next night."""
        before = dict(self.players)
        self.rookies = 0
        self.suspect = False
        for pid in self.missing(pids)[:cap]:
            try:
                parsed = parse_espn_career(fetch(pid), sport, self.season)
            except Exception:  # noqa: BLE001 — one player costs that player only
                parsed = None
            if parsed is None:
                self.failed += 1
            else:
                self.players[str(pid)] = {"name": names.get(str(pid)),
                                          "prior": parsed["prior"],
                                          "seasons": parsed["seasons"]}
                self.fetched += 1
                self.rookies += not any((parsed["prior"] or {}).values())
            if sleep:
                sleep()
        if self.fetched >= 20 and self.rookies / self.fetched > self.MAX_ROOKIE_SHARE:
            self.players, self.suspect = before, True
            self.fetched = 0
        return self

    def prior(self, pid):
        return ((self.players.get(str(pid)) or {}).get("prior")) or None

    def to_json(self):
        return {"season": self.season, "format": self.format, "players": self.players}
