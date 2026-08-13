"""Every name a view imports from an engine must exist in that engine.

2026-08-13: the site went down with

    ImportError: cannot import name 'slam_from_profile'
                 from 'engines.slam_engine'

app/engines/slam_engine.py was overwritten with a copy of
statcast_engine.py, which deleted slam_from_profile outright.
GameCard.py still imported it, so the Game Card page raised at import
time and the break was found by a user rather than by the suite.

Two neighbours cover the adjacent cases and neither covers this one.
test_view_imports.py checks that every name a view CALLS is bound
somewhere in that view — it would pass here, because the import line is
present and spelled correctly; the name it asks for is what stopped
existing. test_probe_imports.py guards the probes' reach into engine
internals, which is the cheaper direction: a broken probe is noticed by
whoever runs it, a broken view is a dead page in production.

This does NOT import the views — they call st.set_page_config at module
scope and pull the whole dependency tree with them. It reads both sides
as source and compares names, so it runs in a bare container with no
streamlit and no data archive, and costs nothing.

TOURNIQUETS
An import wrapped in `try: ... except ImportError:` with a fallback is
deliberate and temporary. Those are listed below rather than ignored,
and the test fails BOTH ways: an unlisted one appears (someone papered
over a break quietly), or a listed one starts resolving again (the real
fix landed and the stub is now dead code returning fake emptiness).
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS = ROOT / "app" / "views"
ENGINES = ROOT / "app" / "engines"

# (view file, engine module, imported name) -> why it is guarded.
# Delete an entry the moment the underlying name is restored; the test
# will tell you to.
KNOWN_TOURNIQUETS = {
    ("GameCard.py", "engines.slam_engine", "slam_from_profile"):
        "slam_engine.py was clobbered 2026-08-13; restore from git history",
}


def module_names(path: Path) -> set:
    """Top-level names a module exposes: defs, classes, assignments, and
    anything it imports itself (a re-export is a legitimate way for a
    caller's name to resolve)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    out = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out.add(a.asname or a.name.split(".")[0])
    return out


def engine_imports(path: Path):
    """Yield (module, name, guarded) for every `from engines.X import ...`
    in a view. guarded is True when the import sits inside a try block
    with an ImportError handler."""
    tree = ast.parse(path.read_text(), filename=str(path))
    guarded_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            (h.type is not None and "ImportError" in ast.dump(h.type))
            for h in node.handlers
        ):
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    guarded_lines.add(getattr(sub, "lineno", None))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("engines."):
            for a in node.names:
                if a.name == "*":
                    continue
                yield node.module, a.name, node.lineno in guarded_lines


_cache = {}
missing, unlisted, resolved_tourniquets, checked = [], [], [], 0

for view in sorted(VIEWS.glob("*.py")):
    for mod, name, guarded in engine_imports(view):
        engine_path = ENGINES / (mod.split(".", 1)[1] + ".py")
        assert engine_path.exists(), f"{view.name} imports from {mod}, which has no file"
        if engine_path not in _cache:
            _cache[engine_path] = module_names(engine_path)
        exists = name in _cache[engine_path]
        key = (view.name, mod, name)
        checked += 1
        if guarded:
            if key not in KNOWN_TOURNIQUETS:
                unlisted.append(key)
            elif exists:
                resolved_tourniquets.append(key)
        elif not exists:
            missing.append(key)

if missing:
    for v, m, n in missing:
        print(f"BROKEN: {v} imports {n} from {m} — that name does not exist")
    sys.exit("a view imports an engine name that is gone — this page is a dead "
             "page in production the moment it is opened")

if unlisted:
    for v, m, n in unlisted:
        print(f"UNLISTED TOURNIQUET: {v} guards {n} from {m}")
    sys.exit("an ImportError fallback was added without an entry in "
             "KNOWN_TOURNIQUETS — a stub returning empty data looks exactly "
             "like measured data that happens to be missing")

if resolved_tourniquets:
    for v, m, n in resolved_tourniquets:
        print(f"FIXED: {m}.{n} resolves again")
    sys.exit("the real fix has landed — delete the try/except in the view and "
             "the KNOWN_TOURNIQUETS entry here")

print(f"PASS: all {checked} view-to-engine imports resolve "
      f"({len(KNOWN_TOURNIQUETS)} tourniquet(s) outstanding)")

# --- NEGATIVE CONTROL -------------------------------------------------
# Confirm the check can actually go red. A test that only ever sees
# working code proves nothing — this repo has shipped fixtures that
# passed against deliberately broken input.
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    fake = Path(td) / "fake_engine.py"
    fake.write_text("def real_name():\n    return 1\n")
    assert "real_name" in module_names(fake)
    assert "vanished_name" not in module_names(fake), (
        "module_names claims a name that was never defined — the whole "
        "check would pass against any break")
print("PASS: negative control — a missing name is detected as missing")
