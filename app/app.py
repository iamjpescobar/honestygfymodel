"""
Los Cappers — entry point (single right sidebar, hide extra sidebar for subscribers)

This entry file:
- Renders a single right-hand sidebar containing the full subscriber navigation.
- Prevents any code from rendering into Streamlit's built-in left `st.sidebar`
  for non-admin users by replacing `st.sidebar` with a no-op shim.
- Ensures admin pages and controls are only included when is_admin() returns True.
- Loads page modules by running their file when selected from the right menu.
- Adds minimal responsive CSS and an expander fallback so the menu collapses on phones.
- Preserve widget keys: when moving widgets into the right sidebar, keep original key= values.
"""
import runpy
from pathlib import Path
import os
import types

import streamlit as st

from styles.kc_theme import inject_kc_theme, sport_switcher
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
# Defensive shim: disable st.sidebar for subscribers
# This prevents any leftover code from rendering a second sidebar.
# For admins we leave st.sidebar intact.
# -------------------------
if not user_is_admin:
    class _HiddenSidebar:
        """A minimal shim that swallows common Streamlit sidebar calls."""
        def __getattr__(self, name):
            # Return a callable that does nothing for widget calls
            def _no_op(*args, **kwargs):
                return None
            return _no_op

        # Support context manager usage: `with st.sidebar: ...`
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    # Replace the sidebar object with the shim
    st.sidebar = _HiddenSidebar()

# -------------------------
# Sport selection — top-level sport switcher (always visible)
# -------------------------
selected_sport = st.session_state.get("lc_sport", "MLB")

_, _strip_col = st.columns([4, 6])
with _strip_col:
    sport_switcher(active=selected_sport)

# -------------------------
# Helper: build MLB pages list
# Admin pages are only added when include_admin is True.
# -------------------------
def build_mlb_pages(include_admin: bool):
    pages = [
        ("Game Card", "pages/GameCard.py"),
        ("Player of the Day", "pages/Player_Of_The_Day.py"),
        ("Model", "pages/Model.py"),
        ("Pitcher Report", "pages/1_Pitcher_Report.py"),
        ("Pitcher Splits", "pages/1_Pitcher_Splits.py"),
        ("Pitch Mix Splits", "pages/2_Pitch_Mix_Splits.py"),
        ("Lineup Analysis", "pages/2_Lineup_Analysis.py"),
        ("Team Tools", "pages/3_Team_Tools.py"),
        ("KC Lineup Dashboard", "pages/KC_Page.py"),
    ]

    if include_admin:
        pages.append(("Debug Roster (Admin)", "pages/0_Debug_Roster.py"))

    return pages

# -------------------------
# Non-MLB sport page loader
# -------------------------
SPORT_PAGES = {
    "KBO": "pages/KBO.py",
    "WNBA": "pages/WNBA.py",
    "NPB": "pages/NPB.py",
    "NFL": "pages/NFL.py",
    "NBA": "pages/NBA.py",
    "NHL": "pages/NHL.py",
}


def load_page_module(rel_path: str):
    """Executes a sport page file in-place. Pages must NOT call
    st.set_page_config — it's already set once above for the whole app."""
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

    /* Right sidebar wrapper */
    .right-sidebar { position: sticky; top: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }

    /* Admin visual separator (admins only) */
    .admin-sidebar { margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.5rem; }

    /* Defensive: hide any leftover left sidebar or duplicate menu elements that might be injected */
    [data-testid="stSidebar"] { display: none !important; }
    .css-1d391kg { display: none !important; } /* fallback for some Streamlit versions */

    /* Mobile: hide the right column content so main content becomes full width */
    @media (max-width: 900px) {
      .right-sidebar { display: none !important; }
      .admin-sidebar { display: none !important; }
      [data-testid="stAppViewContainer"] .main { width: 100% !important; }
    }
    """
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

inject_minimal_css()

# -------------------------
# Render UI
# -------------------------
if selected_sport == "MLB":
    pages = build_mlb_pages(include_admin=user_is_admin)

    # Layout: main content + right-hand sidebar
    main_col, right_col = st.columns([8, 2])

    # MAIN: render the currently selected page (default to first page)
    with main_col:
        active_page = st.session_state.get("lc_active_page", pages[0][0] if pages else None)
        if active_page:
            # Find module path for active page
            module_path = None
            for title, path in pages:
                if title == active_page:
                    module_path = path
                    break

            if module_path:
                load_page_module(module_path)
            else:
                st.error("Selected page not found.")
        else:
            st.info("No pages available.")

    # RIGHT: subscriber navigation (everything that used to be on the left)
    with right_col:
        # Expander fallback for mobile
        with st.expander("Menu", expanded=False):
            st.markdown('<div class="right-sidebar">', unsafe_allow_html=True)

            # Build a menu UI (radio) that sets st.session_state["lc_active_page"]
            # Include all subscriber items (everything that was on the left)
            menu_titles = [title for title, _ in pages if not title.lower().startswith("debug roster (admin)")]
            # Determine default index safely
            default_index = 0
            current = st.session_state.get("lc_active_page")
            if current in menu_titles:
                default_index = menu_titles.index(current)

            selected = st.radio(
                "Navigation",
                menu_titles,
                index=default_index,
                key="lc_nav_radio"
            )
            # Persist selection
            st.session_state["lc_active_page"] = selected

            # --- Everything that used to live in the left sidebar goes here ---
            # Move your left-sidebar widgets into this block. Preserve original keys.
            # Example placeholders (replace with your actual widgets and keep keys):
            # st.markdown("### Subscriber")
            # st.button("Sign out", key="sign_out")
            # st.selectbox("Choose team", ["NYM", "PHI"], key="team_select")
            # st.checkbox("Master Subscriber", value=True, key="master_subscriber")
            #
            # If you have a helper like render_account_sidebar(), call it here
            # but ensure it does not render admin-only items for subscribers.
            #
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
