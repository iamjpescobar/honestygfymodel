"""
NBA late news (10-30) — live_injuries.overlay keeps the rows of players
ruled out since the nightly; nba_context.late_out_bump gives their
teammates the tested teammate-out bump; nba_view.load runs it on every NBA
page.

Izzy: "feed the NBA projections the news DraftKings has". The NBA pages
already dropped a late scratch from the board, but his teammates kept their
morning numbers while the book moved its lines.

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - the bump not applied (late_out_bump returning early) -> "teammates of a
    late scratch move up" fails
  - a bench player below ROT_MIN counted as a real absence -> "a deep-bench
    scratch moves nobody" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import live_injuries as li  # noqa: E402
from engines import nba_context as nc  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def row(pid, name, mins, pts, reb=5.0, ast=4.0, tpm=2.0, status=None):
    mu = {"pts": pts, "reb": reb, "ast": ast, "tpm": tpm}
    mu.update(pra=pts + reb + ast, pr=pts + reb, pa=pts + ast, ra=reb + ast)
    return {"pid": pid, "name": name, "min": mins, "mu": mu, "status": status}


games = [{"away_props": [row("1", "Star", 36, 28.0), row("2", "Mate", 32, 15.0),
                         row("3", "Bench", 6, 2.0)],
          "home_props": [row("9", "Other", 34, 20.0)]}]
feed = {"by_id": {"1": "Out", "3": "Out"}, "by_name": {}}
g2, out = li.overlay(games, feed, "nba")
check("a late scratch leaves the board and his row is kept for the bump",
      [r["pid"] for r in g2[0]["away_props"]] == ["2"]
      and {r["pid"] for r in g2[0]["away_out_live_rows"]} == {"1", "3"})
ctx = {"out": {"pts": {"alpha": 0.3, "hl": 2}, "reb": {"alpha": 0.2, "hl": 2},
               "ast": None, "tpm": None}}
before = dict(g2[0]["away_props"][0]["mu"])
b = nc.late_out_bump(g2[0]["away_props"], g2[0]["away_out_live_rows"], ctx)
mate = g2[0]["away_props"][0]
check("teammates of a late scratch move up by the tested bump",
      b["pts"] > 1.0 and abs(mate["mu"]["pts"] - round(before["pts"] * b["pts"], 3)) < 1e-9
      and b["ast"] == 1.0 and mate["mu"]["ast"] == before["ast"])
check("combos follow their parts",
      abs(mate["mu"]["pra"] - (mate["mu"]["pts"] + mate["mu"]["reb"] + mate["mu"]["ast"])) < 1e-6)
check("the row says why", "Star ruled out since this morning: pts +" in mate["why"]
      and "Bench" not in mate["why"])
rows2 = [row("2", "Mate", 32, 15.0)]
check("a deep-bench scratch moves nobody",
      nc.late_out_bump(rows2, [{"pid": "3", "name": "Bench", "min": 6, "mu": {"pts": 2.0}}],
                       ctx) == {} and rows2[0]["mu"]["pts"] == 15.0)
check("no tested bump in the model: nothing moves",
      nc.late_out_bump([row("2", "M", 32, 15.0)], [{"min": 36, "mu": {"pts": 28.0}}],
                       {"out": {}}) == {})
check("the other team is untouched", g2[0]["home_props"][0]["mu"]["pts"] == 20.0
      and "home_out_live_rows" not in g2[0])
check("the slate is copied: the original rows never change",
      games[0]["away_props"][1]["mu"]["pts"] == 15.0)
src = (ROOT / "app" / "engines" / "nba_view.py").read_text()
check("every NBA page's loader runs it", "_nc.late_out_bump(g[f\"{side}_props\"], outs" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
