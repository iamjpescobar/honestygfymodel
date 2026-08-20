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


# ---------------------------------------------------------------------
# THE GAME CARD MUST WARM ITS REQUESTS TOO
#
# prefetch_slate has existed for a while and hr_edge_board and daily_13
# both call it. The GAME CARD did not — so the page a reader spends the
# most time in was the one place still making its MLB calls one at a
# time, each waiting on the last: both rosters, the boxscore, and each
# club's transactions.
#
# Nothing breaks without it. That is exactly why it needs a test: a
# missing prefetch is invisible, it just makes the slowest page slower.
# ---------------------------------------------------------------------
_gc = open("app/views/GameCard.py", encoding="utf-8").read()
if "prefetch_slate(" not in _gc:
    raise SystemExit(
        "FAIL: GameCard never calls prefetch_slate, so every roster, "
        "boxscore and transactions request on the card is serial")
_i_pf = _gc.index("prefetch_slate(\n") if "prefetch_slate(\n" in _gc else _gc.index("prefetch_slate(")
_i_read = _gc.index("get_confirmed_lineup(game.get")
if _i_pf > _i_read:
    raise SystemExit(
        "FAIL: prefetch_slate runs AFTER the first read it was meant to "
        "warm — a prefetch behind its own consumer warms nothing")
print("PASS: the Game Card warms its slate before reading it")

# THE PREFETCH AND THE READER MUST AGREE ON THE URL.
#
# The memo is keyed on (url, params). get_recent_activations reads the
# transactions endpoint and prefetch_slate warms it; if the two built
# that request separately and drifted by one day of window, the prefetch
# would warm one key and the reader would miss on another. Silent
# failure: correct output, serial speed. One shared builder is the fix,
# and this pins that they both use it.
_rs = open("app/engines/roster.py", encoding="utf-8").read()
if "_transactions_spec" not in _rs:
    raise SystemExit("FAIL: the transactions request is no longer built in one place")
if _rs.count("_transactions_spec(") < 3:   # the def, the reader, the prefetch
    raise SystemExit(
        "FAIL: something builds the transactions request without the shared "
        "spec builder, so its memo key can drift from the warmed one")
if '"https://statsapi.mlb.com/api/v1/transactions"' in _rs.split("def _transactions_spec")[0]:
    raise SystemExit("FAIL: a second hand-built transactions URL exists")
print("PASS: prefetch and reader build the transactions request identically")
