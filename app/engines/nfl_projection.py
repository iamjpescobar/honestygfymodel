"""Projected stat lines for every skill player on an NFL slate.

WHAT THIS IS

A projection is a volume times a rate. Both halves are measured from
real box scores, and the matchup adjustment between them is a ratio of
two measured numbers — never a weight somebody liked the look of.

    expected volume   = the player's share of his team's carries or
                        targets  x  his team's carries or targets a game
    matchup multiplier= what the defense across from him allows per
                        attempt  /  the league average per attempt
    projected yards   = expected volume x his own rate x that multiplier

Touchdowns take the same shape, anchored to the market rather than to
our own guess at how many points a team scores:

    implied points    = (posted total -/+ posted spread) / 2   [exact]
    expected team TDs = implied points x offensive TDs per point [measured]
    player lambda     = expected team TDs x his share of team TDs
    P(anytime)        = 1 - exp(-lambda)                    [ASSUMPTION]

THE FREE-PARAMETER RULE

Standing rule 1 says every number on this site chosen by eye turned out
wrong when it was finally measured — a scale whose top tiers no team
could reach, a floor that cleared 373 of 373 hitters. So this engine
contains NO fitted weights and no blends. Every constant it divides by
is recomputed from the season's real finals by nfl_precompute on every
nightly and shipped in games.json, and every multiplier is a ratio of
two of those measured quantities.

That is a deliberate v1 restriction, not a claim that the result is
optimal. Three questions stay open and nfl_projection_probe.py measures
them against outcomes:

  1. Does the matchup multiplier at full strength help, or overshoot?
  2. Does the posted spread predict run/pass volume enough to be worth
     a game-script adjustment?
  3. Does a share measured over three games predict the next game?

Until the probe answers them, nothing here is tuned, and the board says
so in as many words.

THE ONE ASSUMPTION, NAMED

P(anytime) = 1 - exp(-lambda) treats touchdowns as Poisson. That is a
modelling choice, not a measurement, and it is the only one in the file.
It is labelled on the board and it is what the probe checks first.
"""
import math

# Every market the board can rank, and what each row needs to exist.
# A market a player has no sample for returns None and renders as an
# em-dash — never a zero, which would read as a real projection of
# nothing (rule 6).
MARKETS = {
    "Anytime TD": ("anytime_pct", "%"),
    "Rushing yards": ("rush_yds", ""),
    "Carries": ("carries", ""),
    "Receiving yards": ("rec_yds", ""),
    "Receptions": ("rec", ""),
    "Targets": ("targets", ""),
    "Passing yards": ("pass_yds", ""),
    "Pass attempts": ("pass_att", ""),
    "Rush + rec yards": ("scrim_yds", ""),
}

# Which role each market belongs to, so the board never ranks a guard's
# receiving yards against a number one receiver's.
MARKET_ROLES = {
    "Anytime TD": ("RB", "REC"),
    "Rushing yards": ("RB", "QB"),
    "Carries": ("RB",),
    "Receiving yards": ("REC", "RB"),
    "Receptions": ("REC", "RB"),
    "Targets": ("REC", "RB"),
    "Passing yards": ("QB",),
    "Pass attempts": ("QB",),
    "Rush + rec yards": ("RB", "REC"),
}


def implied_totals(odds, away_abbr="", home_abbr=""):
    """(away_points, home_points, note) implied by the posted line.

    EXACT ARITHMETIC ON THE MARKET'S OWN NUMBERS, not an estimate. The
    favourite is implied for (total + margin) / 2 and the underdog for
    (total - margin) / 2; those two always sum back to the total.

    ESPN states `spread` relative to the HOME team, so a negative spread
    means the home side is favoured. That convention is the one thing
    here that could silently invert every projection on the card, so it
    is CHECKED rather than trusted: `details` names the favourite by
    abbreviation, and when that name contradicts the sign, this returns
    no implied totals at all and says why. A backwards implied total
    would not look wrong on screen — it would look like a confident
    projection of the wrong team.
    """
    total, spread = (odds or {}).get("total"), (odds or {}).get("spread")
    if total is None:
        return None, None, "no posted total"
    if spread is None:
        half = round(total / 2.0, 1)
        return half, half, "no posted spread — split evenly"
    home = round((total - spread) / 2.0, 1)
    away = round((total + spread) / 2.0, 1)

    details = str((odds or {}).get("details") or "").upper()
    fav = details.split()[0] if details else ""
    if fav and away_abbr and home_abbr and fav in (away_abbr.upper(), home_abbr.upper()):
        fav_is_home = fav == home_abbr.upper()
        sign_says_home = spread < 0
        if spread and fav_is_home != sign_says_home:
            return None, None, (f"posted line disagrees with itself "
                                f"({details} vs spread {spread:+g}) — no implied "
                                f"totals rather than a backwards one")
    return away, home, ""


def _ratio(allowed, league):
    """Matchup multiplier: what this defence allows over the league.

    1.0 when either side is unmeasured, so a missing number leaves the
    projection at the player's own rate instead of silently moving it.
    """
    if allowed is None or not league:
        return 1.0, None
    return round(allowed / league, 3), round(allowed / league, 3)


def project_player(p, team, opp, league, implied_pts):
    """One player's projected line, with every input that produced it.

    `p` is a row from games.json's {side}_players, `team` and `opp` the
    two team profiles, `league` the measured constants, `implied_pts`
    what the market implies his team scores.

    Returns a dict carrying the projections AND the inputs, because a
    number whose inputs are hidden cannot be checked — and on a
    three-game sample checking it is the whole job.
    """
    out = {"role": p.get("role"), "gp": p.get("gp")}
    # `opp` is NOT required. _ratio already returns 1.0 for anything it
    # cannot measure, so a team that has not played yet leaves the
    # projection at the player's own rate — which is a true, useful
    # number — instead of deleting the row entirely. The row carries
    # `unadjusted` so the board can say which of the two it is showing.
    if not team or not league:
        return out
    opp = opp or {}
    if opp.get("ypc_allowed") is None and opp.get("ypt_allowed") is None:
        out["unadjusted"] = True

    # ---- volume ------------------------------------------------------
    # The team's own per-game attempts. NOT blended with what the
    # opponent faces: a blend needs a weight, a weight would be chosen by
    # eye, and rule 1 is what it is. The opponent's faced rate travels on
    # the row instead, as context the reader can apply themselves.
    car_share, tgt_share = p.get("carry_share"), p.get("target_share")
    team_car, team_tgt = team.get("carries_pg"), team.get("targets_pg")
    if car_share is not None and team_car:
        out["carries"] = round(car_share * team_car, 1)
    if tgt_share is not None and team_tgt:
        out["targets"] = round(tgt_share * team_tgt, 1)

    # ---- rates, adjusted by the matchup ------------------------------
    rush_mult, out["rush_matchup"] = _ratio(opp.get("ypc_allowed"), league.get("ypc"))
    rec_mult, out["rec_matchup"] = _ratio(opp.get("ypt_allowed"),
                                          league.get("yards_per_target"))
    catch_mult, _ = _ratio(opp.get("catch_rate_allowed"), league.get("catch_rate"))

    if out.get("carries") is not None and p.get("ypc") is not None:
        out["ypc_adj"] = round(p["ypc"] * rush_mult, 2)
        out["rush_yds"] = round(out["carries"] * out["ypc_adj"], 1)
    if out.get("targets") is not None:
        if p.get("catch_rate") is not None:
            out["rec"] = round(out["targets"] * p["catch_rate"] * catch_mult, 1)
        if p.get("yards_per_target") is not None:
            out["ypt_adj"] = round(p["yards_per_target"] * rec_mult, 2)
            out["rec_yds"] = round(out["targets"] * out["ypt_adj"], 1)
    if out.get("rush_yds") is not None or out.get("rec_yds") is not None:
        out["scrim_yds"] = round((out.get("rush_yds") or 0)
                                 + (out.get("rec_yds") or 0), 1)

    # ---- passing -----------------------------------------------------
    # A quarterback's attempts are his team's pass attempts; targets are
    # the honest proxy the box score gives us (they differ by throwaways
    # and spikes, which is why this says "attempts" and not "dropbacks").
    if p.get("role") == "QB" and team_tgt:
        out["pass_att"] = round(team_tgt, 1)
        ypa = ((p.get("pass_yds") / p.get("pass_att"))
               if p.get("pass_att") else None)
        if ypa:
            out["ypa_adj"] = round(ypa * rec_mult, 2)
            out["pass_yds"] = round(out["pass_att"] * out["ypa_adj"], 1)

    # ---- touchdowns --------------------------------------------------
    # Anchored to the MARKET's view of how many points this team scores,
    # converted at the measured offensive-TDs-per-point rate, then split
    # by the player's measured share of his team's scores.
    tpp = league.get("td_per_point")
    if implied_pts is not None and tpp:
        team_tds = implied_pts * tpp
        out["team_td_exp"] = round(team_tds, 2)
        share = p.get("td_share")
        if share is not None:
            lam = team_tds * share
            out["td_exp"] = round(lam, 2)
            # THE ONE ASSUMPTION IN THIS FILE, and it is named on the
            # board: scores arrive as a Poisson process, so the chance of
            # at least one is 1 - exp(-lambda).
            out["anytime_pct"] = round(100.0 * (1.0 - math.exp(-lam)))
    return out


def attach_td_shares(games, league=None):
    """Each player's expected share of his team's touchdowns, in place.

    REPLACED WHAT THE PROBE KILLED. This used to be his share of his
    team's ACTUAL scores, which measured terribly: 65% of skill players
    had none and were handed a flat 0% against a real 23% base rate,
    while one score in one game came out at 88%.

    Now the share is built from OPPORTUNITY — carries plus targets, the
    part of scoring that repeats — times his own conversion rate shrunk
    toward the league by the fitted beta-binomial prior (see
    nfl_precompute.td_opportunity_prior). The shares are then normalised
    so a team's skill players divide that team's expected touchdowns
    between them.

    Normalising to the FULL team expectation deliberately: measured on
    the week-3 slate it reproduced the real 23.0% base rate to within
    0.2 points, because the listed skill players take nearly all of a
    team's offensive scores. Scaling it down for quarterback rushing
    would have made it worse, not better.

    Falls back to the old realised-share method only when no prior has
    been fitted, so an old data file still renders rather than blanking.
    """
    a = (league or {}).get("prior_a")
    b = (league or {}).get("prior_b")
    for g in games or []:
        for side in ("away", "home"):
            rows = g.get(f"{side}_players") or []
            team_td = sum(r.get("td_total") or 0 for r in rows)
            for r in rows:
                r["team_td_total"] = team_td
            if a is None or b is None:
                for r in rows:
                    if team_td:
                        r["td_share"] = round((r.get("td_total") or 0) / team_td, 3)
                continue
            raw = []
            for r in rows:
                opps = r.get("opps") or 0
                touches = round(opps * (r.get("td_games") or 0))
                scores = min(r.get("td_total") or 0, touches)
                rate = (scores + a) / (touches + a + b) if (touches + a + b) else 0.0
                r["td_rate"] = round(rate, 4)
                r["touches"] = touches
                raw.append(opps * rate)
            total = sum(raw)
            for r, v in zip(rows, raw):
                r["td_share"] = round(v / total, 4) if total else None


def projection_rows(games, league, market):
    """Every player on the slate for one market, best projection first."""
    key, _suffix = MARKETS[market]
    roles = MARKET_ROLES[market]
    attach_td_shares(games, league)
    out = []
    for g in games or []:
        odds = g.get("odds") or {}
        away_pts, home_pts, note = implied_totals(
            odds, g.get("away_abbr"), g.get("home_abbr"))
        for side, other in (("away", "home"), ("home", "away")):
            team, opp = g.get(f"{side}_profile"), g.get(f"{other}_profile")
            implied = away_pts if side == "away" else home_pts
            for p in g.get(f"{side}_players") or []:
                if p.get("role") not in roles:
                    continue
                proj = project_player(p, team, opp, league, implied)
                if proj.get(key) is None:
                    continue
                out.append({
                    "Player": p.get("name"), "Pos": p.get("pos") or p.get("role"),
                    "Team": g.get(f"{side}_abbr") or g.get(side),
                    "Opp": g.get(f"{other}_abbr") or g.get(other),
                    "Status": p.get("status") or "", "GP": p.get("gp"),
                    "Proj": proj[key],
                    "Carries": proj.get("carries"), "Targets": proj.get("targets"),
                    "Rush yds": proj.get("rush_yds"), "Rec yds": proj.get("rec_yds"),
                    "Rec": proj.get("rec"), "Pass yds": proj.get("pass_yds"),
                    "TD exp": proj.get("td_exp"), "Anytime %": proj.get("anytime_pct"),
                    # THE SAMPLE, ON THE ROW. A share of 2-of-2 and a
                    # share of 9-of-18 are both "100%" and "50%" and are
                    # not remotely the same claim. There is no shrinkage
                    # factor applied to the first — that would be a free
                    # parameter chosen by eye (rule 1) — so instead the
                    # reader is shown exactly what it rests on and can
                    # discount it himself.
                    # BOTH halves guarded: a player with no scoring game
                    # at all has td_total None, not 0, and formatting a
                    # None crashed the whole board on the first such row.
                    # TOUCHES, not team share. What drives the number now
                    # is how often he gets the ball; the scores he has
                    # ride alongside so the reader sees both.
                    "TD sample": (f'{p.get("td_total") or 0:.0f} on {p["touches"]:.0f}'
                                  if p.get("touches") else
                                  (f'{p.get("td_total") or 0:.0f} of '
                                   f'{p["team_td_total"]:.0f}'
                                   if p.get("team_td_total") else None)),
                    "TD/touch": (round((p.get("td_rate") or 0) * 100, 1)
                                 if p.get("td_rate") is not None else None),
                    "Matchup": (proj.get("rush_matchup") if market in
                                ("Rushing yards", "Carries") else proj.get("rec_matchup")),
                    "Implied pts": implied,
                    "_p": p, "_proj": proj, "_note": note,
                    "_window": g.get("window") or "", "_final": g.get("status") == "final",
                })
    out.sort(key=lambda r: -(r["Proj"] if r["Proj"] is not None else -1))
    return out


def why(row, market):
    """The row restated as a sentence: what produced this number.

    A projection nobody can take apart is indistinguishable from a
    number that was made up, so every figure on the row appears here in
    the order the engine used it.
    """
    p, proj = row.get("_p") or {}, row.get("_proj") or {}
    bits = []
    if market in ("Rushing yards", "Carries", "Rush + rec yards") and proj.get("carries"):
        bits.append(f'{(p.get("carry_share") or 0) * 100:.0f}% of {row["Team"]}’s '
                    f'carries → {proj["carries"]:.1f} a game')
        if proj.get("ypc_adj") and p.get("ypc"):
            bits.append(f'{p["ypc"]:.2f} yds a carry, {row["Opp"]} allows '
                        f'{proj.get("rush_matchup", 1):.2f}x the league '
                        f'→ {proj["ypc_adj"]:.2f}')
    if market in ("Receiving yards", "Receptions", "Targets", "Rush + rec yards") \
            and proj.get("targets"):
        bits.append(f'{(p.get("target_share") or 0) * 100:.0f}% of {row["Team"]}’s '
                    f'targets → {proj["targets"]:.1f} a game')
        if proj.get("ypt_adj") and p.get("yards_per_target"):
            bits.append(f'{p["yards_per_target"]:.2f} yds a target, {row["Opp"]} allows '
                        f'{proj.get("rec_matchup", 1):.2f}x → {proj["ypt_adj"]:.2f}')
    if market in ("Passing yards", "Pass attempts") and proj.get("pass_att"):
        bits.append(f'{proj["pass_att"]:.0f} attempts at {proj.get("ypa_adj", 0):.2f} '
                    f'yards each after the {row["Opp"]} adjustment')
    if market == "Anytime TD":
        if row.get("Implied pts") is not None:
            bits.append(f'market implies {row["Team"]} score {row["Implied pts"]:g} '
                        f'→ {proj.get("team_td_exp", 0):.2f} offensive TDs')
        if p.get("touches") is not None:
            bits.append(f'{p.get("opps") or 0:.1f} touches a game, and he has '
                        f'{p.get("td_total") or 0:.0f} score(s) on {p["touches"]:.0f} '
                        f'of them \u2014 shrunk toward the league that gives '
                        f'{(p.get("td_rate") or 0) * 100:.1f}% a touch')
        elif p.get("td_total") is not None and p.get("team_td_total"):
            bits.append(f'he has {p["td_total"]:.0f} of their {p["team_td_total"]:.0f} '
                        f'scores in {p.get("td_games", 0)} games')
        if proj.get("td_exp") is not None:
            bits.append(f'{proj["td_exp"]:.2f} expected → {row["Proj"]:.0f}% '
                        f'chance of at least one')
    return " · ".join(bits)
