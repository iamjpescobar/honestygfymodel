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

# A fallback lineup is never today's confirmed lineup — check the
# BEHAVIOUR, not one literal line. An earlier version of this assertion
# pinned the exact source text and broke the moment that block gained
# active-roster filtering, even though the contract was unchanged.
fb = board[board.index("last, _game_date, last_ok"):]
fb = fb[:fb.index("\n\n@")] if "\n\n@" in fb else fb
# NOT named `returns` — that shadowed the helper defined at the top of
# this file, so any check added below this line silently became a
# "list object is not callable" crash.
fb_returns = re.findall(r"return ([^\n]+)", fb)
assert fb_returns, "no returns found in the fallback path"
assert all(r.strip().endswith("False") for r in fb_returns), (
    f"every fallback return must report confirmed=False, got: {fb_returns}")
print("PASS: fallback lineup always reports confirmed=False")

# The view must unpack the board's 2-tuple too.
view = open("app/views/HR_Edge_Board.py").read()
m = re.search(r"(\w+(?:, \w+)*)\s*=\s*get_hr_edge_board\(", view)
assert len(m.group(1).split(",")) == 2
print("PASS: HR Edge Board view unpacks get_hr_edge_board as 2")


# ======================================================================
# VIEW-LEVEL SWEEP: every unpack in every view must match its function
# ======================================================================
#
# WHY THIS BLOCK EXISTS
#
# NPB._load_games returned a 3-tuple on success and `None, None` in its
# except branch, while line 44 unpacked three names. Every failure to
# read the slate file — missing, truncated, written mid-request by the
# nightly — raised "ValueError: not enough values to unpack" and took
# the page down, instead of reaching the in-development panel the except
# branch exists to reach. KBO.py had the identical bug and was fixed by
# hand; nothing stopped the next copy of the pattern.
#
# It shipped green because it is only reachable when the read fails, and
# the read does not fail in CI. That is the same reason the four checks
# above this line exist, so this is the same medicine applied to the
# whole directory instead of one function at a time: no named function,
# no maintained list of views. Add a view, it is covered.
#
# Two rules, both purely static:
#   1. a function that ever returns a tuple must always return a tuple
#      of the SAME length (a bare `return` and `return None` count as
#      the wrong length — they are what the except branch usually does)
#   2. anything unpacking that function must take exactly that many names
import glob
import os

def _own_returns(fn):
    """Return arities for fn's OWN body — nested defs excluded.

    ast.walk descends into inner functions, so a helper defined inside
    the one under test would otherwise contribute its returns and the
    arity set would be nonsense.
    """
    out = set()
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue                       # a different function's contract
        if isinstance(node, ast.Return):
            if node.value is None:
                out.add(0)                 # bare `return` -> None
            elif isinstance(node.value, ast.Tuple):
                out.add(len(node.value.elts))
            elif (isinstance(node.value, ast.Constant)
                  and node.value.value is None):
                out.add(0)                 # `return None`
            else:
                out.add("value")
            continue
        stack.extend(ast.iter_child_nodes(node))
    return out


_problems = []
_checked = 0

for path in sorted(glob.glob("app/views/*.py")):
    tree = ast.parse(open(path).read())
    name = os.path.basename(path)

    # Top-level functions only. A view's module-level loaders are the
    # ones whose failure branch takes the page down on import.
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    # Rule 1: consistent arity within each function.
    tuple_arity = {}
    for fname, fn in funcs.items():
        arities = _own_returns(fn)
        tuples = {a for a in arities if isinstance(a, int) and a > 1}
        if not tuples:
            continue                       # not a tuple-returning function
        _checked += 1
        if len(arities) > 1:
            _problems.append(
                f"{name}:{fn.lineno} {fname}() returns mixed shapes "
                f"{sorted(arities, key=str)} — the odd one out is almost "
                f"always an error path the caller cannot unpack")
        else:
            tuple_arity[fname] = tuples.pop()

    # Rule 2: every unpack of those functions takes the right count.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)):
            continue
        fname = node.value.func.id
        if fname not in tuple_arity:
            continue
        for target in node.targets:
            if isinstance(target, (ast.Tuple, ast.List)):
                got = len(target.elts)
                want = tuple_arity[fname]
                if got != want and not any(isinstance(e, ast.Starred)
                                           for e in target.elts):
                    _problems.append(
                        f"{name}:{node.lineno} unpacks {fname}() into "
                        f"{got} names, function returns {want}")

assert not _problems, (
    "view return-shape contract violated:\n  "
    + "\n  ".join(_problems))
print(f"PASS: {_checked} tuple-returning view functions have one consistent "
      f"arity, and every unpack of them matches")
