"""
Edge boards for NHL and NFL (10-06) — the hockey and football versions
of HR Edge and Pitchers to Target.

    NHL Goal Edge        every skater on tonight's slate, ranked by his
                         DELIVERED chance to score (the NHL model's goal
                         line, run through its own walk-forward record),
                         with the things that drive it beside it.
    Goalies to Target    every goalie who could start tonight, ranked by
                         how many goals the game model expects against
                         him, and the shooters facing him.
    NFL TD Edge          every skill player this week, ranked by his
                         DELIVERED anytime-TD chance.
    Defenses to Target   every defense this week, with the positions and
                         stats it gives away most (defense vs position,
                         this season + last) and the offense facing it.

NOTHING NEW IS ESTIMATED HERE. Every chance comes from a model the
nightly already fits and tests (engines/nhl_model, engines/nfl_projection
+ nfl_prop_check); every rank from engines/defense_matchup. This module
only gathers them into one board per question, ranked, with the
delivered-chance correction applied the same way Top Plays and the price
checker apply it (top_plays_board.calibrate).

Unlike HR Edge, there is no 0-100 composite score: these boards rank by
a chance that has a graded record, so the number on screen is the one a
price is judged against.

Pure — no streamlit, no requests.
"""
from engines import defense_matchup as dm
from engines import model_math as mm
from engines import top_plays_board as tpb

DASH = "—"


def _delivered(p, bins):
    """(chance, basis): the delivered chance when a curve exists, else the
    model's own (labelled)."""
    if p is None:
        return None, None
    c = tpb.calibrate(p, bins) if bins else None
    return (c, "delivered") if c is not None else (p, "model")


def _fair(p):
    return mm.fmt_american(mm.fair_american(p)) if p is not None and 0 < p < 1 else DASH


def _crease_starts(gk):
    """Starts in the team's recent games from a "2 of 3" crease string, or
    the goalie's season starts — whichever exists."""
    cr = str(gk.get("crease") or gk.get("crease_share") or "")
    try:
        return int(cr.split(" of ")[0])
    except (ValueError, IndexError):
        return int(gk.get("starts") or 0)


def likely_starter(goalie_props):
    """The goalie with the most recent starts — a WORKLOAD read, not a
    confirmation (the morning skate decides). None when there are none,
    or when two goalies are TIED on recent starts (a split crease is
    shown as a split, never as a guess)."""
    gs = [g for g in goalie_props or [] if g.get("sv_pct") is not None]
    if not gs:
        return None
    ranked = sorted(gs, key=lambda g: -_crease_starts(g))
    if len(ranked) > 1 and _crease_starts(ranked[0]) == _crease_starts(ranked[1]):
        return None
    return ranked[0]


# ----------------------------------------------------------------------
# NHL
# ----------------------------------------------------------------------
def nhl_goal_rows(games, model):
    """Every skater on the slate with a goal chance, best first."""
    pv = (model or {}).get("props_validation") or {}
    bins = (pv.get("g1") or {}).get("calibration")
    bins2 = (pv.get("g2") or {}).get("calibration")
    out = []
    for g in games or []:
        if g.get("game_type") == "preseason":
            continue
        proj = g.get("model") or {}
        for side, other in (("away", "home"), ("home", "away")):
            opp_abbr = g.get(f"{other}_abbr") or g.get(other)
            team_abbr = g.get(f"{side}_abbr") or g.get(side)
            # the goalie he SHOOTS AT is the other side's; a split crease
            # names both and averages their save rates (never a guess)
            ogp = [x for x in g.get(f"{other}_goalie_props") or [] if x.get("sv_pct") is not None]
            sg = likely_starter(ogp)
            if sg is None and ogp:
                sg = {"name": " / ".join(x.get("name") or "?" for x in ogp[:2]) + " (split)",
                      "sv_pct": sum(x["sv_pct"] for x in ogp[:2]) / len(ogp[:2])}
            env = g.get(f"{side}_env") or {}
            team_goals = proj.get(f"{side}_score")
            for p in g.get(f"{side}_props") or []:
                raw = (p.get("probs") or {}).get("g1")
                if raw is None:
                    continue
                ch, basis = _delivered(raw, bins)
                raw2 = (p.get("probs") or {}).get("g2")
                ch2, _b2 = _delivered(raw2, bins2)
                pp = p.get("pp") or {}
                cards = p.get("dvp") or {}
                ice = p.get("ice") or {}
                out.append({
                    "player": p.get("name"), "pos": p.get("pos"), "team": team_abbr,
                    "opp": opp_abbr, "game": f"{g.get('away_abbr')} @ {g.get('home_abbr')}",
                    "time": g.get("time_et"), "chance": ch, "raw": raw, "basis": basis,
                    "fair": _fair(ch), "exp_g": (p.get("mu") or {}).get("g"),
                    "exp_sog": p.get("exp_sog"),
                    "pts_chance": (p.get("probs") or {}).get("pt1"),
                    "ice_recent": ice.get("recent"), "ice_norm": ice.get("base"),
                    "goal_env": env.get("goal_ratio"), "shot_env": env.get("shot_ratio"),
                    "team_goals": team_goals,
                    "goalie": (sg or {}).get("name"), "goalie_sv": (sg or {}).get("sv_pct"),
                    "card_g": cards.get("g"), "card_sog": cards.get("sog"),
                    "why": p.get("why"),
                    # 2+ goals, delivered (10-09)
                    "chance2": ch2, "raw2": raw2, "fair2": _fair(ch2),
                    # power play, context (10-09)
                    "pp_unit": pp.get("unit"), "pp_l5": pp.get("l5"),
                    "pp_season": pp.get("season"),
                    "pid": p.get("pid"), "game_id": g.get("event_id"),
                    "start": g.get("start_et"),
                })
    out.sort(key=lambda r: -(r["chance"] or 0))
    return out


def multi_goal_watch(goal_rows, n=10):
    """The n skaters most likely to score TWICE tonight, by delivered 2+
    goal chance. Even the top of this list misses most nights; it is a
    price list for long shots, not a prediction."""
    rows = [r for r in goal_rows or [] if r.get("chance2") is not None]
    return sorted(rows, key=lambda r: -r["chance2"])[:n]


def nhl_goalie_rows(games, model, goal_rows=None):
    """Every goalie who could start tonight, the most goals expected
    against first: expected shots against (the shots model) x (1 - his
    save rate, last season + this, shrunk to the league). The game
    model's projected goals for the team he faces ride beside it."""
    league_sv = ((model or {}).get("save_prior") or {}).get("mean")
    shooters = {}
    for r in goal_rows or []:
        shooters.setdefault((r["game"], r["team"]), []).append(r)
    out = []
    for g in games or []:
        if g.get("game_type") == "preseason":
            continue
        proj = g.get("model") or {}
        game = f"{g.get('away_abbr')} @ {g.get('home_abbr')}"
        for side, other in (("away", "home"), ("home", "away")):
            gp = g.get(f"{side}_goalie_props") or []
            starter = likely_starter(gp)
            season = {str(x.get("pid")): x for x in g.get(f"{side}_goalies") or []}
            opp_abbr = g.get(f"{other}_abbr") or g.get(other)
            for gk in gp:
                s = season.get(str(gk.get("pid"))) or {}
                sv = gk.get("sv_pct")
                facing = sorted(shooters.get((game, opp_abbr), []),
                                key=lambda r: -(r["chance"] or 0))[:3]
                exp_sa = gk.get("exp_sa")
                out.append({
                    "exp_ga": (round(exp_sa * (1 - sv), 2)
                               if exp_sa is not None and sv is not None else None),
                    "split": starter is None and len(gp) > 1,
                    "goalie": gk.get("name"), "team": g.get(f"{side}_abbr") or g.get(side),
                    "opp": opp_abbr, "game": game, "time": g.get("time_et"),
                    "likely": starter is not None and gk.get("pid") == starter.get("pid"),
                    "crease": gk.get("crease"),
                    "opp_goals": proj.get(f"{other}_score"),
                    "exp_sa": gk.get("exp_sa"), "sv_model": sv,
                    "sv_vs_league": (round(1000 * (sv - league_sv), 1)
                                     if sv is not None and league_sv else None),
                    "sv_season": s.get("sv_pct"), "sv_l5": s.get("l5_sv_pct"),
                    "gaa": s.get("gaa"), "starts": s.get("starts"),
                    "opp_shot_env": (g.get(f"{other}_env") or {}).get("shot_ratio"),
                    "shooters": ", ".join(f"{r['player']} {100 * r['chance']:.0f}%"
                                          for r in facing if r.get("chance") is not None),
                })
    # Most goals expected against HIM first: shots the shots model expects
    # the opponent to put on net x (1 - his save rate). The game model's
    # team-level goals ride beside it as the cross-check.
    out.sort(key=lambda r: (not (r["likely"] or r["split"]), -(r["exp_ga"] or 0)))
    return out


# ----------------------------------------------------------------------
# NFL
# ----------------------------------------------------------------------
NFL_DVP_GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE"}
NFL_GROUP_LABELS = {"QB": "QBs", "RB": "RBs", "WR": "WRs", "TE": "TEs"}
# The stats a defense is judged on, per position group.
DEFENSE_KEYS = {
    "QB": (("pass_yds", "pass yds"), ("pass_td", "pass TDs")),
    "RB": (("rush_yds", "rush yds"), ("td", "TDs"), ("rec", "catches")),
    "WR": (("rec_yds", "rec yds"), ("rec", "catches"), ("td", "TDs")),
    "TE": (("rec_yds", "rec yds"), ("rec", "catches"), ("td", "TDs")),
}


def nfl_td_rows(games, league, dvp=None):
    """Every skill player with an anytime-TD chance this week, best first.
    The chance is the projection's, run through the NFL prop test's own
    calibration curve for touchdowns when it exists."""
    from engines.nfl_projection import projection_rows
    bins = (((league or {}).get("prop_validation") or {}).get("td") or {}).get("calibration")
    live = [g for g in games or [] if g.get("status") != "final"]
    rows = projection_rows(live, league or {}, "Anytime TD")
    opp_of = {}
    for g in live:
        opp_of[(g.get("away_abbr") or g.get("away"))] = (g.get("home"), g.get("home_profile"))
        opp_of[(g.get("home_abbr") or g.get("home"))] = (g.get("away"), g.get("away_profile"))
    out = []
    for r in rows:
        if str(r.get("Status") or "").lower() == "out":
            continue
        raw = (r.get("Proj") or 0) / 100.0 if r.get("Proj") is not None else None
        ch, basis = _delivered(raw, bins)
        p, proj = r.get("_p") or {}, r.get("_proj") or {}
        grp = NFL_DVP_GROUP.get(str(p.get("pos") or "").upper())
        opp_name, opp_prof = opp_of.get(r.get("Team"), (None, None))
        card = dm.card(dvp, opp_name, grp, "td") if (dvp and grp and opp_name) else None
        ranks = (opp_prof or {}).get("ranks") or {}
        out.append({
            "player": r.get("Player"), "pos": r.get("Pos"), "team": r.get("Team"),
            "opp": r.get("Opp"), "status": r.get("Status") or "",
            "chance": ch, "raw": raw, "basis": basis, "fair": _fair(ch),
            "td_exp": proj.get("td_exp"), "touches": p.get("opps"),
            "implied": r.get("Implied pts"), "card_td": card,
            "opp_td_allowed_rank": ranks.get("td_allowed_pg"),
            "opp_rz_rank": ranks.get("rz_td_allowed_pct"),
            "of": (opp_prof or {}).get("rank_of"),
        })
    out.sort(key=lambda r: -(r["chance"] or 0))
    return out


def nfl_defense_rows(games, dvp, teams=None):
    """Every defense playing this week: for each position group, the stat
    it gives away most (its best card for the offense), the offense that
    faces it, and how many SOFT spots it has — most exploitable first."""
    out = []
    for g in games or []:
        if g.get("status") == "final":
            continue
        for side, other in (("home", "away"), ("away", "home")):
            dname = g.get(side)
            row = {"defense": g.get(f"{side}_abbr") or dname,
                   "attack": g.get(f"{other}_abbr") or g.get(other),
                   "game": f"{g.get('away_abbr')} @ {g.get('home_abbr')}",
                   "soft": 0, "soft_size": 0.0, "spots": [], "best": {}}
            for grp, keys in DEFENSE_KEYS.items():
                best = None
                for stat, lab in keys:
                    c = dm.card(dvp, dname, grp, stat)
                    if not c or not c.get("rank"):
                        continue
                    if best is None or c["rank"] < best[0]["rank"]:
                        best = (c, lab)
                if best:
                    row["best"][grp] = best
                    if best[0].get("tier") == "soft" and (best[0].get("vs_league_pct") or 0) > 0:
                        row["soft_size"] = row.get("soft_size", 0.0) + best[0]["vs_league_pct"]
                        row["soft"] += 1
                        row["spots"].append(f"{NFL_GROUP_LABELS[grp]} ({best[1]}, "
                                            f"{dm.rank_text(best[0]).rsplit(' of ', 1)[0]}, "
                                            f"{best[0].get('vs_league_pct') or 0:+.0f}%)")
            prof = (teams or {}).get(dname) or g.get(f"{side}_profile") or {}
            row["pa_pg"] = prof.get("pa_pg")
            row["pa_rank"] = (prof.get("ranks") or {}).get("pa_pg")
            row["td_allowed_pg"] = prof.get("td_allowed_pg")
            row["of"] = prof.get("rank_of")
            out.append(row)
    # Most SOFT spots first; among equals, the bigger gaps (summed % above
    # the league on those spots) — a +36% hole outranks a +4% one.
    out.sort(key=lambda r: (-r["soft"], -r.get("soft_size", 0.0), r["pa_rank"] or 99))
    return out


# ----------------------------------------------------------------------
# NHL Player of the Day (10-09) — MLB's structure on a tested number
# ----------------------------------------------------------------------
# MLB's Player of the Day is the site's best graded board (46% extra-base
# hits vs a 27% league rate). What makes it work is not its formula; it
# is one target, strict gates, matchup kept in proportion, and a nightly
# grade. Hockey keeps all four, on a number that is already tested:
#
#   TARGET   1+ point (Pts O0.5) — the most frequent scoring outcome, and
#            the one the skater model prices best end to end.
#   GATES    his market's walk-forward verdict is "beats" (no pick off an
#            untested number); POTD_MIN_GP games across both seasons (no
#            small-sample crowning); he played his team's last game (a
#            scratch or an injury shows up as a missed game first).
#   RANK     the DELIVERED chance (the curve of what calls like it hit on
#            unseen games). The matchup is already inside it, at the size
#            it measured — the shot and goal environment, ice time — so
#            nothing is nudged on top: MLB adds capped nudges because its
#            score is a 0-100 skill index with no matchup in it. Adding
#            them here would count the matchup twice.
#   GRADE    logged before puck drop, graded off the box score nightly
#            (data/top_plays/nhl_potd.json), judged on the Scorecard.
POTD_MIN_GP = 20
POTD_MARKET = "pt1"


def nhl_player_of_the_day(games, model, n=5):
    """(pick, top-n candidates, note). note says why there is no pick."""
    pv = (model or {}).get("props_validation") or {}
    v = pv.get(POTD_MARKET) or {}
    if ((v.get("verdict") or {}).get("verdict")) != "beats":
        return None, [], ("No pick: the 1+ point line has not beaten the skater's own "
                          "hit rate on unseen games, and this pick is only made off a "
                          "tested number.")
    bins = v.get("calibration")
    cands, gated = [], {"gp": 0, "missed": 0}
    for g in games or []:
        if g.get("game_type") == "preseason":
            continue
        for side, other in (("away", "home"), ("home", "away")):
            for p in g.get(f"{side}_props") or []:
                raw = (p.get("probs") or {}).get(POTD_MARKET)
                if raw is None:
                    continue
                if (p.get("gp") or 0) < POTD_MIN_GP:
                    gated["gp"] += 1
                    continue
                lg, tl = p.get("last_game"), p.get("team_last_game")
                if lg and tl and lg < tl:
                    gated["missed"] += 1
                    continue
                ch, basis = _delivered(raw, bins)
                cards = p.get("dvp") or {}
                cands.append({
                    "player": p.get("name"), "pid": p.get("pid"), "pos": p.get("pos"),
                    "team": g.get(f"{side}_abbr") or g.get(side),
                    "opp": g.get(f"{other}_abbr") or g.get(other),
                    "team_name": g.get(side),
                    "game": f"{g.get('away_abbr')} @ {g.get('home_abbr')}",
                    "game_label": f"{g.get('away')} @ {g.get('home')}",
                    "game_id": g.get("event_id"), "start": g.get("start_et"),
                    "time": g.get("time_et"), "gp": p.get("gp"),
                    "chance": ch, "raw": raw, "basis": basis, "fair": _fair(ch),
                    "exp_pts": p.get("exp_pts"), "exp_sog": p.get("exp_sog"),
                    "ice": p.get("ice") or {}, "pp": p.get("pp") or {},
                    "card_pts": cards.get("pts"), "why": p.get("why"),
                    "goal_env": (g.get(f"{side}_env") or {}).get("goal_ratio"),
                })
    cands.sort(key=lambda r: (-(r["chance"] or 0), -(r["exp_pts"] or 0)))
    note = None
    if not cands:
        note = (f"No eligible skater tonight ({gated['gp']} under {POTD_MIN_GP} games, "
                f"{gated['missed']} missed their team's last game).")
    return (cands[0] if cands else None), cands[:n], note


def potd_play(pick, date_str):
    """The pick in the shape top_plays_board.log_plays records and grades."""
    if not pick or not pick.get("game_id") or not pick.get("start"):
        return None
    return {"sport": "nhl", "game_id": pick["game_id"], "game": pick.get("game_label"),
            "start": pick["start"], "date": date_str, "player_id": pick["pid"],
            "player": pick["player"], "team": pick.get("team_name"),
            "market": POTD_MARKET, "label": "Pts O0.5", "stat": "pts", "at_least": 1,
            "p": pick["raw"], "p_cal": round(pick["chance"], 4),
            "fair": mm.fair_american(pick["chance"]), "why": pick.get("why")}


# ----------------------------------------------------------------------
# Multi-goal check (10-09): did the board see tonight's two-goal games?
# ----------------------------------------------------------------------
SNAP_TOP = 100


def multi_goal_snapshot(goal_rows, top=SNAP_TOP):
    """The pre-game 2+ goal ranking, kept small: the top `top` names with
    rank and delivered chance, how many skaters were ranked, and which
    games it covers (so grading knows when the night is complete)."""
    rows = sorted((r for r in goal_rows or [] if r.get("chance2") is not None),
                  key=lambda r: -r["chance2"])
    return {"n": len(rows),
            "games": sorted({str(r["game_id"]) for r in rows if r.get("game_id")}),
            "ranks": {str(r["pid"]): [i + 1, round(r["chance2"], 4), r.get("player"),
                                      r.get("team")]
                      for i, r in enumerate(rows[:top]) if r.get("pid")},
            "scorers": None}


def grade_multi_snapshot(snap, box_by_event):
    """Fill snap["scorers"] once EVERY game in it is final: each skater
    with 2+ goals, where he ranked before the game (None = outside the
    kept top). Returns True when it graded something."""
    if snap.get("scorers") is not None or not snap.get("games"):
        return False
    boxes = [box_by_event.get(g) for g in snap["games"]]
    if not all(b and b.get("final") for b in boxes):
        return False
    out = []
    for b in boxes:
        for pid, ln in (b.get("players") or {}).items():
            if (ln.get("g") or 0) >= 2:
                r = (snap.get("ranks") or {}).get(str(pid))
                out.append({"pid": str(pid), "name": ln.get("name") or (r[2] if r else None),
                            "g": ln.get("g"), "rank": r[0] if r else None,
                            "chance2": r[1] if r else None})
    snap["scorers"] = sorted(out, key=lambda x: (x["rank"] is None, x["rank"] or 0))
    return True


def multi_check_summary(snaps, top=25):
    """Over graded nights: multi-goal scorers, how many sat in the board's
    top `top`, and how many a RANDOM `top` names would have caught (the
    honest comparison — a list that does no better than random sees
    nothing)."""
    nights = [(d, s) for d, s in sorted((snaps or {}).items()) if s.get("scorers") is not None]
    total = sum(len(s["scorers"]) for _d, s in nights)
    caught = sum(1 for _d, s in nights for x in s["scorers"]
                 if x.get("rank") is not None and x["rank"] <= top)
    random_ = sum(len(s["scorers"]) * min(top, s.get("n") or 0) / s["n"]
                  for _d, s in nights if s.get("n"))
    return {"nights": len(nights), "scorers": total, "caught": caught,
            "random": round(random_, 1), "top": top}
