#!/usr/bin/env python3
"""Applies: cross-sport board cards on Home + the Home card restyle.

Exact-match replacements. If any anchor has moved, nothing is written.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
edits = []


def edit(relpath, old, new, label):
    p = ROOT / relpath
    s = p.read_text()
    if old not in s:
        sys.exit(f"ANCHOR NOT FOUND ({label}) in {relpath} - nothing written.")
    if s.count(old) != 1:
        sys.exit(f"ANCHOR NOT UNIQUE ({label}) in {relpath} - nothing written.")
    edits.append((p, s.replace(old, new, 1), label))


# ----------------------------------------------------------------------
# 1. app.py — consume a pending sport BEFORE the switcher widget exists.
# ----------------------------------------------------------------------
edit(
    "app/app.py",
    '''st.session_state.setdefault("lc_view", "home")

selected_sport = (''',
    '''st.session_state.setdefault("lc_view", "home")

# A HOME CARD CAN ASK FOR A SPORT CHANGE, and this is the only place it
# can be granted.
#
# sport_switcher() instantiates st.segmented_control(key="lc_sport_seg")
# further down this file, ABOVE the main column — so by the time
# views/Home.py runs, that widget already exists and Streamlit raises
# StreamlitAPIException on any write to its key. Writing lc_sport alone
# does not work either: selected_sport below prefers lc_sport_seg, so the
# widget wins and the click appears to do nothing.
#
# So Home writes an INTENT (lc_pending_sport) and reruns, and it is
# consumed here on the next pass, before the widget is created. Setting a
# widget key before its widget exists is legal and seeds the value.
# Popped rather than read so it fires exactly once.
_pending_sport = st.session_state.pop("lc_pending_sport", None)
if _pending_sport:
    st.session_state["lc_sport_seg"] = _pending_sport
    st.session_state["lc_sport"] = _pending_sport
    st.session_state["lc_view"] = "sport"

selected_sport = (''',
    "app.py pending-sport consumer",
)

# ----------------------------------------------------------------------
# 2. Home.py — a jump that changes sport.
# ----------------------------------------------------------------------
edit(
    "app/views/Home.py",
    '''# ----------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------''',
    '''def _goto_sport(sport, page_title, key, label):
    """Jump into a board that belongs to a DIFFERENT sport.

    Home cannot change sport directly — see the lc_pending_sport comment
    in app.py. It records the intent and reruns; app.py applies it at the
    top of the next pass, before the switcher widget is instantiated.

    The nav key is written here rather than there because it is
    per-sport, and this is the only place that knows which page was
    asked for.
    """
    if st.button(label, key=key, type="tertiary"):
        st.session_state["lc_pending_sport"] = sport
        if sport == "WNBA":
            st.session_state["lc_sub_WNBA"] = page_title
        else:
            st.session_state["lc_nav_radio"] = page_title
            st.session_state["lc_active_page"] = page_title
        st.rerun()


# ----------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------''',
    "Home.py _goto_sport",
)

# ----------------------------------------------------------------------
# 3. Home.py — render cross-sport boards as real, openable cards.
# ----------------------------------------------------------------------
OLD_OTHERS = '''    # ---- what the OTHER sport published, as rows rather than cards ----
    #
    # These are worth knowing about — the site published them today — but
    # they cannot be opened from here, and giving an unopenable board the
    # same card as a live one is the mistake the Explore grid used to
    # make with its "Select WNBA above" tiles.
    if others:
        # ONE markdown call for the whole block, not one per row.
        # Streamlit ships every st.markdown as its own element in the
        # delta, so a six-board night cost seven round-trips to draw what
        # is visually a single list.
        _sports = sorted({sp for sp, _b, _e in others})
        _where = " or ".join(_sports)
        _html = [
            f'<div style="color:{COLOR["text_muted"]}; '
            f'font-size:var(--lc-text-caption); font-weight:600; '
            f'padding:var(--lc-space-2xl) var(--lc-space-none) '
            f'var(--lc-space-sm);">Also published today \\u00b7 '
            f'<span style="color:{COLOR["text_faint"]}; font-weight:400;">'
            f'switch to {_where} above to open these</span></div>'
        ]
        for sport, board, entry in others:
            cfg = BOARDS.get(board, {})
            _n = len(entry.get("picks", []))
            _last = _last_night_score(board)
            _html.append(
                f'<div style="display:flex; align-items:baseline; '
                f'justify-content:space-between; gap:var(--lc-space-lg); '
                f'padding:var(--lc-space-sm) var(--lc-space-none); '
                f'border-bottom:1px solid {COLOR["border_soft"]};">'
                f'<span style="color:{COLOR["text"]};">'
                f'{cfg.get("label", board)}'
                f'<span style="color:{COLOR["text_faint"]}; '
                f'font-size:var(--lc-text-tiny); '
                f'margin-left:var(--lc-space-sm);">{sport}</span></span>'
                f'<span style="font-family:\\'JetBrains Mono\\',monospace; '
                f'font-size:var(--lc-text-tiny); color:{COLOR["text_faint"]};">'
                f'{_n} picks{"  " + _last if _last else ""}</span></div>')
        st.markdown("".join(_html), unsafe_allow_html=True)'''

NEW_OTHERS = '''    # ---- what the OTHER sports published, as cards you can open ----
    #
    # These were rows, not cards, for a good reason: they could not be
    # opened from here, and giving an unopenable board the same card as a
    # live one is the mistake the Explore grid used to make with its
    # "Select WNBA above" tiles. The fix was NOT to promote a dead end
    # back to a card — it was to stop it being a dead end. _goto_sport
    # carries the sport change through app.py, so one click now lands on
    # the board itself.
    #
    # They stay visually distinct all the same. A cross-sport card is
    # keyed card_home_other_* and edged in `cold` rather than `accent`,
    # so "published, elsewhere" reads differently from "published, here"
    # at a glance instead of on inspection. The colour is carrying the
    # fact, which is the same job the demotion to rows used to do.
    if others:
        _sports = sorted({sp for sp, _b, _e in others})
        _where = " and ".join(_sports)
        st.markdown(
            f'<div style="color:{COLOR["text_muted"]}; '
            f'font-size:var(--lc-text-caption); font-weight:600; '
            f'padding:var(--lc-space-2xl) var(--lc-space-none) '
            f'var(--lc-space-sm);">Also published today \\u00b7 '
            f'<span style="color:{COLOR["text_faint"]}; font-weight:400;">'
            f'{_where} \\u2014 opening one switches sport</span></div>',
            unsafe_allow_html=True,
        )
        _ocols = 2 if len(others) == 4 else max(1, min(len(others), 3))
        cols = st.columns(_ocols)
        for i, (sport, board, entry) in enumerate(others):
            cfg = BOARDS.get(board, {})
            picks = entry.get("picks", [])
            page = SPORT_BOARDS.get(sport, {}).get(board)
            with cols[i % _ocols]:
                with card(f"home_other_{board}"):
                    st.markdown(
                        f'<div class="lc-elsewhere">{sport}</div>',
                        unsafe_allow_html=True,
                    )
                    if page:
                        _goto_sport(sport, page, key=f"home_jump_{board}",
                                    label=f"{cfg.get('label', board)}  \\u2192")
                    else:
                        st.markdown(
                            f'<div style="font-weight:700; '
                            f'color:{COLOR["text"]};">'
                            f'{cfg.get("label", board)}</div>',
                            unsafe_allow_html=True,
                        )
                    _rows_html = "".join(_pick_row(p)
                                         for p in picks[:_PREVIEW_ROWS])
                    _extra = ""
                    if len(picks) > _PREVIEW_ROWS:
                        _extra = (f'<span style="color:{COLOR["text_faint"]};">'
                                  f'+{len(picks) - _PREVIEW_ROWS} more</span>')
                    _last = _last_night_score(board)
                    if _last or _extra:
                        _rows_html += (
                            f'<div style="display:flex; align-items:center; '
                            f'justify-content:space-between; '
                            f'gap:var(--lc-space-md); '
                            f'padding-top:var(--lc-space-sm); '
                            f'font-size:var(--lc-text-tiny); '
                            f'font-family:\\'JetBrains Mono\\',monospace;">'
                            f'{_extra}{_last}</div>')
                    st.markdown(_rows_html, unsafe_allow_html=True)'''

edit("app/views/Home.py", OLD_OTHERS, NEW_OTHERS, "Home.py cross-sport cards")

# ----------------------------------------------------------------------
# 4. Home.py — the cards get depth, a meaningful edge, and a sport badge.
# ----------------------------------------------------------------------
OLD_CSS = '''        "[class*='st-key-card_home_'] {"
        f"  background: {COLOR['surface']};"
        f"  border: 1px solid {COLOR['border']};"
        "  border-radius: var(--lc-radius-lg);"
        "  padding: var(--lc-space-lg) var(--lc-space-xl);"
        "  position: relative; overflow: hidden;"
        "  transition: border-color .18s ease, transform .18s ease; }"

        # A hairline of the accent along the top edge, revealed on hover.
        # Costs no layout (it is a pseudo-element), and it is the only
        # thing on the page that moves — the card tells you it is
        # clickable at the moment you are considering clicking it.
        "[class*='st-key-card_home_']::before {"
        "  content: ''; position: absolute; top: 0; left: 0; right: 0;"
        f"  height: 2px; background: {COLOR['accent']};"
        "  opacity: 0; transition: opacity .18s ease; }"
        "[class*='st-key-card_home_']:hover::before { opacity: 1; }"
        "[class*='st-key-card_home_']:hover {"
        f"  border-color: {COLOR['accent_border']};"
        "  transform: translateY(-1px); }"'''

NEW_CSS = '''        # THE EDGE CARRIES THE FACT.
        #
        # Every card declares its own --lc-edge, and that one variable
        # drives the top rule, the glow behind it and the hover border.
        # Cyan means "this sport, published today"; steel blue means
        # "published, but it lives under another sport". So the colour is
        # doing the work the old row-vs-card demotion did, without
        # stripping the content back to a line of text.
        #
        # The edge is now always visible rather than hover-only. A rule
        # that appears when you are already pointing at the card tells you
        # something you have found out; a rule that is there tells you
        # which cards are worth pointing at.
        "[class*='st-key-card_home_'] {"
        f"  --lc-edge: {COLOR['accent']};"
        f"  --lc-edge-dim: {COLOR['accent_dim']};"
        f"  --lc-edge-border: {COLOR['accent_border']};"
        f"  background: linear-gradient(158deg, {COLOR['surface_raised']} 0%,"
        f"    {COLOR['surface']} 62%);"
        f"  border: 1px solid {COLOR['border']};"
        "  border-radius: var(--lc-radius-lg);"
        "  padding: var(--lc-space-lg) var(--lc-space-xl);"
        "  position: relative; overflow: hidden;"
        "  box-shadow: 0 1px 2px rgba(0,0,0,.35);"
        "  transition: border-color .18s ease, transform .18s ease,"
        "    box-shadow .18s ease; }"

        "[class*='st-key-card_home_other_'] {"
        f"  --lc-edge: {COLOR['cold']};"
        f"  --lc-edge-dim: {COLOR['cold_dim']};"
        f"  --lc-edge-border: {COLOR['cold_border']}; }"

        # The rule itself, plus a short wash of the same colour bleeding
        # down from it. The wash is what stops the gradient reading as a
        # flat panel with a stripe glued on top.
        "[class*='st-key-card_home_']::before {"
        "  content: ''; position: absolute; top: 0; left: 0; right: 0;"
        "  height: 2px; background: var(--lc-edge);"
        "  opacity: .55; transition: opacity .18s ease; }"
        "[class*='st-key-card_home_']::after {"
        "  content: ''; position: absolute; top: 0; left: 0; right: 0;"
        "  height: 96px; pointer-events: none;"
        "  background: linear-gradient(180deg, var(--lc-edge-dim),"
        "    transparent 78%);"
        "  opacity: .7; transition: opacity .18s ease; }"
        "[class*='st-key-card_home_']:hover::before { opacity: 1; }"
        "[class*='st-key-card_home_']:hover::after { opacity: 1; }"
        "[class*='st-key-card_home_']:hover {"
        "  border-color: var(--lc-edge-border);"
        "  box-shadow: 0 6px 18px rgba(0,0,0,.45);"
        "  transform: translateY(-2px); }"

        # Keyboard users get the same signal mouse users do.
        "[class*='st-key-card_home_']:focus-within {"
        "  border-color: var(--lc-edge-border); }"
        "[class*='st-key-card_home_']:focus-within::before { opacity: 1; }"

        # The sport badge on a cross-sport card. Small, uppercase, tracked
        # out — it names the destination the card will take you to, which
        # is the one thing a reader needs before clicking something that
        # changes sport underneath them.
        ".lc-elsewhere {"
        "  display: inline-block; font-size: var(--lc-text-micro);"
        "  font-weight: 700; letter-spacing: .14em; text-transform: uppercase;"
        f"  color: {COLOR['cold']}; background: {COLOR['cold_dim']};"
        f"  border: 1px solid {COLOR['cold_border']};"
        "  border-radius: 999px; padding: .1rem .5rem;"
        "  margin-bottom: var(--lc-space-hair); }"'''

edit("app/views/Home.py", OLD_CSS, NEW_CSS, "Home.py card styling")

OLD_RM = '''        "@media (prefers-reduced-motion: reduce) {"
        "  .lc-live-dot { animation: none; }"
        "  [class*='st-key-card_home_'] { transition: none; }"
        "  [class*='st-key-card_home_']:hover { transform: none; } }"'''
NEW_RM = '''        "@media (prefers-reduced-motion: reduce) {"
        "  .lc-live-dot { animation: none; }"
        "  [class*='st-key-card_home_'] { transition: none; }"
        "  [class*='st-key-card_home_']:hover { transform: none; } }"

        # The lift and the shadow are the two things that cost paint on a
        # phone, and a stacked column of cards is where that is felt.
        "@media (hover: none) {"
        "  [class*='st-key-card_home_']:hover { transform: none;"
        "    box-shadow: 0 1px 2px rgba(0,0,0,.35); } }"'''
edit("app/views/Home.py", OLD_RM, NEW_RM, "Home.py touch-device guard")

for path, content, label in edits:
    path.write_text(content)
    print(f"patched: {label}")
print("done")
