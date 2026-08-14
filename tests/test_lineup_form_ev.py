"""Form and AvgEV on the Game Card lineup table.

BOTH NUMBERS ALREADY EXISTED. rank_batters has attached `form` to every
rated bat since the HR Edge board wanted it, and AvgEV has been in the
batted-ball profile the lineup table already reads. Neither was rendered
on the lineup, so the only place to see either was a board that publishes
once a day — on a page that recomputes both live, for the game in front
of you, hours earlier.

Wiring, then, not new maths. What this file guards is the part of wiring
that breaks quietly:

  1. The columns are actually IN the row the table is built from. A
     column nobody renders is not a feature (rule 20).
  2. Form does NOT read the Window control, and AvgEV DOES. That split
     is the whole design and it is invisible in the output — a Form
     column silently wired to the window would look completely normal
     and be a different quantity than the caption claims.
  3. Both print at one decimal through the REAL formatters, on both
     boards. Rule 11: this renders the actual dicts the views build
     rather than grepping for the strings.
  4. The page says out loud that Form ignores the Window.
"""
import io
import re
import sys
import textwrap
import tokenize
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

# Column headers come from the component, never retyped here. A test
# that spells out the names it is guarding goes green after a rename
# while asserting nothing about the shipped table.
import types as _types
sys.modules.setdefault("streamlit", _types.ModuleType("streamlit"))
from engines.form import FORM_COLUMNS  # noqa: E402

GC = (ROOT / "app" / "views" / "GameCard.py").read_text()
HRE = (ROOT / "app" / "views" / "HR_Edge_Board.py").read_text()

failures = []


def check(cond, msg):
    if cond:
        print(f"PASS: {msg}")
    else:
        failures.append(msg)
        print(f"FAIL: {msg}")


def strip_comments(src: str) -> str:
    """Blank comments, preserving offsets.

    Rule 26 — a comment is not a command. Every assertion below that
    looks at source has to run on this, because this repo puts a
    paragraph of prose above every tricky line and the words "Form" and
    "AvgEV" now appear in a dozen of them.
    """
    chars = list(src)
    starts, pos = [0], 0
    for ln in src.splitlines(keepends=True):
        pos += len(ln)
        starts.append(pos)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            (r1, c1), (r2, c2) = tok.start, tok.end
            for i in range(starts[r1 - 1] + c1, starts[r2 - 1] + c2):
                chars[i] = " "
    except (tokenize.TokenError, IndentationError):
        return src
    return "".join(chars)


GC_CODE = strip_comments(GC)
HRE_CODE = strip_comments(HRE)


# ------------------------------------------------------------------ 1
# The columns exist in the row builder, and each pulls from the right
# place: AvgEV out of the windowed `profile`, Form out of the row.
check('"AvgEV": profile.get("AvgEV")' in GC_CODE,
      "the lineup row reads AvgEV from the windowed profile bundle")
check("**(form_deltas or {})" in GC_CODE,
      "the lineup row spreads whatever engines/form measures, so a third "
      "input cannot be added there and silently missed here")
check("form_engine.FORM_COLUMNS" in GC_CODE,
      "Form columns are fed from the ranked row by the component's own "
      "header list, not by names retyped in the view")

# rank_batters must actually produce it, or the line above reads a key
# that is never written and the column is silently empty forever.
TP = (ROOT / "app" / "engines" / "top_plays.py").read_text()
check("**_form_deltas_for(b)" in strip_comments(TP),
      "rank_batters attaches the real deltas, so the lineup has something "
      "to read")
check('"avg_ev"' in strip_comments(TP),
      "rank_batters attaches avg_ev, keeping the HR Edge board's source")


# ------------------------------------------------------------------ 2
# THE WINDOW SPLIT — the assertion this file exists for.
#
# Pull the sort handler map out of the view and check what each of the
# two new keys reads. AvgEV must go through windowed_profile_cache
# (it sits beside EV90 and the two are read against each other); Form
# must NOT, because hr_form measures FORM_WINDOW against season and a
# windowed lookup would sort by a different quantity than the column
# shows, with nothing on screen to reveal it.
_km = re.search(r"sort_key_map = \{(.*?)\n                \}", GC_CODE, re.S)
check(_km is not None, "the sort handler map is still findable")
if _km:
    body = _km.group(1)
    handlers = dict(re.findall(r'"([^"]+)": (lambda r: [^\n]+)', body))

    for _fc in FORM_COLUMNS:
        check(_fc in handlers,
              f"{_fc} has a sort handler (a missing one is a KeyError)")
        check("windowed_profile_cache" not in handlers.get(_fc, ""),
              f"{_fc} does NOT sort off the window cache \u2014 it is a "
              f"comparison between two windows and pinning it to one would "
              f"compare a window with itself")
        check(f'r.get("{_fc}")' in handlers.get(_fc, ""),
              f"{_fc} sorts off the same value the column displays")
    check("AvgEV" in handlers, "AvgEV has a sort handler")
    check("windowed_profile_cache" in handlers.get("AvgEV", ""),
          "AvgEV DOES follow the window, like the EV90 it sits next to")

# Both must be offered in the dropdown, or the handlers are unreachable.
_opts = re.findall(r'"([^"]+)"',
                   re.search(r'"Sort by", \[(.*?)\],\s*\n\s*key=', GC_CODE, re.S).group(1))
for _c in (*FORM_COLUMNS, "AvgEV"):
    check(_c in _opts, f'"{_c}" is selectable in the Sort by control')


# ------------------------------------------------------------------ 3
# PRECISION, THROUGH THE REAL FORMATTERS.
#
# Not a grep for "{:.1f}". Both views' format dicts are lifted out,
# evaluated with the cell renderers stubbed, and applied to a frame
# holding the values a hitter actually produces. 89.3 must print as
# 89.3 — the failure this catches is 89.30, which is what the precision
# FLOOR gives an unlisted column and is therefore invisible to any test
# that only checks "no six decimals".
_stub_ns = {
    "score_bar": lambda *a, **k: (lambda v: str(v)),
    "bats_chip": lambda *a, **k: (lambda v: str(v)),
    "team_logo_cell": lambda *a, **k: (lambda v: str(v)),
}

from styles.table_style import _base_styler, stat_formats  # noqa: E402


def rendered(fmt_arg, frame):
    return _base_styler(frame).format(fmt_arg, na_rep="N/A").to_html()


# -- Game Card lineup ------------------------------------------------
_i = GC_CODE.index("styled = styled.format({")
_j = GC_CODE.index("}, na_rep=", _i) + 1
_gc_dict = eval(textwrap.dedent(GC_CODE[_i + len("styled = styled.format("):_j]), dict(_stub_ns))

_lineup = pd.DataFrame([{"AvgEV": 89.3, "ΔEV": 1.8, "ΔHH%": -6.9,
                          "EV90": 104.2}])
_html = rendered({k: v for k, v in _gc_dict.items() if k in _lineup.columns}, _lineup)
check(">89.3<" in _html and ">89.30<" not in _html,
      "lineup AvgEV prints 89.3, not 89.30")
# SIGNED. A delta column without a sign is unreadable — "1.8" does not
# say which way he moved — and this is the only place on the table where
# that is true, so it is the only place it can be forgotten.
check(">+1.8<" in _html, "a positive lineup delta prints its + sign")
check(">-6.9<" in _html, "a negative lineup delta keeps its - sign")

# -- HR Edge board ---------------------------------------------------
# Same two columns, same numbers, and they must agree: a hitter's AvgEV
# reading 89.3 on his game card and 89.30 on the board is one number
# rendered two ways, which is exactly the drift STAT_FORMATS exists to
# stop (rule 21 — parity is structural, not remembered).
#
# THE ARGUMENT IS EVALUATED WHOLE, whatever shape it has.
#
# The first version of this pinned the shape — it searched for the
# literal "stat_formats(df, extra={". Reverting the board to a
# hand-written dict then made this file CRASH on a missing substring
# rather than report a failure, which in CI is a red run for the wrong
# reason and, in a suite of plain scripts, a stack trace nobody reads as
# "AvgEV is printing 89.30 again". Grabbing the whole argument and
# evaluating it means either shape runs, and the assertion is about what
# actually reaches the reader.
_board = pd.DataFrame([{"AvgEV": 89.3, "ΔEV": 1.8, "ΔHH%": -6.9,
                         "PA": 543.0, "Clears%": 0.6789}])
_hi = HRE_CODE.index(".format(", HRE_CODE.index("style_stat_table("))
_open = HRE_CODE.index("(", _hi)
_depth, _close = 0, _open
for _k in range(_open, len(HRE_CODE)):
    if HRE_CODE[_k] in "([{":
        _depth += 1
    elif HRE_CODE[_k] in ")]}":
        _depth -= 1
        if _depth == 0:
            _close = _k
            break
_arg = HRE_CODE[_open + 1:_close].rsplit(", na_rep=", 1)[0]
_hre_fmt = eval(textwrap.dedent(_arg),
                dict(_stub_ns, stat_formats=stat_formats, df=_board))

_html = rendered({k: v for k, v in _hre_fmt.items() if k in _board.columns}, _board)
check(">89.3<" in _html and ">89.30<" not in _html,
      "HR Edge AvgEV prints 89.3, not 89.30")
check(">+1.8<" in _html and ">-6.9<" in _html,
      "HR Edge deltas print signed, at one decimal")
check(">543<" in _html, "the PA fix from the last batch still holds")
check("543.000000" not in _html, "and no column falls to six decimals")


# ------------------------------------------------------------------ 4
# Colour must be a VERDICT, not a rank among whoever is on screen.
#
# _magnitude_column falls back to colouring a column against its own min
# and max when the header has no entry in stat_scales. On a nine-row
# lineup that makes the coldest of nine hitters look cold in absolute
# terms even if all nine are hot, and the tier flips when you change the
# Bats filter without any number moving.
from styles.stat_scales import has_scale  # noqa: E402

for _c in ("AvgEV", *FORM_COLUMNS):
    check(has_scale(_c),
          f"{_c} has absolute cut points, so its colour means the same thing "
          f"on the lineup and on the HR Edge board")


# ------------------------------------------------------------------ 5
# The exception is disclosed.
#
# Every other column on that table moves with the Window control. A
# reader who sets Window to Last 5 and watches one column sit still has
# to be told why, or the honest design reads as a stale cell. Asserted
# as a property — some caption in the lineup card names both Form and
# the Window — not as the spelling of the sentence.
_card = GC_CODE[GC_CODE.index('with card("lineup"):'):]
_card = _card[:_card.index("Weak spot vs this lineup")]
_captions = re.findall(r"st\.caption\((.*?)\n                    \)", _card, re.S)
check(any("FORM_COLUMNS" in c and "Window" in c for c in _captions),
      "the lineup card tells the reader that the Form deltas do not follow "
      "the Window")

# And the window it DOES use is named from the engine, not retyped.
check("form_engine.FORM_WINDOW" in GC_CODE,
      "the caption reads the window off the component rather than hardcoding 15")

# THE COMPONENT ITSELF IS RENDERED, not just its columns. A shared
# renderer nobody calls is the "computed field nobody renders" defect
# (rule 20) one level up: the definition would live in one place and the
# only thing on screen would be a table nobody could check.
check("form_engine.render_form(" in GC_CODE,
      "the Game Card draws the Form component, not only its columns")


print()
if failures:
    print(f"FAILED {len(failures)} check(s):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All lineup Form/AvgEV checks passed.")
