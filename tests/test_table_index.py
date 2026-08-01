"""A throwaway index must never be rendered in a wide table.

st.dataframe PINS the index column. When that index is a meaningless
0,1,2 RangeIndex it adds nothing, and a frozen column smears against
momentum scrolling in iOS Safari while the stats scroll underneath it.
That was fixed across the MLB tables and the WNBA lineup table was
missed — it kept rendering a numbered column nobody needs.

The flip side is equally important: a df built with set_index() has an
index that IS data (a player name, a split label), and hiding THAT
deletes the only thing identifying each row. Blanket-hiding every index
is how the pitcher Splits tables lost their Overall / vs RHB / vs LHB
labels. So this checks both directions.
"""
import re
from pathlib import Path

VIEWS = Path(__file__).resolve().parent.parent / "app" / "views"

missing, wrongly_hidden = [], []
for view in sorted(VIEWS.glob("*.py")):
    lines = view.read_text().split("\n")
    for i, ln in enumerate(lines):
        if "st.dataframe(" not in ln:
            continue
        call = "\n".join(lines[i:i + 15])
        # Look back for how this frame was built.
        context = "\n".join(lines[max(0, i - 18):i + 15])
        meaningful = bool(re.search(r"set_index\(|\.T\b|index\s*=\s*\[", context))
        hidden = "hide_index" in call

        if meaningful and hidden:
            wrongly_hidden.append(
                f"{view.name}:{i+1} hides an index that carries data "
                f"(set_index/.T/index=) — that index is the row label")
        if not meaningful and not hidden:
            missing.append(
                f"{view.name}:{i+1} renders a throwaway RangeIndex as a "
                f"pinned column — it identifies nothing and smears when "
                f"the table is scrolled sideways on a phone")

assert not wrongly_hidden, (
    "tables hiding an index that IS the data:\n  " + "\n  ".join(wrongly_hidden))
assert not missing, (
    "tables rendering a meaningless pinned index column:\n  " + "\n  ".join(missing))
print("PASS: every table hides a throwaway index and keeps a meaningful one")
