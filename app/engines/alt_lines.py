"""
Team totals, alternate spreads and alternate totals — every line a book
hangs on a game, priced from the SAME score distributions the game model
already uses. No new parameters: nothing here is fitted or chosen.

    MLB / NHL   each side's score is the game model's negative binomial
                (or Poisson) around its projected mean; a margin is the
                difference of the two, with a level game resolved by one
                run/goal at the MEASURED rate the home side wins those
                (model_math.margin_cover_prob).
    NFL         margin and total are normal with the SDs the nightly
                MEASURED on its walk-forward residuals. A TEAM total needs
                one side's SD, which is derived from those two:
                    home = (total + margin) / 2
                    Var(home) = (Var(total) + Var(margin)) / 4
                taking the total and margin errors as uncorrelated (by
                symmetry, Cov = Var(home) - Var(away), which is ~0 over a
                season of home and road teams). Labelled DERIVED on the page.

What these are NOT: anchored to a market. The feeds carry one total and
one spread per game, so an alt line or a team total has no posted price
to measure the model against — the page says "model only", and the
any-line checker prices it at the reader's own number.

Pure — no streamlit.
"""
from engines import model_math as mm

# Lines shown in the tables (the reader can price any other).
TEAM_TOTAL_LINES = {"mlb": (2.5, 3.5, 4.5, 5.5), "nhl": (1.5, 2.5, 3.5, 4.5),
                    "nfl": (17.5, 20.5, 23.5, 26.5, 29.5)}
ALT_SPREADS = {"mlb": (-2.5, -1.5, 1.5, 2.5), "nhl": (-2.5, -1.5, 1.5, 2.5),
               "nfl": (-10.5, -7.5, -6.5, -3.5, -2.5, 2.5, 3.5, 6.5, 7.5, 10.5)}


def _count_ok(proj):
    return proj and proj.get("mu_home") is not None and proj.get("mu_away") is not None


def team_total_over(proj, side, line, sport):
    """P(that side scores more than `line`), pushes excluded."""
    if not _count_ok(proj) or line is None:
        return None
    mu = proj["mu_home"] if side == "home" else proj["mu_away"]
    if sport == "nfl":
        sd = team_sd(proj)
        return None if sd is None else 1 - mm.normal_cdf(line, mu, sd)
    return mm.over_prob_pmf(mm.score_pmf(mu, proj.get("dispersion")), line)


def team_sd(proj):
    """NFL one-side SD, DERIVED from the measured margin and total SDs."""
    sm, stt = proj.get("sd_margin"), proj.get("sd_total")
    if not sm or not stt:
        return None
    return ((sm * sm + stt * stt) / 4.0) ** 0.5


def home_cover(proj, home_spread, sport):
    """P(home covers `home_spread`), pushes excluded."""
    if not _count_ok(proj) or home_spread is None:
        return None
    if sport == "nfl":
        sd = proj.get("sd_margin")
        if not sd:
            return None
        return mm.normal_cdf(proj["mu_home"] - proj["mu_away"] + home_spread, 0, sd)
    return mm.margin_cover_prob(proj["mu_home"], proj["mu_away"], home_spread,
                                proj.get("dispersion"), proj.get("tie_home_win_used", 0.5))


def total_over(proj, line, sport):
    if not _count_ok(proj) or line is None:
        return None
    if sport == "nfl":
        sd = proj.get("sd_total")
        if not sd:
            return None
        return 1 - mm.normal_cdf(line, proj["mu_home"] + proj["mu_away"], sd)
    return mm.total_over_prob(proj["mu_home"], proj["mu_away"], line, proj.get("dispersion"))


def alt_total_lines(proj, sport):
    """The posted total and the lines around it (book alt-total ladders)."""
    base = proj.get("market_total")
    if base is None and _count_ok(proj):
        base = round((proj["mu_home"] + proj["mu_away"]) * 2) / 2.0
    if base is None:
        return ()
    step = {"mlb": 1.0, "nhl": 1.0, "nfl": 3.0}.get(sport, 1.0)
    out = sorted({base + k * step for k in (-2, -1, 0, 1, 2) if base + k * step > 0})
    return tuple(out)


def tables(proj, sport):
    """{"team_totals": [...], "spreads": [...], "totals": [...]} rows of
    (label, line, p_over_or_cover) for the page."""
    if not _count_ok(proj):
        return None
    tt = []
    for side in ("away", "home"):
        for ln in TEAM_TOTAL_LINES.get(sport, ()):
            tt.append((side, ln, team_total_over(proj, side, ln, sport)))
    sp = [(s, home_cover(proj, s, sport)) for s in ALT_SPREADS.get(sport, ())]
    to = [(ln, total_over(proj, ln, sport)) for ln in alt_total_lines(proj, sport)]
    return {"team_totals": tt, "spreads": sp, "totals": to}
