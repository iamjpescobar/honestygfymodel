"""The two failures behind "the home page is inconsistent and WNBA is
not working". Neither was caught by anything in this suite.

1) THE BACKFILL WENT STRAIGHT AT THE BLOCKED HOST.

   wnba_precompute carries a long comment explaining that ESPN 403s the
   site.api scoreboard path from cloud IPs, and fetch_scoreboard exists
   with three mirror hosts because of it. The season backfill loop in
   main() never used it — it called get_json(f"{BASE}/scoreboard?...")
   directly.

   The failure was PARTIAL, which is why it survived. Tonight's slate
   goes through fetch_scoreboard and succeeded, so games.json wrote
   cleanly and the archive verifier (which only checks the file exists)
   passed. But every historical day failed, and `logs` is what every
   WNBA number is built from — so the site shipped a slate of real
   fixtures in which no player had a single stat, the Props and Defense
   Matchup boards had nothing to rank, and the job still exited 0.

2) HOME PRESENTED WNBA'S BOARDS AS EVERY OTHER SPORT'S.

   _render_today chose its board list with
   `BOARD_PAGE if CURRENT_SPORT == "MLB" else WNBA_PAGE`, which has no
   third branch — so on KBO, NPB, NBA, NFL and NHL the else fired and
   basketball's two boards were rendered as that sport's own, at full
   card weight, with no way to open them.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

failures = []

# ----------------------------------------------------------------------
# 1) Every scoreboard request goes through the fallback.
# ----------------------------------------------------------------------
build = (ROOT / "wnba_precompute.py").read_text()


def _code_only(src):
    """Source with comments and docstrings removed.

    Necessary, not fussiness: the fix left a comment quoting the old
    broken call verbatim so the next reader knows what not to do, and a
    naive scan flagged that comment as the defect it warns about.
    """
    out = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Drop trailing comments, but not a '#' inside a string literal.
        if "#" in line and line.count('"') % 2 == 0 and line.count("'") % 2 == 0:
            line = line.split("#", 1)[0]
        out.append(line)
    code = "\n".join(out)
    # Docstrings: strip triple-quoted blocks wholesale.
    code = re.sub(r'"""(?:.|\n)*?"""', "", code)
    code = re.sub(r"'''(?:.|\n)*?'''", "", code)
    return code


build_code = _code_only(build)

# The whole point: no raw BASE scoreboard call anywhere. fetch_scoreboard
# is allowed to name it, because that is where the mirror list lives.
_raw = re.findall(r'get_json\(\s*f?"[^"]*scoreboard[^"]*"', build_code)
if _raw:
    failures.append(
        "wnba_precompute still calls the scoreboard endpoint directly: "
        + "; ".join(_raw) + " — that host is the one ESPN blocks from CI, "
        "so it must go through fetch_scoreboard's mirror list")
else:
    print("PASS: no raw scoreboard call — every day goes through the mirrors")

_main = build_code[build_code.index("def main("):]
if "fetch_scoreboard(d.strftime" not in _main.replace(" ", "").replace(
        "\n", "").replace("fetch_scoreboard(d.strftime", "fetch_scoreboard(d.strftime"):
    # tolerate reformatting: just require the backfill loop to call it
    if "fetch_scoreboard(" not in _main.split("while d <=")[-1]:
        failures.append("the season backfill loop does not call "
                        "fetch_scoreboard — it is back on a single host")
    else:
        print("PASS: the season backfill loop calls fetch_scoreboard")
else:
    print("PASS: the season backfill loop calls fetch_scoreboard")

# An off-day must be an answer, not a failure, or the loop re-probes all
# three hosts on every date the league didn't play.
if "require_events" not in build:
    failures.append("fetch_scoreboard can no longer distinguish an empty "
                    "slate from an unreachable host, so every off-day costs "
                    "three failed requests")
else:
    print("PASS: an empty slate is a real answer, not a retry")

# ----------------------------------------------------------------------
# 2) A wholly failed backfill must NOT publish.
#
# Publishing a slate with no stats behind it is worse than publishing
# nothing: the pages render, look live, and answer nothing. Exiting
# non-zero lets the workflow's `|| echo` keep the rest of the nightly
# alive while the WNBA views honestly show their placeholder.
# ----------------------------------------------------------------------
_guard = _main[_main.index("players = player_summaries"):] if \
    "players = player_summaries" in _main else ""
_pre_guard = _main[:_main.index("players = player_summaries")] if \
    "players = player_summaries" in _main else _main
if "raise RuntimeError" not in _pre_guard:
    failures.append("main() no longer refuses to publish when the backfill "
                    "produced nothing — a numberless league would ship "
                    "again, silently and with a green build")
else:
    print("PASS: a wholly failed backfill raises instead of publishing")

if "days_failed" not in build:
    failures.append("the backfill no longer counts failed days, so a "
                    "systemic block cannot be told from a few flaky dates")
else:
    print("PASS: failed days are counted, so a block is distinguishable")

# ----------------------------------------------------------------------
# 3) Home never shows one sport's boards as another's.
# ----------------------------------------------------------------------
home_src = (ROOT / "app" / "views" / "Home.py").read_text()

if "SPORT_BOARDS" not in home_src:
    failures.append("Home lost SPORT_BOARDS — the board list is being "
                    "re-derived inline again, which is what produced the "
                    "two-branch guess")
else:
    print("PASS: Home maps sport -> boards explicitly, in one place")

# The exact shape of the original defect: a binary choice on CURRENT_SPORT
# whose else-branch hands back another sport's boards.
_bad = re.search(r'if\s+CURRENT_SPORT\s*==\s*"MLB"\s+else\s+list\(WNBA_PAGE\)',
                 home_src)
if _bad:
    failures.append("Home is back to `BOARD_PAGE if CURRENT_SPORT == 'MLB' "
                    "else WNBA_PAGE` — every sport that is neither gets "
                    "basketball's boards presented as its own")
else:
    print("PASS: no two-branch sport guess remains")

# And the behaviour itself, read off the module rather than the source.
_ns = {}
_tree = ast.parse(home_src)
for _node in _tree.body:
    if isinstance(_node, ast.Assign) and any(
            getattr(t, "id", "") in ("BOARD_PAGE", "WNBA_PAGE", "SPORT_BOARDS")
            for t in _node.targets):
        try:
            exec(compile(ast.Module([_node], []), "<home>", "exec"), _ns, _ns)
        except Exception:
            pass

_sb = _ns.get("SPORT_BOARDS", {})
if _sb:
    _mlb = set(_sb.get("MLB", {}))
    _wnba = set(_sb.get("WNBA", {}))
    if _mlb & _wnba:
        failures.append(f"a board is owned by two sports: {_mlb & _wnba}")
    elif not _mlb or not _wnba:
        failures.append("SPORT_BOARDS is missing MLB or WNBA boards")
    else:
        print(f"PASS: {len(_mlb)} MLB boards and {len(_wnba)} WNBA boards, "
              f"no overlap")
    # The sports that publish nothing must resolve to nothing.
    for _sport in ("KBO", "NPB", "NBA", "NFL", "NHL"):
        if _sb.get(_sport):
            failures.append(f"{_sport} claims boards it does not publish")
    else:
        print("PASS: KBO/NPB/NBA/NFL/NHL claim no boards of their own")

# ----------------------------------------------------------------------
# 4) Home's record reads are cached, and cached on the FILES.
#
# A TTL cache would keep serving the pre-write record after the app logs
# picks mid-session — the board a subscriber just triggered would be
# missing from Home and Results until it expired.
# ----------------------------------------------------------------------
cal_src = (ROOT / "app" / "engines" / "calibration.py").read_text()
if "_record_stamp" not in cal_src:
    failures.append("calibration no longer fingerprints the record files, "
                    "so _load/summary are either uncached or cached on a "
                    "timer that goes stale after a mid-session write")
elif re.search(r"def _load_cached\(\s*_", cal_src) or \
        re.search(r"def _summary_cached\(\s*_", cal_src):
    failures.append("the cache key argument starts with an underscore — "
                    "Streamlit EXCLUDES those from the key, so the cache "
                    "would never invalidate at all")
else:
    print("PASS: _load and summary cache on the record's own mtime/size")

if failures:
    print("\n" + "=" * 68)
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("\nAll WNBA-routing and Home-scope checks passed.")
