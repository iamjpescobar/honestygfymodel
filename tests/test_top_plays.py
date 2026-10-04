"""
Top Plays (engines/top_plays_board, top_plays_log.py, views/Top_Plays.py):
only proven markets, probabilities shown at what that kind of call has
DELIVERED, every play logged before it starts and graded after.

Negative controls, confirmed red by exit code when written (rule 4):
  - calibrate() returning the raw model probability -> "an overconfident
    model is shown at what it delivered" fails
  - select() without the verdict gate -> "a market that did not beat its
    baseline never reaches Top Plays" fails
  - parse_box keeping every pitcher's line, not only the starter's ->
    "a reliever's line is never graded as a starter play" fails
"""
import random
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import top_plays_board as tpb  # noqa: E402
from engines import mlb_props as mp         # noqa: E402
import top_plays_log as tpl                 # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --------------------------------------------------------- 1. calibration
over = [{"band": "60-69%", "n": 400, "predicted": 0.65, "actual": 0.60},
        {"band": "70-79%", "n": 300, "predicted": 0.75, "actual": 0.66},
        {"band": "80-89%", "n": 200, "predicted": 0.84, "actual": 0.74}]
check("an overconfident model is shown at what it delivered (84% said -> 74% done)",
      abs(tpb.calibrate(0.84, over) - 0.74) < 1e-9)
check("between bins: linear between what neighbouring calls delivered",
      abs(tpb.calibrate(0.795, over) - 0.70) < 1e-9)
check("past the last bin: flat, never extrapolated upward", tpb.calibrate(0.97, over) == 0.74)
bumpy = [{"band": "60-69%", "n": 100, "predicted": 0.65, "actual": 0.70},
         {"band": "70-79%", "n": 100, "predicted": 0.75, "actual": 0.62}]
check("a non-monotone record is pooled (PAV): a higher call never shows lower",
      tpb.calibrate(0.65, bumpy) == tpb.calibrate(0.75, bumpy) == 0.66)
check("no calibration record -> no calibrated number", tpb.calibrate(0.8, []) is None)
check("the record a call falls in", tpb.record_at(0.84, over) == ("80-89%", 200, 0.74))

# ------------------------------------------------------------ 2. selecting
val = {"h1": {"verdict": {"verdict": "beats"}, "calibration": over},
       "tb1": {"verdict": {"verdict": "beats"}, "calibration": over},
       "k1": {"verdict": {"verdict": "fails"}, "calibration": over},
       "h2": {"verdict": {"verdict": "beats"}, "calibration": over}}
base = {"sport": "mlb", "game_id": 1, "game": "A @ B", "start": "2026-10-05T23:05:00Z",
        "date": "2026-10-05", "team": "B"}
cands = [dict(base, player_id=7, player="Seven", market="h1", label="Hits O0.5", stat="h", at_least=1, p=0.84),
         dict(base, player_id=7, player="Seven", market="tb1", label="TB O0.5", stat="tb", at_least=1, p=0.84),
         dict(base, player_id=7, player="Seven", market="h2", label="Hits O1.5", stat="h", at_least=2, p=0.40),
         dict(base, player_id=8, player="Eight", market="k1", label="K O0.5", stat="k", at_least=1, p=0.90),
         dict(base, player_id=9, player="Nine", market="h1", label="Hits O0.5", stat="h", at_least=1, p=0.70)]
plays = tpb.select(cands, val)
check("a market that did not beat its baseline never reaches Top Plays (K O0.5 at 90%)",
      not any(p["market"] == "k1" for p in plays))
check("one play per player, the most likely of his lines", [p["player"] for p in plays] == ["Seven", "Nine"])
check("TB O0.5 is the same event as a hit and is never listed beside it",
      not any(p["market"] == "tb1" for p in plays))
check("each play carries its calibrated chance, record and the most to pay",
      plays[0]["p_cal"] == 0.74 and plays[0]["record"]["n"] == 200 and plays[0]["fair"] == -285)

# ------------------------------------------------------ 3. log and grade
root = Path(tempfile.mkdtemp())
now = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
started = dict(plays[1], start="2026-10-05T17:00:00Z")
n = tpb.log_plays("mlb", [plays[0], started], now=now, root=root)
check("a play is logged only before its game starts", n == 1)
check("first writer wins: the same play logged twice is one play",
      tpb.log_plays("mlb", [plays[0]], now=now, root=root) == 0)
boxes = {"1": {"final": True, "players": {"7": {"h": 2}}}}
g_, v_ = tpb.grade("mlb", lambda gid: boxes.get(str(gid)), root=root, today=date(2026, 10, 6))
rec = tpb.load("mlb", root)["plays"]
check("graded from the box score: 2 hits on Hits O0.5 is a hit", rec[0]["result"] == "hit" and g_ == 1)
tpb.log_plays("mlb", [dict(plays[1], game_id=2)], now=now, root=root)
tpb.grade("mlb", lambda gid: {"final": True, "players": {}}, root=root, today=date(2026, 10, 6))
check("a player missing from a final box score did not play -> void",
      tpb.load("mlb", root)["plays"][1]["result"] == "void")
s = tpb.summary([{"result": "hit", "p_cal": 0.8}, {"result": "miss", "p_cal": 0.8},
                 {"result": "hit", "p_cal": 0.7}, {"result": "void", "p_cal": 0.9}])
check("summary: DELIVERED beside PROMISED, voids counted nowhere",
      s["all"]["n"] == 3 and abs(s["all"]["hit_rate"] - 2 / 3) < 1e-4
      and abs(s["all"]["promised"] - 0.7667) < 1e-4)

# --------------------------------------------------- 4. MLB box score shape
box = {"teams": {"home": {"players": {
    "ID7": {"person": {"id": 7}, "stats": {"batting": {"plateAppearances": 4, "hits": 2, "doubles": 1,
                                                        "triples": 0, "homeRuns": 1, "baseOnBalls": 0,
                                                        "hitByPitch": 1, "strikeOuts": 1, "rbi": 3}}},
    "ID50": {"person": {"id": 50}, "stats": {"pitching": {"gamesStarted": 1, "strikeOuts": 7, "hits": 4,
                                                          "baseOnBalls": 2, "hitBatsmen": 0, "homeRuns": 1}}},
    "ID51": {"person": {"id": 51}, "stats": {"pitching": {"gamesStarted": 0, "strikeOuts": 2}}}}},
    "away": {"players": {}}}}
pb = tpl.parse_box(box, {"dates": [{"games": [{"status": {"abstractGameState": "Final"}}]}]})
b7 = pb["players"]["7"]
check("batting line -> h/tb/hr/k/bb/s/d/rbi (a double and a homer: TB 6, no singles)",
      b7["h"] == 2 and b7["tb"] == 6 and b7["d"] == 1 and b7["s"] == 0 and b7["rbi"] == 3)
check("walks graded the way the model counts them (walks + hit-by-pitch)", b7["bb"] == 1)
check("the starter's pitching line is graded", pb["players"]["50"]["p_k"] == 7)
check("a reliever's line is never graded as a starter play", "51" not in pb["players"])
check("final read from the schedule status", pb["final"] is True)

# --------------------------------------------------------- 5. NHL plumbing
sk = {"11": {"games": {"e1": {"sog": 4, "g": 1, "a": 0}}}}
nb = tpl.nhl_box_by_event(sk)
check("NHL box: shots, goals, assists and points per player per final",
      nb["e1"]["players"]["11"] == {"sog": 4, "g": 1, "a": 0, "pts": 1})
slate = [{"event_id": "e9", "start_et": "2026-10-05T19:00:00-04:00", "away": "A", "home": "H",
          "home_props": [{"pid": "11", "name": "Eleven", "probs": {"sog2": 0.7, "pt1": 0.5}}]}]
nc = tpl.nhl_candidates(slate, "2026-10-05")
check("NHL candidates carry stat and line for grading",
      {(c["market"], c["stat"], c["at_least"]) for c in nc} == {("sog2", "sog", 2), ("pt1", "pts", 1)})

# ------------------------------------------- 6. MLB candidates end to end
src = (ROOT / "tests" / "test_mlb_props.py").read_text()
src = src.split("# ------------------------------------------------------ 3. the reader")[0].replace(
    "Path(__file__)", f'Path("{ROOT / "tests" / "x.py"}")')
ns = {}
exec(compile(src, "props_fixture", "exec"), ns)
pm, LG = ns["model"], ns["LG"]
rg = random.Random(2)


def counts(_pid):
    c = {o: int(500 * v * rg.uniform(0.8, 1.2)) for o, v in LG.items()}
    c["PA"] = sum(c.values())
    return c


games = [{"game_pk": 77, "game_time": "2026-10-05T23:05:00Z", "away": "A", "home": "H",
          "home_pitcher_id": 501, "away_pitcher_id": 502, "home_pitcher": "Hp", "away_pitcher": "Ap"}]
lineup = [{"id": 900 + i, "name": f"B{i}", "battingOrder": str(100 * (i + 1))} for i in range(9)]
pm.setdefault("starter_bf", {})["501"] = [24] * 10
pm["starter_bf"]["502"] = [22] * 10
mc = tpl.mlb_candidates(games, pm, counts, counts, lambda g, side: lineup, "2026-10-05")
check("MLB candidates: every tested batter line for both lineups",
      len([c for c in mc if not c["stat"].startswith("p_")]) == 18 * len(mp.MARKETS))
check("...and every starter line for both starters, graded on his PITCHING stats",
      len([c for c in mc if c["stat"].startswith("p_")]) == 2 * len(mp.PITCHER_MARKETS))
sel = tpb.select(mc, tpl.mlb_validation(pm))
check("selection over a real candidate set returns proven, calibrated, ranked plays",
      sel and all(0 < p["p_cal"] < 1 for p in sel)
      and [p["p_cal"] for p in sel] == sorted((p["p_cal"] for p in sel), reverse=True))

# ------------------------------------------------- 7. the page is wired in
app_src = (ROOT / "app" / "app.py").read_text()
check("Top Plays is in the MLB, NFL and NHL navs", app_src.count('"views/Top_Plays.py"') == 3)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
