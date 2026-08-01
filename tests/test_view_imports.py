"""Every name a view calls must actually be imported.

A view that calls an undefined function dies with NameError on load, and
nothing catches it before deploy: the file parses fine, the tests don't
import views (they'd need a Streamlit runtime), and the page only breaks
when someone opens it.

That is exactly how render_calibration_trend shipped — an edit anchored on
an import line that didn't match, so the CALL landed and the IMPORT
silently didn't. The patch reported success and the page was dead.
"""
import ast
from pathlib import Path

VIEWS = Path(__file__).resolve().parent.parent / "app" / "views"

failures = []
for view in sorted(VIEWS.glob("*.py")):
    tree = ast.parse(view.read_text())

    bound = set(dir(__builtins__)) | {
        "__file__", "__name__", "__doc__", "st", "pd", "np",
    }
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for a in list(n.args.args) + list(n.args.kwonlyargs):
                    bound.add(a.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        elif isinstance(n, ast.comprehension):
            for t in ast.walk(n.target):
                if isinstance(t, ast.Name):
                    bound.add(t.id)
        elif isinstance(n, ast.Global):
            bound.update(n.names)

    # Every function actually CALLED by name in this view.
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id not in bound:
                failures.append(f"{view.name}:{n.lineno} calls "
                                f"'{n.func.id}()' which is never imported "
                                f"or defined")

assert not failures, (
    "views call names that don't exist — each is a NameError the moment "
    "someone opens that page:\n  " + "\n  ".join(failures))
print(f"PASS: all {len(list(VIEWS.glob('*.py')))} views have every called name bound")
