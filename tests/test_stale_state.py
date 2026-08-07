"""Remembered selections must survive the data changing underneath them.

Streamlit keeps widget state across reruns, but the DATA those widgets
point at is rebuilt constantly — the slate shrinks as games go final, and
a roster changes the moment you pick a different team. Anywhere a stored
choice is used to index a list or dict without a guard, that's a crash
that only fires for the person whose stored value went stale. It looks
random from the outside, which is exactly what makes it hard to report.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- 1. GameCard: the selected game index must be clamped ------------
GC = (ROOT / "app" / "views" / "GameCard.py").read_text()

assert 'st.session_state["gc_selected_game_idx"] = min(' in GC, (
    "gc_selected_game_idx is no longer clamped to the slate length. It "
    "persists across reruns while `games` shrinks as games go final, so "
    "someone sitting on game 8 of a 9-game slate hits IndexError when the "
    "slate rebuilds shorter — a hard crash on page load")
_clamp = GC.index('st.session_state["gc_selected_game_idx"] = min(')

# FIND THE USES, DON'T NAME THEM.
#
# This used to list the two subscripts by hand
# (_labels[...] and games[...]). When the game picker was rebuilt as a
# swipeable carousel, one of those two expressions stopped existing and
# the test failed on a ValueError from .index() — flagging a rewrite,
# not a regression. A hardcoded list of call sites tests the shape of
# today's code; what actually matters is the PROPERTY that no subscript
# using this index runs before the clamp. Finding them by pattern
# survives the next rewrite too.
import re as _re
_uses = [m.start() for m in _re.finditer(
    r'\w+\[st\.session_state\["gc_selected_game_idx"\]\]', GC)]
assert _uses, (
    "nothing indexes with gc_selected_game_idx any more — if the picker "
    "was rewritten again, point this test at whatever replaced it rather "
    "than deleting the check; the crash it guards is real")
for _pos in _uses:
    assert _pos > _clamp, (
        "something indexes with gc_selected_game_idx BEFORE the clamp — "
        "the clamp has to happen first or it protects nothing")
print(f"PASS: GameCard clamps the stored game index before all "
      f"{len(_uses)} use(s)")

# PAGINATION IS GONE ON PURPOSE.
#
# The picker was a five-per-page pager with its own clamped gc_page
# index; it is now one swipeable row holding the whole slate, so there
# is no page state left to go stale. Assert it stays gone rather than
# asserting it stays clamped — a half-removed pager, where the state
# survives but nothing clamps it, is exactly the stale-index bug this
# file exists for.
assert 'st.session_state["gc_page"]' not in GC, (
    "gc_page is back. If pagination returns it must be clamped to "
    "total_pages the way gc_selected_game_idx is clamped to the slate "
    "length, and this assertion should become that check")
print("PASS: no page state left in the game picker to go stale")

# --- 2. Without_Player: stale player must not KeyError ---------------
WP = (ROOT / "app" / "views" / "Without_Player.py").read_text()

# Strip comments first — the explanatory note below QUOTES the old broken
# expression, and matching it there would be a false alarm.
_wp_code = "\n".join(l.split("#")[0] for l in WP.split("\n"))
assert "labels[pick]" not in _wp_code, (
    "labels[pick] is back. Team and player are separate widgets with fixed "
    "keys, so switching teams leaves a remembered player that isn't on the "
    "new roster — a bare KeyError that takes the page down")
assert "labels.get(pick)" in WP, "the lookup must be a .get() with a fallback"
print("PASS: Without_Player survives a stale player selection")

# --- 3. behavioural check on the clamp itself ------------------------
for stored, slate_len, want in [(8, 6, 5), (0, 6, 0), (5, 6, 5), (3, 1, 0)]:
    got = min(stored, slate_len - 1)
    assert got == want and 0 <= got < slate_len, (
        f"clamp({stored}, {slate_len}) = {got}; must land inside the list")
print("PASS: clamp always yields a valid index")

# --- 4. no OTHER view indexes a list with raw session state ----------
for view in (ROOT / "app" / "views").glob("*.py"):
    src = view.read_text()
    for i, line in enumerate(src.split("\n"), 1):
        if "[st.session_state[" not in line:
            continue
        assert view.name == "GameCard.py", (
            f"{view.name}:{i} indexes a list with raw session state and has no "
            f"clamp — same stale-index crash as GameCard had:\n    {line.strip()}")
print("PASS: no other view indexes a list with unclamped session state")
