"""parse_boxscore must actually parse a box score.

WHY THIS EXISTS — Aug 5. A one-character typo inside `_made_att` wrote
`line[al]` instead of `line[ak]`. `al` is not defined anywhere, so the
first player of every box score raised NameError. Nothing about that
was visible:

  1. parse_boxscore is called inside `except Exception as exc: print(...)`,
     so each game printed "boxscore NNN failed" and the crawl continued.
  2. With every game failing, `logs` finished empty and the deliberate
     RuntimeError ("parsed ZERO box scores") killed the script.
  3. The nightly runs it as `python wnba_precompute.py || echo "WNBA
     fetch failed - continuing without it"`, which swallowed THAT too.
  4. The archive published with no data/wnba/ in it — a ::warning::,
     not an error, by design.
  5. slate_guard found no file, and the page honestly reported "No WNBA
     slate on disk for <today>".

Five correct, defensive layers turned a NameError into a silent
league-wide outage with a green pipeline. Every one of them is right on
its own; what was missing was anything that ran the parser against a
payload. So: a payload.

Uses a hand-built summary in ESPN's shape and a stubbed get_json — no
network, no ESPN dependency, runs in CI in milliseconds.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import wnba_precompute as W  # noqa: E402

# One team block, two players, in the shape ESPN's summary endpoint
# returns: parallel `labels` and per-athlete `stats` lists of strings,
# with the made-attempted stats as "M-A".
LABELS = ["MIN", "FG", "3PT", "FT", "REB", "AST", "STL", "BLK", "TO", "PTS"]

PAYLOAD = {
    "boxscore": {
        "players": [
            {
                "team": {"id": "1", "displayName": "Home Team",
                         "logo": "https://example.invalid/home.png"},
                "statistics": [{
                    "labels": LABELS,
                    "athletes": [
                        {"athlete": {"id": "101", "displayName": "Starter One",
                                     "position": {"abbreviation": "G"}},
                         "stats": ["32", "9-17", "3-7", "4-4", "6", "5",
                                   "2", "1", "3", "25"]},
                        {"athlete": {"id": "102", "displayName": "Bench Two",
                                     "position": {"abbreviation": "F"}},
                         "stats": ["11", "1-4", "0-2", "2-2", "3", "1",
                                   "0", "0", "1", "4"]},
                    ],
                }],
            },
            {
                "team": {"id": "2", "displayName": "Away Team",
                         "logo": "https://example.invalid/away.png"},
                "statistics": [{
                    "labels": LABELS,
                    "athletes": [
                        {"athlete": {"id": "201", "displayName": "Opponent One",
                                     "position": {"abbreviation": "C"}},
                         "stats": ["28", "6-11", "0-0", "5-6", "12", "2",
                                   "1", "3", "2", "17"]},
                        {"athlete": {"id": "202", "displayName": "Did Not Play"},
                         "didNotPlay": True, "stats": []},
                    ],
                }],
            },
        ]
    }
}

W.get_json = lambda url, **kw: PAYLOAD  # no network, ever

logs = {}
W.parse_boxscore("999", "2026-08-04", logs)

# --- it parsed at all -------------------------------------------------
# This single assertion is the whole bug. Before the fix, `logs` came
# back EMPTY here, because every athlete raised NameError.
assert logs, "parse_boxscore produced nothing — the parser is broken"
assert len(logs) == 3, f"expected 3 players (one DNP skipped), got {len(logs)}"
assert "202" not in logs, "didNotPlay must be skipped"
print("PASS: a realistic box score parses into per-player lines")

# --- the made/attempted split, which is where the typo lived ----------
line = logs["101"]["games"][0]
assert line["fgm"] == 9 and line["fga"] == 17, line
assert line["tpm"] == 3 and line["tpa"] == 7, line
assert line["ftm"] == 4 and line["fta"] == 4, line
print("PASS: FG / 3PT / FT each split into made AND attempted")

# The ATTEMPTED half is the specific thing that was never written. The
# Volume prop tab reads fga/fta; without them it renders empty columns.
for key in ("fga", "tpa", "fta"):
    assert line.get(key) is not None, f"{key} missing — attempts not parsed"
print("PASS: attempts are present, not just makes")

# --- the plain counting stats -----------------------------------------
assert line["min"] == 32 and line["pts"] == 25 and line["reb"] == 6
assert line["ast"] == 5 and line["stl"] == 2 and line["blk"] == 1
assert line["to"] == 3
print("PASS: minutes and counting stats land in the right columns")

# --- the derived combos every prop tab depends on ---------------------
assert line["pra"] == 25 + 6 + 5, line.get("pra")
assert line["pr"] == 31 and line["pa"] == 30 and line["ra"] == 11
assert line["stocks"] == 3, line.get("stocks")
print("PASS: PRA / PR / PA / RA / stocks derive correctly")

# --- opponent context, which the vs-OPP tables key on -----------------
assert line["opp"] == "Away Team" and line["opp_id"] == "2", line
assert line["team"] == "Home Team"
opp_line = logs["201"]["games"][0]
assert opp_line["opp"] == "Home Team" and opp_line["opp_id"] == "1", opp_line
print("PASS: each side records the OTHER team as its opponent")

# --- and the guard that turned this into an outage --------------------
# The crawl deliberately raises when it parses nothing, which is right.
# Pinned so nobody softens it into a warning: a WNBA build that parsed
# zero box scores must fail loudly, not ship an empty slate.
src = (ROOT / "wnba_precompute.py").read_text()
assert "parsed ZERO box" in src, (
    "the zero-box-scores RuntimeError is the last line of defence here")
print("PASS: the zero-box-scores guard is still in place")

print("\nOK: the box score parser works on a real-shaped payload")
