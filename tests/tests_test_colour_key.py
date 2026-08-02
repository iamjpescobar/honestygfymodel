"""Any table that colour-codes values must say what the colours mean.

Five filled tiers look authoritative whether or not the reader knows the
scale. Worse, the DIRECTION flips between boards: on Pitchers to Target
gold means "target this arm", which is the opposite of what gold means on
Daily 13. A colour-coded table with no key invites someone to read a
grade backwards and bet on it.

This fails if a view renders tier-coloured bars without a legend beside
them.
"""
from pathlib import Path

VIEWS = Path(__file__).resolve().parent.parent / "app" / "views"

missing = []
for view in sorted(VIEWS.glob("*.py")):
    src = view.read_text()
    code = "\n".join(l.split("#")[0] for l in src.split("\n"))
    if "score_bar(" not in code:
        continue
    if "tier_legend(" not in code:
        missing.append(view.name)

assert not missing, (
    "these views render tier-coloured bars with no colour key: "
    + ", ".join(missing)
    + ". Colour without a legend is a guess, and the direction that counts "
      "as 'good' is not the same on every board.")
print(f"PASS: every board with tier-coloured bars carries a colour key")

# The key must state DIRECTION, not just list swatches — that's the part
# that stops a pitcher board being read like a batter board.
for view in sorted(VIEWS.glob("*.py")):
    src = view.read_text()
    if "tier_legend(" not in src:
        continue
    call = src[src.index("tier_legend("):]
    call = call[:call.index(")") + 1]
    assert "favor_note" in call, (
        f"{view.name} shows a colour key without saying which direction is "
        f"good. On a pitcher board gold means the opposite of what it means "
        f"on a batter board, and the swatches alone don't carry that.")
print("PASS: every colour key states which direction is favourable")

# And the tiers themselves must stay mutually distinguishable.
import sys, types
st = types.ModuleType("streamlit")
st.cache_data = lambda **kw: (lambda f: f)
sys.modules["streamlit"] = st
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from styles.table_style import _TIERS  # noqa: E402

cols = [c for _u, c, _l in _TIERS if c]
def _rgb(h):
    return tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
worst = None
for i in range(len(cols)):
    for j in range(i + 1, len(cols)):
        d = sum((a - b) ** 2 for a, b in zip(_rgb(cols[i]), _rgb(cols[j]))) ** 0.5
        if worst is None or d < worst[0]:
            worst = (d, cols[i], cols[j])
assert worst[0] > 90, (
    f"tiers {worst[1]} and {worst[2]} are only {worst[0]:.0f} apart in RGB — "
    f"below ~90 two tiers start reading as the same colour, which is the "
    f"collision the discrete tiers exist to prevent")
print(f"PASS: closest two tiers are {worst[0]:.0f} apart, all distinguishable")
