"""
app.py — Los Cappers entrypoint (unified right sidebar)

This file:
- Renders ONE persistent right-hand sidebar containing: the account card,
  the full page navigation (previously buried in the top-right "Menu"
  dropdown), the Glossary (previously inside the Game Card's own in-page
  sidebar — the only thing carried over from it), a Sign out button, and
  an admin section for admins.
- The Game Card no longer renders its own sidebar; pages get the full
  width of the main column.
- Never reassigns st.sidebar (doing so corrupts every st.cache_data
  write — see the hard rule below). The native sidebar is
  suppressed via the views/ folder name, config.toml, and CSS instead.
- Ensures admin pages and controls are only included when is_admin()
  returns True.
- Loads page modules by running their file when selected from the sidebar
  (plain runpy — no monkeypatching around it; see the hard rule below).
- Page files live in views/ (NOT pages/) on purpose: Streamlit auto-registers
  any pages/ folder as native multipage nav with public URL routes, which both
  drew its own left sidebar on the login screen and let visitors reach every
  page without authenticating. views/ is invisible to that convention.
"""
import runpy
import traceback
from pathlib import Path
import os

import streamlit as st

from styles.kc_theme import inject_kc_theme, sport_switcher, COLOR
from auth import require_login, is_admin

st.set_page_config(
    page_title="Los Cappers",
    page_icon="⚾",
    layout="wide"
)

# -------------------------
# Home-screen / standalone mobile tags
#
# Streamlit exposes no API for adding <head> tags: page_icon sets only the
# browser-tab favicon, st.markdown strips <link> and <meta>, and
# components.html runs in an iframe that cannot reach the parent document.
# So the tags are written directly into Streamlit's own index.html.
#
# This is a workaround, not a supported interface. It edits a file inside
# site-packages, which is rebuilt on every deploy here, so the patch is
# reapplied on each boot and disappears cleanly if it is ever removed.
# Everything is wrapped so that ANY failure — missing file, read-only
# filesystem, a Streamlit release that restructures index.html — leaves the
# app running exactly as before. A cosmetic icon must never take the site
# down.
#
# Note it takes effect from the NEXT page load: the browser has already
# fetched index.html by the time this script first runs, and may cache it.
# After deploying, refresh once, then re-add to the home screen.
# -------------------------
def _install_mobile_head_tags():
    import streamlit as _st

    icon_path = Path(__file__).parent / "static" / "loscappers-icon-180.png"
    index_path = Path(_st.__file__).parent / "static" / "index.html"
    marker = "<!--lc-mobile-tags-->"

    if not icon_path.exists() or not index_path.exists():
        return
    html = index_path.read_text(encoding="utf-8")
    if marker in html:
        return  # already patched this boot

    # A REAL URL, not a data: URI.
    #
    # The first version of this embedded the PNG as base64 straight into
    # the tag. That renders fine in a browser tab but iOS Safari IGNORES
    # a data: URI for apple-touch-icon — it silently falls back to the
    # letter tile, which is exactly what it did. The icon has to be
    # fetchable, so app/.streamlit/config.toml turns on Streamlit's
    # static serving and this points at the served path.
    icon_url = "/app/static/loscappers-icon-180.png"
    tags = (
        f'{marker}'
        f'<link rel="apple-touch-icon" href="{icon_url}">'
        f'<link rel="apple-touch-icon" sizes="180x180" href="{icon_url}">'
        f'<link rel="icon" type="image/png" href="{icon_url}">'
        f'<link rel="manifest" href="/app/static/manifest.json">'
        # Launches without Safari's address bar and toolbar from the home
        # screen. Ordinary browser visits are unaffected.
        f'<meta name="apple-mobile-web-app-capable" content="yes">'
        f'<meta name="mobile-web-app-capable" content="yes">'
        # Status bar matches COLOR["bg"] instead of sitting on white.
        f'<meta name="apple-mobile-web-app-status-bar-style" content="black">'
        f'<meta name="theme-color" content="#0a0d10">'
        # Short label under the icon, rather than a truncated page title.
        f'<meta name="apple-mobile-web-app-title" content="Los Cappers">'
        f'<meta name="application-name" content="Los Cappers">'
    )
    index_path.write_text(html.replace("</head>", tags + "</head>", 1), encoding="utf-8")


try:
    _install_mobile_head_tags()
except Exception:
    # Deliberately silent and non-fatal — see the note above.
    pass


inject_kc_theme()
require_login()  # blocks with a themed login screen until authenticated

# -------------------------
# Admin detection (authoritative server-side is_admin())
# Optional local dev toggle via LC_FORCE_ADMIN env var
# -------------------------
force_admin_env = os.getenv("LC_FORCE_ADMIN", "").lower() in ("1", "true", "yes")
try:
    user_is_admin = is_admin() or force_admin_env
except Exception:
    user_is_admin = bool(force_admin_env)

# -------------------------
# HARD RULE for this app: NEVER monkeypatch attributes on the shared
# `streamlit` module (st.sidebar, st.set_page_config, anything). The
# module is global to the server process and shared by EVERY session —
# a temporary swap in one session races every other session. This has
# now bitten twice: the st.sidebar shim corrupted every st.cache_data
# write, and a set_page_config no-op swap intermittently stripped other
# sessions' page config (default centered layout, "Streamlit" tab
# title). Views may call st.set_page_config themselves — repeat calls
# are legal on this Streamlit version and simply re-apply.
# -------------------------

# -------------------------
# Sport selection — top-level sport switcher (always visible)
# -------------------------
# Read the switcher's WIDGET key first — Streamlit updates it at click
# time, before this rerun executes. Reading only lc_sport (which
# sport_switcher sets at the bottom of its render, after this line has
# already run) made every sport change take two clicks.
# -------------------------
# Top-level view: Home, or a sport.
#
# Home is NOT an MLB page. It reports every board on the site — the WNBA
# ones included — so filing it under baseball's nav made it unreachable
# from every other sport and implied the track record belonged to one of
# them. It sits beside the sport switcher as its own destination, and a
# new session lands there.
# -------------------------
st.session_state.setdefault("lc_view", "home")

selected_sport = (
    st.session_state.get("lc_sport_seg")
    or st.session_state.get("lc_sport", "MLB")
)

# A SPORT CLICK LEAVES HOME, and it has to be detected HERE.
#
# Streamlit updates the widget key (lc_sport_seg) at click time, before
# this script runs, while sport_switcher writes lc_sport at the bottom of
# its own render. So the two disagree on exactly one run — the click —
# and agree on every other. Checking after the switcher has rendered
# would always be too late: it has already synced them and reran.
_seg = st.session_state.get("lc_sport_seg")
if _seg is not None and _seg != st.session_state.get("lc_sport"):
    st.session_state["lc_view"] = "sport"

# A PAGE-NAV CLICK ALSO LEAVES HOME. Same mechanism: Streamlit writes
# lc_nav_radio at click time, while render_right_sidebar writes
# lc_active_page at the bottom of its own render, so the two disagree on
# exactly the click. Home's own jump buttons set both together, so they
# never trip this.
_nav = st.session_state.get("lc_nav_radio")
if _nav is not None and _nav != st.session_state.get("lc_active_page"):
    st.session_state["lc_view"] = "sport"

_on_home = st.session_state["lc_view"] == "home"

_home_col, _strip_col = st.columns([4, 6])
with _home_col:
    # Occupies the column that was previously an empty spacer, so this
    # costs no layout and the mobile stacking rules are unchanged.
    #
    # THE LABEL FLIPS, and it has to. The first version was a Home button
    # that highlighted when you were already on Home — which left no way
    # back, because clicking the ALREADY-SELECTED sport in the switcher
    # is a no-op (sport_switcher only reruns when the sport CHANGES). A
    # new session landed on Home and could reach five destinations out of
    # ten. The one control in this corner has to work in both directions.
    if _on_home:
        if st.button(f"\u2190  Back to {selected_sport}", key="lc_home_btn"):
            st.session_state["lc_view"] = "sport"
            st.rerun()
    else:
        if st.button("\u2302  Home", key="lc_home_btn"):
            st.session_state["lc_view"] = "home"
            st.rerun()
with _strip_col:
    sport_switcher(active=selected_sport)

# -------------------------
# Helper: build MLB pages list
# Admin pages are only added when include_admin is True.
# -------------------------
def build_mlb_pages(include_admin: bool):
    pages = [
        # Home is deliberately NOT in this list — it is a top-level view
        # above the sport switcher, not one of baseball's pages. See the
        # lc_view block near the top of this file.
        ("Game Card", "views/GameCard.py"),
        # Slate-wide HR Edge. The Game Card shows one game's version of
        # the same number; this ranks every bat on the slate, and it is
        # the exact list the calibration logger records.
        ("HR Edge", "views/HR_Edge_Board.py"),
        ("Strikeout Board", "views/Strikeout_Board.py"),
        ("Daily 13", "views/Daily_13.py"),
        ("Pitchers to Target", "views/Pitchers_To_Target.py"),
        # Sits next to the starter-facing pages on purpose: it answers
        # what happens AFTER the starter leaves, which is where roughly a
        # third of a hitter's plate appearances actually occur.
        ("Bullpen Board", "views/Bullpen_Board.py"),
        ("Weather Board", "views/Weather_Board.py"),
        ("Player of the Day", "views/Player_Of_The_Day.py"),
        # The site's own track record. Subscriber-facing on purpose:
        # the Calibration page keeps the admin diagnostics (raw records,
        # storage path, odds entry), and this shows the numbers a paying
        # user is entitled to see — hit rate per board against the
        # measured league baseline for that same outcome.
        ("Results", "views/Results.py"),
        # Model / Pitcher Report / Pitcher Splits / Pitch Mix Splits /
        # Lineup Analysis / Team Tools / KC Lineup Dashboard removed
        # from the nav on purpose: unstable pages are worse than absent
        # ones for a paid product. The files stay in views/ so any of
        # them can be rehabbed and re-listed later.
    ]

    if include_admin:
        # Admin-only diagnostics. Calibration shows raw pick records and
        # sample sizes — useful for verifying the tracker is actually
        # accumulating, not a subscriber-facing feature.
        pages.append(("Calibration (Admin)", "views/Calibration.py"))
        pages.append(("Debug Roster (Admin)", "views/0_Debug_Roster.py"))

    return pages

# -------------------------
# Non-MLB sport page loader
# -------------------------
SPORT_PAGES = {
    "KBO": "views/KBO.py",
    "WNBA": "views/WNBA.py",
    "NPB": "views/NPB.py",
    "NFL": "views/NFL.py",
    "NBA": "views/NBA.py",
    "NHL": "views/NHL.py",
}

# Sports with more than one page get their own nav. WNBA's boards used
# to sit in the MLB list, which put basketball pages in front of
# baseball users — they belong here, visible only when WNBA is the
# selected sport.
SPORT_SUBPAGES = {
    "WNBA": [
        ("Slate & Props", "views/WNBA.py"),
        ("Defense Matchup", "views/WNBA_Defense.py"),
        ("Props Board", "views/WNBA_Props.py"),
        ("Without Player", "views/Without_Player.py"),
        # Same page as the MLB nav. It reports every board, so a WNBA
        # user sees the baseball record too. That is intended: the
        # track record belongs to the site, not to one sport.
        ("Results", "views/Results.py"),
    ],
}


def load_page_module(rel_path: str):
    """Executes a view file in-place with plain runpy — nothing patched
    around it. Views may call st.set_page_config themselves; repeat
    calls are legal on this Streamlit version and simply re-apply
    (page title updates per view, layout stays wide)."""
    page_path = Path(__file__).parent / rel_path
    if not page_path.exists():
        st.error(f"Page not found: {rel_path}")
        return
    try:
        runpy.run_path(str(page_path), run_name="__main__")
    except Exception as e:
        # st.exception() rendered the whole traceback — absolute file
        # paths, internal module names, local variables — straight into
        # the page for whoever happened to be looking. That's a paying
        # subscriber's screen, not a dev console.
        #
        # The traceback still goes to stderr, so it lands in the Render
        # logs either way, and admins still see it inline.
        traceback.print_exc()
        if st.session_state.get("lc_role") == "admin":
            st.exception(e)
        else:
            st.error(
                "Something went wrong loading this page. It's been logged — "
                "try another page from the menu, or refresh in a moment."
            )

# -------------------------
# Minimal responsive CSS injection
# -------------------------
def inject_minimal_css():
    css = """
    /* Make images and tables responsive */
    img, table { max-width: 100%; height: auto; }

    /* Right sidebar / admin markers (cosmetic wrappers only — Streamlit
       widgets are NOT inside these divs, so never rely on them to
       show/hide the actual sidebar content) */
    .right-sidebar { padding-left: 0.5rem; padding-right: 0.5rem; }
    .admin-sidebar { margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.5rem; }

    /* Defensive: hide any leftover native left sidebar */
    [data-testid="stSidebar"] { display: none !important; }

    /* MOBILE (portrait phones / narrow windows): Streamlit keeps
       st.columns side-by-side at every width, which crushed the 80/20
       content+sidebar split into an unreadable sliver. Stack the two
       top-level rows vertically at full width — the sport switcher row
       (spacer column collapses to nothing) and the content+sidebar row
       (page content first, then account card / nav / glossary / sign
       out below it). :has() scopes this to exactly those two blocks;
       columns inside pages (weather strip, pitcher pills, carousels)
       are untouched.

       .right-sidebar is the load-bearing selector here. The other two
       key off radio aria-labels, which only exist on MLB — the
       Navigation radio is rendered ONLY when render_right_sidebar gets
       nav_titles, and non-MLB sports pass none. So when the sidebar was
       extended to every sport, KBO/NPB/WNBA/NBA/NFL/NHL matched neither
       selector and kept the desktop 8/2 split on a phone, squeezing
       page content into 80% width. render_right_sidebar always emits
       .right-sidebar, on every sport, which is why the rule hangs off
       that instead. */
    @media (max-width: 900px) {
      div[data-testid="stHorizontalBlock"]:has(.right-sidebar),
      div[data-testid="stHorizontalBlock"]:has([aria-label="Navigation"]),
      div[data-testid="stHorizontalBlock"]:has([aria-label="Sport"]) {
        flex-direction: column !important;
        gap: 0.75rem !important;
      }
      div[data-testid="stHorizontalBlock"]:has(.right-sidebar) > div[data-testid="stColumn"],
      div[data-testid="stHorizontalBlock"]:has(.right-sidebar) > div[data-testid="column"],
      div[data-testid="stHorizontalBlock"]:has([aria-label="Navigation"]) > div[data-testid="stColumn"],
      div[data-testid="stHorizontalBlock"]:has([aria-label="Sport"]) > div[data-testid="stColumn"],
      div[data-testid="stHorizontalBlock"]:has([aria-label="Navigation"]) > div[data-testid="column"],
      div[data-testid="stHorizontalBlock"]:has([aria-label="Sport"]) > div[data-testid="column"] {
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
      }
    }
    """
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

inject_minimal_css()


# -------------------------
# Glossary — moved here from the Game Card's old in-page sidebar so it
# lives in the one unified sidebar and is available on every MLB page.
# -------------------------
def render_glossary():
    with st.expander("\U0001F4D6 Glossary"):
        def _section(title):
            st.markdown(
                f'<div style="display:inline-block; padding:var(--lc-space-hair) var(--lc-space-md); border-radius:var(--lc-radius-sm); '
                f'background:{COLOR["error"]}22; border:1px solid {COLOR["error"]}55; '
                f'color:{COLOR["error"]}; font-weight:700; font-size:var(--lc-text-tiny); text-transform:uppercase; '
                f'letter-spacing:0.04em; margin:var(--lc-space-md) var(--lc-space-none) var(--lc-space-sm) var(--lc-space-none);">{title}</div>',
                unsafe_allow_html=True,
            )

        _section("Colors")
        st.markdown(
            f'<span style="color:{COLOR["player_name"]}; font-weight:700;">Names</span> \u00b7 '
            f'<span style="color:{COLOR["bats_l"]}; font-weight:700;">L</span>/'
            f'<span style="color:{COLOR["bats_r"]}; font-weight:700;">R</span>/'
            f'<span style="color:{COLOR["bats_s"]}; font-weight:700;">S</span> \u00b7 '
            f'<span style="color:{COLOR["error"]}; font-weight:700;">weak</span>\u2192'
            f'<span style="color:{COLOR["warn"]}; font-weight:700;">avg</span>\u2192'
            f'<span style="color:{COLOR["stat_high"]}; font-weight:700;">strong</span>',
            unsafe_allow_html=True,
        )

        _section("Composite Scores")
        st.markdown(
            "- **SLAM** \u2014 real xSLG/xwOBA power score, last 25 PA/BBE/Games. ~50 = league avg.\n"
            "- **HR/Hit/K Score** \u2014 real MLB percentile rankings, matched by player ID.\n"
            "- **Matchup tier** \u2014 bucketed from SLAM. **Confidence** \u2014 sample size only.\n"
            "- **Edge tag** \u2014 from HR/Hit/K Score thresholds, see engines/top_plays.py."
        )
        _section("Contact Quality")
        st.markdown(
            "- **Brl% / HH%** \u2014 Barrel% / Hard-Hit% (95+ mph EV).\n"
            "- **SweetSpot%** \u2014 launch angle 8\u201332\u00b0.\n"
            "- **Blast%** \u2014 (squared-up% \u00d7 100) + bat speed \u2265 164, MLB's real formula."
        )
        _section("Batted Ball Direction")
        st.markdown(
            "- **LD% / FB% / GB%** \u2014 Line Drive / Fly Ball / Ground Ball %.\n"
            "- **PullAir% / PullBrl%** \u2014 pulled fly balls / pulled AND barreled, real "
            "spray-angle math (handedness-aware)."
        )
        _section("Plate Discipline")
        st.markdown(
            "- **SwStr%** \u2014 whiffs / ALL pitches. **Whiff%** \u2014 whiffs / SWINGS only "
            "(different denominator, don't conflate them).\n"
            "- **xSLG / xwOBA** \u2014 MLB's own expected stats from exit velo + launch angle."
        )


# -------------------------
# The unified right sidebar.
#
# Extracted into a function because it used to be inline inside the
# `if selected_sport == "MLB"` branch — which meant the account card,
# the Glossary, the admin section and, critically, the Sign out button
# existed ONLY on MLB pages. Switch to KBO, NPB, WNBA, NBA, NFL or NHL
# and there was no way to log out at all: the only other logout is the
# one auth.render_account_sidebar() draws into st.sidebar, which this
# app hides with `display: none !important`. A subscriber who changed
# sport was stuck until they cleared their cookie.
#
# nav_titles/active_page are MLB-only (that's the page nav); everything
# else renders for every sport.
# -------------------------
def render_right_sidebar(nav_titles=None, active_page=None, show_glossary=False,
                         nav_caption=None):
    st.markdown('<div class="right-sidebar">', unsafe_allow_html=True)

    # Account card — who's signed in and their role
    name = st.session_state.get("name", "")
    role = st.session_state.get("lc_role", "subscriber")
    role_badge_color = COLOR["stat_high"] if role == "admin" else COLOR["warn"]
    st.markdown(
        f'<div class="pf-card" style="padding:var(--lc-space-lg) var(--lc-space-lg); margin-bottom:var(--lc-space-md);">'
        f'<div style="font-size:var(--lc-text-body); font-weight:700; color:{COLOR["text"]};">{name}</div>'
        f'<div style="display:inline-block; margin-top:var(--lc-space-sm); padding:var(--lc-space-hair) var(--lc-space-md); border-radius:var(--lc-radius-sm); '
        f'background:{role_badge_color}22; color:{role_badge_color}; font-size:var(--lc-text-tiny); font-weight:700; '
        f'text-transform:uppercase; letter-spacing:0.05em;">{role}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if nav_titles:
        # Page navigation — always visible (was hidden inside the "Menu"
        # dropdown before). Same key as the old radio so nothing else
        # reading lc_nav_radio breaks.
        #
        # Accent-rail restyle: pure CSS over the same st.radio — circles
        # hidden, each option becomes a full-width row, the active row
        # gets a teal left rail + tint (matches the section-tag / badge
        # language in kc_theme). If a future Streamlit version changes
        # that DOM, the nav gracefully degrades to plain radios.
        _rail = COLOR["stat_high"]
        _hover = COLOR["text"]
        st.markdown(
            "<style>"
            "div[role='radiogroup'][aria-label='Navigation'] label > div > :not(:has(p)):not(p) {"
            "  display: none !important; }"
            "div[role='radiogroup'][aria-label='Navigation'] label *::before,"
            "div[role='radiogroup'][aria-label='Navigation'] label *::after {"
            "  display: none !important; }"
            "div[role='radiogroup'][aria-label='Navigation'] label {"
            "  display: flex !important; align-items: center !important;"
            "  width: 100% !important; padding:var(--lc-space-md) var(--lc-space-lg) !important; margin:var(--lc-space-none) !important;"
            "  border-left: 2px solid transparent !important; border-radius: 0 !important;"
            "  cursor: pointer; transition: background 0.15s; }"
            "div[role='radiogroup'][aria-label='Navigation'] label:hover {"
            f"  background: {_hover}0D !important; }}"
            "div[role='radiogroup'][aria-label='Navigation'] label[data-selected='true'] {"
            f"  background: {_rail}1A !important; border-left-color: {_rail} !important; }}"
            "div[role='radiogroup'][aria-label='Navigation'] label[data-selected='true'] p {"
            f"  color: {_rail} !important; font-weight: 600 !important; }}"
            "</style>",
            unsafe_allow_html=True,
        )
        # WHOSE PAGES THESE ARE. Unlabelled, the list reads as the
        # current page's nav — which is wrong on Home, where it is the
        # selected SPORT's page list and Home belongs to no sport.
        if nav_caption:
            st.caption(nav_caption)

        # index=None, NOT 0, when nothing is active.
        #
        # Falling back to 0 put the teal active rail on Game Card while
        # the user was standing on Home, which states plainly that they
        # are on a page they are not on. A nav with no current page must
        # show no current page.
        _idx = nav_titles.index(active_page) if active_page in nav_titles else None
        selected = st.radio(
            "Navigation",
            nav_titles,
            index=_idx,
            key="lc_nav_radio",
            label_visibility="collapsed",
        )
        st.session_state["lc_active_page"] = selected

    # Glossary — carried over from the Game Card's old sidebar. Every
    # term in it is baseball, so it only shows on MLB.
    if show_glossary:
        render_glossary()

    # Sign out — the native left sidebar (where logout used to live) is
    # hidden, so subscribers need it here, on every sport.
    authenticator = st.session_state.get("lc_authenticator")
    if authenticator is not None:
        authenticator.logout("Sign out", "main", key="lc_sidebar_logout")

    st.markdown("</div>", unsafe_allow_html=True)

    # Admin-only controls: render only for admins and in a separate section
    if user_is_admin:
        st.markdown('<div class="admin-sidebar">', unsafe_allow_html=True)
        st.markdown("### Admin Controls")
        st.markdown("</div>", unsafe_allow_html=True)


# -------------------------
# Render UI
# -------------------------
if st.session_state.get("lc_view") == "home":
    # Home keeps the sport's page nav in the sidebar. Dropping it made
    # every page without a card on Home — Game Card, Pitchers to Target,
    # Bullpen Board, Weather Board — unreachable from the screen a new
    # session lands on.
    #
    # The nav radio is created in the RIGHT column, which renders after
    # the main one, so Home's jump buttons can still write lc_nav_radio:
    # they call st.rerun() immediately, which ends the script before the
    # widget is ever instantiated. Order matters here — see the note in
    # views/Home.py.
    _home_nav = ([t for t, _p in build_mlb_pages(include_admin=user_is_admin)]
                 if selected_sport == "MLB" else None)

    # No page is active on Home, so clear the nav's selection. Both keys,
    # and BEFORE the widget is created: the radio ignores `index` once
    # its key holds a value, so leaving lc_nav_radio set would re-select
    # the last page and re-light the rail. Clearing lc_active_page too
    # keeps the "did the user just click nav?" check above honest — it
    # compares the two, and a None against a stale title would read as a
    # click on every single run.
    st.session_state["lc_nav_radio"] = None
    st.session_state["lc_active_page"] = None

    _main_col, _right_col = st.columns([8, 2])
    with _main_col:
        load_page_module("views/Home.py")
    with _right_col:
        render_right_sidebar(nav_titles=_home_nav, active_page=None,
                             nav_caption=f"{selected_sport} pages")

elif selected_sport == "MLB":
    pages = build_mlb_pages(include_admin=user_is_admin)
    menu_titles = [title for title, _ in pages]

    # Resolve the active page BEFORE rendering the main column. The nav
    # radio's widget state (key="lc_nav_radio") is updated by Streamlit
    # at click time, before this rerun executes — reading it here (rather
    # than only after the sidebar renders) means a nav click switches the
    # page on the very next rerun instead of lagging one click behind.
    active_page = st.session_state.get("lc_nav_radio") or st.session_state.get("lc_active_page")
    if active_page not in menu_titles:
        active_page = menu_titles[0] if menu_titles else None

    # Layout: main content + persistent right sidebar
    main_col, right_col = st.columns([8, 2])

    # MAIN: render the currently selected page
    with main_col:
        if active_page:
            module_path = dict(pages).get(active_page)
            if module_path:
                load_page_module(module_path)
            else:
                st.error("Selected page not found.")
        else:
            st.info("No pages available.")

    # RIGHT: the unified sidebar — this replaces both the old "Menu"
    # expander (top right) and the Game Card's old in-page sidebar. The
    # Glossary is the one piece carried over from that old sidebar.
    with right_col:
        render_right_sidebar(nav_titles=menu_titles,
                             active_page=active_page,
                             show_glossary=True)

else:
    # Non-MLB sports load their own page modules. Sports with several
    # pages get a nav row above the content; single-page sports load
    # straight through exactly as before.
    #
    # Same two-column layout as MLB so the account card and Sign out are
    # present here too — see render_right_sidebar. The page nav stays as
    # the horizontal row above the content (these sports have two or
    # three pages, not a dozen), so no nav_titles are passed.
    _main_col, _right_col = st.columns([8, 2])

    with _main_col:
        _subpages = SPORT_SUBPAGES.get(selected_sport)
        if _subpages:
            _titles = [t for t, _p in _subpages]
            _key = f"lc_sub_{selected_sport}"
            # Read the widget key first so a click takes effect on the
            # same rerun (same one-click fix the main nav uses).
            _active = st.session_state.get(_key, _titles[0])
            _choice = st.radio(
                f"{selected_sport} pages", _titles,
                index=_titles.index(_active) if _active in _titles else 0,
                key=_key, horizontal=True, label_visibility="collapsed",
            )
            _path = dict(_subpages).get(_choice or _titles[0], _subpages[0][1])
            load_page_module(_path)
        else:
            # .get(), not [selected_sport]. selected_sport comes from
            # session state, which outlives a deploy: if a sport is ever
            # renamed or removed, a returning subscriber's stale cookie
            # raised a bare KeyError here and rendered a blank page with
            # no way back. Fall back to the default sport instead.
            _path = SPORT_PAGES.get(selected_sport)
            if _path:
                load_page_module(_path)
            else:
                st.warning(
                    f"{selected_sport} isn't available any more. "
                    f"Pick another sport above."
                )

    with _right_col:
        render_right_sidebar()
