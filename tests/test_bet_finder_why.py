"""
The Bet Finder says WHY (10-24). Izzy: "the bet finder doesn't attack
defense or nothing" — it did (the board's chance is the model's whole
projection), but it never SAID so. Now every judged / reference row has
its "why": the model's own inputs (his rate, ice time / minutes,
tonight's opponent and defense, teammates out) and this stat's matchup
note, bets first; and the NHL why marks which parts are IN the number
(the team-level matchup) and which are context (defense vs position).

Plain script — exits non-zero on failure. _why_lines is read out of the
view and run on rows in the Bet Finder's shape (rule 5).

Negative controls, confirmed red by exit code when written (rule 4):
  - _why_lines dropping the stat's matchup note
    -> "each line: the player, his line and call, his why, the stat's note" fails
  - the NHL why no longer saying the position split is context
    -> "the NHL why says what is in the number and what is context" fails
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


src = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_why_lines")
ns = {"bf": type("bf", (), {"TIER_LABEL": {"value": "VALUE"}}),
      "COLOR": {"warn": "#f00"}, "_pct": lambda x: "—" if x is None else f"{100 * x:.1f}%"}
exec(compile(ast.Module([fn], []), "why", "exec"), ns)
rows = [{"_name": "A (BOS)", "_why": "1.9 shots a game · BOS matchup x1.05",
         "_notice": {"sog": "BOS allows the most shots to centres"}},
        {"_name": "B (NSH)", "_why": None}]
judged = [{"name": "A (BOS)", "line_label": "O2.5", "tier": "value", "chance": 0.55},
          {"name": "B (NSH)", "line_label": "O1.5", "chance": 0.4}]
out = ns["_why_lines"](judged, rows, "sog")
check("each line: the player, his line and call, his why, the stat's note; no why -> no line",
      len(out) == 1 and "<b>A (BOS)</b> (O2.5, VALUE, our chance 55.0%)" in out[0]
      and "BOS matchup x1.05" in out[0] and "allows the most shots to centres" in out[0])
check("the Bet Finder shows them under the table, bets first, opened when there are bets",
      "_why_rows = _why_lines(res or ref, players, stat)" in src
      and 'st.expander(f"Why these numbers ({len(_why_rows)} players)"' in src
      and "expanded=bool(res)" in src)
from engines import nhl_model as nm  # noqa: E402
w = nm.why_line("X", "C", {"sog": 2.0, "g": 0.3, "a": 0.4, "gp": 50},
                {"shot_ratio": 1.1, "goal_ratio": 1.0}, None, "BOS",
                {"rank": 3, "of": 32, "group": "C", "per_game": 9.9, "league": 9.6,
                 "dir": "most"}, 2.2, 0.7)
check("the NHL why says what is in the number and what is context",
      "(in the number)" in w and "context, not in the number" in w)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall Bet Finder why checks passed")
