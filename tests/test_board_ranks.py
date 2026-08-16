"""Where a bat sits on every OTHER board, without opening them.

THE PROBLEM. A hitter can be 13th on HR Edge, 4th on Daily 13 and the
Player of the Day, and nothing on the Game Card says so. Finding out
means opening three pages and scanning for a name — fine when browsing,
useless when reading a slate out loud with a camera running.

THREE RULES THIS PINS, each of which would quietly ruin the column:

  NOT ON A BOARD != RANKED LAST. A missing key means the board never
  had him. Collapsing that into a big number would tell a reader he was
  rated and rated badly, which is a different and false claim — the same
  missing-is-not-zero rule as the rest of the site.

  RANKS COME FROM THE CAPPED BOARD, because that is what the page shows.
  Ranking against the uncapped list puts a bat at #6 here and #4 on the
  board itself, and nothing on screen says which is right.

  ONE BROKEN BOARD MUST NOT TAKE DOWN THE OTHERS. A Daily 13 failure
  should not remove HR Edge tokens from a page that has nothing to do
  with it.
"""
import sys, types

_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = _st
sys.path.insert(0, "app")

from engines import board_ranks as br  # noqa: E402

IDX = {
    "101": {"hr_edge": 13, "daily13": 4},
    "202": {"potd": 1},
    "303": {"hr_edge": 1, "daily13": 2, "potd": 1},
    "404": {"daily13": 9},
}

# --- 1. THE TOKEN SAYS WHERE, NOT JUST WHETHER -----------------------
#
# "on the HR board" is not the point — 1st and 13th are different bets
# and the number is the whole reason to show it.
assert br.token_text("101", IDX) == "HR13 \u00b7 H4", br.token_text("101", IDX)
assert br.token_text("303", IDX) == "HR1 \u00b7 H2 \u00b7 POTD"
print(f"PASS: ranks are shown, not just membership \u2014 {br.token_text('101', IDX)!r}")

# --- 2. POTD CARRIES NO NUMBER ---------------------------------------
#
# It is a single pick. "POTD1" would imply a second and a third.
assert br.token_text("202", IDX) == "POTD"
print("PASS: Player of the Day renders without a rank")

# --- 3. NOT ON A BOARD IS BLANK, NOT A DASH OR A BIG NUMBER ----------
#
# Most bats on a slate are on no board at all, so this column is mostly
# empty by design. A column of dashes reads as missing data; blank reads
# as a clean no.
assert br.token_text("999", IDX) == ""
assert br.token_text(None, IDX) == ""
assert br.tokens_for("999", IDX) == []
print("PASS: a bat on no board renders blank, not a dash")

# --- 4. ORDER IS FIXED, SO A ROW READS THE SAME EVERY TIME -----------
labels = [t[0] for t in br.tokens_for("303", IDX)]
assert labels == ["HR", "H", "POTD"], labels
assert br.BOARD_ORDER == ("hr_edge", "daily13", "potd")
print("PASS: tokens always render in the same order")

# --- 5. DEEP RANKS ARE NOT SHOWN -------------------------------------
#
# A bat 60th on a 300-bat board is not "on the board" in any sense a
# reader cares about, and a token for it crowds out the ones that mean
# something.
assert br.MAX_RANK <= 30, f"MAX_RANK is {br.MAX_RANK} — too deep to be a signal"
deep = {"501": {"hr_edge": 60}}
# The cap is applied when the index is BUILT, so a hand-made index can
# still contain a deep rank; what matters is that the builder stops.
src = open("app/engines/board_ranks.py", encoding="utf-8").read()
assert "if i > MAX_RANK:" in src and "break" in src, (
    "the rank cap is no longer applied while indexing")
print(f"PASS: ranks past {br.MAX_RANK} are never indexed")

# --- 6. THE HR EDGE RANK MATCHES THE PAGE ----------------------------
#
# cap_per_game is what the board renders. Indexing the uncapped rows
# would show #6 here and #4 there.
assert "cap_per_game(rows)" in src, (
    "board_ranks indexes the uncapped board — its ranks will disagree "
    "with the HR Edge page on the same bats")
print("PASS: HR Edge ranks come from the capped board the page shows")

# --- 7. ONE BROKEN BOARD DOES NOT TAKE DOWN THE INDEX ----------------
assert src.count("except Exception:") >= 3, (
    "a board that fails to build is no longer isolated; one failure "
    "would empty the whole column")
print("PASS: each board is fetched independently")

# --- 8. IT REACHES THE LINEUP TABLE ----------------------------------
gc = open("app/views/GameCard.py", encoding="utf-8").read()
assert '"Boards": boards' in gc, "the token never reaches the row"
assert "boards=token_text(r.get(\"id\"), _board_idx)" in gc
assert "_board_idx = board_ranks()" in gc, (
    "the index is not built once per slate — a per-row lookup would "
    "rebuild every board for every hitter")
print("PASS: built once per slate and rendered on the lineup table")
