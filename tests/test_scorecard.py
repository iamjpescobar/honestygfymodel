"""
Model Scorecard (10-08) — engines/scorecard and its place at the top of
the Results page.

Plain script — exits non-zero on failure. Fixtures carry the shapes the
records really have: calibration.summary() board entries with a "days"
list, data/top_plays play rows (p, p_cal, result, date), data/model_picks
rows (p, result, units, formula) — rule 5.

Negative controls, confirmed red by exit code when written (rule 4):
  - _with_recent never overriding (return status, False)
    -> "a model that fell off over the last 30 days is SLIPPING" fails
  - game_pick_rows judging model-only picks with the current ones
    -> "retired picks are never judged" fails
  - z_vs_promise using the mean promise instead of the sum
    -> "Top Plays landing far under its promise is SLIPPING" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from engines import scorecard as sc  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def board(label, days, base):
    hits = sum(d["hits"] for d in days)
    total = sum(d["total"] for d in days)
    return {"label": label, "hits": hits, "total": total,
            "rate": round(100 * hits / total, 1) if total else None,
            "baseline": base, "days": days}


def day(i, hits, total, month=8):
    return {"date": f"2026-{month:02d}-{i:02d}", "hits": hits, "total": total}


# --- 1. the verdict ladder ---------------------------------------------
check("under MIN_N is TOO EARLY whatever the gap", sc.verdict(29, 9.0, "baseline") == "too_early")
check("z >= 2 is BEATING", sc.verdict(100, 2.1, "baseline") == "beating")
check("z <= -2 is SLIPPING", sc.verdict(100, -2.1, "promise") == "slipping")
check("inside the noise vs a promise is ON TARGET", sc.verdict(100, 1.0, "promise") == "on_target")
check("inside the noise vs a baseline is NO EDGE YET", sc.verdict(100, 1.0, "baseline") == "no_edge")

# --- 2. pick boards ----------------------------------------------------
good = board("Good", [day(i, 8, 10) for i in range(1, 21)], 62.0)        # 80% on 200
r = sc.board_rows({"good": good})[0]
check("a board well above its league rate is BEATING", r["status"] == "beating")
check("the gap is rate minus baseline", r["gap"] == round(80.0 - 62.0, 1))

# Strong for ten days in early August (90%), then 40 picks at 30% in late
# September — still above 62% over the whole record, which is the point.
fell = board("Fell", [day(i, 9, 10) for i in range(1, 11)]
             + [day(i, 3, 10, month=9) for i in range(20, 24)], 62.0)
check("fixture: the whole record still beats its baseline",
      sc.verdict(fell["total"], sc.z_vs_rate(fell["hits"], fell["total"], 0.62), "baseline")
      == "beating")
r = sc.board_rows({"fell": fell})[0]
check("a model that fell off over the last 30 days is SLIPPING",
      r["status"] == "slipping" and r["fell_off"])
check("the recent window counts only the last 30 days", r["recent"]["n"] == 40)

# The same record dated years ago: the window follows the record's own
# newest date, so a stale feed does not read as an empty window.
old = board("Old", [{"date": f"2020-08-{i:02d}", "hits": 8, "total": 10} for i in range(1, 21)], 62.0)
r = sc.board_rows({"old": old})[0]
check("the window is anchored to the newest graded date, not today", r["recent"]["n"] == 200)

nobase = board("K", [day(i, 4, 10) for i in range(1, 11)], None)
r = sc.board_rows({"k_board": nobase})[0]
check("a board with no league rate is NO TARGET, never coloured", r["status"] == "no_target")

# --- 3. Top Plays, judged against what they promised ------------------
def plays(n, hits, p, start=1):
    return [{"date": f"2026-10-{start + i // 10:02d}", "p": p + 0.02, "p_cal": p,
             "result": "hit" if i < hits else "miss"} for i in range(n)]


r = sc.top_play_rows({"NHL": plays(50, 41, 0.80)})[0]
check("Top Plays landing about what it promised is ON TARGET", r["status"] == "on_target")
check("the target is the promised (delivered) chance, not the raw one", r["target"] == 80.0)
r = sc.top_play_rows({"NHL": plays(50, 30, 0.80)})[0]
check("Top Plays landing far under its promise is SLIPPING", r["status"] == "slipping")
r = sc.top_play_rows({"MLB": [dict(p, result="void") for p in plays(40, 40, 0.8)]})[0]
check("voids are not graded", r["status"] == "no_picks" and r["n"] == 0)

# --- 4. game bets -------------------------------------------------------
def pick(res, p, formula=None, units=None):
    d = {"result": res, "p": p, "units": units if units is not None else (0.9 if res == "win" else -1.0)}
    if formula:
        d["formula"] = formula
    return d


old_only = [pick("loss", 0.75) for _ in range(40)]
rows = sc.game_pick_rows({"NFL": old_only})
check("retired picks are never judged",
      [x["status"] for x in rows] == ["no_picks", "retired"])
check("retired picks keep their record and units",
      rows[1]["record"] == "0-40-0" and rows[1]["units"] == -40.0)
check("no current picks says so instead of showing 0-0-0", rows[0]["record"] is None)
cur = [pick("win" if i < 18 else "loss", 0.55, "market-anchored") for i in range(34)]
r = sc.game_pick_rows({"NHL": cur})[0]
check("market-anchored bets are judged against their logged chance", r["status"] == "on_target")
pushes = [pick("push", 0.5, "market-anchored", 0) for _ in range(3)]
r = sc.game_pick_rows({"MLB": pushes})[0]
check("pushes are not a record to judge", r["status"] == "no_picks")

# --- 5. ordering and headline -----------------------------------------
rows = sc.all_rows({"fell": fell, "good": good, "k_board": nobase},
                   {"NHL": plays(50, 41, 0.80)}, {"NFL": old_only})
check("problems are listed first", rows[0]["status"] == "slipping")
check("retired rows are listed last", rows[-1]["status"] == "retired")
h = sc.headline(rows)
check("the headline counts only judged models",
      h["judged"] == 3 and h["slipping"] == 1 and h["beating"] == 1 and h["on_target"] == 1)

# --- 6. the page --------------------------------------------------------
src = (ROOT / "app" / "views" / "Results.py").read_text(encoding="utf-8")
check("Results renders the scorecard", "_render_scorecard(sums)" in src)
check("the scorecard comes before the board detail",
      src.index("_render_scorecard(sums)\n") < src.index('_section_tag("By board")'))
check("no backslash inside an f-string expression (Python < 3.12)",
      'join(bits)}' not in src)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall scorecard checks passed")
