"""
NBA Game Simulator (10-20) — engines/nba_sim and the Simulator page's
wiring.

Plain script — exits non-zero on failure. Synthetic games and players
(rule 5: the shapes the nightly ships). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - simulate drawing every stat as plain Poisson (ignoring the model's
    size) -> "each player's chance matches the props model" fails
  - simulate with the score link removed (e pts 0)
    -> "teammates' points move together" fails
  - simulate without the blowout minutes share
    -> "starters sit in blowouts" fails
  - sgp_support treating every test as one that beats
    -> "an untested SGP is capped at THIN..." fails
  - sgp_support putting a beating test IN range (STRONG allowed)
    -> the same check fails
  - the book's total in a caption with <b> tags
    -> "no HTML inside a caption" fails
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nba_model as nm  # noqa: E402
from engines import nba_sim as ns  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


LINKS = {"e": {"pts": 0.97, "reb": -0.29, "ast": 1.11, "tpm": 1.04},
         "min_share": {"starter": [1.04, 0.97, 0.88], "bench": [1.05, 1.02, 1.02]}}
SIZES = {"pts": 6.0, "reb": 5.0, "ast": 4.0, "tpm": 3.0}
players = [
    {"pid": "a", "side": "home", "min": 35, "mu": {"pts": 26, "reb": 6, "ast": 7, "tpm": 3}},
    {"pid": "b", "side": "home", "min": 33, "mu": {"pts": 20, "reb": 9, "ast": 3, "tpm": 1.5}},
    {"pid": "c", "side": "away", "min": 34, "mu": {"pts": 24, "reb": 5, "ast": 5, "tpm": 2.5}},
    {"pid": "d", "side": "home", "min": 18, "mu": {"pts": 8, "reb": 3, "ast": 2, "tpm": 1}},
]
sim = ns.simulate(115, 111, 13.5, 19.0, players, SIZES, LINKS, n=40000, seed=3)

# each player on his own still prices like the props model
worst = 0.0
for p in players:
    for stat in ("pts", "reb", "ast"):
        mu = p["mu"][stat]
        for line in (mu - 3.5, mu - 0.5, mu + 2.5):
            if line < 0.5:
                continue
            line = np.floor(line) + 0.5
            want = nm.over(mu, SIZES[stat], line)
            got = float((sim["stats"][p["pid"]][stat] > line).mean())
            worst = max(worst, abs(got - want))
print(f"     worst marginal gap {worst:.4f}")
check("each player's chance matches the props model (within 1.5 pts)", worst < 0.015)

# teammates' points move together (score link), opponents' less so
mate = ns.joint(sim, [{"pid": "a", "stat": "pts", "line": 25.5, "side": "Over"},
                      {"pid": "b", "stat": "pts", "line": 19.5, "side": "Over"}])
print(f"     teammate lift {mate['lift']:.3f}")
check("teammates' points move together (lift > 1.02)", mate["lift"] > 1.02)
check("the joint is the share of games where every leg hit",
      abs(mate["all"] - mate["product"] * mate["lift"]) < 1e-9)
under = ns.joint(sim, [{"pid": "a", "stat": "pts", "line": 25.5, "side": "Over"},
                       {"pid": "b", "stat": "pts", "line": 19.5, "side": "Under"}])
check("over one teammate, under the other pull apart (lift < 1)", under["lift"] < 1.0)

# starters sit in blowouts: a starter's minutes-driven mean drops when |margin| >= 20
margin = sim["home"] - sim["away"]
blow = np.abs(margin) >= 20
close = np.abs(margin) < 10
a_reb = sim["stats"]["a"]["reb"]  # rebounds ride pace, so this isolates the minutes share
d_reb = sim["stats"]["d"]["reb"]
ra = a_reb[blow].mean() / a_reb[close].mean()
rd = d_reb[blow].mean() / d_reb[close].mean()
print(f"     blowout/close rebounds: starter {ra:.3f}, bench {rd:.3f}")
check("starters sit in blowouts (starter drops more than bench)", ra < 0.93 and ra < rd - 0.04)

# game legs and the score itself
check("the score is centred on the game model",
      abs(sim["home"].mean() - 115) < 0.5 and abs(sim["away"].mean() - 111) < 0.5)
tot = ns.joint(sim, [{"pid": "_game", "stat": "total", "line": 225.5, "side": "Over"}])
check("a game-total leg reads the simulated total",
      abs(tot["each"][0] - float(((sim["home"] + sim["away"]) > 225.5).mean())) < 1e-12)
check("a leg that never hits leaves no lift (no false price)",
      ns.joint(sim, [{"pid": "d", "stat": "pts", "line": 199.5, "side": "Over"}])["lift"] is None)
check("same seed, same games", np.array_equal(
    ns.simulate(115, 111, 13.5, 19.0, players[:1], SIZES, LINKS, n=500, seed=9)["stats"]["a"]["pts"],
    ns.simulate(115, 111, 13.5, 19.0, players[:1], SIZES, LINKS, n=500, seed=9)["stats"]["a"]["pts"]))

# the page's honesty and wiring
page = (ROOT / "app" / "views" / "NBA_Sim.py").read_text(encoding="utf-8")
from engines import bet_finder as bf  # noqa: E402
thin_t = {"n": 1065, "verdict": {"verdict": "thin", "z": 1.3}}
r_thin = bf.judge(0.36, 250, None, None, ns.sgp_support(thin_t))
r_beat = bf.judge(0.36, 250, None, None, ns.sgp_support({"n": 1065, "verdict": {"verdict": "beats"}}))
print(f"     36% at +250: thin test -> {r_thin['tier']}, beating test -> {r_beat['tier']}")
check("an untested SGP is capped at THIN; a tested one at VALUE, never STRONG",
      r_thin["tier"] == "thin" and r_beat["tier"] == "value"
      and ns.sgp_support(None)["untested"] and "ns.sgp_support(test)" in page)
check("the SGP joint is delivered leg chances x the simulator's lift",
      "prod * j[\"lift\"]" in page and "nv.chance(p[\"row\"], st_, ln, model, sd)" in page)
import re as _re  # noqa: E402
_caps = _re.findall(r"st\.caption\((.*?)\)\n", page, flags=_re.S)
check("no HTML inside a caption (st.caption prints tags as text — the <b>47%</b> bug)",
      _caps and not any("<b>" in c or "</" in c for c in _caps))
check("the scoreboard shows each team's score on its own, never one squeezed metric",
      "def _team(" in page and 'metric("Typical score"' not in page)
check("Out players are left out of the simulation", "av.is_out(r.get(\"status\"))" in page)
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("the Simulator is in the NBA nav", '("Simulator", "views/NBA_Sim.py")' in app)
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly ships the simulator's links and test",
      "nba_sim.build(prior, model)" in pc and '"sim": sim_block' in pc)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NBA simulator checks passed")
