"""
Parlay checker (10-18) — engines/parlay and the slip on the Bet Finder.

Plain script — exits non-zero on failure. Legs carry the shape every page
adds (player, game label as that page prints it, chance, American price,
support from model_view.support_for / curve_support, the single's tier)
— rule 5.

THE CASE: Izzy's 10-13 four-leg NHL anytime-goal ticket (+38,686).

Negative controls, confirmed red by exit code when written (rule 4):
  - judge() ignoring the profit boost
    -> "a 25% boost turns the same ticket into STRONG" fails
  - judge() without the same-game cap
    -> "two legs in one game cap the ticket at THIN, and say why" fails
  - judge() ignoring the book's typed parlay price
    -> "the book's own parlay price is used when typed" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import parlay as pl  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


OK = {"measured": True, "in_range": True, "n": 400, "untested": False}
legs = [
    {"player": "Charlie Coyle", "game": "FLA @ CBJ", "what": "Goal O0.5", "chance": 0.219,
     "price": 310, "support": OK, "single_tier": "none"},
    {"player": "Simon Holmstrom", "game": "VAN @ NYI  7:45 PM", "what": "Goal O0.5",
     "chance": 0.245, "price": 400, "support": OK, "single_tier": "value"},
    {"player": "Lawson Crouse", "game": "TOR vs UTA", "what": "Goal O0.5", "chance": 0.246,
     "price": 330, "support": OK, "single_tier": "thin"},
    {"player": "James Hagens", "game": "BOS @ SJ", "what": "Goal O0.5", "chance": 0.213,
     "price": 340, "support": OK, "single_tier": "none"}]

v = pl.judge(legs)
check("all four hit about 1 in 356", abs(v["chance"] - 0.219 * 0.245 * 0.246 * 0.213) < 1e-12
      and 340 < 1 / v["chance"] < 370)
check("the legs multiply to +38,686", abs(v["payout"] - 387.86) < 0.01 and v["american"] == 38686)
check("worth about +$9 per $100 -> THIN", 0.07 < v["ev"] < 0.11 and v["tier"] == "thin")
check("Holmstrom carries it, Coyle and Hagens drag it",
      v["legs"][0]["player"] == "Simon Holmstrom"
      and {x["player"] for x in v["drag"]} == {"Charlie Coyle", "James Hagens"})
vb = pl.judge(legs, boost=0.25)
check("a 25% boost turns the same ticket into STRONG", vb["tier"] == "strong" and vb["ev"] > 0.3)
vbook = pl.judge(legs, parlay_price=30000)
check("the book's own parlay price is used when typed",
      vbook["used_book_price"] and abs(vbook["payout"] - 301.0) < 1e-9 and vbook["ev"] < 0)
check("...and a short parlay price is a SKIP", vbook["tier"] == "none")

# --- the guard, leg by leg ------------------------------------------------
same = [dict(legs[1]), dict(legs[1], player="Bo Horvat", chance=0.30, price=260,
                             game="VAN @ NYI")]
vs = pl.judge(same, boost=0.5)
check("two legs in one game cap the ticket at THIN, and say why",
      vs["tier"] == "thin" and vs["linked"] == ["NYI/VAN"] and "same-game" in vs["reasons"][0])
vu = pl.judge([dict(legs[1]), dict(legs[2], support={"untested": True})], boost=0.5)
check("an untested leg (Live) caps it at THIN", vu["tier"] == "thin")
vr = pl.judge([dict(legs[1]), dict(legs[2], support=dict(OK, in_range=False))], boost=0.5)
check("a leg past its graded range caps it at VALUE", vr["tier"] == "value")
vc = pl.judge([dict(legs[1]), dict(legs[2], single_tier="check")], boost=0.5)
check("a leg the book disagrees with makes the ticket CHECK", vc["tier"] == "check")
check("one leg is not a parlay", pl.judge(legs[:1]) is None)
check("game labels from every page are one game",
      pl.game_id("CAR @ MTL  7:00 PM") == pl.game_id("MTL vs CAR") == "CAR/MTL")
st = pl.judge(legs, boost=0.25, staking=(1000.0, 0.25, 0.02))
check("a positive ticket gets a stake, capped like a single", st["stake"] and st["stake"] <= 20.0)

# --- wiring ---------------------------------------------------------------
for page in ("Bet_Finder.py", "Long_Shots.py", "Live.py"):
    check(f"{page} can put any typed leg on the slip",
          "mv.parlay_add_ui(" in (ROOT / "app" / "views" / page).read_text(encoding="utf-8"))
bf = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("the slip is judged on the Bet Finder", "pl.judge(legs, pprice" in bf)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall parlay checks passed")
