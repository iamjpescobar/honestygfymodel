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
for use in ('_labels[st.session_state["gc_selected_game_idx"]]',
            'games[st.session_state["gc_selected_game_idx"]]'):
    assert GC.index(use) > _clamp, (
        f"{use} is read BEFORE the clamp — the clamp has to happen first or "
        f"it protects nothing")
print("PASS: GameCard clamps the stored game index before using it")

# The page index was already clamped; both must stay that way.
assert 'st.session_state["gc_page"] = min(' in GC
print("PASS: GameCard clamps the stored page index too")

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
