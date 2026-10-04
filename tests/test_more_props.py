"""
The 10-04 research expansion: team totals and alt lines (engines/
alt_lines), NHL any-line skater props and goalie saves (engines/
nhl_model), and the NFL quarterback rate markets (nfl_projection +
nfl_precompute.qb_rate_priors).

Every new number is checked for agreeing with the number the site already
printed for the same thing (a team total at the line a game total implies,
a skater's SOG O2.5 cell), and every fitted prior for recovering a known
answer (rule 3).

Negative controls, confirmed red by exit code when written (rule 4):
  - saves_pmf thinning with the GOAL rate instead of the save rate ->
    section 3's mean check fails
  - alt_lines.team_sd using the total's SD alone -> section 1's derived-SD
    check fails
  - nhl_model.skater_pmfs pricing points as goals only -> section 2's
    agreement-with-the-table check fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import alt_lines as al        # noqa: E402
from engines import game_model as gm       # noqa: E402
from engines import model_math as mm       # noqa: E402
from engines import nhl_model as nm        # noqa: E402
from engines import nfl_game_model as ngm  # noqa: E402
from engines import nfl_projection as npj  # noqa: E402
from engines import nfl_prop_odds as npo   # noqa: E402
import nfl_precompute as nfp               # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --------------------------------------------- 1. team totals and alt lines
model = {"rates": {"A": {"off": 4.8, "def": 4.0}, "B": {"off": 4.2, "def": 4.6}},
         "league": {"league_rate": 4.5, "home_mult": 1.02, "away_mult": 0.98, "tie_home_win": 0.52},
         "params": {"dispersion": 4.0}}
pj = gm.project(model, "A", "B", market={"total": 8.5})
t = al.tables(pj, "mlb")
check("MLB tables: both teams' totals at every line, alt spreads, alt totals",
      len(t["team_totals"]) == 8 and len(t["spreads"]) == 4 and len(t["totals"]) == 5)
check("the alt-total ladder is centred on the posted total",
      [ln for ln, _p in t["totals"]] == [6.5, 7.5, 8.5, 9.5, 10.5])
check("alt total at the posted line IS the game card's over chance",
      abs(dict(t["totals"])[8.5] - pj["p_over"]) < 1e-3)
check("home -0.5 IS the game card's home win chance",
      abs(al.home_cover(pj, -0.5, "mlb") - pj["p_home"]) < 1e-3)
tt = {(s, ln): p for s, ln, p in t["team_totals"]}
check("team totals fall as the line rises", tt[("home", 2.5)] > tt[("home", 3.5)] > tt[("home", 4.5)])
check("the stronger home side's team total is above the visitor's at the same line",
      tt[("home", 4.5)] > tt[("away", 4.5)])
nmodel = {"rates": {"1": {"off": 24.0, "def": 20.0}, "2": {"off": 21.0, "def": 23.0}},
          "league": {"league_rate": 22.0, "home_mult": 1.03, "away_mult": 0.97},
          "params": {"sd_margin": 13.0, "sd_total": 14.0}, "blend": {}}
npj_ = ngm.project(nmodel, "1", "2", {"total": 44.5, "spread": -3.0, "details": "HOM -3",
                                       "home_ml": -150, "away_ml": 130}, "HOM", "AWY")
check("NFL one-side SD is DERIVED from the measured margin and total SDs",
      abs(al.team_sd(npj_) - ((13.0 ** 2 + 14.0 ** 2) / 4) ** 0.5) < 1e-9)
check("NFL alt spread at the posted line IS the card's cover chance",
      abs(al.home_cover(npj_, -3.0, "nfl") - npj_["p_home_cover"]) < 1e-3)
check("NFL alt total at the posted line IS the card's over chance",
      abs(al.total_over(npj_, 44.5, "nfl") - npj_["p_over"]) < 1e-3)
check("a projection without score means gets no alt tables (never invented)",
      al.tables({"p_home": 0.5}, "nfl") is None)

# ------------------------------------------------ 2. NHL any-line skaters
pri = {"F": {"sog": [2.4, 20.0], "g": [0.3, 40.0], "a": [0.4, 40.0]}}
player = {"pos": "C", "games": [("2025-10-01", "1", 4, 1, 0, 18.0)] * 30}
r = nm.rates(player, pri)
pr = nm.probs(r, 1.1, 0.95, 6.0)
pm = nm.skater_pmfs(pr["_mu"], 6.0)
check("SOG O2.5 from the any-line pmf IS the table's cell",
      abs(mm.prob_at_least(pm["sog"], 3) - pr["sog3"]) < 1e-3)
check("Pts O0.5 from the any-line pmf IS the table's cell",
      abs(mm.prob_at_least(pm["pts"], 1) - pr["pt1"]) < 1e-3)
check("O4.5 shots is priced too (a new standard line)", "sog5" in pr and pr["sog5"] < pr["sog4"])
check("a row with no stored means prices nothing", nm.skater_pmfs(None) == {})

# ----------------------------------------------------- 3. NHL goalie saves
sp = nm.saves_pmf(30.0, 40.0, 0.905)
check("saves pmf sums to 1", abs(sum(sp) - 1) < 1e-6)
mean = sum(i * p for i, p in enumerate(sp))
check(f"expected saves = expected shots x save rate (got {mean:.2f}, want 27.15)",
      abs(mean - 27.15) < 0.05)
check("a better goalie makes more saves on the same shots",
      mm.prob_at_least(nm.saves_pmf(30.0, 40.0, 0.92), 27)
      > mm.prob_at_least(nm.saves_pmf(30.0, 40.0, 0.89), 27))
g = random.Random(3)
goalies = {}
for i in range(60):
    true = g.gauss(0.900, 0.008)
    sa = g.randint(300, 1800)
    goalies[str(i)] = {"sa": sa, "sv": sum(g.random() < true for _ in range(sa))}
mu, s = nm.fit_save_prior(goalies)
pooled = sum(v["sv"] for v in goalies.values()) / sum(v["sa"] for v in goalies.values())
check(f"save prior's mean is the league's pooled save rate ({mu:.4f} vs {pooled:.4f}) "
      f"and its strength is finite", abs(mu - pooled) < 1e-9 and 0 < s < 1e5)
small = nm.goalie_sv(None, {"sa": 30, "sv": 30}, mu, s)
check("a 30-for-30 backup is pulled most of the way back to the league, not 1.000",
      small[0] < 0.92 and small[1] == 30)
check("last season and this one are pooled", nm.goalie_sv({"sa": 1000, "sv": 910},
                                                         {"sa": 100, "sv": 90}, mu, s)[1] == 1100)

# ------------------------------------------------- 4. NFL quarterback rates
logs = {}
for q in range(32):
    rate_c, rate_t, rate_i = g.gauss(0.65, 0.03), g.gauss(0.045, 0.008), g.gauss(0.025, 0.005)
    games = {}
    for w in range(10):
        att = g.randint(25, 42)
        games[f"{q}-{w}"] = {"passing": {"att": att,
                                         "cmp": sum(g.random() < rate_c for _ in range(att)),
                                         "td": sum(g.random() < rate_t for _ in range(att)),
                                         "int": sum(g.random() < rate_i for _ in range(att))}}
    logs[str(q)] = {"games": games}
qp = nfp.qb_rate_priors(logs)["qb_priors"]
_tot = {k: sum(sum(gm_["passing"][k] for gm_ in r["games"].values()) for r in logs.values())
        for k in ("att", "cmp", "td", "int")}
check(f"QB priors centre on the league's pooled per-attempt rates "
      f"(cmp {qp['cmp'][0]:.3f}, TD {qp['td'][0]:.4f}, INT {qp['int'][0]:.4f})",
      all(abs(qp[k][0] - _tot[k] / _tot["att"]) < 1e-4 for k in ("cmp", "td", "int")))
check("...near the fixture's .65 / .045 / .025", abs(qp["cmp"][0] - 0.65) < 0.02
      and abs(qp["td"][0] - 0.045) < 0.008 and abs(qp["int"][0] - 0.025) < 0.006)
qb = {"role": "QB", "pass_yds": 250.0, "pass_att": 34.0, "pass_cmp": 23.0, "pass_td": 3.0,
      "pass_int": 0.0, "pass_gp": 2, "gp": 2}
team = {"targets_pg": 33.0, "carries_pg": 26.0}
league = {"yards_per_target": 7.0, "ypc": 4.3, "catch_rate": 0.65, "qb_priors": qp}
proj = npj.project_player(qb, team, {}, league, 24.0)
check("completions, passing TDs and INTs projected for a quarterback",
      all(proj.get(k) is not None for k in ("pass_cmp", "pass_td", "pass_int")))
check("a 2-game, 0-INT quarterback is NOT projected for zero interceptions (shrunk)",
      proj["pass_int"] > 0.3)
check("...and his 3 TDs a game are pulled toward the league, not projected at 3",
      proj["pass_td"] < 2.5)
rb = {"role": "RB", "td_share": 0.3, "gp": 3}
p2 = npj.project_player(rb, {"carries_pg": 25, "targets_pg": 30}, {}, {"td_per_point": 0.11}, 27.0)
lam = 27.0 * 0.11 * 0.3
check("2+ TDs is the same Poisson read at two",
      abs(p2["two_td_pct"] - 100 * (1 - mm.poisson_pmf(lam)[0] - mm.poisson_pmf(lam)[1])) < 0.11)
spreads = npo.measure_spreads({k: v for k, v in logs.items()})
check("completions / passing TDs / INTs get a measured game-to-game scatter",
      all(m in spreads for m in ("Completions", "Passing TDs", "Interceptions")))
check("over/under chance exists for a completions line",
      0 < npo.p_over("Completions", proj["pass_cmp"], 21.5, spreads) < 1)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
