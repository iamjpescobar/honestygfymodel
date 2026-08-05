#!/usr/bin/env python3
"""Home pass: baseline tile, equal-height cards, section order.

Edits accumulate per file and the script verifies what landed ON DISK
before reporting success.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
buf = {}
applied = []


def edit(relpath, old, new, label):
    s = buf.get(relpath)
    if s is None:
        s = (ROOT / relpath).read_text()
    if old not in s:
        sys.exit(f"ANCHOR NOT FOUND ({label}) - nothing written.")
    if s.count(old) != 1:
        sys.exit(f"ANCHOR NOT UNIQUE ({label}) - nothing written.")
    buf[relpath] = s.replace(old, new, 1)
    applied.append(label)


H = "app/views/Home.py"

# ----------------------------------------------------------------------
# 1. Count what can actually be judged, not just what is winning.
# ----------------------------------------------------------------------
edit(H, '''    days_tracked = len({d for board in record.values() for d in board})
    tracked = [s for s in sums.values() if s.get("total")]
    beating = sum(1 for s in tracked if "beating" in (s.get("verdict") or ""))
''', '''    days_tracked = len({d for board in record.values() for d in board})
    tracked = [s for s in sums.values() if s.get("total")]

    # _edge_verdict answers one of five ways, and two of them mean "we
    # cannot tell yet" rather than any result. Splitting them here is
    # what lets the tile below say something true.
    def _verdict(s):
        return s.get("verdict") or ""

    measurable = [s for s in tracked
                  if "beating the league baseline" in _verdict(s)
                  or "below the league baseline" in _verdict(s)
                  or "no measurable edge" in _verdict(s)]
    beating = sum(1 for s in measurable if "beating" in _verdict(s))
    below = sum(1 for s in measurable if "below" in _verdict(s))
''', "track record: split measurable from unjudgeable")

# ----------------------------------------------------------------------
# 2. Red must mean losing, not "too early".
# ----------------------------------------------------------------------
edit(H, '''        # Coloured by what it actually says. `0/4` was rendered in plain
        # text, styled identically to a good number — the page's worst
        # figure and its best one looked the same. Honest reporting is
        # the point of this site; flat reporting is not the same thing.
        if not beating:
            _bl_color = COLOR["error"]
        elif beating == len(tracked):
            _bl_color = COLOR["accent"]
        else:
            _bl_color = COLOR["stat_high"]
        st.markdown(_tile("Beating baseline", f"{beating}/{len(tracked)}",
                          color=_bl_color),
                    unsafe_allow_html=True)''', '''        # RED MUST MEAN LOSING, NOT "TOO EARLY".
        #
        # Colouring by verdict was the right instinct and the wrong
        # denominator. `beating / len(tracked)` counted every board that
        # had graded a single pick, so a board _edge_verdict had already
        # refused to judge — "only 22 graded picks, far too few" — landed
        # in the same bucket as one measurably below the baseline, and
        # both painted red. With 227 picks spread over six boards that
        # produced a red 0/6 on the landing page, which is the site
        # calling itself a loser on evidence it had itself decided was
        # insufficient. That is the exact failure this whole engine was
        # written to avoid, reintroduced one layer up.
        #
        # Now the denominator is the boards that CAN be judged, and the
        # colour follows the verdicts rather than their absence: green
        # when every measurable board clears the bar, red only when one
        # is genuinely below it, amber for a real mixed picture, and
        # muted when nothing has enough data yet.
        if not measurable:
            _bl_color = COLOR["text_muted"]
            _bl_value = "\\u2014"
            _bl_sub = "no board has enough graded picks to judge yet"
        else:
            _bl_value = f"{beating}/{len(measurable)}"
            _plural = "" if len(measurable) == 1 else "s"
            _bl_sub = f"of {len(measurable)} board{_plural} with enough data"
            if beating == len(measurable):
                _bl_color = COLOR["accent"]
            elif below:
                _bl_color = COLOR["error"]
            elif beating:
                _bl_color = COLOR["stat_high"]
            else:
                _bl_color = COLOR["warn"]
        st.markdown(_tile("Beating baseline", _bl_value, sub=_bl_sub,
                          color=_bl_color),
                    unsafe_allow_html=True)''', "track record: tile colour and denominator")

# ----------------------------------------------------------------------
# 3. Cards in a row should end at the same height.
# ----------------------------------------------------------------------
edit(H, '''        "@media (prefers-reduced-motion: reduce) {"''', '''        # RAGGED ROWS. One board publishes ten picks and another
        # publishes one, so three cards in a row ended at three
        # different heights and the row read as a pile rather than a
        # row. Stretching each card to fill its column costs nothing and
        # gives the eye a line to follow. Both testids are matched
        # because Streamlit has renamed this element between versions
        # and a pinned upgrade should not silently undo the layout.
        "[data-testid='stColumn'], [data-testid='column'] {"
        "  display: flex; align-items: stretch; }"
        "[data-testid='stColumn'] > div, [data-testid='column'] > div {"
        "  width: 100%; }"
        "[class*='st-key-card_home_'] {"
        "  height: 100%; }"

        "@media (prefers-reduced-motion: reduce) {"''', "equal-height cards")

# ----------------------------------------------------------------------
# 4. The proof goes above the menu.
# ----------------------------------------------------------------------
edit(H, '''    st.markdown(_section_tag("Explore"), unsafe_allow_html=True)
    _render_explore()

    st.markdown(_section_tag("Track record"), unsafe_allow_html=True)
    _render_track_record(record)''', '''    # Track record before Explore, on purpose. Explore is a menu; the
    # graded record is the argument. A first-time reader was scrolling
    # past four navigation cards to reach the only thing on this page
    # that distinguishes the site from every other picks account.
    st.markdown(_section_tag("Track record"), unsafe_allow_html=True)
    _render_track_record(record)

    st.markdown(_section_tag("Explore"), unsafe_allow_html=True)
    _render_explore()''', "track record above explore")

for relpath, content in buf.items():
    (ROOT / relpath).write_text(content)
for label in applied:
    print(f"patched: {label}")

_h = (ROOT / H).read_text()
checks = {
    "measurable computed": "measurable = [s for s in tracked" in _h,
    "below computed": "below = sum(1 for s in measurable" in _h,
    "tile uses _bl_value": "_tile(\"Beating baseline\", _bl_value" in _h,
    "old denominator gone": "f\"{beating}/{len(tracked)}\"" not in _h,
    "equal-height css": "align-items: stretch" in _h,
    "track record first": (_h.index('_section_tag("Track record")')
                           < _h.index('_section_tag("Explore")')),
}
print()
for name, ok in checks.items():
    print(f"  {'OK  ' if ok else 'FAIL'} {name}")
print("done" if all(checks.values()) else "INCOMPLETE - tell Claude")
