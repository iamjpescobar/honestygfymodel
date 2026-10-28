"""
MLB batter letters by the hitter's hand (10-28) — engines/defense_matchup
fit_platoon / add_platoon / mlb_starter_card(bats=...).

Izzy: "players with the same exact grades ... graded individually on what
the team allows to that specific position". In MLB a batter's "position"
against a starter is his hand. Before this, every hitter facing the same
starter got the same letter on every stat.

Plain script — exits non-zero on failure. Synthetic plate appearances.
No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - ranking by side (same / opp) across both arms instead of by the batter's
    hand -> "a lefty's letter ranks tonight's starter among every starter
    against lefties" fails
  - a switch hitter treated as same-side -> "switch hitters bat from the
    opposite side" fails
  - the gate ignoring the test (any candidate adopted) -> "no real split:
    stays on the overall rate" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import defense_matchup as dm  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


check("same hand = same side; opposite = opp", dm.platoon_side("L", "L") == "same"
      and dm.platoon_side("R", "L") == "opp" and dm.platoon_side("R", "R") == "same")
check("switch hitters bat from the opposite side",
      dm.platoon_side("S", "R") == "opp" and dm.platoon_side("S", "L") == "opp")
check("unknown hand: no side", dm.platoon_side(None, "R") is None
      and dm.platoon_side("L", None) is None)

PRI = {"1B": [0.14, 300], "2B": [0.045, 300], "3B": [0.004, 300], "HR": [0.03, 300],
       "BB": [0.08, 300], "K": [0.22, 300], "OUT": [0.48, 300]}


def season(k_split, n_p=60, days=150, pa_day=6, seed=1):
    """rows [(date, pid, side, outcome)]: each pitcher a K rate, plus +k_split
    against same-side hitters for half of them and -k_split for the rest."""
    rng = random.Random(seed)
    rows = []
    kr = {f"p{i}": rng.uniform(0.17, 0.29) for i in range(n_p)}
    sign = {f"p{i}": (1 if i % 2 else -1) for i in range(n_p)}
    for d in range(days):
        date = f"2026-{4 + d // 30:02d}-{1 + d % 30:02d}"
        for p in kr:
            for _ in range(pa_day):
                side = "same" if rng.random() < 0.45 else "opp"
                k = kr[p] + (sign[p] * k_split if side == "same" else -sign[p] * k_split)
                o = "K" if rng.random() < k else ("1B" if rng.random() < 0.2 else "OUT")
                rows.append((date, p, side, o))
    return rows


real = season(0.09)
fit = dm.fit_platoon(real, [r[0] for r in real], PRI, stats=("k",))
check("a real split in strikeouts beats the overall rate and is adopted (own)",
      fit["k"]["mode"] == "own" and fit["k"]["verdict"]["verdict"] == "beats")
none = season(0.0, seed=2)
fit0 = dm.fit_platoon(none, [r[0] for r in none], PRI, stats=("k",))
check("no real split: stays on the overall rate", fit0["k"]["mode"] == "overall")
check("too few dates: a note", "note" in dm.fit_platoon(real[:50], [r[0] for r in real[:50]],
                                                         PRI))

# --- ranking by the batter's hand --------------------------------------------
# RHP "r1" is brutal on righties (same side), soft on lefties; LHP "l1" is
# brutal on lefties (same side). Among starters vs LEFTIES, r1 must rank
# softer than l1 even though r1's SAME-side rate is the lowest.
rows = []
for i in range(400):
    rows.append(("2026-05-01", "r1", "same", "K" if i % 10 < 4 else "OUT"))   # .40 vs RHB
    rows.append(("2026-05-01", "r1", "opp", "K" if i % 10 < 1 else "OUT"))    # .10 vs LHB
    rows.append(("2026-05-01", "l1", "same", "K" if i % 10 < 4 else "OUT"))   # .40 vs LHB
    rows.append(("2026-05-01", "l1", "opp", "K" if i % 10 < 2 else "OUT"))    # .20 vs RHB
    rows.append(("2026-05-01", "r2", "same", "K" if i % 10 < 2 else "OUT"))
    rows.append(("2026-05-01", "r2", "opp", "K" if i % 10 < 2 else "OUT"))
tab = {"of": 3, "league": {"k": 0.22}, "pitchers": {
    p: {"pa_cur": 800, "pa_prior": 0, "k": {"blend": 0.22, "rank": 1}} for p in ("r1", "l1", "r2")}}
dm.add_platoon(tab, rows, PRI, {"k": {"mode": "own", "s": 100}},
               {"r1": "R", "l1": "L", "r2": "R"})
cL = {p: dm.mlb_starter_card(tab, p, "k", "L") for p in ("r1", "l1", "r2")}
cR = {p: dm.mlb_starter_card(tab, p, "k", "R") for p in ("r1", "l1", "r2")}
check("a lefty's letter ranks tonight's starter among every starter against lefties",
      cL["l1"]["rank"] == 1 and cL["r1"]["rank"] == 3 and cL["r1"]["side"] == "opp"
      and cL["l1"]["side"] == "same" and cL["l1"]["per_game"] > cL["r2"]["per_game"] + 0.05)
check("a righty's: r1 (brutal on righties) ranks first in strikeouts allowed",
      cR["r1"]["rank"] == 1 and cR["r1"]["side"] == "same")
check("the same starter gives a lefty and a righty different letters",
      cL["r1"]["grade"] != cR["r1"]["grade"])
check("the card says whose hand it is about",
      cL["r1"]["group"] == "left-handed batters" and cL["r1"]["basis"] == "platoon"
      and "this side of the plate" in dm.notice(cL["r1"], "strikeouts", cL["r1"]["group"],
                                                "Tonight's starter"))
check("no hand known: the overall card, as before",
      dm.mlb_starter_card(tab, "r1", "k")["basis"] != "platoon")
tab2 = {"of": 3, "league": {"h": 0.22}, "pitchers": {
    "r1": {"pa_cur": 800, "pa_prior": 0, "throws": "R", "h": {"blend": 0.22, "rank": 1}}}}
dm.add_platoon(tab2, rows, PRI, {"h": {"mode": "overall", "s": None}}, {"r1": "R"})
check("a stat whose split did not beat keeps the overall card for every hand",
      dm.mlb_starter_card(tab2, "r1", "h", "L")["basis"] != "platoon")

# --- wiring ---------------------------------------------------------------------
mv = (ROOT / "app" / "engines" / "model_view.py").read_text()
tp = (ROOT / "top_plays_log.py").read_text()
mpp = (ROOT / "mlb_prop_precompute.py").read_text()
check("the lineup board passes each batter's hand",
      'mlb_starter_card(table, opp_pitcher_id, stat, bats)' in mv
      and '.get("batter_hand")' in mv and 'b.get("id"))' in mv)
check("top plays pass it too", '(pm.get("batter_hand") or {}).get(' in tp)
check("the nightly fits the split and ships the hands",
      "dm.fit_platoon(rows" in mpp and 'out["batter_hand"] = bats' in mpp
      and '"stand", "p_throws"' in mpp)
import pandas as pd  # noqa: E402
import mlb_prop_precompute as m  # noqa: E402
pa = pd.DataFrame({"game_date": ["d1"] * 12, "pitcher": [7] * 12,
                   "batter": [1] * 10 + [2, 2], "stand": ["L"] * 5 + ["R"] * 5 + ["R", "R"],
                   "p_throws": ["R"] * 12, "outcome": ["K"] * 12})
_r, th, bats = m.platoon_inputs(pa)
check("a hitter seen from both sides is a switch hitter; throws read per pitcher",
      bats == {"1": "S", "2": "R"} and th == {"7": "R"} and _r[0][2] == "opp")

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
