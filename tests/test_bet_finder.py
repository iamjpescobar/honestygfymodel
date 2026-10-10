"""
Bet Finder (10-09) — engines/bet_finder and views/Bet_Finder.py.

Plain script — exits non-zero on failure. Rows carry the shape every
board's prop rows have ({"_name", "_pmfs": {stat: pmf}}), calibration the
shape calibration_map returns, game projections the shape
market_blend.apply writes (p_*_final) — rule 5.

Negative controls, confirmed red by exit code when written (rule 4):
  - chance_at returning the model's raw chance instead of the delivered one
    -> "the Finder judges the DELIVERED chance, like every board" fails
  - judge calling a break-even price a BET
    -> "a price that only breaks even is SKIP" fails
  - results sorted weakest first
    -> "BETs come first, strongest edge first" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import bet_finder as bf  # noqa: E402
from engines import model_math as mm  # noqa: E402
from engines import model_view as mv  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- 1. prices ------------------------------------------------------------
check("an American price parses", bf.valid_price("+700") == 700 and bf.valid_price(-150) == -150)
check("a price a book cannot post is rejected",
      bf.valid_price(50) is None and bf.valid_price("abc") is None and bf.valid_price(None) is None)
check("break-even of +700 is 12.5%", abs(bf.break_even(700) - 0.125) < 1e-9)

# --- 2. the call ----------------------------------------------------------
j = bf.judge(0.15, 700, (500.0, 0.25, 0.02))
check("15% at +700 is a BET (needs 12.5%)", j["call"] == "BET" and abs(j["edge"] - 0.025) < 1e-9)
check("...tiered like every board (2-5 pts = VALUE)", j["tier"] == "value")
check("...with a stake at the reader's settings", j["stake"] and j["stake"] > 0)
check("15% at +500 is SKIP (needs 16.7%)", bf.judge(0.15, 500)["call"] == "SKIP")
fair = mm.fair_american(0.25)
check("a price that only breaks even is SKIP", bf.judge(0.25, fair)["call"] == "SKIP")
check("a big edge is STRONG", bf.judge(0.42, 200)["tier"] == "strong")
check("no price, no call", bf.judge(0.3, None) is None)

# --- 3. the chance is the boards' chance ---------------------------------
pmf = mm.poisson_pmf(0.4, 10)                  # P(1+) = 0.3297
markets = (("g1", "Goal O0.5", "g", 1),)
cal = {"g1": [{"band": "20-29%", "n": 500, "predicted": 0.25, "actual": 0.22},
              {"band": "30-39%", "n": 500, "predicted": 0.35, "actual": 0.30}]}
row = {"_name": "A (X)", "_pmfs": {"g": pmf}}
ch, raw, basis = bf.chance_at(row, "g", 0.5, "Over", markets, cal)
want, _b = mv.delivered_over(mm.over_prob_pmf(pmf, 0.5), "g", 0.5, markets, cal)
check("the Finder judges the DELIVERED chance, like every board",
      abs(ch - want) < 1e-12 and ch < raw and basis == "exact")
chu, rawu, _ = bf.chance_at(row, "g", 0.5, "Under", markets, cal)
check("the under is the other side of the same chance", abs(chu - (1 - ch)) < 1e-12)
check("no distribution for that stat -> nothing", bf.chance_at(row, "sog", 1.5, "Over", markets,
                                                              cal)[0] is None)

# --- 4. a list ------------------------------------------------------------
rows = [{"_name": n, "_pmfs": {"g": mm.poisson_pmf(mu, 10)}}
        for n, mu in (("Low", 0.1), ("Mid", 0.25), ("High", 0.5))]
items = bf.price_list(rows, "g", 0.5, "Over", (), {})
check("the price list is most likely first", [x["name"] for x in items] == ["High", "Mid", "Low"])
check("each row carries the price it is worth",
      all(x["worth"] == mm.fair_american(x["chance"]) for x in items))
res = bf.results(items, {"High": 300, "Mid": 300, "Low": 2000})   # 39% / 22% / 9.5%
check("only priced rows are judged", len(res) == 3 and bf.results(items, {}) == [])
check("BETs come first, strongest edge first",
      [r["name"] for r in res][:2] == ["High", "Low"] and res[-1]["call"] == "SKIP")

# --- 5. game lines --------------------------------------------------------
proj = {"p_home": 0.6, "p_home_mkt": 0.55, "p_home_final": 0.55,
        "p_over": 0.5, "market_total": 6.5, "p_over_mkt": None, "p_over_final": None}
odds = {"home_ml": -120, "away_ml": 100, "over_price": -110, "under_price": -110}
li = bf.game_line_items(proj, odds, "AWY", "HOM")
check("game lines are priced on the FINAL chance", any(
    x["name"] == "HOM moneyline" and abs(x["chance"] - 0.55) < 1e-12 for x in li))
check("a side with no market to anchor to is left out", not any("total" in x["name"] for x in li))
check("the posted price rides along", next(x for x in li if x["name"] == "HOM moneyline")[
    "posted"] == -120)

# --- 6. tonight's card ----------------------------------------------------
card = {"a": {"call": "SKIP", "tier": "none", "edge": -0.01},
        "b": {"call": "BET", "tier": "value", "edge": 0.03},
        "c": {"call": "BET", "tier": "strong", "edge": 0.07}}
check("the card holds BETs only, strongest first",
      [r["edge"] for r in bf.card_rows(card)] == [0.07, 0.03])
check("card keys separate line and side",
      bf.card_key("NHL", "G", "A", "Goals", 0.5, "Over")
      != bf.card_key("NHL", "G", "A", "Goals", 1.5, "Over"))

# --- 7. the page ----------------------------------------------------------
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("Bet Finder is in the MLB, NHL and NFL navs",
      app.count('("Bet Finder", "views/Bet_Finder.py")') == 3)
page = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("the page judges with the engine (one definition of a good bet)",
      "bf.chance_at(" in page and "bf.judge(" in page)
check("every sport is a source", all(f'"{s}": (_' in page for s in ("NHL", "MLB", "NFL")))
check("a failing feed costs that sport, never the page",
      "except Exception as exc:  # noqa: BLE001 — a missing feed" in page)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall Bet Finder checks passed")
