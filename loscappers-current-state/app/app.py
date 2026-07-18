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
selected_sport = (
    st.session_state.get("lc_sport_seg")
    or st.session_state.get("lc_sport", "MLB")
)

_, _strip_col = st.columns([4, 6])
with _strip_col:
    sport_switcher(active=selected_sport)

# -------------------------
# Helper: build MLB pages list
# Admin pages are only added when include_admin is True.
# -------------------------
def build_mlb_pages(include_admin: bool):
    pages = [
        ("Game Card", "views/GameCard.py"),
        ("Strikeout Board", "views/Strikeout_Board.py"),
        ("Player of the Day", "views/Player_Of_The_Day.py"),
        ("Model", "views/Model.py"),
        ("Pitcher Report", "views/1_Pitcher_Report.py"),
        ("Pitcher Splits", "views/1_Pitcher_Splits.py"),
        ("Pitch Mix Splits", "views/2_Pitch_Mix_Splits.py"),
        ("Lineup Analysis", "views/2_Lineup_Analysis.py"),
        ("Team Tools", "views/3_Team_Tools.py"),
        ("KC Lineup Dashboard", "views/KC_Page.py"),
    ]

    if include_admin:
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
        st.exception(e)

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
       are untouched. */
    @media (max-width: 900px) {
      div[data-testid="stHorizontalBlock"]:has([aria-label="Navigation"]),
      div[data-testid="stHorizontalBlock"]:has([aria-label="Sport"]) {
        flex-direction: column !important;
        gap: 0.75rem !important;
      }
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
                f'<div style="display:inline-block; padding:3px 10px; border-radius:4px; '
                f'background:{COLOR["error"]}22; border:1px solid {COLOR["error"]}55; '
                f'color:{COLOR["error"]}; font-weight:700; font-size:10.5px; text-transform:uppercase; '
                f'letter-spacing:0.04em; margin:10px 0 6px 0;">{title}</div>',
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
# Render UI
# -------------------------
if selected_sport == "MLB":
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
        st.markdown('<div class="right-sidebar">', unsafe_allow_html=True)

        # Account card — who's signed in and their role
        name = st.session_state.get("name", "")
        role = st.session_state.get("lc_role", "subscriber")
        role_badge_color = COLOR["stat_high"] if role == "admin" else COLOR["warn"]
        st.markdown(
            f'<div class="pf-card" style="padding:12px 14px; margin-bottom:10px;">'
            f'<div style="font-size:13px; font-weight:700; color:{COLOR["text"]};">{name}</div>'
            f'<div style="display:inline-block; margin-top:6px; padding:3px 10px; border-radius:4px; '
            f'background:{role_badge_color}22; color:{role_badge_color}; font-size:10.5px; font-weight:700; '
            f'text-transform:uppercase; letter-spacing:0.05em;">{role}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Page navigation — always visible (was hidden inside the "Menu"
        # dropdown before). Same key as the old radio so nothing else
        # reading lc_nav_radio breaks.
        #
        # Accent-rail restyle: pure CSS over the same st.radio — circles
        # hidden, each option becomes a full-width row, the active row
        # gets a teal left rail + tint (matches the section-tag / badge
        # language in kc_theme). Targets Streamlit's .st-key-lc_nav_radio
        # wrapper and :has(input:checked); if a future Streamlit version
        # changes that DOM, the nav gracefully degrades to plain radios.
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
            "  width: 100% !important; padding: 8px 12px !important; margin: 0 !important;"
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
        selected = st.radio(
            "Navigation",
            menu_titles,
            index=menu_titles.index(active_page) if active_page in menu_titles else 0,
            key="lc_nav_radio",
            label_visibility="collapsed",
        )
        st.session_state["lc_active_page"] = selected

        # Glossary — carried over from the Game Card's old sidebar
        render_glossary()

        # Sign out — the native left sidebar (where logout used to live)
        # is hidden/shimmed, so subscribers need it here.
        authenticator = st.session_state.get("lc_authenticator")
        if authenticator is not None:
            authenticator.logout("Sign out", "main", key="lc_sidebar_logout")

        st.markdown("</div>", unsafe_allow_html=True)

        # Admin-only controls: render only for admins and in a separate section
        if user_is_admin:
            st.markdown('<div class="admin-sidebar">', unsafe_allow_html=True)
            st.markdown("### Admin Controls")
            # Admin widgets (only visible to admins)
            # Example:
            # st.checkbox("Show debug logs", key="admin_debug")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.empty()

else:
    # Non-MLB sports load their own page modules
    load_page_module(SPORT_PAGES[selected_sport])