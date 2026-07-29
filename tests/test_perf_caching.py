"""Every view data-loader must be cached.

Streamlit re-runs a page's entire script on every widget interaction, so
an uncached loader re-reads and re-parses its JSON each time someone
touches a control. That was the cause of the multi-minute page loads,
and WNBA.py — the largest page on the site — was still uncached after
the first pass fixed the others.
"""
import glob, re

# _load(path, key) in KBO is a generic helper called only from cached
# wrappers, so caching it again would be pointless double-caching.
ALLOWED_UNCACHED = {"KBO.py:_load"}

bad = []
for view in sorted(glob.glob("app/views/*.py")):
    src = open(view).read()
    fname = view.split("/")[-1]
    for m in re.finditer(r"^\s*def (_load[a-z_]*)\(", src, re.M):
        name = m.group(1)
        if f"{fname}:{name}" in ALLOWED_UNCACHED:
            continue
        if "@st.cache_data" not in src[max(0, m.start() - 220):m.start()]:
            bad.append(f"{fname}:{name}")

assert not bad, (
    "uncached view loaders — these re-parse their data file on every "
    f"widget click: {bad}")
print("PASS: every view data-loader is cached (or an internal helper)")

# The generic KBO helper must genuinely only be reached through cached
# wrappers, or the exemption above is hiding a real problem.
kbo = open("app/views/KBO.py").read()
for wrapper in ("_load_games", "_load_pitchers", "_load_batters", "_load_team_stats"):
    m = re.search(rf"def {wrapper}\(", kbo)
    assert m, f"{wrapper} missing"
    assert "@st.cache_data" in kbo[max(0, m.start() - 220):m.start()], \
        f"{wrapper} is uncached but calls the shared _load helper"
print("PASS: KBO's shared _load is only reached through cached wrappers")

# The expensive board rankings must be cached too.
for mod, fn in (("wnba_props", "build_props"), ("wnba_defense", "build_board")):
    src = open(f"app/engines/{mod}.py").read()
    assert f"_{fn}_cached" in src, f"{mod}.{fn} is not cached"
print("PASS: WNBA board rankings cached")
