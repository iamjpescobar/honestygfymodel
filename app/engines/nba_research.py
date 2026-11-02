"""
NBA player research (11-02) — the shot profile and the team ranks behind
the "Player research" section of NBA Trends.

Izzy (11-02): "make our NBA research page similar to this — I love that
shot profile thing". Built from the play-by-play the nightly already reads
(engines/nba_pbp.shots / team_box), for this season and — once the
nba-pbp-prior workflow is run again — last season.

  shot profile   each zone's share of his field-goal attempts and his FG%
                 there, beside what tonight's defense allows in that zone
                 (opponents' FG%, ranked over the league: 1st = toughest,
                 like Overall D)
  team ranks     pace, offensive / defensive rating, paint / three / free
                 throw points and rebounds a game — the player's team on
                 offense vs tonight's opponent on defense, 1-30

What counts (missing is never zero): a player's games count only where his
play-by-play shots add up to his box-score FGA and FGM (shots_ok); a
defense's games only where every opponent's shots check out
(teams_shots_ok). Coordinates are used only in games where they agree with
the distance written in the play; a season mixes the two only zone by
zone ("three" / "two" when the side or the distance is unknown).

DISPLAY ONLY. Nothing here moves a projection, a chance or a letter — it is
research context until a walk-forward test says a zone matchup predicts.

Pure — no streamlit, no requests.
"""
from engines import nba_pbp as pb

ZONES = pb.ZONES
LABEL = {"rim": "Rim", "paint": "In the paint", "mid": "Mid-range",
         "corner3": "Corner 3", "above3": "Above break 3",
         "three": "Three (side unknown)", "two": "Two (distance unknown)"}
MIN_TEAM_GAMES = 1
LEAGUE_TEAMS = 30


def _add(dst, zones):
    for z, (a, m) in (zones or {}).items():
        c = dst.setdefault(z, [0, 0])
        c[0] += a
        c[1] += m


def _in(g, since=None, until=None):
    d = str(g.get("date") or "")
    return (not since or d >= since) and (not until or d < until)


def player_zones(games, pid, since=None, until=None):
    """{"zones": {zone: [att, made]}, "games": n} over the games where his
    shots check out against the box score."""
    zones, n = {}, 0
    for g in games or []:
        if not _in(g, since, until) or pid not in (g.get("shots_ok") or []):
            continue
        _add(zones, (g.get("shots") or {}).get(pid))
        n += 1
    return {"zones": zones, "games": n}


def profile(z):
    """[{zone, label, att, made, share, fg}] in court order; share of ALL
    his attempts (unknown zones included, so shares add to 100)."""
    zones = (z or {}).get("zones") or {}
    tot = sum(a for a, _m in zones.values())
    out = []
    for k in ZONES + pb.UNKNOWN:
        if k not in zones:
            if k in ZONES and tot:
                out.append({"zone": k, "label": LABEL[k], "att": 0, "made": 0,
                            "share": 0.0, "fg": None})
            continue
        a, m = zones[k]
        out.append({"zone": k, "label": LABEL[k], "att": a, "made": m,
                    "share": a / tot if tot else None, "fg": m / a if a else None})
    return out


def _sides(g):
    return [s for s in (str(g.get("home") or ""), str(g.get("away") or "")) if s]


def defense_zones(games, since=None, until=None):
    """{team: {"zones": {zone: [att, made]} its opponents took, "games"}}."""
    out = {}
    for g in games or []:
        if not _in(g, since, until):
            continue
        sides = _sides(g)
        if len(sides) != 2:
            continue
        ok = set(g.get("teams_shots_ok") or [])
        team_of = g.get("shot_team") or {}
        for d_team in sides:
            o_team = sides[1] if d_team == sides[0] else sides[0]
            if o_team not in ok:
                continue
            rec = out.setdefault(d_team, {"zones": {}, "games": 0})
            rec["games"] += 1
            for pid, zones in (g.get("shots") or {}).items():
                if team_of.get(pid) == o_team:
                    _add(rec["zones"], zones)
    return out


def _rank(vals, low_first=True):
    """{team: rank} 1 = lowest value when low_first; ties share a rank."""
    order = sorted(vals.items(), key=lambda kv: kv[1] if low_first else -kv[1])
    out, last, rk = {}, None, 0
    for i, (t, v) in enumerate(order, 1):
        if v != last:
            rk, last = i, v
        out[t] = rk
    return out


def defense_table(dz, teams=None):
    """{"teams": {team: {zone: {"fg", "share", "att", "rank", "of"}}},
    "league": {zone: {"fg", "share"}}, "games": {team: n}}. Rank by
    opponents' FG% in the zone, 1st = lowest (toughest). Only the NBA
    teams (`teams`, else the LEAGUE_TEAMS most-faced) are ranked."""
    if teams is None:
        teams = [t for t, _ in sorted(dz.items(), key=lambda kv: -kv[1]["games"])[:LEAGUE_TEAMS]]
    teams = [t for t in teams if t in dz and dz[t]["games"] >= MIN_TEAM_GAMES]
    league = {}
    for t in teams:
        _add(league, dz[t]["zones"])
    ltot = sum(a for a, _m in league.values()) or 0
    out = {"teams": {t: {} for t in teams}, "games": {t: dz[t]["games"] for t in teams},
           "league": {z: {"fg": (m / a if a else None), "share": (a / ltot if ltot else None)}
                      for z, (a, m) in league.items()}}
    for z in ZONES + pb.UNKNOWN:
        fg = {}
        for t in teams:
            zz = dz[t]["zones"]
            a, m = zz.get(z, [0, 0])
            tot = sum(x for x, _y in zz.values())
            cell = {"att": a, "fg": (m / a if a else None), "share": (a / tot if tot else None)}
            out["teams"][t][z] = cell
            if a:
                fg[t] = cell["fg"]
        rk = _rank(fg, low_first=True)
        for t, r in rk.items():
            out["teams"][t][z].update(rank=r, of=len(rk))
    return out


# --- team ranks --------------------------------------------------------
METRICS = (("pace", "Pace", "possessions per 48 minutes"),
           ("rtg", "Rating", "points per 100 possessions"),
           ("paint", "Paint scoring", "points a game from the rim and the paint"),
           ("three", "3PT scoring", "points a game from threes"),
           ("ft", "Free throws", "free-throw points a game"),
           ("reb", "Rebounding", "rebounds a game"))


def _poss(b):
    if any(b.get(k) is None for k in ("fga", "oreb", "tov", "fta")):
        return None
    return b["fga"] - b["oreb"] + b["tov"] + 0.44 * b["fta"]


def _paint_pts(g, team):
    """2 x made shots at the rim / in the paint by the team, when every
    player's shots check out; else None."""
    if team not in (g.get("teams_shots_ok") or []):
        return None
    team_of = g.get("shot_team") or {}
    pts = 0
    for pid, zones in (g.get("shots") or {}).items():
        if team_of.get(pid) == team:
            pts += 2 * sum((zones.get(z) or [0, 0])[1] for z in ("rim", "paint"))
    return pts


def team_totals(games, since=None, until=None):
    """{team: {"off": {metric: [sum, n]}, "def": {...}, "games"}} — "def"
    is what its opponents did against it."""
    out = {}
    for g in games or []:
        if not _in(g, since, until):
            continue
        tb = g.get("team_box") or {}
        sides = _sides(g)
        if len(sides) != 2 or not all(s in tb for s in sides):
            continue
        for me in sides:
            op = sides[1] if me == sides[0] else sides[0]
            rec = out.setdefault(me, {"off": {}, "def": {}, "games": 0})
            rec["games"] += 1
            for side, who in (("off", me), ("def", op)):
                b = tb[who]
                poss = _poss(b)
                mins = b.get("min")
                vals = {"pace": (poss * 48.0 / (mins / 5.0)) if (poss and mins) else None,
                        "rtg": (100.0 * b["pts"] / poss) if (poss and b.get("pts") is not None)
                        else None,
                        "paint": _paint_pts(g, who),
                        "three": (3 * b["tpm"]) if b.get("tpm") is not None else None,
                        "ft": b.get("ftm"), "reb": b.get("reb")}
                for k, v in vals.items():
                    if v is None:
                        continue
                    c = rec[side].setdefault(k, [0.0, 0])
                    c[0] += v
                    c[1] += 1
    return out


def team_ranks(tt, teams=None):
    """{team: {metric: {"off", "off_rank", "def", "def_rank", "of"}}}.
    Offense 1st = most; defense 1st = toughest (least allowed); pace 1st =
    fastest on both sides."""
    if teams is None:
        teams = [t for t, _ in sorted(tt.items(), key=lambda kv: -kv[1]["games"])[:LEAGUE_TEAMS]]
    teams = [t for t in teams if t in tt]
    out = {t: {} for t in teams}
    for k, _lab, _d in METRICS:
        for side in ("off", "def"):
            vals = {}
            for t in teams:
                s, n = tt[t][side].get(k, [0, 0])
                if n:
                    vals[t] = s / n
            fast_or_most = side == "off" or k == "pace"
            rk = _rank(vals, low_first=not fast_or_most)
            for t, v in vals.items():
                out[t].setdefault(k, {})[side] = round(v, 1)
                out[t][k][f"{side}_rank"] = rk[t]
                out[t][k]["of"] = len(vals)
    return out


def season_block(games, since=None, until=None, teams=None, pids=()):
    """Everything the page needs for one season: players' zones (the
    slate's players only), the defense table, the team ranks."""
    dz = defense_zones(games, since, until)
    return {"players": {pid: player_zones(games, pid, since, until) for pid in pids},
            "defense": defense_table(dz, teams),
            "ranks": team_ranks(team_totals(games, since, until), teams),
            "src": source_mix(games, since, until)}


def source_mix(games, since=None, until=None):
    """{"xy", "text", "none"} game counts — how the zones were read."""
    out = {"xy": 0, "text": 0, "none": 0}
    for g in games or []:
        if _in(g, since, until):
            out[g.get("shot_src") or "none"] = out.get(g.get("shot_src") or "none", 0) + 1
    return out


def verify_line(label, games, since=None, until=None):
    """One [verify] line: games with shots, how they were read, players and
    teams whose shots match the box score, coordinate agreement."""
    gs = [g for g in games or [] if _in(g, since, until)]
    if not gs:
        return f"  [verify] NBA SHOTS {label}: no games"
    mix = source_mix(gs)
    n_box = sum(len(g.get("team_box") or {}) for g in gs)
    t_ok = sum(len(g.get("teams_shots_ok") or []) for g in gs)
    p_ok = sum(len(g.get("shots_ok") or []) for g in gs)
    p_all = sum(len(g.get("shots") or {}) for g in gs)
    chk = [g.get("shot_check") or {} for g in gs]
    d = sum(c.get("dist", 0) for c in chk)
    a = sum(c.get("agree", 0) for c in chk)
    xy = sum(c.get("xy", 0) for c in chk)
    n = sum(c.get("n", 0) for c in chk)
    return (f"  [verify] NBA SHOTS {label}: {len(gs)} games ({mix['xy']} by coordinates, "
            f"{mix['text']} by written distance, {mix['none']} none); shots {n}, "
            f"{xy} with coordinates; coordinates within {pb.XY_AGREE_FT:.0f} ft of the written "
            f"distance {a}/{d}; players matching the box {p_ok}/{p_all}; teams {t_ok}/{n_box}")
