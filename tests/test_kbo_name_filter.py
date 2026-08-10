"""The KBO probe's name filter rejects Korean UI text.

WHY THIS EXISTS

`kbo_probables_probe` v2 reported:

    VERDICT — NAMES ARE ON THE PAGE: 10 candidates near starter markers,
    server-rendered, no XHR. The KBO migration is unblocked.

It was not unblocked. The ten "names" were:

    기록이 됩니다 등록 라인업 선택 업데이트 전력 전력분석 전력비교 키플레이

— "is recorded", "will be", "register", "lineup", "select", "update",
"power", "power analysis", "power comparison", "key play". Every one is
UI vocabulary. Not one is a person.

That verdict was recorded as a real finding and had to be corrected in a
later session, which is the expensive kind of wrong: a probe that says
"no" costs a re-run, a probe that says "yes" costs everything built on
top of it.

TWO SEPARATE CAUSES, BOTH NOW FIXED, AND THIS FILE GUARDS THE SECOND.

  1. THE CORPUS. All ten came from inside <script> — a setPreview()
     function and a commented-out alert string. The probe now strips
     script and style blocks and counts only rendered content, which
     removes these ten at source. That fix is not mine and is not what
     this file tests.

  2. THE FILTER. `[가-힣]{2,4}` plus a hand-written stoplist. A stoplist
     cannot win: it needs the exact word to have been foreseen, and a
     page has more UI vocabulary than anyone will list. Rendered content
     has its own nav labels and table headers, so a loose filter would
     manufacture the same false positive again from a different corpus.

The filter is now structural: exactly three syllables, first syllable a
common Korean surname. Korean names are overwhelmingly surname + a
two-syllable given name, and Korean surnames are a small closed set.

PRECISION OVER RECALL, ON PURPOSE. This drops rare two- and
four-syllable names. For a probe that is the right trade — the question
is "are names present at all", and an invented name misdirects where a
missed one merely understates.

IT IS STILL A HEURISTIC. 이용자 ("user") is three syllables and starts
with the most common surname in Korea. No syllable-shape rule separates
that from a person, which is why the probe prints the accepted names
rather than only counting them, and why its verdict says to check them
against tonight's actual probables.
"""
import importlib.util
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
_spec = importlib.util.spec_from_file_location(
    "kbo_probables_probe", os.path.join(ROOT, "kbo_probables_probe.py"))
kp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kp)

failures = []


def check(label, ok):
    if ok:
        print(f"PASS: {label}")
    else:
        failures.append(label)


# ----------------------------------------------------------------------
# 1. THE EXACT TEN. This is the regression, pinned verbatim.
# ----------------------------------------------------------------------
V2_FALSE_POSITIVES = ["기록이", "됩니다", "등록", "라인업", "선택",
                      "업데이트", "전력", "전력분석", "전력비교", "키플레이"]

accepted = [w for w in V2_FALSE_POSITIVES if kp._looks_like_a_name(w)]
check(f"none of v2's ten UI words is read as a name (got {accepted or 'none'})",
      not accepted)

# 기록이 gets its own line because it is the one that survived the FIRST
# version of this filter. 기 is a real surname, so a surname check alone
# passed it — "record" plus a subject particle is three syllables
# starting with a genuine (if rare) surname. The rare tail was dropped
# for exactly this reason, and this assertion is why it stays dropped.
check("기록이 specifically is rejected (a noun plus a particle)",
      not kp._looks_like_a_name("기록이"))

# ----------------------------------------------------------------------
# 2. REAL NAMES STILL PASS. A filter that rejects everything would also
#    make the assertion above true, so the other direction has to be
#    checked or this test proves nothing.
# ----------------------------------------------------------------------
REAL_PITCHERS = ["류현진", "김광현", "양현종", "고우석", "원태인",
                 "박세웅", "안우진", "이의리", "문동주", "최원준", "정우영"]
missed = [n for n in REAL_PITCHERS if not kp._looks_like_a_name(n)]
check(f"every three-syllable KBO pitcher name is accepted (missed {missed or 'none'})",
      not missed)

# The documented recall cost, asserted so it is a KNOWN trade rather than
# a surprise. 곽빈 is two syllables. If someone widens the filter to
# catch it, this line fails and makes them read the precision argument
# above before deciding.
check("곽빈 (two syllables) is a KNOWN miss, not an accident",
      not kp._looks_like_a_name("곽빈"))

# ----------------------------------------------------------------------
# 3. THE STRUCTURE, not the spelling.
# ----------------------------------------------------------------------
check("a four-syllable UI compound is rejected",
      not kp._looks_like_a_name("전력분석"))
check("a two-syllable word is rejected",
      not kp._looks_like_a_name("등록"))
check("three syllables alone is not enough — the surname must be real",
      not kp._looks_like_a_name("라인업"))

# The stoplist is belt-and-braces and must stay SHORT. If it grows, the
# structural test is the thing to fix, not the list.
check("the UI stoplist has not become the filter (under 25 entries)",
      len(kp.UI_WORDS) < 25)
check("the surname set excludes the rare tail that caused the leak",
      not {"기", "반", "왕", "금", "옥", "육", "맹", "제", "모", "탁"}
      & kp.KOREAN_SURNAMES)
check("the surname set still holds the common ones",
      {"김", "이", "박", "최", "정", "강", "조", "윤"} <= kp.KOREAN_SURNAMES)

# ----------------------------------------------------------------------
# 4. THE PROBE STILL SHOWS ITS WORK.
#
# A count can be wrong in silence; a printed list cannot. Both the
# accepted names and the rejects have to reach the log, or the next
# reader cannot tell "the page has no names" from "the filter ate them"
# — which is the ambiguity that made this probe need three runs.
# ----------------------------------------------------------------------
src = open(os.path.join(ROOT, "kbo_probables_probe.py"), encoding="utf-8").read()
check("accepted names are printed, not just counted",
      "join(sorted(named)" in src)
check("rejected candidates are printed too",
      "rejected" in src and "rejected as UI text" in src)
# ASSERT THE DATA FLOW, NOT THE PRESENCE OF A LINE.
#
# This first checked only that a `re.sub(r"<script` call existed
# somewhere in the file. Setting `rendered = html` on the line above it
# left that call in place, doing nothing, and the assertion stayed
# green — the same failure as an earlier test in this repo that matched
# a workflow's COMMENT instead of its command. What matters is that
# `rendered` is BUILT from the substitution and that nothing downstream
# reads raw html.
import ast as _ast
_tree = _ast.parse(src)
_main = next((n for n in _tree.body
              if isinstance(n, _ast.FunctionDef) and n.name == "main"), None)
check("the probe has a main()", _main is not None)
if _main:
    _assigns = [n for n in _ast.walk(_main)
                if isinstance(n, _ast.Assign)
                and any(isinstance(t, _ast.Name) and t.id == "rendered"
                        for t in n.targets)]
    check("`rendered` is assigned at all", bool(_assigns))
    check("every `rendered` assignment strips markup (none is a bare alias)",
          _assigns and all(isinstance(a.value, _ast.Call) for a in _assigns))
    # And the windows/excerpt/chunk reads must not fall back to raw html.
    _reads_raw = [n for n in _ast.walk(_main)
                  if isinstance(n, _ast.Subscript)
                  and isinstance(n.value, _ast.Name) and n.value.id == "html"]
    check("nothing slices raw html after the strip", not _reads_raw)
    check("the marker scan runs over rendered content",
          're.finditer("\uc120\ubc1c", rendered)' in src)

if failures:
    print()
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(1)

print("\nTen UI words once read as an unblock. A count is not a finding.")
