"""
NFL week board — real data from ESPN's public NFL API (scoreboard +
game summaries + team rosters), the same host family the WNBA pipeline
measured answering from GitHub Actions.

WHY A WEEK, NOT A DAY

Every other league on this site is a nightly slate. Football is not: a
week runs Tuesday to Monday, most of it lands on one Sunday, and the
research people do happens days ahead. So the file this writes is keyed
on the WEEK (week_start_et..week_end_et) and the page shows the whole
week at once. slate_guard is a per-date guard and cannot express a
range, so the week check lives in app/engines/nfl_week.py — see there.

WHAT IT PRODUCES, all from real finals:
- This week's games: kickoff (ET), TV window, venue, roof, weather
  (summary gameInfo), spread/total as ESPN lists them, records, injuries.
- Team UNIT profiles: offense per game (yards, pass, rush, turnovers,
  3rd-down %, red-zone TD %, sacks taken) and the same numbers ALLOWED
  by the defense, plus a league rank for each. The ranks are what the
  Mismatch Finder reads.
- Player logs: passing / rushing / receiving per game, with season,
  last-3 and last-game lines.

Nothing is estimated. A column the feed did not return is absent, and
the page prints an em-dash. Samples are shipped with their game counts.
"""
import json
import sys
import time
from datetime import datetime, timedelta
from math import exp, lgamma
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef  # noqa: E402
from engines.nfl_week import (  # noqa: E402
    SEASON_START, SEASON_WEEKS, week_of, week_window, tv_window,
)

EASTERN = ZoneInfo("America/New_York")
LEAGUE = "nfl"
OUT = Path("build_data") / "data" / "nfl"

# THE PROJECTION LOG IS THE ONE THING HERE THAT WRITES TO THE REPO, and
# it is a module constant so a test can point it somewhere else.
#
# It was ROOT / "data" / ... inline, which meant every run of
# tests/test_nfl_pipeline.py — which calls main() four times against
# synthetic games — wrote FIXTURE projections into the real log
# directory, under today's date, looking exactly like a genuine record.
# A grader reading that later would score claims the site never made,
# against players who were never on the slate, and nothing about the
# file would say so. The suite polluting production data is the bug;
# the repo path is correct and stays.
PROJECTION_LOG = ROOT / "data" / "nfl" / "projections"
# 2025 finals for the game model — fetched once, committed with the log.
PRIOR_PATH = ROOT / "data" / "nfl" / "prior_season.json"
# Graded model-picks record; module-level so tests sandbox it.
PICKS_ROOT = ROOT / "data" / "model_picks"

# ----------------------------------------------------------------------
# Box-score column maps. keys first, labels second — see
# espn_feed.box_group_index. Group NAME decides the category, because
# "YDS" appears in all three.
# ----------------------------------------------------------------------
PASSING = {
    "cmp_att": (("completions/passingAttempts",), ("C/ATT", "CMP/ATT")),
    "yds": (("passingYards",), ("YDS",)),
    "td": (("passingTouchdowns",), ("TD",)),
    "int": (("interceptions",), ("INT",)),
    "sacks": (("sacks-sackYardsLost", "sacks"), ("SACKS", "SCK")),
}
RUSHING = {
    "att": (("rushingAttempts",), ("CAR", "ATT")),
    "yds": (("rushingYards",), ("YDS",)),
    "td": (("rushingTouchdowns",), ("TD",)),
    "long": (("longRushing",), ("LONG", "LNG")),
}
RECEIVING = {
    "rec": (("receptions",), ("REC",)),
    "yds": (("receivingYards",), ("YDS",)),
    "td": (("receivingTouchdowns",), ("TD",)),
    "long": (("longReception",), ("LONG", "LNG")),
    "tgt": (("receivingTargets",), ("TGTS", "TAR", "TGT")),
}

# Team box stats, matched on ESPN's `name` (lower-cased).
TEAM_STATS = {
    "yds": ("totalyards",),
    "pass_yds": ("netpassingyards",),
    "rush_yds": ("rushingyards",),
    "to": ("turnovers",),
    "first_downs": ("firstdowns",),
    "third": ("thirddowneff",),          # "4-11"
    "rz": ("redzoneattempts",),          # "2-3"  (TDs-trips)
    "sacked": ("sacksyardslost",),       # "2-14" (sacks-yards)
    "plays": ("totaloffensiveplays", "totalplays"),
    "top": ("possessiontime",),          # "31:05"
}


def parse_team_box(team_stats):
    """One team's box line from a summary boxscore.teams[] entry."""
    raw = {}
    for s in team_stats or []:
        nm = str(s.get("name") or "").lower().replace(" ", "")
        raw[nm] = s.get("displayValue", s.get("value"))
    out = {}
    for ours, names in TEAM_STATS.items():
        val = next((raw[n] for n in names if n in raw), None)
        if val is None:
            continue
        if ours in ("third", "rz"):
            m, a = ef.pair(val)
            if a:
                out[f"{ours}_m"], out[f"{ours}_a"] = m, a
        elif ours == "sacked":
            m, _y = ef.pair(val)
            if m is not None:
                out["sacked"] = m
        elif ours == "top":
            v = ef.clock_minutes(val)
            if v is not None:
                out["top"] = v
        else:
            v = ef.num(val)
            if v is not None:
                out[ours] = v
    return out


def parse_player_groups(team_block, line_base, logs):
    """Adds each athlete's passing/rushing/receiving line to `logs`.

    Returns how many athlete lines were read (the self-check counts it).
    """
    n = 0
    for grp in team_block.get("statistics") or []:
        gname = str(grp.get("name") or "").lower()
        wanted = {"passing": PASSING, "rushing": RUSHING,
                  "receiving": RECEIVING}.get(gname)
        if not wanted:
            continue
        idx = ef.box_group_index(grp, wanted)
        if not idx:
            continue
        for ent in grp.get("athletes") or []:
            ath = ent.get("athlete") or {}
            stats = ent.get("stats") or []
            if not ath.get("id") or not stats:
                continue
            cat = {}
            for ours, i in idx.items():
                if i >= len(stats):
                    continue
                if ours == "cmp_att":
                    c, a = ef.pair(stats[i])
                    if a is not None:
                        cat["cmp"], cat["att"] = c, a
                elif ours == "sacks":
                    s, _y = ef.pair(stats[i])
                    cat["sacks"] = s if s is not None else ef.num(stats[i])
                else:
                    cat[ours] = ef.num(stats[i])
            if not cat:
                continue
            pid = str(ath["id"])
            rec = logs.setdefault(pid, {
                "pid": pid,
                "name": ath.get("displayName") or ath.get("shortName"),
                "short": ath.get("shortName") or ath.get("displayName"),
                "pos": ((ath.get("position") or {}).get("abbreviation") or ""),
                "games": {},
            })
            rec["team"] = line_base["team"]
            g = rec["games"].setdefault(line_base["event_id"], dict(line_base))
            g[gname] = cat
            n += 1
    return n


def parse_summary_final(summary, event_id, game_date, week, logs):
    """Team box lines [(team_name, line)] for one final; players into logs."""
    box = summary.get("boxscore") or {}
    teams = box.get("teams") or []
    names = [((t.get("team") or {}).get("displayName") or "") for t in teams]
    team_lines = []
    for i, t in enumerate(teams):
        line = parse_team_box(t.get("statistics"))
        line["team"] = names[i]
        line["opp"] = names[1 - i] if len(names) == 2 else ""
        team_lines.append(line)
    n_players = 0
    pblocks = box.get("players") or []
    pnames = [((b.get("team") or {}).get("displayName") or "") for b in pblocks]
    for i, b in enumerate(pblocks):
        base_line = {"event_id": str(event_id), "date": game_date, "week": week,
                     "team": pnames[i],
                     "opp": pnames[1 - i] if len(pnames) == 2 else ""}
        n_players += parse_player_groups(b, base_line, logs)
    return team_lines, n_players


def game_info(summary):
    """Venue roof, weather and injuries from a summary — whatever exists."""
    gi = summary.get("gameInfo") or {}
    out = {}
    v = gi.get("venue") or {}
    if isinstance(v.get("indoor"), bool):
        out["indoor"] = v["indoor"]
    if isinstance(v.get("grass"), bool):
        out["grass"] = v["grass"]
    w = gi.get("weather") or {}
    if isinstance(w, dict) and w:
        t = ef.num(w.get("temperature"))
        if t is not None:
            out["temp_f"] = t
        txt = w.get("displayValue") or w.get("conditionText")
        if txt:
            out["weather"] = str(txt)
        gust = ef.num(w.get("gust"))
        if gust is not None:
            out["gust_mph"] = gust
        pr = ef.num(w.get("precipitation"))
        if pr is not None:
            out["precip_pct"] = pr
    inj = {}
    for blk in summary.get("injuries") or []:
        tname = (blk.get("team") or {}).get("displayName") or ""
        rows = []
        for it in blk.get("injuries") or []:
            a = it.get("athlete") or {}
            status = it.get("status") or (it.get("type") or {}).get("description")
            if not a.get("displayName") or not status:
                continue
            rows.append({"name": a["displayName"],
                         "pos": (a.get("position") or {}).get("abbreviation", ""),
                         "status": str(status)})
        if tname and rows:
            inj[tname] = rows
    if inj:
        out["injuries"] = inj
    pc = summary.get("pickcenter") or []
    if isinstance(pc, list) and pc and isinstance(pc[0], dict):
        o = ef.odds_of({"odds": pc})
        if o:
            out["odds"] = o
    return out


# ----------------------------------------------------------------------
# Team research
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# PER-GAME TEAM USAGE, summed from the player lines.
#
# Derived from the players rather than read off the team box on purpose:
# a share needs a numerator and a denominator from the SAME source. Team
# box "rushing attempts" and the sum of the backs' carries disagree on
# scrambles and laterals, and a share built across that mismatch can
# exceed 1.0 for no visible reason.
# ----------------------------------------------------------------------
def team_game_usage(logs):
    """{(event_id, team): {carries, targets, rec, rush_yds, rec_yds, td}}."""
    out = {}
    for rec in logs.values():
        for eid, g in (rec.get("games") or {}).items():
            key = (str(eid), g.get("team"))
            t = out.setdefault(key, {"carries": 0.0, "targets": 0.0, "rec": 0.0,
                                     "rush_yds": 0.0, "rec_yds": 0.0, "td": 0.0})
            r, c = g.get("rushing") or {}, g.get("receiving") or {}
            t["carries"] += r.get("att") or 0
            t["rush_yds"] += r.get("yds") or 0
            t["targets"] += c.get("tgt") or 0
            t["rec"] += c.get("rec") or 0
            t["rec_yds"] += c.get("yds") or 0
            # RUSHING + RECEIVING ONLY. A passing TD IS the receiving TD
            # on the other end of the same throw — adding both would
            # double every passing score, inflating team TD rates and
            # every opponent's TDs allowed under a label saying
            # otherwise (rule 9).
            t["td"] += (r.get("td") or 0) + (c.get("td") or 0)
    return out


def td_opportunity_prior(logs):
    """How often a touch becomes a touchdown, and how much to trust one
    player's own rate over the league's. BOTH MEASURED.

    THE PROBLEM THIS SOLVES. The first version of the projection split a
    team's expected touchdowns by the player's share of his team's
    ACTUAL scores. Measured against outcomes over weeks 1-3
    (nfl_projection_probe, 2026-09-27), that was badly wrong in both
    directions: 65% of skill players had scored zero and were handed a
    flat 0% when the real base rate for a skill player is 23%, while a
    tight end with ONE score in ONE game came out at 88%. The
    calibration curve showed every band above 30% coming in at roughly
    half its claim.

    The fix is to estimate from OPPORTUNITY — carries plus targets,
    which is stable week to week — rather than from realised scores,
    which on three games are almost pure noise. A player's own
    conversion rate still counts, shrunk toward the league in proportion
    to how much evidence he has:

        rate = (his TDs + a) / (his touches + a + b)

    a and b are NOT chosen. They come from fitting a beta-binomial to
    every skill player in the league by maximum likelihood, so the
    amount of shrinkage is whatever the season's own spread supports.
    Early on the fit is strong (a player needs many touches before his
    own rate outweighs the league's) because three weeks genuinely
    cannot tell one converter from another; as the sample grows and real
    differences emerge, the fitted strength falls and good red-zone
    players come through on their own. It self-adjusts, with nothing to
    retune by hand.

    Returns {} when there is nothing to fit, so the caller falls back
    rather than inventing a prior.
    """
    obs = []
    for rec in logs.values():
        k = n = 0
        for g in (rec.get("games") or {}).values():
            r, c = g.get("rushing") or {}, g.get("receiving") or {}
            n += (r.get("att") or 0) + (c.get("tgt") or 0)
            k += (r.get("td") or 0) + (c.get("td") or 0)
        if n > 0:
            obs.append((min(k, n), n))
    total_n = sum(n for _, n in obs)
    if not obs or not total_n:
        return {}
    mu = sum(k for k, _ in obs) / total_n
    if mu <= 0 or mu >= 1:
        return {}

    def _lbeta(x, y):
        return lgamma(x) + lgamma(y) - lgamma(x + y)

    def _ll(strength):
        a, b = mu * strength, (1.0 - mu) * strength
        base = _lbeta(a, b)
        return sum(_lbeta(k + a, n - k + b) - base for k, n in obs)

    # Golden-section search on log(strength). A search rather than a
    # closed form because the method-of-moments alternative needs a
    # minimum-touches cutoff to keep its variance estimate sane, and that
    # cutoff would be a number chosen by eye (rule 1).
    lo, hi = 0.0, 8.0
    g = (5 ** 0.5 - 1) / 2
    c, d = hi - g * (hi - lo), lo + g * (hi - lo)
    for _ in range(80):
        if _ll(exp(c)) > _ll(exp(d)):
            hi = d
        else:
            lo = c
        c, d = hi - g * (hi - lo), lo + g * (hi - lo)
    strength = exp((lo + hi) / 2)
    return {"td_per_opportunity": round(mu, 5),
            "prior_strength": round(strength, 1),
            "prior_a": round(mu * strength, 4),
            "prior_b": round((1.0 - mu) * strength, 4),
            "players_fitted": len(obs),
            "touches_fitted": int(total_n)}


def league_constants(finals, usage):
    """The league-average rates the projection divides by, MEASURED.

    Every one of these was a candidate to be typed in by eye, and rule 1
    says everything on this site chosen that way turned out wrong. They
    are recomputed from the season's real finals on every nightly and
    shipped in games.json, so the page can show what it used and a
    reader can check it.

    td_per_point is the load-bearing one: given the market implies a
    team scores N points, how many offensive touchdowns has a point
    historically been worth? Measured as offensive TDs over team points,
    which correctly nets out field goals — and, deliberately, counts a
    defensive score in the denominator, because the market's total
    includes those points too and the projection is dividing that same
    total.
    """
    pts = tds = carries = rush_yds = targets = recs = rec_yds = 0.0
    games = 0
    for f in finals:
        for side, opp in (("away", "home"), ("home", "away")):
            u = usage.get((str(f.get("event_id")), f[side]))
            if not u:
                continue
            games += 1
            pts += f[f"{side}_score"]
            tds += u["td"]
            carries += u["carries"]
            rush_yds += u["rush_yds"]
            targets += u["targets"]
            recs += u["rec"]
            rec_yds += u["rec_yds"]
    if not games:
        return {}
    return {
        "team_games": games,
        "td_per_point": round(tds / pts, 4) if pts else None,
        "points_pg": round(pts / games, 1),
        "td_pg": round(tds / games, 2),
        "ypc": round(rush_yds / carries, 2) if carries else None,
        "yards_per_target": round(rec_yds / targets, 2) if targets else None,
        "catch_rate": round(recs / targets, 3) if targets else None,
        "carries_pg": round(carries / games, 1),
        "targets_pg": round(targets / games, 1),
    }


def _avg(vals, nd=1):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), nd) if vals else None


def _rate(m_vals, a_vals):
    pairs = [(m, a) for m, a in zip(m_vals, a_vals) if m is not None and a]
    if not pairs:
        return None
    return round(100.0 * sum(m for m, _ in pairs) / sum(a for _, a in pairs), 1)


def team_research(finals, usage=None):
    """{team: profile} from final game records.

    `finals` items: {date, week, away, home, away_score, home_score,
    away_box, home_box}. Allowed numbers are the OPPONENT's offense in
    the same game, so offense and defense are measured on identical
    definitions.
    """
    per = {}
    for f in sorted(finals, key=lambda x: x["date"]):
        for side, opp in (("away", "home"), ("home", "away")):
            per.setdefault(f[side], []).append({
                "date": f["date"], "week": f.get("week"),
                "opp": f[opp], "home": side == "home",
                "pf": f[f"{side}_score"], "pa": f[f"{opp}_score"],
                "off": f.get(f"{side}_box") or {},
                "dff": f.get(f"{opp}_box") or {},
                # None, not 0, when this game's player block did not
                # parse — an unparsed game is not a shutout (rule 6).
                "use": (usage or {}).get((str(f.get("event_id")), f[side])),
                "use_opp": (usage or {}).get((str(f.get("event_id")), f[opp])),
            })
    out = {}
    for team, games in per.items():
        w = sum(1 for g in games if g["pf"] > g["pa"])
        l_ = sum(1 for g in games if g["pf"] < g["pa"])
        t_ = sum(1 for g in games if g["pf"] == g["pa"])
        off = [g["off"] for g in games]
        dff = [g["dff"] for g in games]
        prof = {
            "gp": len(games),
            "record": f"{w}-{l_}" + (f"-{t_}" if t_ else ""),
            "pf_pg": _avg([g["pf"] for g in games]),
            "pa_pg": _avg([g["pa"] for g in games]),
            "avg_total": _avg([g["pf"] + g["pa"] for g in games]),
            "ypg": _avg([o.get("yds") for o in off]),
            "pass_ypg": _avg([o.get("pass_yds") for o in off]),
            "rush_ypg": _avg([o.get("rush_yds") for o in off]),
            "to_pg": _avg([o.get("to") for o in off]),
            "sacked_pg": _avg([o.get("sacked") for o in off]),
            "third_pct": _rate([o.get("third_m") for o in off], [o.get("third_a") for o in off]),
            "rz_td_pct": _rate([o.get("rz_m") for o in off], [o.get("rz_a") for o in off]),
            "top": _avg([o.get("top") for o in off]),
            "td_pg": _avg([(g["use"] or {}).get("td") if g["use"] else None
                           for g in games], 2),
            "td_allowed_pg": _avg([(g["use_opp"] or {}).get("td") if g["use_opp"] else None
                                   for g in games], 2),
            "ypg_allowed": _avg([d.get("yds") for d in dff]),
            "pass_allowed": _avg([d.get("pass_yds") for d in dff]),
            "rush_allowed": _avg([d.get("rush_yds") for d in dff]),
            "takeaways_pg": _avg([d.get("to") for d in dff]),
            "sacks_pg": _avg([d.get("sacked") for d in dff]),
            "third_allowed_pct": _rate([d.get("third_m") for d in dff], [d.get("third_a") for d in dff]),
            "rz_td_allowed_pct": _rate([d.get("rz_m") for d in dff], [d.get("rz_a") for d in dff]),
            "last": {k: games[-1][k] for k in ("date", "opp", "pf", "pa", "home")},
            "results": [f'{"W" if g["pf"] > g["pa"] else "L" if g["pf"] < g["pa"] else "T"}'
                        for g in games],
        }
        # VOLUME AND EFFICIENCY, on both sides of the ball, per attempt.
        #
        # Yards per game says a defense is leaky; yards per CARRY says
        # whether that is the defense or just how often it was run on.
        # The projection multiplies a volume by a rate, so it needs the
        # rate — a per-game figure would smuggle the opponent's play
        # count into this team's number.
        own = [g["use"] for g in games if g["use"]]
        opp_use = [g["use_opp"] for g in games if g["use_opp"]]

        # NOT named _rate. A module-level _rate() already exists and is
        # called higher up in this same function for third-down and
        # red-zone conversion; a nested def with that name shadows it for
        # the ENTIRE function body, including those earlier calls, and
        # Python raises UnboundLocalError on the first of them. Caught by
        # the suite, which is the only reason this is a comment and not a
        # production outage.
        def _per(rows, num, den, nd=2):
            n = sum(r[num] for r in rows)
            d = sum(r[den] for r in rows)
            return round(n / d, nd) if d else None

        if own:
            prof["carries_pg"] = round(sum(r["carries"] for r in own) / len(own), 1)
            prof["targets_pg"] = round(sum(r["targets"] for r in own) / len(own), 1)
            prof["ypc"] = _per(own, "rush_yds", "carries")
            prof["yards_per_target"] = _per(own, "rec_yds", "targets")
            prof["catch_rate"] = _per(own, "rec", "targets", 3)
        if opp_use:
            prof["ypc_allowed"] = _per(opp_use, "rush_yds", "carries")
            prof["ypt_allowed"] = _per(opp_use, "rec_yds", "targets")
            prof["catch_rate_allowed"] = _per(opp_use, "rec", "targets", 3)
            prof["carries_faced_pg"] = round(
                sum(r["carries"] for r in opp_use) / len(opp_use), 1)
            prof["targets_faced_pg"] = round(
                sum(r["targets"] for r in opp_use) / len(opp_use), 1)

        if prof["to_pg"] is not None and prof["takeaways_pg"] is not None:
            prof["to_margin_pg"] = round(prof["takeaways_pg"] - prof["to_pg"], 1)
        out[team] = prof
    return out


# (stat, True when HIGHER is better for the team that owns it)
RANKED = [
    ("pf_pg", True), ("pa_pg", False), ("td_pg", True), ("td_allowed_pg", False),
    ("ypc_allowed", False), ("ypt_allowed", False), ("catch_rate_allowed", False),
    ("ypg", True), ("pass_ypg", True), ("rush_ypg", True),
    ("to_pg", False), ("sacked_pg", False), ("third_pct", True), ("rz_td_pct", True),
    ("ypg_allowed", False), ("pass_allowed", False), ("rush_allowed", False),
    ("takeaways_pg", True), ("sacks_pg", True),
    ("third_allowed_pct", False), ("rz_td_allowed_pct", False),
    ("to_margin_pg", True),
]


def attach_ranks(teams):
    """Adds `ranks` {stat: 1..N} to every profile. 1 = best for that team.

    Ties share the better rank (competition ranking), so two teams on
    300.0 yards are both #4 rather than one being arbitrarily #5. A team
    with no value for a stat gets no rank for it — never a last place.
    """
    for stat, higher_better in RANKED:
        have = [(t, p[stat]) for t, p in teams.items() if p.get(stat) is not None]
        have.sort(key=lambda x: -x[1] if higher_better else x[1])
        prev, prev_rank = None, 0
        for i, (t, v) in enumerate(have, start=1):
            rank = prev_rank if v == prev else i
            teams[t].setdefault("ranks", {})[stat] = rank
            prev, prev_rank = v, rank
    n = len(teams)
    for p in teams.values():
        p["rank_of"] = n
    return teams


# ----------------------------------------------------------------------
# Players
# ----------------------------------------------------------------------
PLAYER_STATS = [
    ("passing", "yds"), ("passing", "att"), ("passing", "cmp"),
    ("passing", "td"), ("passing", "int"),
    ("rushing", "yds"), ("rushing", "att"), ("rushing", "td"), ("rushing", "long"),
    ("receiving", "yds"), ("receiving", "rec"), ("receiving", "tgt"),
    ("receiving", "td"), ("receiving", "long"),
]


def player_summaries(logs, usage=None):
    """{pid: summary} with season / L3 / last per stat, from logs only."""
    out = {}
    for pid, rec in logs.items():
        games = sorted(rec["games"].values(), key=lambda g: g["date"])
        if not games:
            continue
        s = {"pid": pid, "name": rec["name"], "short": rec.get("short"),
             "team": rec.get("team"), "pos": rec.get("pos") or "",
             "gp": len(games)}
        for cat, stat in PLAYER_STATS:
            # A game where the player has no line in this category is not
            # a zero in it: a QB who did not rush has no rushing line.
            # Averages are over the games that HAVE the category, and the
            # count ships beside them (MISSING IS NOT ZERO).
            vals = [(g.get(cat) or {}).get(stat) for g in games if cat in g]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            key = f"{cat[:4]}_{stat}"
            s[key] = round(sum(vals) / len(vals), 1)
            s[f"{key}_l3"] = round(sum(vals[-3:]) / len(vals[-3:]), 1)
            s[f"{key}_last"] = vals[-1]
            s[f"{cat[:4]}_gp"] = len(vals)
        # SHARES, from season totals rather than an average of per-game
        # shares. A back who took 2 carries in a blowout and 20 the week
        # before has two very different game shares; averaging them
        # weights the 2-carry game equally. Totals over totals is the
        # share he actually had of the football.
        tc = tt = 0.0
        for g in games:
            u = (usage or {}).get((str(g.get("event_id")), g.get("team")))
            if not u:
                continue
            tc += u["carries"]
            tt += u["targets"]
        own_car = sum((g.get("rushing") or {}).get("att") or 0 for g in games)
        own_tgt = sum((g.get("receiving") or {}).get("tgt") or 0 for g in games)
        own_rec = sum((g.get("receiving") or {}).get("rec") or 0 for g in games)
        own_ry = sum((g.get("rushing") or {}).get("yds") or 0 for g in games)
        own_cy = sum((g.get("receiving") or {}).get("yds") or 0 for g in games)
        if tc:
            s["carry_share"] = round(own_car / tc, 3)
        if tt:
            s["target_share"] = round(own_tgt / tt, 3)
        if own_car:
            s["ypc"] = round(own_ry / own_car, 2)
        if own_tgt:
            s["yards_per_target"] = round(own_cy / own_tgt, 2)
            s["catch_rate"] = round(own_rec / own_tgt, 3)

        # TOUCHDOWNS, per game rather than per category. A rushing score
        # and a receiving score are different plays and add; a passing
        # score is the same play as somebody's receiving score and is
        # kept in its own column (see team_game_usage).
        per_game_td, per_game_opps = [], []
        for g in games:
            r, c = g.get("rushing"), g.get("receiving")
            if r is None and c is None:
                continue
            per_game_td.append(((r or {}).get("td") or 0) + ((c or {}).get("td") or 0))
            per_game_opps.append(((r or {}).get("att") or 0) + ((c or {}).get("tgt") or 0))
        if per_game_td:
            s["td"] = round(sum(per_game_td) / len(per_game_td), 2)
            s["td_total"] = sum(per_game_td)
            s["td_games"] = len(per_game_td)
            # A COUNT of what happened, never a probability of what will:
            # the share of his games with a score in them.
            s["anytime_rate"] = round(
                100.0 * sum(1 for v in per_game_td if v >= 1) / len(per_game_td))
        if per_game_opps:
            s["opps"] = round(sum(per_game_opps) / len(per_game_opps), 1)
            s["opps_l3"] = round(sum(per_game_opps[-3:]) / len(per_game_opps[-3:]), 1)

        s["log"] = [
            {"week": g.get("week"), "opp": g.get("opp"),
             "pass_yds": (g.get("passing") or {}).get("yds"),
             "rush_yds": (g.get("rushing") or {}).get("yds"),
             "rec_yds": (g.get("receiving") or {}).get("yds"),
             "rec": (g.get("receiving") or {}).get("rec"),
             "tgt": (g.get("receiving") or {}).get("tgt"),
             "td": (((g.get("rushing") or {}).get("td") or 0)
                    + ((g.get("receiving") or {}).get("td") or 0)
                    if (g.get("rushing") or g.get("receiving")) else None),
             "pass_td": (g.get("passing") or {}).get("td")}
            for g in games
        ]
        out[pid] = s
    return out


def role_of(p):
    """Which prop family a player belongs to, from VOLUME not a label."""
    if (p.get("pass_att") or 0) >= 10:
        return "QB"
    if (p.get("rush_att") or 0) >= 5 and (p.get("rush_att") or 0) >= (p.get("rece_tgt") or 0):
        return "RB"
    if (p.get("rece_tgt") or 0) >= 1 or (p.get("rece_rec") or 0) >= 1:
        return "REC"
    if (p.get("rush_att") or 0) >= 1:
        return "RB"
    return None


def _walk_roster(obj, out):
    if isinstance(obj, dict):
        if obj.get("id") and (obj.get("displayName") or obj.get("fullName")) \
                and isinstance(obj.get("position"), dict):
            inj = obj.get("injuries") or []
            status = None
            if inj and isinstance(inj[0], dict):
                status = inj[0].get("status") or (inj[0].get("type") or {}).get("description")
            out[str(obj["id"])] = {
                "name": obj.get("displayName") or obj.get("fullName"),
                "pos": obj["position"].get("abbreviation") or "",
                "jersey": obj.get("jersey"),
                "status": status,
            }
            return
        for v in obj.values():
            _walk_roster(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_roster(v, out)


def fetch_roster(team_id, _get=None):
    get = _get or ef.get_json
    try:
        data = get(f"{ef.base(LEAGUE)}/teams/{team_id}/roster")
    except Exception as exc:
        print(f"  roster {team_id} failed: {exc}")
        return {}
    out = {}
    _walk_roster(data.get("athletes") or data, out)
    return out


SIDE_ROLE_CAP = {"QB": 2, "RB": 3, "REC": 6}


def side_players(team, players, roster):
    """This week's prop pool for one team: roster-gated, volume-ranked.

    The roster decides WHO (a traded or released player keeps his box
    score history but is not on this team's card). When the roster call
    failed, history is used instead, so a failed fetch degrades rather
    than emptying the card.
    """
    pool = [p for p in players.values() if p.get("team") == team]
    if roster:
        pool = [p for p in pool if p["pid"] in roster]
    rows = []
    for role, cap in SIDE_ROLE_CAP.items():
        mine = [p for p in pool if role_of(p) == role]
        key = {"QB": "pass_att", "RB": "rush_att", "REC": "rece_tgt"}[role]
        mine.sort(key=lambda p: -(p.get(key) or p.get("rece_rec") or 0))
        for p in mine[:cap]:
            r = dict(p)
            r["role"] = role
            info = roster.get(p["pid"]) if roster else None
            if info:
                r["pos"] = info.get("pos") or r.get("pos")
                r["status"] = info.get("status")
            rows.append(r)
    return rows


# ----------------------------------------------------------------------
# Scoreboard -> game dict
# ----------------------------------------------------------------------
def slate_game(event):
    comp, away, home = ef.event_sides(event)
    if comp is None:
        return None
    status, completed, detail = ef.status_of(event)
    kick = ef.to_et(comp.get("date") or event.get("date"))
    g = {"event_id": str(event.get("id") or ""), "status": status,
         "detail": detail}
    for side, c in (("away", away), ("home", home)):
        t = c.get("team") or {}
        g[side] = t.get("displayName") or "TBD"
        g[f"{side}_abbr"] = t.get("abbreviation") or ""
        g[f"{side}_id"] = str(t.get("id") or "")
        g[f"{side}_color"] = t.get("color")
        g[f"{side}_logo"] = ef.team_logo(t)
        for r in c.get("records") or []:
            if isinstance(r, dict) and (r.get("name") or r.get("type") or "").lower() in ("overall", "total") \
                    and r.get("summary"):
                g[f"{side}_record"] = r["summary"]
    if kick:
        g["kickoff_et"] = kick.isoformat()
        g["kick_date_et"] = kick.date().isoformat()
        g["kick_time_et"] = kick.strftime("%-I:%M %p")
        g["window"] = tv_window(kick)
    g["venue"] = (comp.get("venue") or {}).get("fullName") or ""
    nets = []
    # The full scoreboard gives broadcast OBJECTS; the flattened header
    # has been seen to give plain strings. Both are read, nothing else.
    for b in comp.get("broadcasts") or []:
        if isinstance(b, str) and b.strip():
            nets.append(b.strip())
        elif isinstance(b, dict):
            nets.extend(b.get("names") or ([b["name"]] if b.get("name") else []))
            if b.get("shortName"):
                nets.append(b["shortName"])
    if not nets and isinstance(event.get("broadcast"), str) and event["broadcast"]:
        nets.append(event["broadcast"])
    if nets:
        g["network"] = " / ".join(dict.fromkeys(str(n) for n in nets))
    o = ef.odds_of(comp)
    if o:
        g["odds"] = o
    if status in ("in progress", "final"):
        a, h = ef.num(away.get("score")), ef.num(home.get("score"))
        if a is not None and h is not None:
            g["away_score"], g["home_score"] = int(a), int(h)
    return g


def main(today=None):
    now_et = datetime.now(EASTERN)
    today = today or now_et.date()
    wk = week_of(today)
    OUT.mkdir(parents=True, exist_ok=True)

    if wk is None or wk > SEASON_WEEKS:
        phase = "preseason" if wk is None else "postseason"
        (OUT / "games.json").write_text(json.dumps({
            "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
            "source": "ESPN public NFL API",
            "phase": phase, "season_start": SEASON_START.isoformat(),
            "week": None, "games": [], "teams": {},
        }, indent=2))
        print(f"NFL: {phase} on {today} — wrote an empty week, honestly labelled")
        return

    w_start, w_end = week_window(wk)
    # KEYED BY EVENT ID, NOT APPENDED.
    #
    # ESPN's NFL scoreboard answers a date inside the current week with
    # the WHOLE week's games, not that day's. This loop walks every day
    # from the season opener to the end of the week, so each of those
    # days handed back the same sixteen fixtures and every one was
    # appended again: the 09-27 file held 49 entries for 16 real games,
    # each player appeared three or four times on every board, and the
    # Projections page died outright on a duplicate Streamlit key.
    #
    # The numbers themselves were never wrong — each duplicate carried
    # the same correctly-normalised projection, and `logs` was already
    # keyed by event id so the league constants and team profiles were
    # unaffected. It was the ROWS that multiplied.
    #
    # Dicts here rather than a dedupe pass at the end, so a game cannot
    # be double-counted no matter how many days return it. Later fetches
    # of the same event overwrite the earlier one, which is what we want:
    # the last read is the freshest status and score.
    finals, logs, week_events = {}, {}, {}
    days = failed = finals_seen = parsed = 0
    first = True
    d = SEASON_START
    while d <= w_end:
        days += 1
        try:
            sb, _src = ef.fetch_scoreboard(LEAGUE, d.strftime("%Y%m%d"))
        except Exception as exc:
            failed += 1
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in sb.get("events") or []:
            g = slate_game(ev)
            if not g:
                continue
            gw = week_of(d)
            if w_start <= d <= w_end:
                week_events[g["event_id"]] = g
            if g["status"] != "final" or g.get("away_score") is None:
                continue
            if d > today:
                continue
            finals_seen += 1
            try:
                summ = ef.fetch_summary(LEAGUE, g["event_id"])
                lines, n_pl = parse_summary_final(summ, g["event_id"], d.isoformat(), gw, logs)
            except Exception as exc:
                print(f"  summary {g['event_id']} ({d}) failed: {exc}")
                continue
            box = {ln["team"]: ln for ln in lines}
            if first:
                print(f"  [verify] first final {g['away']} @ {g['home']}: team box "
                      f"keys {sorted(box.get(g['home'], {}))}; {n_pl} player lines")
                first = False
            if n_pl:
                parsed += 1
            finals[g["event_id"]] = ({"date": d.isoformat(), "week": gw,
                           "event_id": g["event_id"],
                           "away": g["away"], "home": g["home"],
                           # ids for the game model; names are display only
                           "away_id": g.get("away_id"), "home_id": g.get("home_id"),
                           "away_score": g["away_score"], "home_score": g["home_score"],
                           "away_box": box.get(g["away"]),
                           "home_box": box.get(g["home"])})
            time.sleep(0.1)
        time.sleep(0.1)
        d += timedelta(days=1)

    # A league whose finals parsed into nothing is an outage, not a data
    # state — same rule as wnba_precompute. Before week 1 finishes there
    # are legitimately no finals, and that is allowed through.
    finals = list(finals.values())
    week_events = list(week_events.values())
    if finals_seen and not parsed:
        raise RuntimeError(f"NFL: {finals_seen} finals seen, ZERO box scores parsed "
                           f"({failed}/{days} scoreboard days unreachable). Refusing "
                           f"to publish a week with no numbers behind it.")

    usage = team_game_usage(logs)
    league = league_constants(finals, usage)
    league.update(td_opportunity_prior(logs))
    # How widely each prop stat scatters game to game, MEASURED — what
    # turns a projection into an over/under chance (nfl_prop_odds).
    try:
        from engines.nfl_prop_odds import measure_spreads
        league["prop_spreads"] = measure_spreads(logs)
        print("  [verify] prop spreads: " + ", ".join(
            f"{m} {('cv ' + str(v['cv'])) if v['kind'] == 'yards' else ('size ' + str(v['size']))}"
            for m, v in league["prop_spreads"].items()))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NFL prop spreads not measured: {exc}")
    teams = attach_ranks(team_research(finals, usage))
    players = player_summaries(logs, usage)
    print(f"NFL: week {wk} ({w_start}..{w_end}) — {len(week_events)} games; "
          f"{parsed}/{finals_seen} finals parsed -> {len(teams)} teams, "
          f"{len(players)} players")
    if players:
        top = max(players.values(), key=lambda p: p.get("pass_yds") or 0)
        print(f"  [verify] passing-yards leader parsed: {top['name']} ({top['team']}) "
              f"{top.get('pass_yds')} per game over {top.get('pass_gp')} GP")
        scorer = max(players.values(), key=lambda p: p.get("td_total") or 0)
        print(f"  [verify] TD leader parsed: {scorer['name']} ({scorer['team']}) "
              f"{scorer.get('td_total')} TD in {scorer.get('td_games')} games, "
              f"{scorer.get('opps')} opportunities/G")
    # THE CONSTANTS THE PROJECTION DIVIDES BY, printed every run. A
    # td_per_point that drifts far from ~0.10, or a league ypc far from
    # ~4.2, means the parse changed shape — and that would move every
    # projection on the board with nothing else to show for it.
    print(f"  [verify] TD prior fitted on {league.get('players_fitted')} players / "
          f"{league.get('touches_fitted')} touches: {league.get('td_per_opportunity')} "
          f"TD per touch, shrink strength {league.get('prior_strength')} touches "
          f"(a high strength early is correct — three weeks cannot tell one "
          f"converter from another)")
    print(f"  [verify] league constants over {league.get('team_games')} team-games: "
          f"{league.get('points_pg')} pts/G, {league.get('td_pg')} off TD/G, "
          f"td_per_point {league.get('td_per_point')}, ypc {league.get('ypc')}, "
          f"yds/target {league.get('yards_per_target')}, "
          f"catch rate {league.get('catch_rate')}")

    rosters = {}
    for g in week_events:
        for side in ("away", "home"):
            tid = g.get(f"{side}_id")
            if tid and tid not in rosters:
                rosters[tid] = fetch_roster(tid)
    print(f"NFL: {sum(1 for r in rosters.values() if r)}/{len(rosters)} rosters fetched")

    for g in week_events:
        if g["status"] != "final":
            try:
                info = game_info(ef.fetch_summary(LEAGUE, g["event_id"]))
            except Exception as exc:
                print(f"  summary(pre) {g['event_id']} failed: {exc}")
                info = {}
            if info.get("odds") and not g.get("odds"):
                g["odds"] = info.pop("odds")
            info.pop("odds", None)
            g.update(info)
        for side in ("away", "home"):
            prof = teams.get(g[side])
            if prof:
                g[f"{side}_profile"] = prof
            g[f"{side}_players"] = side_players(
                g[side], players, rosters.get(g.get(f"{side}_id")) or {})

    week_events.sort(key=lambda g: g.get("kickoff_et") or "")

    # THE GAME MODEL (engines/nfl_game_model): the site's own projected
    # score, win %, fair spread and total, beside the market's. Fitted on
    # 2025 while 2026 is young; 2025 is fetched once and committed. A
    # model failure costs the model block, never the week.
    model_block = None
    try:
        from engines import nfl_game_model as ngm
        import nfl_prior_season as nps
        prior_finals = nps.load_or_fetch(
            lambda dd: ef.fetch_scoreboard(LEAGUE, dd.strftime("%Y%m%d"))[0], slate_game,
            path=PRIOR_PATH)
        model_block = ngm.build(finals, prior_finals)
        if model_block:
            for g in week_events:
                pj = ngm.project(model_block, g.get("home_id"), g.get("away_id"), g.get("odds"),
                                 g.get("home_abbr", ""), g.get("away_abbr", ""))
                if pj:
                    g["model"] = pj
            v, pr = model_block["validation"], model_block["params"]
            print(f"  [verify] NFL model fit on {pr['fit_on']} season: k={pr['shrink_k']} "
                  f"carryover={pr.get('carryover')} sd_margin={pr['sd_margin']} "
                  f"sd_total={pr['sd_total']} home_mult={model_block['league'].get('home_mult')}")
            if v.get("n"):
                print(f"  [verify] walk-forward {v['n']} games: log loss {v['model']['log_loss']} "
                      f"vs coin {v['coin_flip']['log_loss']} vs home-rate {v['home_rate']['log_loss']}; "
                      f"margin MAE {v['margin_mae_model']} vs home-edge {v['margin_mae_home_edge']}; "
                      f"total MAE {v['total_mae_model']} vs league avg {v['total_mae_league_avg']}")
            print(f"  [verify] week games with a projection: "
                  f"{sum(1 for g in week_events if g.get('model'))} of {len(week_events)}; "
                  f"with a posted moneyline: {sum(1 for g in week_events if (g.get('odds') or {}).get('home_ml'))}, "
                  f"spread price: {sum(1 for g in week_events if (g.get('odds') or {}).get('home_spread_price'))}")
            from engines import model_picks as mpk
            _new = mpk.log_picks("nfl", [
                {"id": g["event_id"], "date": g.get("kick_date_et"), "start": g.get("kickoff_et"),
                 "home": g["home"], "away": g["away"], "proj": g.get("model"), "odds": g.get("odds")}
                for g in week_events if g.get("model") and g.get("kickoff_et")], root=PICKS_ROOT)
            print(f"  [verify] NFL value picks logged this run: {_new}")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NFL game model failed: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # THE PROJECTION LOG — written to the REPO, not the archive.
    #
    # build_data/ is rebuilt from scratch every run and only survives as
    # the tarball the app unpacks, so a record written there is a record
    # that vanishes. calibration.json and lineup_lock.json already take
    # the repo route for exactly this reason, and the workflow commits
    # them; this joins them.
    #
    # Only games that have NOT kicked off are logged. A projection made
    # after the whistle is not a projection, and grading one later would
    # measure a claim the site never made — the same rule hr_edge
    # follows about confirmed lineups.
    # ------------------------------------------------------------------
    try:
        from engines.nfl_projection import MARKETS, projection_rows
        _pending = [g for g in week_events if g.get("status") == "scheduled"]
        if _pending and league:
            _log = {}
            for _m in MARKETS:
                _log[_m] = [
                    {"player": r["Player"], "team": r["Team"], "opp": r["Opp"],
                     "pos": r["Pos"], "gp": r["GP"], "proj": r["Proj"],
                     "window": r["_window"]}
                    for r in projection_rows(_pending, league, _m)[:40]
                ]
            _dir = PROJECTION_LOG
            _dir.mkdir(parents=True, exist_ok=True)
            (_dir / f"{now_et:%Y-%m-%d}.json").write_text(json.dumps({
                "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
                "week": wk,
                "league": league,
                "markets": _log,
            }, ensure_ascii=False, indent=2))
            print(f"NFL: logged projections for {len(_pending)} unplayed games "
                  f"across {len(_log)} markets -> data/nfl/projections/"
                  f"{now_et:%Y-%m-%d}.json")
    except Exception as exc:
        # A failed log must never cost the week file — the board is the
        # product, the log is a record for grading it later.
        print(f"NFL: projection log skipped ({type(exc).__name__}: {exc})")

    (OUT / "games.json").write_text(json.dumps({
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
        "source": "ESPN public NFL API (scoreboard + game summaries + rosters)",
        "phase": "regular",
        "season_start": SEASON_START.isoformat(),
        "week": wk,
        "week_start_et": w_start.isoformat(),
        "week_end_et": w_end.isoformat(),
        "finals_parsed": parsed,
        "league": league,
        "model": model_block,
        "games": week_events,
        "teams": teams,
    }, ensure_ascii=False, indent=2))
    print(f"NFL: wrote games.json (week {wk}, {len(week_events)} games)")


if __name__ == "__main__":
    main()
