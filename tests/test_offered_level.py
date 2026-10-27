"""
The offered projection's level, learned from the graded record (10-27) —
engines/offered_level, wired in nba_precompute / nhl_precompute.

The first graded night (10-26) read actual / ours: NBA rebounds x1.17,
assists x1.11, NHL assists x1.23. One night is not a verdict, so the level
is learned walk-forward and used only once it beats on MIN_TEST+ lines.

Plain script — exits non-zero on failure. Synthetic graded rows. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - the walk-forward factor reading the SAME night (x[0] <= d) -> "a night is
    scored with the factor from the nights before it" fails
  - the gate ignoring MIN_TEST -> "thin record: not used" fails
  - combos not re-summed -> "PRA follows its parts" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import offered_level as ol  # noqa: E402
from engines import nhl_model as hm  # noqa: E402
import nba_precompute as nbp  # noqa: E402
import nhl_precompute as nhp  # noqa: E402

fails = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def row(date, eid, pid, stat, ours, actual, letter="C"):
    return [date, eid, pid, stat, 5.5, 0.5, 0.5, 1, -110, -110, letter, ours, actual]


def record(nights, per_night, ratio, stat="reb", seed=3):
    rng = random.Random(seed)
    out = []
    for d in range(nights):
        for i in range(per_night):
            o = rng.uniform(3, 10)
            a = max(0.0, rng.gauss(o * ratio, 1.0))
            out.append(row(f"2026-11-{d + 1:02d}", f"e{d}", f"p{i}", stat, o, a))
    return out


# --- factor: shrunk toward 1, clipped -------------------------------------
few = [("d", 10.0, 12.0)] * 10
f_few = ol.factor(few)
check("10 lines move the factor only a little (shrunk toward 1)", 1.0 < f_few < 1.02)
many = [("d", 10.0, 12.0)] * 3000
check("3000 lines move it most of the way", 1.18 < ol.factor(many) <= ol.CLIP[1])
check("never past the clip", ol.factor([("d", 1.0, 9.0)] * 5000) == ol.CLIP[1])
check("no rows -> 1", ol.factor([]) == 1.0)

# --- rows: once per player-game, needs the projection and the box --------
g = [row("2026-11-01", "e", "p", "reb", 5, 6), row("2026-11-01", "e", "p", "reb", 5, 6),
     row("2026-11-01", "e", "q", "reb", None, 6), ["2026-11-01", "e", "z", "reb", 5.5]]
check("a player-game counts once; missing projection or old rows skipped",
      len(ol._rows(g, "reb")) == 1)
check("since drops nights before a model change",
      len(ol._rows(record(3, 5, 1.0), "reb", since="2026-11-02")) == 10)

# --- walk-forward: never the same night ------------------------------------
# night 1 dead on, night 2 runs 30% low. Scored only with night 1's level
# (x1.00) the test cannot beat; a factor that peeked at night 2 would.
wf = ([row("2026-11-01", "e0", f"p{i}", "reb", 4.0 + i % 7, 4.0 + i % 7) for i in range(200)]
      + [row("2026-11-02", "e1", f"p{i}", "reb", 4.0 + i % 7, 1.3 * (4.0 + i % 7))
         for i in range(300)])
fw = ol.fit(wf, ["reb"])["reb"]
check("a night is scored with the factor from the nights before it",
      fw["n_test"] == 300 and fw["test"].get("verdict") != "beats" and fw["used"] == 1.0)

# --- the gate --------------------------------------------------------------
thin = ol.fit(record(3, 40, 1.15), ["reb"])["reb"]
check("thin record: not used (n_test < MIN_TEST)",
      thin["n_test"] < ol.MIN_TEST and thin["used"] == 1.0)
big = ol.fit(record(8, 120, 1.15), ["reb"])["reb"]
check("a steady 15% shortfall on many nights beats and is used",
      big["test"].get("verdict") == "beats" and big["used"] > 1.05)
flat = ol.fit(record(8, 120, 1.00), ["reb"])["reb"]
check("no shortfall: not used", flat["used"] == 1.0)

# --- wiring: scales base stats, re-sums combos, refresh runs ---------------
rows = [{"pid": "1", "mu": {"pts": 20.0, "reb": 5.0, "ast": 4.0, "tpm": 2.0,
                            "pra": 29.0, "pr": 25.0, "pa": 24.0, "ra": 9.0}}]
seen = []
graded = record(8, 120, 1.15, stat="reb")
out = nbp.apply_offered_level([rows], "nba", ("pts", "reb", "ast", "tpm"),
                              {"pra": ("pts", "reb", "ast"), "pr": ("pts", "reb"),
                               "pa": ("pts", "ast"), "ra": ("reb", "ast")},
                              refresh=seen.append, graded=graded)
mu = rows[0]["mu"]
check("rebounds scaled by the used factor",
      abs(mu["reb"] - round(5.0 * out["reb"]["used"], 3)) < 1e-9 and mu["reb"] > 5.0)
check("points untouched (no record for it)", mu["pts"] == 20.0)
check("PRA follows its parts", abs(mu["pra"] - (mu["pts"] + mu["reb"] + mu["ast"])) < 1e-6
      and abs(mu["ra"] - (mu["reb"] + mu["ast"])) < 1e-6)
check("refresh called for each row", len(seen) == 1)
rows2 = [{"pid": "1", "mu": {"reb": 5.0}}]
nbp.apply_offered_level([rows2], "nba", ("reb",), refresh=seen.append,
                        graded=graded, since="2026-12-01")
check("since past the record: nothing moves", rows2[0]["mu"]["reb"] == 5.0)

# NHL: chances re-read from the scaled means, same as nhl_model.probs
r = hm.probs({"sog": 2.6, "g": 0.3, "a": 0.4, "gp": 40}, sog_disp=8.0)
sk = {"mu": dict(r["_mu"]), "probs": {k: r[k] for k, *_ in hm.MARKETS},
      "exp_sog": r["_exp_sog"], "exp_pts": r["_exp_pts"]}
before = dict(sk["probs"])
nhp.nhl_refresh(8.0)(sk)
check("NHL refresh at factor 1 reproduces the stored chances",
      all(abs(sk["probs"][k] - before[k]) < 1e-3 for k in before))
sk["mu"]["a"] *= 1.2
nhp.nhl_refresh(8.0)(sk)
check("NHL refresh: more assists -> higher assist and point chances",
      sk["probs"]["a1"] > before["a1"] and sk["probs"]["pt1"] > before["pt1"]
      and sk["probs"]["sog2"] == before["sog2"] and sk["exp_pts"] > r["_exp_pts"])

# --- the nightlies call it --------------------------------------------------
src_nba = (ROOT / "nba_precompute.py").read_text()
src_nhl = (ROOT / "nhl_precompute.py").read_text()
check("NBA nightly applies the level from 10-27 on",
      'model["offered_level"] = level_block' in src_nba and "since=LEVEL_SINCE" in src_nba
      and 'LEVEL_SINCE = "2026-10-27"' in src_nba)
check("NHL nightly applies the level to shots and assists, re-pricing",
      'model_block["offered_level"] = apply_offered_level(' in src_nhl
      and '("sog", "a"), refresh=nhl_refresh(' in src_nhl)
check("verify line names the test and whether it is used",
      "OFFERED LEVEL NBA: reb x" in ol.line("NBA", {"reb": big}) and "USED" in
      ol.line("NBA", {"reb": big}))

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
