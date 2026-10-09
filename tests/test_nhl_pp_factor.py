"""
NHL power-play weighted ice time (10-09): last season's PP minutes
(nhl_prior_season.py --pp-only -> data/nhl/prior_pp.json), and the
PP-weighted version of the ice-time factor, fitted and TESTED against the
plain one (engines/nhl_model.fit_pp) — in the chance only on "beats".

Plain script — exits non-zero on failure. Game rows are the six-field
tuples every reader unpacks (date, opp, SOG, G, A, TOI); PP minutes ride
beside them as {date: minutes} — rule 5. Temp directories only.

Negative controls, confirmed red by exit code when written (rule 4):
  - _family_losses ignoring the PP weight (always the plain ratio)
    -> "a world where PP minutes drive scoring: the PP factor is adopted" fails
  - toi_scales using the PP ratio whether or not it was adopted
    -> "not adopted: the plain ice-time ratio stands" fails
  - weighted_ratio weighting PP minutes by w instead of (w - 1) on top of TOI
    -> "w = 1 is exactly today's ice-time ratio" fails
"""
import json
import math
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

import nhl_precompute as npc  # noqa: E402
import nhl_prior_season as nps  # noqa: E402
from engines import nhl_model as nm  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- 1. the weighted ratio ---------------------------------------------
games = [(f"2025-10-{d:02d}", "T", 2, 0, 0, toi) for d, toi in
         ((1, 16.0), (2, 17.0), (3, 18.0), (4, 20.0), (5, 21.0), (6, 22.0))]
pp = {"2025-10-01": 0.5, "2025-10-02": 0.5, "2025-10-03": 0.5,
      "2025-10-04": 3.0, "2025-10-05": 3.5, "2025-10-06": 4.0}
st = nm.pp_window_stats(games, 3, pp)
check("stats over games carrying both minutes", st == (114.0, 12.0, 6, 63.0, 10.5, 3))
plain = nm.toi_ratio(games, 3)[2]
check("w = 1 is exactly today's ice-time ratio", abs(nm.weighted_ratio(st, 1.0) - plain) < 1e-12)
check("weighting PP minutes up makes a PP1 promotion count for more",
      nm.weighted_ratio(st, 4.0) > plain)
check("no PP minutes -> no PP ratio (unknown, not zero)",
      nm.pp_window_stats(games, 3, {}) is None and nm.weighted_ratio(None, 3.0) is None)

# --- 2. toi_scales only uses it when adopted ---------------------------
base_toi = {"sog": {"window": 3, "alpha": 0.5}, "pts": {"window": 3, "alpha": 0.7}}
off = dict(base_toi, pts=dict(base_toi["pts"], pp={"adopted": False, "weight": 4.0,
                                                    "alpha": 0.6}))
on = dict(base_toi, pts=dict(base_toi["pts"], pp={"adopted": True, "weight": 4.0,
                                                   "alpha": 0.6}))
s_off = nm.toi_scales(games, off, pp)
s_on = nm.toi_scales(games, on, pp)
check("not adopted: the plain ice-time ratio stands",
      abs(s_off["pts"] - plain ** 0.7) < 1e-12 and "pp_used" not in s_off)
check("adopted: the PP-weighted ratio is used for that family",
      abs(s_on["pts"] - nm.weighted_ratio(st, 4.0) ** 0.6) < 1e-12 and s_on["pp_used"] == ["pts"])
check("...and only that family", abs(s_on["sog"] - plain ** 0.5) < 1e-12)
check("adopted but no PP minutes for him: the plain ratio",
      abs(nm.toi_scales(games, on, {})["pts"] - plain ** 0.7) < 1e-12)
check("PP minutes recent vs norm are reported for the page",
      s_off.get("pp_recent") == 3.5 and s_off.get("pp_base") == 2.0)


# --- 3. the fit, on a simulated season ---------------------------------
def world(pp_mult, seed=3, n_sk=70, n_days=160, with_pp=True):
    g = random.Random(seed)
    days = [(date(2025, 10, 1) + timedelta(days=i)).isoformat() for i in range(n_days)]

    def pois(lam):
        lim, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= g.random()
            if p < lim:
                return k
            k += 1
    sk = {}
    for k in range(n_sk):
        es_pts, es_sog = g.uniform(0.015, 0.05), g.uniform(0.08, 0.2)
        roles = [0.2, 0.5, 1.5, 3.0]
        before, after, switch = g.choice(roles), g.choice(roles), g.randrange(20, n_days)
        rows, ppm_by = [], {}
        for i, d in enumerate(days):
            if g.random() < 0.5:
                continue
            ppm = max(0.0, g.gauss(before if i < switch else after, 0.5))
            es = max(5.0, g.gauss(16, 1.5))
            pts = pois(es_pts * (es + pp_mult * ppm))
            gl = sum(1 for _ in range(pts) if g.random() < 0.4)
            rows.append((d, "T", pois(es_sog * (es + min(pp_mult, 2.0) * ppm)), gl, pts - gl,
                         round(es + ppm, 2)))
            ppm_by[d] = round(ppm, 2)
        sk[str(k)] = {"name": f"S{k}", "pos": "C", "games": rows}
        if with_pp:
            sk[str(k)]["pp"] = ppm_by
    return sk


res = nm.fit_toi(world(4.0), [], [], days=60)
x = res["sog"]["pp"]
check("a world where PP minutes drive scoring: the PP factor is adopted",
      x.get("adopted") is True and x["weight"] > 1 and x["verdict"]["z"] >= 2)
check("the test is against the plain ice-time factor, on games the fit never saw",
      x["n"] > 0 and x["log_loss_with"] < x["log_loss_without"])
res0 = nm.fit_toi(world(4.0, with_pp=False), [], [], days=60)
check("no PP minutes loaded: not adopted, and it says why",
      res0["sog"]["pp"]["adopted"] is False and "too few" in res0["sog"]["pp"]["note"])
check("...and the plain ice-time fit is exactly what it was",
      res0["sog"]["fitted_alpha"] == res["sog"]["fitted_alpha"]
      and res0["pts"]["fitted_alpha"] == res["pts"]["fitted_alpha"])

# --- 4. the plumbing ----------------------------------------------------
prior_sk = {"7": {"name": "A", "pos": "C", "team": "1",
                  "games": [["2025-10-07", "2", 3, 1, 0, 18.0]], "pp": {"2025-10-07": 2.5}}}
cur = {"7": {"name": "A", "pos": "C", "games": {"e1": {"date": "2026-10-08", "opp": "X",
                                                        "sog": 2, "g": 0, "a": 1, "toi": 19.0,
                                                        "pptoi": 3.25}}}}
pool = nm.pool_skaters(prior_sk, cur, {"X": "2"})
check("the pool carries PP minutes from both seasons",
      pool["7"]["pp"] == {"2025-10-07": 2.5, "2026-10-08": 3.25})
check("game rows stay six fields", all(len(r) == 6 for r in pool["7"]["games"]))

with tempfile.TemporaryDirectory() as td:
    prior_path = Path(td) / "prior_season.json"
    (Path(td) / npc.PRIOR_PP_NAME).write_text(json.dumps({"7": {"2025-10-07": 2.5}}))
    prior = {"skaters": {"7": {"games": []}, "8": {"games": []}}}
    n = npc.load_prior_pp(prior, prior_path)
    check("last season's PP minutes are laid over its skaters",
          n == 1 and prior["skaters"]["7"]["pp"] == {"2025-10-07": 2.5}
          and "pp" not in prior["skaters"]["8"])
    check("no PP file: nothing laid over, nothing breaks",
          npc.load_prior_pp({"skaters": {"7": {}}}, Path(td) / "elsewhere" / "p.json") == 0)
    out = Path(td) / "pp.json"
    check("an empty PP file is refused", nps.write_pp({"7": {"games": [[1]]}}, out) is False
          and not out.exists())
    check("the PP file is {pid: {date: minutes}}",
          nps.write_pp({"7": {"games": [[1]], "pp": {"2025-10-07": 2.5}}}, out)
          and json.loads(out.read_text()) == {"7": {"2025-10-07": 2.5}})

src = (ROOT / "nhl_prior_season.py").read_text(encoding="utf-8")
check("a full rebuild keeps prior_season.json's rows unchanged (pp stripped)",
      'k != "pp"' in src)
wf = (ROOT / ".github" / "workflows" / "nhl-prior-pp.yml").read_text(encoding="utf-8")
check("the one-time workflow runs --pp-only and commits only prior_pp.json",
      "nhl_prior_season.py --pp-only" in wf and "git add data/nhl/prior_pp.json" in wf
      and "prior_season.json" not in wf.split("Commit the PP minutes file")[1])

# --- 5. what the pages say ---------------------------------------------
check("adopted: the pages say PP time is IN the chance",
      "IS in the chance for points" in nm.pp_note(dict(on, pts=dict(
          on["pts"], pp=dict(on["pts"]["pp"], verdict={"z": 3.1}))))
      and "4x" in nm.pp_note(dict(on, pts=dict(on["pts"], pp=dict(on["pts"]["pp"],
                                                                   verdict={"z": 3.1})))))
check("tested and not adopted: context only, and why",
      "did not beat" in nm.pp_note(dict(off, pts=dict(off["pts"], pp=dict(
          off["pts"]["pp"], verdict={"verdict": "fails"})))))
check("untested: context only until the file is loaded", "until" in nm.pp_note(base_toi))

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall PP factor checks passed")
