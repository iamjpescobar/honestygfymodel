"""
Projected run total for a KBO or NPB game.

WHAT THIS IS
------------
An expected total built from four measured quantities and nothing else:

    each team's runs scored per game      (their offense)
    each team's runs allowed per game     (their pitching + defense)
    the league's runs per game            (the baseline both sit against)
    the announced starter's ERA           (when it's published)

The core is the standard log5-style pairing: a team's expected runs
against a specific opponent is its own offense adjusted by how that
opponent actually pitches, relative to the league. Written out:

    expected = (team_rs_pg * opp_ra_pg) / league_rs_pg

That is not a heuristic — it is what those three numbers mean when you
combine them. A team scoring 5.0 against an opponent allowing exactly
league average returns 5.0. Against an opponent allowing 20% fewer runs
than average, it returns 20% less. The total is the two sides summed.

WHAT IT IS NOT
--------------
It is NOT a moneyline, and it deliberately doesn't try to be. A win
probability requires converting an expected run margin into a
percentage, and that conversion is a FITTED relationship — you cannot
derive it from run averages alone. Without graded history to fit
against, any exponent chosen here would be invented, and the output
would be a confident percentage backed by nothing. That is the one thing
this site doesn't do. Totals are arithmetic on real numbers; moneylines
need evidence that doesn't exist yet.

STARTERS
--------
When a probable starter's ERA is published it nudges the opposing side's
expectation, bounded hard. A starter throws maybe six of nine innings
and ERA is a noisy, defense-contaminated stat, so it gets a small,
capped voice rather than a starring role. Absent, the pairing above
stands on its own — which is honest, because a team's runs-allowed
average already contains its rotation.
"""

# A starter covers roughly two thirds of a game, and ERA is noisy enough
# that the full difference shouldn't flow through even for that share.
STARTER_WEIGHT = 0.45
# Hard ceiling on the starter's influence, in runs.
STARTER_CAP = 1.2
# Sanity band. Outside this the inputs are wrong, not the teams.
MIN_TOTAL, MAX_TOTAL = 3.0, 20.0


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None          # reject NaN


def expected_runs(team_rs_pg, opp_ra_pg, league_rs_pg):
    """One side's expected runs, or None if any input is missing.

    None rather than a fallback: a total built on a guessed offense is
    not a projection, and quietly substituting the league average would
    make every unmeasurable team look exactly average.
    """
    rs, ra, lg = _num(team_rs_pg), _num(opp_ra_pg), _num(league_rs_pg)
    if rs is None or ra is None or not lg:
        return None
    return rs * ra / lg


def starter_adjustment(starter_era, league_era):
    """Runs to shave off (or add to) the opposing side, bounded.

    Negative when the starter is better than league average — he
    suppresses the other team's expectation.
    """
    era, lg = _num(starter_era), _num(league_era)
    if era is None or not lg:
        return 0.0
    # ERA is already runs per nine innings, so the gap IS a per-game run
    # difference — scaled down for the share of the game he actually
    # throws, then capped.
    diff = (era - lg) * STARTER_WEIGHT
    return max(-STARTER_CAP, min(STARTER_CAP, round(diff, 2)))


def project_total(home, away, league_rs_pg, league_era=None,
                  home_starter_era=None, away_starter_era=None):
    """(total, detail) — projected runs for this game, or (None, why).

    home/away are dicts carrying rs_pg and ra_pg under either the KBO
    names (runs_per_game / runs_allowed_per_game) or the NPB ones
    (rs_pg / ra_pg), so one engine serves both leagues rather than two
    copies drifting apart.
    """
    def rs(d):
        return (d or {}).get("rs_pg", (d or {}).get("runs_per_game"))

    def ra(d):
        return (d or {}).get("ra_pg", (d or {}).get("runs_allowed_per_game"))

    home_exp = expected_runs(rs(home), ra(away), league_rs_pg)
    away_exp = expected_runs(rs(away), ra(home), league_rs_pg)
    if home_exp is None or away_exp is None:
        return None, {"reason": "not enough real run data for both teams yet"}

    # The AWAY starter suppresses the HOME offense, and vice versa.
    h_adj = starter_adjustment(away_starter_era, league_era)
    a_adj = starter_adjustment(home_starter_era, league_era)
    home_exp = max(0.0, home_exp + h_adj)
    away_exp = max(0.0, away_exp + a_adj)

    total = round(home_exp + away_exp, 1)
    if not (MIN_TOTAL <= total <= MAX_TOTAL):
        return None, {"reason": f"projected total {total} is outside the "
                                f"plausible range — inputs look wrong"}

    return total, {
        "home_exp": round(home_exp, 2),
        "away_exp": round(away_exp, 2),
        "home_starter_adj": a_adj,
        "away_starter_adj": h_adj,
        "league_rs_pg": _num(league_rs_pg),
        # Stated on the card so nobody reads this as a priced line.
        "basis": ("team runs scored/allowed per game paired against each "
                  "other, relative to the league average"),
    }


def league_run_average(team_stats):
    """League runs per game, measured across the teams on file.

    Uses runs SCORED, since every run scored is a run allowed and the two
    must average to the same figure — computing it from the data keeps
    the baseline honest as a season develops rather than freezing an
    assumed constant.
    """
    vals = []
    for t in (team_stats or {}).values():
        v = _num((t or {}).get("rs_pg", (t or {}).get("runs_per_game")))
        if v is not None:
            vals.append(v)
    return round(sum(vals) / len(vals), 3) if vals else None