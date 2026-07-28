"""Return-shape contracts for cross-module calls.

THIS TEST EXISTS BECAUSE I GOT IT WRONG THREE TIMES:
  - get_daily_13() returns (rows, meta); assumed a list
      -> "AttributeError: 'list' object has no attribute 'get'",
         Daily 13 never logged a single pick
  - get_mlb_player_of_the_day() shape varied; assumed a dict
  - get_last_starting_lineup() returns (lineup, date, confirmed);
      assumed a list -> same AttributeError, crashed the whole
      HR Edge Board page on load

Every one shipped green: the caller compiled, imported, and only failed
when real data flowed through it. Static shape checks are cheap; these
parse the source and assert the arity a caller depends on.
"""
import ast, re

def returns(path, func):
    """Every `return` arity in a function: int for tuples, 'value' else."""
    tree = ast.parse(open(path).read())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == func), None)
    assert fn, f"{func} not found in {path}"
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            out.add(len(node.value.elts) if isinstance(node.value, ast.Tuple)
                    else "value")
    return out

R = "app/engines/roster.py"
assert returns(R, "get_confirmed_lineup") == {2}, returns(R, "get_confirmed_lineup")
print("PASS: get_confirmed_lineup returns a 2-tuple everywhere")

assert returns(R, "get_last_starting_lineup") == {3}, returns(R, "get_last_starting_lineup")
print("PASS: get_last_starting_lineup returns a 3-tuple everywhere")

assert returns("app/engines/daily_13.py", "get_daily_13") == {2}
print("PASS: get_daily_13 returns a 2-tuple everywhere")

assert returns("app/engines/hr_edge_board.py", "get_hr_edge_board") == {2}
print("PASS: get_hr_edge_board returns a 2-tuple everywhere")

# --- callers must unpack to the matching arity ------------------------
board = open("app/engines/hr_edge_board.py").read()

m = re.search(r"(\w+(?:, \w+)*)\s*=\s*get_last_starting_lineup\(", board)
assert m, "hr_edge_board no longer calls get_last_starting_lineup"
n = len(m.group(1).split(","))
assert n == 3, f"unpacks get_last_starting_lineup into {n} names, function returns 3"
print("PASS: hr_edge_board unpacks get_last_starting_lineup as 3")

m = re.search(r"(\w+(?:, \w+)*)\s*=\s*get_confirmed_lineup\(", board)
assert len(m.group(1).split(",")) == 2
print("PASS: hr_edge_board unpacks get_confirmed_lineup as 2")

# A fallback lineup is never today's confirmed lineup.
fb = board[board.index("last, _game_date, last_ok"):]
fb = fb[:fb.index("\n\n")] if "\n\n" in fb else fb
assert "return [p for p in last if not p.get(\"is_pitcher\")], False" in board, \
    "fallback lineup must report confirmed=False"
print("PASS: fallback lineup always reports confirmed=False")

# The view must unpack the board's 2-tuple too.
view = open("app/views/HR_Edge_Board.py").read()
m = re.search(r"(\w+(?:, \w+)*)\s*=\s*get_hr_edge_board\(", view)
assert len(m.group(1).split(",")) == 2
print("PASS: HR Edge Board view unpacks get_hr_edge_board as 2")
