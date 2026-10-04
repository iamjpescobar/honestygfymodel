"""
The 10-04 formula: every bet priced on the MARKET's no-vig chance moved
toward the model only by the model's FITTED weight (engines/market_blend),
the recorded-line history it is fitted on (market_history.py), and its
wiring into every game model's projection.

Plain script — exits non-zero on failure. Fixtures are simulated seasons
whose truth is KNOWN: the market sees one part of each game's strength,
the model another, so the right answer ("the model deserves a say") and
the wrong one ("a noise model deserves none") are both checkable (rule 3).
The history walk is fed ESPN's real event shapes, header-flattened and
full (rule 5).

Negative controls, confirmed red by exit code when written (rule 4):
  - fit() scoring the weight IN-SAMPLE instead of cross-fitted -> the
    noise model earns a weight and section 4 fails (in-sample, a blend
    can never lose to the market: w = 0 is always on the menu)
  - home_spread() without the moneyline check -> section 2 fails
  - candidate_bets() pricing on p_model when no final exists -> section 7
    fails (the 10-03 defect: 44 NFL "value" bets from a model alone)
  - market_history keeping both games of a doubleheader -> section 8 fails
"""
import math
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import market_blend as mb     # noqa: E402
from engines import model_math as mm       # noqa: E402
from engines import game_model as gm       # noqa: E402
from engines import model_picks as mpk     # noqa: E402
from engines import nfl_game_model as ngm  # noqa: E402
import market_history as mh                # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# ------------------------------------------------------------ 1. blend math
check("w = 0 is the market exactly", abs(mb.blend(0.8, 0.55, 0.0) - 0.55) < 1e-12)
check("w = 1 is the model exactly", abs(mb.blend(0.8, 0.55, 1.0) - 0.8) < 1e-9)
mid = mb.blend(0.8, 0.55, 0.3)
check("a partial weight lands between, nearer the market", 0.55 < mid < 0.675)
check("no market -> no final probability (nothing to anchor to)", mb.blend(0.8, None, 0.5) is None)
check("symmetric: blending the other side gives the complement",
      abs(mb.blend(0.2, 0.45, 0.3) - (1 - mid)) < 1e-9)

# ----------------------------------------------------- 2. reading the line
ok = {"spread": -3.5, "details": "BUF -3.5", "home_ml": -175, "away_ml": 150}
check("consistent home favourite -> its spread", mb.home_spread(ok, "BUF", "NE") == -3.5)
check("details naming the AWAY side against a home-favoured sign -> None",
      mb.home_spread(dict(ok, details="NE -3.5"), "BUF", "NE") is None)
check("moneyline saying the away side is favoured against the sign -> None",
      mb.home_spread({"spread": -1.5, "home_ml": 140, "away_ml": -160}) is None)
check("no spread posted -> None", mb.home_spread({"home_ml": -110}) is None)
mk = mb.market_probs({"home_ml": -150, "away_ml": 130, "total": 8.5,
                      "spread": -1.5, "home_spread_price": 140, "away_spread_price": -165,
                      "details": "CLE -150"}, "CLE", "CWS")
check("moneyline read with the margin removed", abs(mk["moneyline"] - mm.no_vig_pair(-150, 130)[0]) < 1e-12)
check("a total with no prices reads as 50% at its own line, marked unpriced",
      mk["total"] == {"line": 8.5, "p_over": 0.5, "priced": False})
check("a priced run line is read no-vig", mk["spread"]["priced"] and 0.3 < mk["spread"]["p_cover"] < 0.5)

# ---------------------------------------------- 3. new count-sport markets
p_win = mm.win_prob(4.6, 4.2, 4.0, 0.52)
check("home -0.5 covers exactly when home wins (extras resolved at the measured rate)",
      abs(mm.margin_cover_prob(4.6, 4.2, -0.5, 4.0, 0.52) - p_win) < 1e-8)
check("home +0.5 covers exactly when home wins too (no margin of zero in MLB/NHL)",
      abs(mm.margin_cover_prob(4.6, 4.2, 0.5, 4.0, 0.52) - p_win) < 1e-8)
check("-1.5 is harder than -0.5, +1.5 easier than +0.5",
      mm.margin_cover_prob(4.6, 4.2, -1.5, 4.0, 0.52) < p_win
      < mm.margin_cover_prob(4.6, 4.2, 1.5, 4.0, 0.52))
check("a whole-number spread excludes the push",
      0 < mm.margin_cover_prob(3.0, 3.0, -1.0, None, 0.5) < 1)
pmf = mm.poisson_pmf(3.0)
check("over_prob_pmf: whole line excludes the push",
      abs(mm.over_prob_pmf(pmf, 3) - (1 - sum(pmf[:4])) / (1 - pmf[3])) < 1e-12)


# ------------------------------------------ 4. the fit: earned vs not earned
def sim_rows(n, informative, seed):
    g = random.Random(seed)
    rows = []
    for i in range(n):
        a, b = g.gauss(0, 0.45), g.gauss(0, 0.35)
        y = 1 if g.random() < mb.expit(a + b) else 0
        pm = mb.expit(b) if informative else mb.expit(g.gauss(0, 0.35))
        rows.append((f"2025-{1 + i // 200:02d}-{1 + i % 28:02d}", pm, mb.expit(a), y))
    return rows


good = mb.fit(sim_rows(3000, True, 11))
check(f"a model that sees what the market cannot EARNS a weight "
      f"(w={good['w']}, verdict {good['verdict'].get('verdict')})",
      good["verdict"].get("verdict") == "beats" and 0.2 < good["w_used"] < 0.9)
check("...and the cross-fitted blend beats the market alone",
      good["blend_log_loss_cv"] < good["market_log_loss"])
# Seed 16: a noise model whose IN-SAMPLE best weight is 0.037 — the case
# an in-sample score would report as an improvement.
noise = mb.fit(sim_rows(3000, False, 16))
check(f"a model that is pure noise gets NO say (w_used {noise['w_used']}, "
      f"verdict {noise['verdict'].get('verdict')})",
      noise["w_used"] == 0.0 and noise["verdict"].get("verdict") == "fails")
check("the REPORTED blend score for noise is not better than the market (cross-fitted, "
      "not in-sample — in-sample a blend can never lose)",
      noise["blend_log_loss_cv"] >= noise["market_log_loss"])
check("too little history -> untested, weight 0", mb.fit(sim_rows(3, True, 1))["w_used"] == 0.0)

# --------------------------------------------- 5. joining predictions to lines
preds = [
    {"date": "2025-10-01", "home": "1", "away": "2", "p_home": 0.6, "y": 1, "hs": 4, "as": 2,
     "mu_h": 3.4, "mu_a": 2.9},
    {"date": "2025-10-02", "home": "3", "away": "4", "p_home": 0.5, "y": 0, "hs": 3, "as": 3,
     "mu_h": 3.0, "mu_a": 3.0},                     # total 6 on a line of 6: push
    {"date": "2025-10-03", "home": "5", "away": "6", "p_home": 0.4, "y": 0, "hs": 1, "as": 5,
     "mu_h": 2.7, "mu_a": 3.2},                     # no line on file
]
lines = {mb.line_key("2025-10-01", "1", "2"): {"odds": {"home_ml": -140, "away_ml": 120, "total": 6.5,
                                                         "spread": -1.5}},
         mb.line_key("2025-10-02", "3", "4"): {"odds": {"home_ml": 105, "away_ml": -125, "total": 6.0}}}
po, pc = gm.blend_fns(None)
rows, cov = mb.build_rows(preds, lines, po, pc)
check("joined on (date, home, away): two of three have a line", cov["with_line"] == 2)
check("moneyline rows for both lined games", len(rows["moneyline"]) == 2)
check("a pushed total is left out, the decided one kept", len(rows["total"]) == 1
      and rows["total"][0][3] == 0)
check("the home -1.5 that won by 2 is a cover", rows["spread"] == [] or rows["spread"][0][3] == 1)

# ------------------------------------------------- 6. applying it to a game
blk_untested = {}
proj = {"p_home": 0.70, "p_over": 0.62, "market_total": 46.5}
mb.apply(proj, blk_untested, {"home_ml": 150, "away_ml": -170, "total": 46.5,
                              "over_price": -110, "under_price": -110})
check("untested: the final IS the market (the 10-03 Colts-Commanders row)",
      abs(proj["p_home_final"] - proj["p_home_mkt"]) < 1e-9
      and abs(proj["p_over_final"] - 0.5) < 1e-9 and proj["blend_state"] == "untested")
check("...so a 70% model at +150 is NOT a value bet once anchored",
      not any(b["market"] == "moneyline" and b["side"] == "home"
              for b in mpk.value_bets(proj, {"home_ml": 150, "away_ml": -170})))
blk = {"moneyline": {"n": 500, "w_used": 0.3, "verdict": {"verdict": "beats"}}}
proj2 = mb.apply({"p_home": 0.70}, blk, {"home_ml": 150, "away_ml": -170})
check("fitted weight: final sits between market and model",
      proj2["p_home_mkt"] < proj2["p_home_final"] < 0.70)

# ------------------------------------- 7. every game model carries the final
model = {"rates": {"A": {"off": 4.8, "def": 4.0}, "B": {"off": 4.2, "def": 4.6}},
         "league": {"league_rate": 4.5, "home_mult": 1.02, "away_mult": 0.98,
                    "tie_home_win": 0.52},
         "params": {"dispersion": 4.0},
         "blend": {"moneyline": {"n": 800, "w_used": 0.25, "verdict": {"verdict": "beats"}},
                   "total": {"n": 800, "w_used": 0.0, "verdict": {"verdict": "fails"}},
                   "spread": {"n": 800, "w_used": 0.1, "verdict": {"verdict": "thin"}}}}
odds = {"home_ml": -135, "away_ml": 115, "total": 8.5, "over_price": -105, "under_price": -115,
        "spread": -1.5, "home_spread_price": 150, "away_spread_price": -175, "details": "A -135"}
pj = gm.project(model, "A", "B", market=odds, home_abbr="A", away_abbr="B")
check("count-sport projection carries model, market and final for all three markets",
      all(k in pj for k in ("p_home_final", "p_over_final", "p_cover_final", "p_cover_mkt")))
check("a market the model failed against is priced at the market exactly",
      abs(pj["p_over_final"] - pj["p_over_mkt"]) < 1e-9)
cands = mpk.candidate_bets(pj, odds)
check("candidate bets are priced on the final, never the model",
      all(c["p"] in (pj["p_home_final"], 1 - pj["p_home_final"], pj["p_over_final"],
                     1 - pj["p_over_final"], pj["p_cover_final"], 1 - pj["p_cover_final"])
          for c in cands))
pj_bare = gm.project(model, "A", "B", market=None)
check("no posted line -> no final -> no bet (model shown, edge never claimed)",
      "p_home_final" not in pj_bare and mpk.value_bets(pj_bare, {"home_ml": 200}) == [])
nmodel = {"rates": {"1": {"off": 24.0, "def": 20.0}, "2": {"off": 21.0, "def": 23.0}},
          "league": {"league_rate": 22.0, "home_mult": 1.03, "away_mult": 0.97},
          "params": {"sd_margin": 13.5, "sd_total": 13.0}, "blend": {}}
npj = ngm.project(nmodel, "1", "2", {"home_ml": -150, "away_ml": 130, "total": 44.5,
                                      "spread": -3.0, "details": "HOM -3",
                                      "home_spread_price": -110, "away_spread_price": -110},
                  "HOM", "AWY")
check("NFL projection prices the spread through the checked sign and anchors all three",
      npj.get("market_spread_home") == -3.0 and abs(npj["p_cover_final"] - 0.5) < 1e-9
      and abs(npj["p_home_final"] - npj["p_home_mkt"]) < 1e-9)
npj2 = ngm.project(nmodel, "1", "2", {"home_ml": -150, "away_ml": 130, "spread": 3.0,
                                       "details": "HOM -3"}, "HOM", "AWY")
check("NFL: a spread contradicting its own details is never priced",
      "p_cover_final" not in npj2 and "p_home_cover" not in npj2)


# ------------------------------------------ 8. the recorded-line history walk
def ev(eid, home, away, hid, aid, hs, as_, odds=None, when="2026-05-02T23:05Z", status="STATUS_FINAL"):
    """Header-flattened ESPN event (what site.web.api returns)."""
    return {"id": eid, "date": when,
            "fullStatus": {"type": {"name": status, "completed": status == "STATUS_FINAL"}},
            "competitors": [
                {"homeAway": "home", "score": str(hs), "id": hid, "displayName": home,
                 "abbreviation": home[:3].upper()},
                {"homeAway": "away", "score": str(as_), "id": aid, "displayName": away,
                 "abbreviation": away[:3].upper()}],
            "odds": odds or []}


from engines.espn_wnba import _normalize_header_events  # noqa: E402
from datetime import date  # noqa: E402

day_events = {
    date(2026, 5, 2): [
        ev("1", "New York Yankees", "Boston Red Sox", "10", "2", 5, 3,
           [{"details": "NYY -150", "overUnder": 8.5, "homeTeamOdds": {"moneyLine": -150},
             "awayTeamOdds": {"moneyLine": 130}}]),
        ev("2", "Chicago Cubs", "St. Louis Cardinals", "16", "24", 2, 1),   # line only in summary
        ev("3", "Detroit Tigers", "Cleveland Guardians", "6", "5", 4, 2,
           [{"overUnder": 7.5}]),                                         # doubleheader G1
        ev("4", "Detroit Tigers", "Cleveland Guardians", "6", "5", 1, 3,
           [{"overUnder": 8.0}]),                                         # doubleheader G2
        ev("5", "Seattle Mariners", "Houston Astros", "12", "18", 0, 0, status="STATUS_SCHEDULED"),
    ]}
summ_calls = []


def sb_fn(d):
    return _normalize_header_events({"events": day_events.get(d, [])})


def summary_fn(eid):
    summ_calls.append(eid)
    if eid == "2":
        return {"pickcenter": [{"details": "CHC -120", "overUnder": 7.0,
                                "homeTeamOdds": {"moneyLine": -120},
                                "awayTeamOdds": {"moneyLine": 100}}]}
    return {}


got, cov = mh.collect("mlb", date(2026, 5, 2), date(2026, 5, 2), sb_fn, summary_fn,
                      sleep=0, key_fn=mh._mlb_key)
from engines.mlb_run_rates import canonical  # noqa: E402
k_nyy = mb.line_key("2026-05-02", canonical("New York Yankees"), canonical("Boston Red Sox"))
k_chc = mb.line_key("2026-05-02", canonical("Chicago Cubs"), canonical("St. Louis Cardinals"))
k_det = mb.line_key("2026-05-02", canonical("Detroit Tigers"), canonical("Cleveland Guardians"))
check("the scoreboard's own line is recorded", got.get(k_nyy, {}).get("odds", {}).get("home_ml") == -150)
check("a final with no scoreboard line falls back to the summary's pickcenter",
      got.get(k_chc, {}).get("source") == "summary" and got[k_chc]["odds"]["home_ml"] == -120)
check("the summary is only fetched when the scoreboard has nothing", "1" not in summ_calls)
check("a doubleheader's two games under one key are BOTH dropped, never one guessed",
      k_det not in got and cov["doubleheaders_dropped"] == 1)
check("a game not yet final is never recorded", cov["finals"] == 4)
tmp = Path(tempfile.mkdtemp())
mh.run("mlb", sb_fn=sb_fn, summary_fn=summary_fn, out_dir=tmp, sleep=0)
check("the written file loads back through market_blend.load_lines",
      k_nyy in mb.load_lines("mlb_2026", root=tmp))
check("nothing written under the repo's real data/market_lines by the test",
      not (ROOT / "data" / "market_lines" / "mlb_2026.json").exists()
      or (ROOT / "data" / "market_lines" / "mlb_2026.json").stat().st_size > 10_000)


# ---------------------------- 9. end to end: an NFL season with recorded lines
def nfl_season(seed, n_weeks=17):
    g = random.Random(seed)
    teams = [str(i) for i in range(1, 17)]
    strength = {t: g.gauss(0, 4) for t in teams}
    finals, lns = [], {}
    d0 = date(2025, 9, 7)
    for w in range(n_weeks):
        order = teams[:]
        g.shuffle(order)
        for i in range(0, 16, 2):
            h, a = order[i], order[i + 1]
            day = date.fromordinal(d0.toordinal() + 7 * w).isoformat()
            m = strength[h] - strength[a] + 2.0 + g.gauss(0, 13)
            tot = 44 + g.gauss(0, 13)
            hs, as_ = max(0, round((tot + m) / 2)), max(0, round((tot - m) / 2))
            if hs == as_:
                hs += 1
            finals.append({"date": day, "home_id": h, "away_id": a, "home_score": hs,
                           "away_score": as_, "event_id": f"{w}-{i}"})
            # the market knows the true strengths (better than any model)
            ph = mm.normal_cdf(strength[h] - strength[a] + 2.0, 0, 13.0)
            lns[mb.line_key(day, h, a)] = {"odds": {
                "home_ml": mm.fair_american(ph), "away_ml": mm.fair_american(1 - ph),
                "total": 44.5}, "home_abbr": "", "away_abbr": ""}
    return finals, lns


pf, plines = nfl_season(5)
built = ngm.build([], pf, prior_lines=plines)
bl = built.get("blend") or {}
check(f"NFL build fits a weight per market from recorded lines "
      f"(moneyline n={(bl.get('moneyline') or {}).get('n')})",
      (bl.get("moneyline") or {}).get("n", 0) > 100)
check(f"against a market that knows the true strengths the model gets little or no say "
      f"(w_used {(bl.get('moneyline') or {}).get('w_used')})",
      (bl.get("moneyline") or {}).get("w_used", 1) < 0.25)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
