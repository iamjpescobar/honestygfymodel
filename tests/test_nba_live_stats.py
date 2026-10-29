"""
NBA Live for every stat (10-29) — nba_pbp quarter rebounds / assists /
threes with a box-score self-check, nba_quarters.live_check per stat.

Before: the play-by-play kept points per quarter only, so the Live page's
test covered points and every other NBA stat stayed THIN.

Plain script — exits non-zero on failure. Synthetic summaries. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - qstats_ok not checking against the box score -> "a stat whose counts do
    not match the box is left out" fails
  - assists credited to the shooter (participant 0) -> "assists go to the
    passer" fails
  - live_check ignoring qstats_ok -> "a game whose counts did not match is
    not used" fails
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import nba_box as nb  # noqa: E402
from engines import nba_model as nm  # noqa: E402
from engines import nba_pbp as pb  # noqa: E402
from engines import nba_quarters as nq  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def play(per, typ, text, who, score=None, team="1"):
    p = {"period": {"number": per}, "type": {"text": typ}, "text": text, "team": {"id": team},
         "participants": [{"athlete": {"id": w}} for w in who]}
    if score:
        p.update(scoringPlay=True, scoreValue=score)
    return p


summ = {"plays": [
    play(1, "Defensive Rebound", "A defensive rebound", ["10"]),
    play(1, "Jump Shot", "B makes 26-foot three point jumper (C assists)", ["11", "12"], 3),
    play(2, "Layup Shot", "C makes layup (B assists)", ["12", "11"], 2),
    play(2, "Free Throw", "B makes free throw 1 of 2", ["11"], 1),
    play(3, "Offensive Rebound", "A offensive rebound", ["10"]),
    play(5, "Jump Shot", "B makes three point jumper", ["11"], 3),        # overtime
]}
box_ok = {"10": {"reb": 2, "ast": 0, "tpm": 0, "team_id": "1"},
          "11": {"reb": 0, "ast": 1, "tpm": 2, "team_id": "1"},
          "12": {"reb": 0, "ast": 1, "tpm": 0, "team_id": "1"}}
orig = nb.parse
nb.parse = lambda s: box_ok
rec = pb.parse(summ)
check("rebounds by quarter", rec["qstats"]["10"]["reb"][:4] == [1, 0, 1, 0])
check("assists go to the passer", rec["qstats"]["12"]["ast"][0] == 1
      and rec["qstats"]["11"]["ast"][1] == 1 and "ast" not in rec["qstats"].get("10", {}))
check("made threes by quarter, overtime kept apart", rec["qstats"]["11"]["tpm"] == [1, 0, 0, 0, 1])
check("a free throw is not a three or an assisted shot",
      sum(rec["qstats"]["11"].get("tpm", [])) == 2)
check("counts that match the box score are vouched for",
      set(rec["qstats_ok"]) == {"reb", "ast", "tpm"})
nb.parse = lambda s: dict(box_ok, **{"10": dict(box_ok["10"], reb=5)})
rec2 = pb.parse(summ)
check("a stat whose counts do not match the box is left out",
      "reb" not in rec2["qstats_ok"] and "ast" in rec2["qstats_ok"])
nb.parse = orig

# --- the live test per stat ---------------------------------------------------
rng = random.Random(3)
rows, games = [], []
for i in range(700):
    d = f"2026-03-{1 + i % 28:02d}"
    team = str(i)
    hist = [[f"2026-01-{k + 1:02d}", team, "9", 30.0, 15, 6, 4, 2] for k in range(12)]
    reb = rng.randint(2, 11)
    g = [d, team, "9", 30.0, 15, reb, 4, 2]
    q = [reb // 4, reb // 4, reb // 4, reb - 3 * (reb // 4)]
    rows.append(("p" + team, g, {"mu": {"pts": 15.0, "reb": 6.0, "ast": 4.0, "tpm": 2.0}}, hist))
    ok = ["reb"] if i % 2 == 0 else []
    games.append({"date": d, "home": team, "away": "9", "lines": {team: [30, 30, 30, 30]},
                  "qpts": {}, "qstats": {"p" + team: {"reb": q + [0]}}, "qstats_ok": ok})
lc = nq.live_check(rows, games, {"reb": 12.0}, "2026-02-01") or {}
check("rebounds are tested at the quarter ends", "reb" in lc and lc["reb"]["n"] >= 300)
n_ok = sum(1 for gg in games if "reb" in gg["qstats_ok"])
check("a game whose counts did not match is not used",
      lc.get("reb", {}).get("n", 0) <= 3 * n_ok)
check("assists with no vouched-for counts: not tested", "ast" not in lc)

src = (ROOT / "nba_precompute.py").read_text()
check("the nightly prints every stat's live test and the play-by-play coverage",
      "for _st, L_ in lc.items():" in src and "stat counts that match the box score" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
