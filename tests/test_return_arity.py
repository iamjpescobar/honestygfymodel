"""Every `a, b = f()` must match what f() actually returns.

WHY THIS EXISTS

kbo_precompute.main() called

    _hp, _hs = fetch_homepage_starters()

against a function that returns ONE dict. Run 84386218583 died on

    ValueError: not enough values to unpack (expected 2, got 0)

and the KBO step of intl-late-refresh exited 1, so the archive kept the
nightly's stale KBO slate. The whole homepage venue/time repair — built,
committed, tested — never ran once in production.

The crash was the lucky outcome. Unpacking a dict yields its KEYS, so on
a slate where exactly two games had announced starters the statement
would have SUCCEEDED, bound two game-id strings to _hp and _hs, and every
lookup after it would have found nothing while reporting nothing wrong.
That is the failure mode this repo keeps rediscovering: not an exception,
a silence.

The 66 tests were green throughout. They tested parse_homepage_starters
and parse_homepage_schedule — both correct — and never once tested that
main() could call them. A unit test on a parser cannot see a wiring
error one frame up.

WHAT THIS CHECKS, AND WHY IT IS A PROPERTY, NOT A SPELLING (rule 11)

Purely static, no imports, no network: parse each pipeline file, work
out how many values each module-level function can return, and compare
that against every call site inside the same file that unpacks the
result. It never names fetch_homepage_starters, so renaming the function
does not defeat it and the next mismatch is caught by the same code.

Deliberately conservative — it reports ONLY a definite contradiction:

  * a function whose every `return` is a literal tuple of the same
    length N, unpacked into a target of a different length; or
  * a function that never returns a tuple at all (or falls off the end),
    unpacked into any tuple target.

Anything ambiguous — a returned variable, a mix of shapes, a starred
target — is skipped rather than guessed at. A test that cries wolf gets
switched off, and a test nobody trusts is worse than no test.
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The files a broken call site actually takes down: the pipelines that
# run unattended in Actions, where nobody is watching a traceback.
FILES = [
    "kbo_precompute.py",
    "npb_precompute.py",
    "wnba_precompute.py",
    "precompute.py",
    "calibration_picks.py",
    "calibration_pipeline.py",
]

failures = []


def check(label, ok):
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def _returned_arities(fn):
    """{n} for a function all of whose returns are n-tuples.

    1 means "never returns a tuple" — a bare `return`, `return x`, or
    falling off the end all produce a single unpackable-or-not value.
    A set with more than one member means the shape varies and this
    test has nothing certain to say.
    """
    arities = set()
    saw_return = False
    for node in ast.walk(fn):
        # Don't attribute a nested function's returns to its parent.
        if node is not fn and isinstance(node, (ast.FunctionDef,
                                                ast.AsyncFunctionDef,
                                                ast.Lambda)):
            continue
        if isinstance(node, ast.Return):
            saw_return = True
            v = node.value
            if isinstance(v, ast.Tuple):
                # A starred element makes the length unknowable here.
                if any(isinstance(e, ast.Starred) for e in v.elts):
                    return set()
                arities.add(len(v.elts))
            else:
                arities.add(1)
    if not saw_return:
        arities.add(1)
    return arities


def _target_arity(target):
    """How many names a single assignment target binds, or None."""
    if isinstance(target, (ast.Tuple, ast.List)):
        if any(isinstance(e, ast.Starred) for e in target.elts):
            return None
        return len(target.elts)
    return 1


for rel in FILES:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        check(f"{rel} exists", False)
        continue

    tree = ast.parse(open(path, encoding="utf-8").read(), rel)

    # Module-level functions only. A method or a nested def can be
    # shadowed or rebound, and this test refuses to guess.
    defs = {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in defs):
            continue
        arities = _returned_arities(defs[call.func.id])
        if len(arities) != 1:
            continue                      # shape varies; say nothing
        returns = arities.pop()
        for t in node.targets:
            want = _target_arity(t)
            if want is None or want == returns:
                continue
            bad.append(
                f"line {node.lineno}: {call.func.id}() returns "
                f"{returns} value(s), unpacked into {want}"
            )

    check(f"{rel}: every unpacking call site matches its function",
          not bad)
    for b in bad:
        print("        " + b)


# The check has to be able to fail, or it proves nothing. Feed it the
# exact shape that broke production and confirm it fires — a green light
# from a detector nobody has ever seen go red is not evidence.
_sample = ast.parse("def f():\n    return {}\n\ndef g():\n    a, b = f()\n")
_defs = {n.name: n for n in _sample.body if isinstance(n, ast.FunctionDef)}
check("the detector fires on the shape that broke run 84386218583",
      _returned_arities(_defs["f"]) == {1})

_ok = ast.parse("def f():\n    return 1, 2\n\ndef g():\n    a, b = f()\n")
_okd = {n.name: n for n in _ok.body if isinstance(n, ast.FunctionDef)}
check("a genuine 2-tuple return is not flagged",
      _returned_arities(_okd["f"]) == {2})


print("FAILING:" + (" " + ", ".join(failures) if failures else " none"))
sys.exit(1 if failures else 0)
