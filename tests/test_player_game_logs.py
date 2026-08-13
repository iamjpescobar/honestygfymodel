"""The per-game stat lines behind the Research page.

WHAT THIS TABLE IS FOR: the page lets the reader move a threshold live
(1+ hit, 2+ hits, 2+ total bases) and see the rate over L5/L10/L20. That
only works if the nightly stores GAME LINES rather than pre-baked rates
— bake a threshold in and the page can only ask the question this file
decided to ask.

Two things it deliberately does NOT contain, both asked for and both
omitted rather than approximated:

  RUNS  are not recoverable from a pitch feed. Nothing in these rows
        says whether the batter later crossed the plate; only a home run
        is self-evident. A runs column built by inference would be the
        most convincing wrong number on the page.

  RBIs  need bat_score and post_bat_score, which ENGINE_COLS does not
        carry. The delta on a PA-ending pitch IS the RBI count, so this
        is a two-column addition plus a re-pull — not impossible, just
        not available from the parquets on disk today.
"""
import sys, types, tempfile
from pathlib import Path
import pandas as pd

pd.DataFrame.to_parquet = lambda self, path, **kw: self.to_pickle(str(path))
pd.read_parquet = lambda path, **kw: pd.read_pickle(str(path))
_pb = types.ModuleType("pybaseball")
_pb.statcast = lambda *a, **k: None
sys.modules["pybaseball"] = _pb
sys.path.insert(0, ".")
import precompute  # noqa: E402

tmp = Path(tempfile.mkdtemp())
precompute.DATA_DIR = tmp

BAT = 101


def pa(date, event, batter=BAT):
    """One plate-appearance-ending row."""
    return {"batter": batter, "game_date": date, "events": event}


def pitch(date, batter=BAT):
    """A mid-PA pitch — events is null, so it must NOT count as a PA."""
    return {"batter": batter, "game_date": date, "events": None}


rows = [
    # 2026-08-01: single, double, home run, strikeout, plus stray pitches
    pa("2026-08-01", "single"), pa("2026-08-01", "double"),
    pa("2026-08-01", "home_run"), pa("2026-08-01", "strikeout"),
    pitch("2026-08-01"), pitch("2026-08-01"), pitch("2026-08-01"),
    # 2026-08-02: triple and a strikeout_double_play
    pa("2026-08-02", "triple"), pa("2026-08-02", "strikeout_double_play"),
    # 2026-08-03: went 0-for-3, all outs — a real game line of zeros
    pa("2026-08-03", "field_out"), pa("2026-08-03", "field_out"),
    pa("2026-08-03", "field_out"),
    # 2026-08-04: CAME TO THE PLATE, NEVER FINISHED ONE.
    #
    # Real and not rare: the inning ends mid-count on a caught stealing,
    # so he has pitches and no PA. This is the case the pa > 0 filter
    # exists for — without it the game becomes a line of zeros and every
    # rate over "his last 10 games" counts it as a miss.
    pitch("2026-08-04"), pitch("2026-08-04"),
    # A second batter, so the groupby is actually exercised
    pa("2026-08-01", "single", batter=202),
]
assert precompute.build_player_game_logs(pd.DataFrame(rows))
out = pd.read_parquet(tmp / "player_game_logs.parquet")
g = out[out["batter"] == BAT].set_index("game_date")

# --- 1. Mid-PA pitches are not plate appearances ---------------------
assert g.at["2026-08-01", "pa"] == 4, g.at["2026-08-01", "pa"]
print("PASS: only PA-ending rows counted — three stray pitches ignored")

# --- 2. Hits and total bases ------------------------------------------
assert g.at["2026-08-01", "hits"] == 3
assert g.at["2026-08-01", "tb"] == 1 + 2 + 4, g.at["2026-08-01", "tb"]
assert g.at["2026-08-02", "tb"] == 3
print("PASS: hits and total bases weight singles/doubles/triples/HR correctly")

# --- 3. BOTH strikeout events count -----------------------------------
#
# strikeout_double_play is still a strikeout for the batter, and a prop
# that pays on strikeouts counts it. Dropping it would quietly
# understate every K rate on the page.
assert g.at["2026-08-01", "k"] == 1
assert g.at["2026-08-02", "k"] == 1, "strikeout_double_play was not counted"
print("PASS: strikeout_double_play counts as a strikeout")

# --- 4. AN 0-FOR IS A GAME LINE, NOT AN ABSENCE ------------------------
assert "2026-08-03" in g.index, "a hitless game vanished from the log"
assert g.at["2026-08-03", "hits"] == 0 and g.at["2026-08-03", "pa"] == 3
print("PASS: a 0-for-3 is stored as a real line of zeros")

# --- 5. A GAME HE DIDN'T PLAY IS ABSENT, NOT A ZERO --------------------
#
# The distinction the whole table rests on. A rate over 'last 10 games'
# must mean ten games he PLAYED. Counting a rest day as a miss punishes
# a hitter for sitting, which is the same missing-is-not-zero rule the
# xHR path had to relearn.
assert "2026-08-04" not in g.index, (
    "a game where he saw pitches but completed no plate appearance was "
    "written as a line of zeros — that is an absence, not an 0-for")
assert len(g) == 3, f"expected 3 game lines, got {len(g)}"
assert (out["pa"] > 0).all(), "a zero-PA row was written"
print("PASS: only games with a plate appearance produce a line")

# --- 6. Batters don't bleed into each other ---------------------------
assert out[out["batter"] == 202]["hits"].sum() == 1
assert len(out) == 4, out
print("PASS: lines are grouped per batter per date")

# --- 7. WHAT IS DELIBERATELY ABSENT ------------------------------------
for gone in ("runs", "rbi", "rbis", "hrr"):
    assert gone not in out.columns, (
        f"'{gone}' appeared — it cannot be computed from a pitch feed and "
        f"must not be approximated into existence")
print("PASS: no runs or RBI column invented from data that cannot support it")
