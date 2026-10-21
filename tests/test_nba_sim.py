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
  - sgp_support ignoring the number of legs
    -> "without a combos test ... 3+ legs stay THIN" fails
  - sgp_support ignoring a kind's verdict (any graded kind measured)
    -> "a kind that has not beaten -> THIN" fails
  - sgp_support putting a parlay with an under in range
    -> "an under in it" fails
  - quarter_links taking the half's share of the PREDICTED total
    -> "the half's share ... of the ACTUAL final" fails
  - joint_precise counting only the last chunk
    -> "every chunk counts" fails
  - joint_precise simulating every player
    -> "only the parlay's own players are simulated" fails
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

# the parlay at SGP_SIMS: chunked, only its own players, with its noise
pleg = [{"pid": "a", "stat": "pts", "line": 25.5, "side": "Over"},
        {"pid": "b", "stat": "pts", "line": 19.5, "side": "Over"},
        {"pid": "c", "stat": "pts", "line": 23.5, "side": "Under"}]
seen = []
_orig = ns.simulate


def _spy(*a, **k):
    seen.append(sorted(str(p["pid"]) for p in a[4]))
    return _orig(*a, **k)


ns.simulate = _spy
jp1 = ns.joint_precise(115, 111, 13.5, 19.0, players, SIZES, LINKS, pleg, n=300_000, chunk=70_000)
ns.simulate = _orig
gap = max(abs(jp1["each"][0] - nm.over(26, SIZES["pts"], 25.5)),
          abs(jp1["each"][1] - nm.over(20, SIZES["pts"], 19.5)),
          abs(jp1["each"][2] - (1 - nm.over(24, SIZES["pts"], 23.5))))
print(f"     300k games in 70k chunks: worst leg gap {gap:.4f}, lift {jp1['lift']:.3f} "
      f"+/- {jp1['lift_se']:.4f}")
check("every chunk counts: each leg matches the props model at 300k games (within 0.6 pts)",
      gap < 0.006 and len(seen) == 5)
check("only the parlay's own players are simulated (the bench never runs)",
      all(x == ["a", "b", "c"] for x in seen))
jp_small = ns.joint_precise(115, 111, 13.5, 19.0, players, SIZES, LINKS, pleg, n=20_000)
ratio = jp1["lift_se"] / jp_small["lift_se"]
check("the noise shrinks with the square root of the games (300k vs 20k: ~0.26x)",
      0.2 < ratio < 0.32)
check("the precise lift agrees with the 40k-game run within its noise",
      abs(jp1["lift"] - ns.joint(sim, pleg)["lift"]) < 4 * (jp1["lift_se"] + 0.01))

# halves and quarters (10-21)
import random as _r  # noqa: E402
_g = _r.Random(2)
pbp_games, gpr = [], {}
for k in range(400):
    d = f"2026-01-{1 + k % 28:02d}-{k}"
    mh, ma = 112 + _g.gauss(0, 4), 110 + _g.gauss(0, 4)
    gpr[(d, "H")] = (mh, ma)
    # this window's games score 6 more than the model predicted
    fh, fa = mh + 3 + _g.gauss(0, 10), ma + 3 + _g.gauss(0, 10)
    qh = [fh * 0.25, fh * 0.25, fh * 0.25, fh * 0.25]
    qa = [fa * 0.26, fa * 0.24, fa * 0.25, fa * 0.25]
    pbp_games.append({"date": d, "home": "H", "away": "A", "lines": {"H": qh, "A": qa}})
ql = ns.quarter_links(pbp_games, gpr, "0000", "9999")
print(f"     halves: {ql['h1']}, quarters: {ql['q1']}")
check("the half's share of the total is the share of the ACTUAL final (not of a biased "
      "prediction)", abs(ql["h1"]["r_t"] - 0.50) < 0.005 and abs(ql["q1"]["r_t"] - 0.255) < 0.005)
_rng = np.random.default_rng(4)
mdraw = _rng.normal(4.0, 14.0, 20000)
per = ns.periods(mdraw, 222.0, ql, _rng)
check("who leads after the half follows the game's own win chance (measured best)",
      abs(float(((per["h1"][0] - per["h1"][1]) > 0).mean()) - float((mdraw > 0).mean())) < 1e-12)
check("the half total sits at its share of the projected game total",
      abs(float(np.median(per["h1"][0] + per["h1"][1])) - 222.0 * ql["h1"]["r_t"]) < 0.5)
sq = ns.simulate(115, 111, 13.5, 19.0, players[:1], SIZES, dict(LINKS, quarters=ql), n=2000, seed=5)
check("the simulator carries halves and quarters when the links have them",
      set(sq.get("periods") or {}) == {"h1", "q1"})
check("the page shows halves and quarters, and the nightly prints their test",
      '"nbs_per"' in (ROOT / "app" / "views" / "NBA_Sim.py").read_text(encoding="utf-8")
      and "NBA halves / quarters" in (ROOT / "nba_precompute.py").read_text(encoding="utf-8"))

# the page's honesty and wiring
page = (ROOT / "app" / "views" / "NBA_Sim.py").read_text(encoding="utf-8")
from engines import bet_finder as bf  # noqa: E402
thin_t = {"n": 1065, "verdict": {"verdict": "thin", "z": 1.3}}
r_thin = bf.judge(0.36, 250, None, None, ns.sgp_support(thin_t))
r_beat = bf.judge(0.36, 250, None, None, ns.sgp_support({"n": 1065, "verdict": {"verdict": "beats"}}))
print(f"     36% at +250: thin test -> {r_thin['tier']}, beating test -> {r_beat['tier']}")
check("without a combos test: untested pairs THIN, a beating pairs test VALUE at most",
      r_thin["tier"] == "thin" and r_beat["tier"] == "value"
      and ns.sgp_support(None)["untested"])
check("the SGP joint is delivered leg chances x the simulator's lift",
      "prod * j[\"lift\"]" in page and "nv.chance(p[\"row\"], st_, ln, model, sd)" in page)
import re as _re  # noqa: E402
_caps = _re.findall(r"st\.caption\((.*?)\)\n", page, flags=_re.S)
check("no HTML inside a caption (st.caption prints tags as text — the <b>47%</b> bug)",
      _caps and not any("<b>" in c or "</" in c for c in _caps))
check("the scoreboard shows each team's score on its own, never one squeezed metric",
      "def _team(" in page and 'metric("Typical score"' not in page)
r_3 = bf.judge(0.36, 250, None, None, ns.sgp_support({"n": 1065, "verdict": {"verdict": "beats"}},
                                                    3))
check("without a combos test (an older nightly), 3+ legs stay THIN",
      r_3["tier"] == "thin" and ns.sgp_support(None, 8)["untested"] and "ns.SGP_MAX_LEGS" in page)
# graded by kind: 2 / 3 / 4 legs, all-points vs mixed (10-20)
P = lambda pid, st="pts", side="Over": {"pid": pid, "stat": st, "line": 9.5, "side": side}
check("a parlay's kind: legs x all-points-overs / mixed",
      ns.combo_kind([P("a"), P("b")]) == "2|pts" and ns.combo_kind([P("a"), P("b", "reb")])
      == "2|mixed" and ns.combo_kind([P("a"), P("b"), P("c", side="Under")]) == "3|mixed")
CB = {"2|pts": {"n": 1065, "verdict": {"verdict": "beats", "z": 2.4}},
      "3|pts": {"n": 709, "verdict": {"verdict": "thin", "z": 0.4}},
      "4|pts": {"n": 60, "verdict": {"verdict": "beats", "z": 2.1}}}
s2 = ns.sgp_support(None, [P("a"), P("b")], CB)
s2u = ns.sgp_support(None, [P("a"), P("b", side="Under")], CB)
s3 = ns.sgp_support(None, [P("a"), P("b"), P("c")], CB)
s4 = ns.sgp_support(None, [P("a"), P("b"), P("c"), P("d")], CB)
s5 = ns.sgp_support(None, [P(x) for x in "abcde"], CB)
t2 = bf.judge(0.36, 250, None, None, s2)["tier"]
t2u = bf.judge(0.36, 250, None, None, s2u)["tier"]
print(f"     36% at +250: 2 points overs (kind beats) {t2}; with an under {t2u}; "
      f"3 legs (kind thin) {bf.judge(0.36, 250, None, None, s3)['tier']}")
check("a kind that BEAT, every leg an over, 100+ graded: STRONG allowed",
      s2["in_range"] and not s2["untested"] and t2 == "strong")
check("an under in it: outside what was graded -> VALUE at most", t2u == "value"
      and ns.sgp_guard(s2u, "value") == ns.SGP_GUARD["unders"])
check("a kind that has not beaten -> THIN, and says so",
      s3["untested"] and ns.sgp_guard(s3, "thin") == ns.SGP_GUARD["not_beaten"])
check("a kind that beat on too few parlays -> VALUE at most",
      s4["measured"] and not s4["in_range"] and ns.sgp_guard(s4, "value") == ns.SGP_GUARD["small"])
check("a size never graded (5+ legs) -> THIN",
      s5["untested"] and ns.sgp_guard(s5, "thin") == ns.SGP_GUARD["untested"])

# the combos test on a synthetic game, every kind built
top = {"H": [("h%d" % i, "H", {"min": 34 - 3 * i, "mu": {"pts": 25 - 4 * i, "reb": 4 + (i == 2) * 6,
                                                       "ast": 3 + (i == 1) * 5, "tpm": 2}},
              {"pts": (20.5, 22), "reb": (5.5, 6), "ast": (4.5, 3)}) for i in range(5)],
       "A": [("a%d" % i, "A", {"min": 34 - 3 * i, "mu": {"pts": 24 - 4 * i, "reb": 4 + (i == 3) * 6,
                                                       "ast": 3 + (i == 1) * 5, "tpm": 2}},
              {"pts": (19.5, 18), "reb": (5.5, 9), "ast": (4.5, 7)}) for i in range(5)]}
kinds = sorted({k for k, _l in ns._combos(top, "H", "A")})
check("one game yields every kind of parlay people build",
      kinds == ["2|mixed", "2|pts", "3|mixed", "3|pts", "4|mixed", "4|pts"])
check("this season's finals join the test in last season's shape",
      ns.season_finals([{"date": "2026-10-21", "home_id": 5, "away_id": 7, "home_score": 110,
                         "away_score": 99}, {"date": "2026-10-22", "home_id": 1,
                                             "away_id": 2, "home_score": None}])
      == [{"date": "2026-10-21", "home": "5", "away": "7", "hs": 110, "as": 99}])
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly grades parlays on this season too (pool + this season's finals)",
      "nba_sim.build(prior, model, merge_pool(prior.get(\"players\"), cur)" in pc
      and "cur_finals)" in pc and "NBA SGP" in pc)
check("the page reads the kinds and shows what has been graded",
      'ns.sgp_support(test, legs, sim_meta.get("combos"))' in page and '"nbs_graded"' in page)

check("the SGP is priced on the precise run, and says when the link is just noise",
      "_legs_run(" in page and "ns.joint_precise(" in page and "no real link" in page
      and "ns.joint(sim, legs)" not in page)
check("the box score: every player's typical night and range, per team",
      '"nbs_box_' in page and "BOX = (" in page and "np.percentile(a_, 10)" in page)
check("simulated stats are stored small (int16) so cached games fit a 512 MB server",
      sim["stats"]["a"]["pts"].dtype == np.int16)
check("Out players are left out of the simulation", "av.is_out(r.get(\"status\"))" in page)
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("the Simulator is in the NBA nav", '("Simulator", "views/NBA_Sim.py")' in app)
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly ships the simulator's links and test",
      "nba_sim.build(prior, model" in pc and '"sim": sim_block' in pc)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NBA simulator checks passed")
