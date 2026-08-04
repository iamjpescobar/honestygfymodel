#!/usr/bin/env python3
"""One-off cleanup for honestygfymodel. Run from the repo root:

    python3 cleanup.py          # apply
    python3 cleanup.py --check  # report only, change nothing

Three jobs, all of them enforcing rules the repo already states:

  1. Drop the dead `inject_kc_theme` import from 19 views. app.py calls
     it once per script run (app.py:109); no view has called it since
     that consolidation, so every one of those imports is dead weight.

  2. Move 4 hardcoded hex colours onto COLOR tokens (2 more are a
     deliberate fallback and are documented rather than changed). The style sweep
     left zero hardcoded font sizes but these six survived, and one of
     them (#3BB8FF) is COLOR["stat_high"] spelled out longhand. Worse,
     bvp.py:351 pulls two stops of a colour range from COLOR and
     hardcodes the third — a palette edit would move two and strand one.

  3. Remove the star from MLB's Player of the Day, so it matches WNBA's
     (which had its removed earlier). The escaped \\u2b50 form is why it
     was missed the first time.

The six warning triangles on "Not ranked / Not projected / Not rated"
expanders are deliberately LEFT ALONE: they mark genuinely excluded
rows, they are consistent across all five views that use them, and they
are the only cue that an expander holds exclusions.
"""
import pathlib
import re
import sys

CHECK = "--check" in sys.argv
ROOT = pathlib.Path(".")
changed, skipped = [], []


def edit(relpath, subs, note):
    p = ROOT / relpath
    if not p.exists():
        skipped.append(f"{relpath}: not found")
        return
    src = orig = p.read_text()
    for old, new in subs:
        n = src.count(old)
        if n != 1:
            skipped.append(f"{relpath}: expected 1 match, found {n} -> {old[:55]!r}")
            return
        src = src.replace(old, new)
    if src == orig:
        return
    if not CHECK:
        p.write_text(src)
    changed.append(f"{relpath}  ({note})")


# ---------------------------------------------------------------- 1
# Dead import. Handled textually per file because the import lines take
# four different shapes (single-line, parenthesised, leading, middle,
# trailing position in the name list).
for rel in sorted(pathlib.Path("app/views").glob("*.py")):
    src = rel.read_text()
    if "inject_kc_theme" not in src:
        continue
    if re.search(r"\binject_kc_theme\s*\(", src):
        skipped.append(f"{rel}: actually calls inject_kc_theme, left alone")
        continue
    new = src
    for pat in (r"inject_kc_theme,\s*\n(\s+)", r"inject_kc_theme,\s*", r",\s*inject_kc_theme"):
        cand = re.sub(pat, lambda m: m.group(1) if m.lastindex else "", new, count=1)
        if cand != new:
            new = cand
            break
    if new == src:
        skipped.append(f"{rel}: import shape not recognised, left alone")
        continue
    if not CHECK:
        rel.write_text(new)
    changed.append(f"{rel}  (dead import removed)")


# ---------------------------------------------------------------- 2
edit("app/engines/weather_icons.py", [
    ('_GREY = "#8fa3ad"\n_COLD = "#5aa9e6"',
     '# Icon strokes read from the palette like everything else, so a\n'
     '# theme change moves them too instead of leaving them behind.\n'
     '_GREY = COLOR["text_muted"]\n_COLD = COLOR["cold"]'),
], "icon colours -> tokens")

# trend_chart.py's two hexes are NOT touched. They look like the same
# violation, but they sit in an `except Exception` that runs exactly when
# importing from styles/ has failed — so reaching back into
# styles.kc_theme for COLOR there is the one thing guaranteed not to
# work. Tokenising them turns a chart that renders in fallback colours
# into a NameError. A comment is added instead so the next sweep leaves
# them alone.
edit("app/engines/trend_chart.py", [
    ('except Exception:      # styling import failing must never break a chart\n'
     '    _TIER_MISSED, _TIER_CLEARED = "#D6304A", "#3BB8FF"',
     'except Exception:      # styling import failing must never break a chart\n'
     '    # LITERALS ON PURPOSE - do not "fix" these into COLOR lookups.\n'
     '    #\n'
     '    # This branch runs precisely when importing from styles/ has failed.\n'
     '    # Reaching back into styles.kc_theme for COLOR here would be the one\n'
     '    # thing guaranteed not to work, and would turn a chart that renders\n'
     '    # in fallback colours into a NameError. They mirror COLOR["error"]\n'
     '    # and COLOR["stat_high"]; if the palette moves, update them by hand.\n'
     '    _TIER_MISSED, _TIER_CLEARED = "#D6304A", "#3BB8FF"'),
], "fallback literals documented, deliberately NOT tokenised")

edit("app/engines/bvp.py", [
    ('line_style = dict(color="#3a4a55", strokeWidth=1.5)',
     'line_style = dict(color=COLOR["border"], strokeWidth=1.5)'),
    ('range=[COLOR["gold"], COLOR["stat_high"], "#8a3a40"]),',
     '# Two stops came from COLOR and the third was hardcoded, so a\n'
     '                                        # palette edit moved two and stranded one.\n'
     '                                        range=[COLOR["gold"], COLOR["stat_high"],\n'
     '                                               COLOR["error"]]),'),
], "chart colours -> tokens")


# ---------------------------------------------------------------- 3
edit("app/views/Player_Of_The_Day.py", [
    ("card_open(f'\\u2b50 {pick[\"name\"]} \\u2014 {pick[\"team\"]}')",
     "card_open(f'{pick[\"name\"]} \\u2014 {pick[\"team\"]}')"),
], "star removed, now matches WNBA's Player of the Day")


print(("WOULD CHANGE" if CHECK else "CHANGED") + f": {len(changed)} file(s)")
for c in changed:
    print(f"  {c}")
if skipped:
    print(f"\nSKIPPED: {len(skipped)}")
    for s in skipped:
        print(f"  {s}")
