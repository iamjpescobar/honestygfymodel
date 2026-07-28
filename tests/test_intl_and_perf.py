"""KBO/NPB correctness and the caching that makes these pages usable."""
import re, sys, types, ast

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, "app")

# --- KBO: innings per START, not per appearance ------------------------
src = open("app/engines/kbo_k_projection.py").read()
assert 'sp.get("games_started")' in src, "GS is not being read"
assert "ip / gs" in src, "innings must be divided by starts when GS exists"
assert 'ip_basis' in src, "the basis must be reported, not silently assumed"
print("PASS: KBO divides innings by GAMES STARTED when published")

# The fallback must be flagged, never printed as if it were per-start.
assert "no GS published" in src, "fallback to appearances must say so"
print("PASS: appearance-based fallback is flagged in the status")

build = open("kbo_precompute.py").read()
assert '"games_started": _val(row, "GS")' in build, "GS not captured in the build"
print("PASS: KBO build captures GS from the leaderboard")

# --- KBO loader arity --------------------------------------------------
kbo = open("app/views/KBO.py").read()
tree = ast.parse(kbo)
fn = next(n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "_load_games")
arities = {len(r.value.elts) if isinstance(r.value, ast.Tuple) else "value"
           for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value}
assert arities == {3}, (
    f"_load_games returns {arities}; every path must return 3 values or the "
    f"caller crashes unpacking on the error path")
print("PASS: KBO _load_games returns 3 values on every path")

# --- caching: the reason these pages were slow -------------------------
# Streamlit re-runs the page script on every widget click. Anything
# uncached here is redone on each interaction.
for view, loaders in (
    ("KBO.py", ["_load_games", "_load_pitchers", "_load_batters", "_load_team_stats"]),
    ("WNBA_Props.py", ["_load_games"]),
    ("WNBA_Defense.py", ["_load_games"]),
    ("NPB.py", ["_load_games"]),
):
    s = open(f"app/views/{view}").read()
    for loader in loaders:
        i = s.index(f"def {loader}(")
        assert "@st.cache_data" in s[max(0, i - 160):i], \
            f"{view}:{loader} is uncached — re-reads its JSON on every click"
    print(f"PASS: {view} — all {len(loaders)} slate loader(s) cached")

# --- the expensive ranking must be cached too --------------------------
for mod, fn_name in (("wnba_props", "build_props"), ("wnba_defense", "build_board")):
    s = open(f"app/engines/{mod}.py").read()
    assert "@st.cache_data" in s, f"{mod} has no caching"
    assert f"_{fn_name}_cached" in s, f"{mod}.{fn_name} is not cached"
    # _games underscore-prefixed so Streamlit skips hashing a big nested list.
    assert "_games" in s, f"{mod} should not hash the whole slate"
    assert "cache_key" in s, f"{mod} needs an explicit staleness key"
    print(f"PASS: {mod}.{fn_name} cached, slate unhashed, keyed on the build")

# --- and the views must actually pass a key ----------------------------
for view in ("WNBA_Props.py", "WNBA_Defense.py"):
    s = open(f"app/views/{view}").read()
    assert "cache_key=" in s, f"{view} doesn't pass a cache key — caching is inert"
print("PASS: both WNBA boards pass a cache key (caching is live, not inert)")
