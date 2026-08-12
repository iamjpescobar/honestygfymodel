"""Guards how numbers print.

THE DEFECT THIS EXISTS FOR, stated exactly:

pandas' `Styler.format()` does not merge with an earlier `format()` call.
It REPLACES the display function for every column in its subset, and with
no subset that means every column in the frame. `_base_styler` calls
`.format(precision=2, na_rep="—")` first; any caller that then adds its
own `.format({...})` — even for two logo columns — silently strips that
precision and that na_rep from every OTHER column.

The two symptoms are separate and both shipped to production:

  * precision — an unlisted numeric column falls back to
    `styler.format.precision`, whose pandas default is SIX. PA rendered
    as "543.000000" on the HR Edge board. The same cause is recorded in
    Strikeout_Board.py as "10.370000".
  * na_rep — a `format()` call that omits na_rep resets it to None for
    every column, and pandas prints a missing value as the literal
    string "nan". That is precisely what the em dash exists to prevent,
    and this app's honesty convention (None, never a fabricated 0) makes
    missing values COMMON rather than exceptional.

Rule 11: these assert the PROPERTY — a number renders at its published
precision, a missing value renders as text — not the spelling of any
particular line.
"""
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from styles.table_style import (           # noqa: E402
    STAT_FORMATS, stat_formats, _base_styler, _norm_stat,
)

failures = []


def check(cond, msg):
    if cond:
        print(f"PASS: {msg}")
    else:
        failures.append(msg)
        print(f"FAIL: {msg}")


# ---------------------------------------------------------------- 1
# The precision FLOOR is in effect. Importing table_style must have set
# it — if a pandas upgrade renames the option, this is where it surfaces,
# rather than as six decimals on a live board.
check(pd.get_option("styler.format.precision") == 2,
      "styler.format.precision is 2, not pandas' default of 6")

# And it must survive the exact call shape that caused the bug: a base
# styler, then a second format() naming only ONE column.
_df = pd.DataFrame({"PA": [543.0], "Clears%": [0.6789]})
_html = _base_styler(_df).format({"Clears%": "{:.2f}"}, na_rep="N/A").to_html()
check("543.000000" not in _html,
      "an unlisted numeric column does not fall through to six decimals")
check("543.00" in _html,
      "an unlisted numeric column lands on the precision floor instead")


# ---------------------------------------------------------------- 2
# stat_formats only ever touches NUMERIC columns.
#
# Load-bearing: several views build their frames with the numbers already
# formatted into strings, and handing "{:.3f}" a str raises ValueError at
# render time — a blank page, not a wrong decimal. See Pitchers_To_Target.
_mixed = pd.DataFrame({"BA": ["0.250"], "SLG": [0.512], "Player": ["x"]})
_fmts = stat_formats(_mixed)
check("BA" not in _fmts,
      "stat_formats skips a stat column that holds pre-formatted strings")
check(_fmts.get("SLG") == "{:.3f}",
      "stat_formats formats a real numeric stat column")
check("Player" not in _fmts,
      "stat_formats leaves text columns alone")

# It must not raise on the string frame it just declined to format.
try:
    _mixed.style.format(stat_formats(_mixed), na_rep="\u2014").to_html()
    check(True, "a frame of pre-formatted strings renders without ValueError")
except Exception as exc:                                  # pragma: no cover
    check(False, f"pre-formatted string frame raised: {exc}")


# ---------------------------------------------------------------- 3
# A caller's own formatter always wins over the map — logo cells and
# score bars live in the same dict as the precisions.
_over = stat_formats(pd.DataFrame({"SLG": [0.5]}), extra={"SLG": "BAR"})
check(_over["SLG"] == "BAR", "the caller's own formatter overrides the map")


# ---------------------------------------------------------------- 4
# The map agrees with itself on the classes of stat the app publishes.
_THREE_DP = ["BA", "SLG", "ISO", "xwOBA", "xSLG"]
_COUNTS = ["PA", "AB", "HR", "G", "GP"]
for _c in _THREE_DP:
    check(STAT_FORMATS.get(_norm_stat(_c)) == "{:.3f}",
          f"{_c} is a .000-scale rate and carries three decimals")
for _c in _COUNTS:
    check(STAT_FORMATS.get(_norm_stat(_c)) == "{:.0f}",
          f"{_c} is a count and carries no decimal point")

# Spellings that actually differ across this app must collapse to one
# entry — "Brl%" on the lineup card, "Brl %" on the bullpen arsenal one.
check(_norm_stat("Brl %") == _norm_stat("BRL%") == "BRL%",
      "column headers match the map regardless of spacing or case")


# ---------------------------------------------------------------- 5
# EVERY Styler.format(dict) in the views passes na_rep.
#
# Static, because the alternative is rendering every page. A missing
# na_rep is invisible until the day a cell is empty, which on a board
# built from optional Statcast samples is any day at all.
#
# COMMENTS ARE BLANKED FIRST, and that is not tidiness — the first draft
# of this check passed after the kwarg was deleted, because the
# explanatory comment above the call still contained the word "na_rep".
# Rule 26: a comment is not a command. Blanking is done with `tokenize`
# rather than a regex on "#", because the views are full of hex colours
# in string literals and cutting one short would unbalance the paren
# walk below. Offsets are preserved so reported line numbers stay true.
import io          # noqa: E402
import tokenize    # noqa: E402


def _strip_comments(src: str) -> str:
    chars = list(src)
    line_starts, pos = [0], 0
    for ln in src.splitlines(keepends=True):
        pos += len(ln)
        line_starts.append(pos)
    try:
        toks = tokenize.generate_tokens(io.StringIO(src).readline)
        for tok in toks:
            if tok.type != tokenize.COMMENT:
                continue
            (r1, c1), (r2, c2) = tok.start, tok.end
            for i in range(line_starts[r1 - 1] + c1, line_starts[r2 - 1] + c2):
                chars[i] = " "
    except (tokenize.TokenError, IndentationError):
        # A file that won't tokenize is a different failure entirely and
        # the import tests will say so; don't mask it by returning junk.
        return src
    return "".join(chars)


_views = sorted((ROOT / "app" / "views").glob("*.py"))
_missing = []
for _p in _views:
    _text = _strip_comments(_p.read_text())
    for _m in re.finditer(r"\.format\(\s*[\{s]", _text):
        # Walk to the closing paren of this format( call.
        _i = _text.index("(", _m.start())
        _depth, _j = 0, _i
        for _j in range(_i, len(_text)):
            if _text[_j] in "([{":
                _depth += 1
            elif _text[_j] in ")]}":
                _depth -= 1
                if _depth == 0:
                    break
        if "na_rep=" not in _text[_i:_j + 1]:
            _missing.append(f"{_p.name}:{_text[:_m.start()].count(chr(10)) + 1}")
check(not _missing,
      f"every Styler.format() in views passes na_rep (missing: {_missing})")


print()
if failures:
    print(f"FAILED {len(failures)} check(s):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"All number-format checks passed ({len(_views)} views scanned).")
