"""
NFL 1st-quarter / 1st-half props and lines (10-22) — engines/nfl_quarters'
model half: only player-games whose quarters add up to his box score,
the measured spread of (his 1Q / 1H value / his game projection) in
three projection bands, the test against his own last-8 1Q / 1H rate,
what the Bet Finder may offer, the team lines, and the wiring (nfl_sim
.build, the nightly, the Simulator page, the Bet Finder).

Plain script — exits non-zero on failure. Rows in nfl_sim.collect's
shape ({"week", "event_id", "home_id", "away_id", "mu_h", "mu_a",
"players": [{"pid", "proj", "actual"}]}) and quarters in
data/nfl/prior_quarters.json's ({event_id: {"lines", "players": {pid:
{stat: [q1..q4, ot]}}}}) (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - clean_rows keeping player-games whose quarters miss the box
    -> "a player-game whose quarters miss his box score is left out" fails
  - fit reading every week (the test's weeks too)
    -> "the spread is fitted before the test weeks only" fails
  - pmf ignoring the projection band (always the middle one)
    -> "a small projection blanks the 1st quarter more often" fails
  - offered() passing a market that did not beat
    -> "only spans and stats that beat are offered" fails
  - team_lines without the tie band
    -> "a tied span is its own outcome" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import model_math as mm  # noqa: E402
from engines import nfl_quarters as nq  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


# --- a synthetic season: 1st-quarter receiving yards ------------------------------------
# A receiver projected mu catches nothing in the 1st quarter with chance
# exp(-mu / 25) (small roles blank more), else 1Q yards ~ his game yards x 0.3.
rng = random.Random(11)
MU = {f"p{i}": rng.uniform(12, 100) for i in range(160)}
rows, Q = [], {}
for w in range(2, 19):
    for gi in range(8):
        eid = f"e{w}-{gi}"
        players, qp = [], {}
        for i in range(20):
            pid = f"p{(gi * 20 + i) % 160}"
            mu = MU[pid]
            game = max(0, round(rng.gammavariate(4, mu / 4)))
            q1 = 0 if rng.random() < pow(2.718, -mu / 25) else min(game, round(game * rng.uniform(
                0.15, 0.55)))
            rest = game - q1
            q2 = rest // 3
            arr = [q1, q2, rest - q2, 0, 0]
            if (w * 7 + gi * 3 + i) % 23 == 0:       # the plays missed a catch: quarters short
                arr = [0, 0, 0, 0, 0] if game else [5, 0, 0, 0, 0]
            players.append({"pid": pid, "proj": {"rec_yds": mu}, "actual": {"rec_yds": game}})
            qp[pid] = {"rec_yds": arr}
        hs, as_ = rng.randrange(10, 35), rng.randrange(7, 31)
        h1 = [rng.randrange(0, 11), rng.randrange(0, 11)]
        a1 = [rng.randrange(0, 11), rng.randrange(0, 11)]
        rows.append({"week": w, "event_id": eid, "home_id": "1", "away_id": "2", "mu_h": 24.0,
                     "mu_a": 21.0, "players": players})
        Q[eid] = {"lines": {"1": h1 + [hs // 4, hs // 4], "2": a1 + [as_ // 4, as_ // 4]},
                  "players": qp}
clean = nq.clean_rows(rows, Q)
n_all = sum(len(g["players"]) for g in rows)
check("a player-game whose quarters miss his box score is left out (missing is not zero)",
      0 < n_all - len(clean) < n_all * 0.08
      and all(sum(r[4]) == next(p["actual"]["rec_yds"] for g in rows for p in g["players"]
                                if p["pid"] == r[1] and g["week"] == r[0]
                                and Q[g["event_id"]]["players"][p["pid"]]["rec_yds"] == r[4])
              for r in clean[:200]))
CUT = 10
M = nq.fit(clean, CUT)
m = M["q1"]["rec_yds"]
check("the spread is fitted before the test weeks only",
      m["n"] == sum(1 for r in clean if r[0] < CUT and r[2] == "rec_yds"))
lo, hi = nq.pmf(M, "q1", "rec_yds", 15.0), nq.pmf(M, "q1", "rec_yds", 95.0)
print(f"     P(0 yards in the 1st) at 15 projected {lo[0]:.2f}, at 95 {hi[0]:.2f} (world: "
      f"{pow(2.718, -15 / 25):.2f} / {pow(2.718, -95 / 25):.2f})")
check("a small projection blanks the 1st quarter more often (the bands are measured)",
      lo[0] > 0.3 and hi[0] < 0.1)
mean_hi = sum(k * x for k, x in enumerate(hi))
check("a pmf adds to 1 and its mean is his game projection x what the 1st quarter carries",
      abs(sum(hi) - 1) < 1e-6 and 15 < mean_hi < 40)
T = nq.test(clean, M, CUT)
x = T.get("q1_rec_yds") or {}
print(f"     test q1 rec yds n={x.get('n')} model {x.get('model_brier')} vs own last-8 "
      f"{x.get('baseline_brier')} -> {(x.get('verdict') or {}).get('verdict')}")
check("the test grades each span x stat against his own last-8 rate, with a curve",
      {"q1_rec_yds", "h1_rec_yds"} <= set(T) and x["n"] > 300 and x["calibration"]
      and (x.get("verdict") or {}).get("verdict") == "beats")
tb = {"q1_rec_yds": {"verdict": {"verdict": "beats"}}, "h1_pass_yds": {"verdict":
                                                                         {"verdict": "thin"}},
      "q1_rec": {"verdict": {"verdict": "fails"}}}
check("only spans and stats that beat are offered (Bet Finder)",
      nq.offered(tb) == ("q1_rec_yds",) and nq.offered(None) == ())

# --- the game ------------------------------------------------------------------------------
tf = nq.team_fit(rows, Q, CUT)
check("the team's share of points in the 1st half / quarter is measured from the lines",
      {"q1", "h1"} <= set(tf) and 0.1 < tf["h1"]["share"] < 0.9 and tf["h1"]["sd"] > 0)
tl = nq.team_lines(24.0, 21.0, {"h1": {"share": 0.5, "sd": 7.0}}, "h1")
check("a tied span is its own outcome; the three add to one; the better team leads more",
      0.03 < tl["tie"] < 0.12 and abs(tl["lead_home"] + tl["tie"] + tl["lead_away"] - 1) < 1e-9
      and tl["lead_home"] > tl["lead_away"] and abs(tl["mu_total"] - 22.5) < 1e-9)
tt = nq.team_test(rows, Q, tf, CUT)
check("the lead after the span is graded against the league's own rate",
      "h1_lead_home" in tt and tt["h1_lead_home"]["n"] > 50)
blk = nq.build(rows, Q, CUT)
check("build ships model, test, team lines and their test",
      {"model", "test", "team", "team_test", "cut_week", "clean_rows"} <= set(blk))
check("prob_at_least on the pmf is the over at a half line",
      abs(mm.prob_at_least(hi, 11) - (1 - sum(hi[:11]))) < 1e-9)

# --- wiring -----------------------------------------------------------------------------------
sim = (ROOT / "app" / "engines" / "nfl_sim.py").read_text(encoding="utf-8")
check("nfl_sim.build fits and tests the quarters on its own first / second half of weeks",
      "qblk = nq.build(old, quarters, cut)" in sim and '"quarters": qblk' in sim)
pc = (ROOT / "nfl_precompute.py").read_text(encoding="utf-8")
check("the nightly reads data/nfl/prior_quarters.json and prints the verdicts",
      '"prior_quarters.json"' in pc and "quarters=_quarters" in pc and "NFL 1Q / 1H:" in pc)
pg = (ROOT / "app" / "views" / "NFL_Sim.py").read_text(encoding="utf-8")
bfp = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("the Simulator shows the 1st quarter / 1st half; the Bet Finder offers only what beat",
      'with card("nfs_q")' in pg and "nq.team_lines(" in pg and "nq.offered(" in bfp
      and '"Players — 1st quarter / 1st half"' in bfp)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NFL 1st-quarter / 1st-half checks passed")
