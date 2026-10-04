"""
Value, staking, the model-picks record and its grader, and NFL prop
over/under chances (engines/value, engines/model_picks,
model_picks_grade.py, engines/nfl_prop_odds, espn_feed.odds_of prices).

Plain script — exits non-zero on failure. Negative controls, confirmed
red by exit code when written (rule 4):
  - log_picks accepting a game that has already started -> section 3
  - spread grading with the line's sign flipped -> section 4
  - value_bets assuming -110 where no price was posted -> section 2
"""
import random
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from engines import value as vl            # noqa: E402
from engines import model_picks as mpk     # noqa: E402
from engines import nfl_prop_odds as npo   # noqa: E402
from engines.espn_feed import odds_of      # noqa: E402
import model_picks_grade as mpg            # noqa: E402

failures = []


def check(label, ok):
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        failures.append(label)


# ------------------------------------------------------------ 1. value
check("-110 breaks even at 52.38%", abs(vl.break_even(-110) - 0.52381) < 1e-4)
check("+150 breaks even at 40%", abs(vl.break_even(150) - 0.4) < 1e-9)
check("55% at -110 is value; 50% is not",
      vl.assess(0.55, -110)["value"] and not vl.assess(0.50, -110)["value"])
check("EV per $100: 55% at +100 is +$10", abs(vl.assess(0.55, 100)["ev_per_100"] - 10.0) < 1e-6)
check("full Kelly at 55% / even money is 10%", abs(vl.kelly_fraction(0.55, 100) - 0.10) < 1e-9)
check("quarter Kelly stake = 2.5% of a $1,000 bankroll", vl.stake(0.55, 100, 1000, 0.25, 0.05) == 25.0)
check("the cap binds: 70% at even money capped at 2%", vl.stake(0.70, 100, 1000, 0.25, 0.02) == 20.0)
check("no edge -> zero stake, not negative", vl.stake(0.40, 100, 1000) == 0.0)
check("an impossible price (+50) is refused", vl.assess(0.5, 50) is None)

# -------------------------------------------- 2. candidate / value bets
# Since 10-04 a bet is priced on the FINAL probability (engines/
# market_blend: market moved toward the model by its fitted weight).
proj = {"p_home": 0.66, "p_home_mkt": 0.55, "p_home_final": 0.60,
        "p_over": 0.45, "p_over_mkt": 0.50, "p_over_final": 0.47, "market_total": 8.5,
        "p_home_cover": 0.53, "p_cover_mkt": 0.50, "p_cover_final": 0.515,
        "market_spread_home": -3.5}
odds = {"home_ml": -130, "away_ml": 110, "over_price": -110}   # no under, no spread prices
cands = mpk.candidate_bets(proj, odds)
check("six candidate sides, each carrying model, market and final",
      len(cands) == 6 and all("p_model" in c and "p_market" in c for c in cands))
check("a candidate's p IS the final probability, not the model's",
      next(c for c in cands if c["market"] == "moneyline" and c["side"] == "home")["p"] == 0.60)
vb = mpk.value_bets(proj, odds)
check("home ML at -130 (break-even 56.5%) is value at a FINAL 60%",
      any(b["market"] == "moneyline" and b["side"] == "home" for b in vb))
check("over at a final 47% vs -110 is not value", not any(b["side"] == "over" for b in vb))
check("a side with NO posted price is never logged (under, spreads)",
      not any(b["side"] == "under" or b["market"] == "spread" for b in vb))
# The 10-03 failure: a model-only probability with no market to anchor
# it must never produce a pick, however far it is from the price.
bare = {"p_home": 0.80, "p_over": 0.75, "market_total": 46.5}
check("no market anchor -> no value bet, even at a model 80% vs +170",
      mpk.value_bets(bare, {"home_ml": 170, "away_ml": -200, "over_price": -110}) == [])
# A moneyline and a spread on the same team are one opinion.
both = {"p_home": 0.6, "p_home_mkt": 0.5, "p_home_final": 0.58,
        "p_home_cover": 0.6, "p_cover_mkt": 0.5, "p_cover_final": 0.58, "market_spread_home": -1.5}
bo = {"home_ml": 100, "away_ml": -120, "home_spread_price": 150, "away_spread_price": -180}
vb2 = mpk.value_bets(both, bo)
check("ML and spread on the same side: only ONE is a value bet (the higher EV)",
      len([b for b in vb2 if b["market"] in ("moneyline", "spread")]) == 1
      and vb2[0]["market"] == "spread")
check("...and all of them are reachable with one_per_group off",
      len(mpk.value_bets(both, bo, one_per_group=False)) == 2)

# ---------------------------------------------------------- 3. the log
def _real_digest():
    import hashlib
    p = ROOT / "data" / "model_picks" / "mlb.json"
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


_REAL_BEFORE = _real_digest()
root = Path(tempfile.mkdtemp())
now = datetime(2026, 10, 3, 18, 0, tzinfo=timezone.utc)
games = [
    {"id": 1, "date": "2026-10-03", "start": "2026-10-03T23:05:00Z", "home": "H", "away": "A",
     "proj": proj, "odds": odds},
    {"id": 2, "date": "2026-10-03", "start": "2026-10-03T17:00:00Z", "home": "H2", "away": "A2",
     "proj": proj, "odds": odds},                    # already started
]
n1 = mpk.log_picks("mlb", games, now=now, root=root)
check("one pick logged — the started game is not a pick", n1 == 1)
moved = dict(games[0], odds={"home_ml": -110, "away_ml": -110})
n2 = mpk.log_picks("mlb", [moved], now=now, root=root)
rec = mpk.load("mlb", root)
check("first writer wins: a later run with a moved line adds nothing",
      n2 == 0 and rec["picks"][0]["price"] == -130)
check("nothing written to the repo's real record (content hash unchanged)",
      _real_digest() == _REAL_BEFORE)

# ------------------------------------------------------------ 4. grading
ml = {"market": "moneyline", "side": "home", "line": None, "price": -130}
check("home ML wins 5-3", mpk.grade_pick(ml, 5, 3)[0] == "win")
check("...and pays 100/130 units", abs(mpk.grade_pick(ml, 5, 3)[1] - 100 / 130) < 1e-3)
tot = {"market": "total", "side": "under", "line": 8.0, "price": -110}
check("total 8 on a line of 8 is a push", mpk.grade_pick(tot, 5, 3)[0] == "push")
sp_home = {"market": "spread", "side": "home", "line": -3.5, "price": -110}
sp_away = {"market": "spread", "side": "away", "line": 3.5, "price": -110}
check("home -3.5 winning by 3 does NOT cover", mpk.grade_pick(sp_home, 24, 21)[0] == "loss")
check("away +3.5 losing by 3 DOES cover", mpk.grade_pick(sp_away, 24, 21)[0] == "win")
check("home -3 winning by 3 pushes",
      mpk.grade_pick(dict(sp_home, line=-3.0), 24, 21)[0] == "push")

# --------------------------------------------------------- 5. the grader
root2 = Path(tempfile.mkdtemp())
mpk.save("nhl", {"picks": [
    dict(ml, game_id="11", date="2026-10-01", home="H", away="A", result=None, p=0.6, edge=0.03),
    dict(ml, game_id="12", date="2026-09-28", home="H", away="A", result=None, p=0.6, edge=0.06),
    dict(ml, game_id="13", date="2026-10-02", home="H", away="A", result=None, p=0.6, edge=0.01),
]}, root2)


def finals(day):
    if day == "2026-10-02":
        raise RuntimeError("ESPN down")
    return {"11": (2, 4, True), "12": (None, None, False)}


g, v = mpg.grade("nhl", finals, today=date(2026, 10, 3), root=root2)
picks = {p["game_id"]: p for p in mpk.load("nhl", root2)["picks"]}
check("a final is graded with units", picks["11"]["result"] == "loss" and picks["11"]["units"] == -1.0)
check("not final 5 days on -> void, counted nowhere", picks["12"]["result"] == "void")
check("a fetch failure leaves the pick pending (retried tomorrow)", picks["13"]["result"] is None)
sm = mpk.summary(list(picks.values()))
check("summary counts graded W/L only, void excluded", sm["all"]["n"] == 1 and sm["pending"] == 1)

# -------------------------------------------------------- 6. odds prices
o = odds_of({"odds": [{"overUnder": 8.5, "overOdds": -115, "underOdds": -105,
                       "homeTeamOdds": {"moneyLine": -150, "spreadOdds": 130},
                       "awayTeamOdds": {"moneyLine": 130, "spreadOdds": -155}}]})
check("posted over/under and spread prices parsed",
      o.get("over_price") == -115 and o.get("under_price") == -105
      and o.get("home_spread_price") == 130)
check("no price published -> no price key (never a filled-in -110)",
      "over_price" not in odds_of({"odds": [{"overUnder": 8.5}]}))

# ------------------------------------------------ 7. NFL prop scatter
rng = random.Random(4)
logs = {}
for i in range(120):
    mean = rng.uniform(20, 90)
    logs[str(i)] = {"games": {str(k): {"rushing": {"yds": max(0.0, rng.gauss(mean, 0.5 * mean)),
                                                   "att": float(rng.randint(5, 20))}}
                              for k in range(4)}}
sp = npo.measure_spreads(logs)
check(f"rushing-yards scatter recovered near the fixture's 0.5 cv (got {sp['Rushing yards']['cv']})",
      0.35 < sp["Rushing yards"]["cv"] < 0.6)
check("over a line below the projection is > 50%",
      npo.p_over("Rushing yards", 60, 50.5, sp) > 0.5)
check("a higher line is always less likely to clear",
      npo.p_over("Rushing yards", 60, 70.5, sp) < npo.p_over("Rushing yards", 60, 50.5, sp))
check("an unmeasured market gives no chance, not a guess",
      npo.p_over("Receptions", 5, 4.5, {}) is None)

# ----------------------------------------- 8. colour and trust verdicts
from engines import model_math as mm2      # noqa: E402
from engines import model_view as mv       # noqa: E402

check("paired verdict: a clear improvement BEATS",
      mm2.paired_verdict([0.60] * 200, [0.70] * 100 + [0.66] * 100)["verdict"] == "beats")
noisy_m = [0.5 + (0.3 if i % 2 else -0.3) for i in range(60)]
noisy_b = [m + (0.01 if i % 3 == 0 else -0.004) for i, m in enumerate(noisy_m)]
check("paired verdict: better on average but inside noise is THIN",
      mm2.paired_verdict(noisy_m, noisy_b)["verdict"] == "thin")
check("paired verdict: worse FAILS", mm2.paired_verdict([0.7] * 50, [0.6] * 50)["verdict"] == "fails")
check("tiers use the Results buckets: 1 pt thin, 3 pts value, 6 pts strong",
      (mv.edge_tier(0.01, True), mv.edge_tier(0.03, True), mv.edge_tier(0.06, True))
      == ("thin", "value", "strong"))
check("no value -> no tier, whatever the edge number", mv.edge_tier(0.06, False) == "none")
check("1.997 pts (prints +2.0) is VALUE, matching how the log stores and buckets it",
      mv.edge_tier(0.01997, True) == "value"
      and mpk.summary([{"result": "win", "units": 1, "edge": round(0.01997, 4),
                        "market": "moneyline"}])["by_edge"][1]["n"] == 1)
check("bucket edges land in the higher tier (2.0 pts is VALUE, 5.0 is STRONG)",
      mv.edge_tier(0.02, True) == "value" and mv.edge_tier(0.05, True) == "strong")
# Game-market trust is AGAINST THE MARKET since 10-04: the blend block.
blend = {"moneyline": {"n": 400, "verdict": {"verdict": "beats"}},
         "total": {"n": 400, "verdict": {"verdict": "thin"}},
         "spread": {"n": 0}}
check("trust reads the blend verdict (total THIN, moneyline BEATS)",
      mv.market_trust(blend, "total") == "thin" and mv.market_trust(blend, "moneyline") == "beats")
check("a market with no line history is UNTESTED", mv.market_trust(blend, "spread") is None)
val = {"n": 100, "beats_coin": True, "beats_home_rate": True, "total_beats_league_avg": True,
       "total_verdict": {"verdict": "beats"}, "ml_verdict": {"verdict": "beats"}}
check("beating a coin flip is NOT beating the market: an old validation dict is UNTESTED",
      mv.market_trust(val, "moneyline") is None and mv.market_trust(val, "total") is None)
check("an untested model is UNTESTED, not a pass", mv.market_trust({}, "moneyline") is None)
check("market badges say MARKET", mv.trust_label("beats", market=True) == "BEATS MARKET"
      and mv.trust_label("fails", market=True) == "MARKET WINS")
sc, f = mv.scale_to_slate([20.0, 20.0, 20.0, 0.0], 1000, 0.03)
check("slate ceiling: three $20 stakes on $1,000 at 3% scale to $10 each",
      sc == [10.0, 10.0, 10.0, 0.0] and abs(f - 0.5) < 1e-9)
check("under the ceiling nothing moves", mv.scale_to_slate([5.0, 5.0], 1000, 0.10) == ([5.0, 5.0], 1.0))
check("THIN and STRONG are visibly different colours",
      mv.TIER_STYLE["thin"][1] != mv.TIER_STYLE["strong"][1]
      and mv.TIER_STYLE["thin"][2] != mv.TIER_STYLE["strong"][2])

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
