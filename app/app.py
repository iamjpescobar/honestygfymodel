"""
Los Cappers — entry point (multi-sport header tabs).

This version removes sport entries from the left navigation and
renders a top-right sport tab bar. Clicking a sport tab loads the
corresponding page module from app/pages/ so the UI behaves like
the MLB Game Card but with the top tabs as the primary controls.
"""
import streamlit as st
import runpy
from pathlib import Path

from styles.kc_theme import inject_kc_theme
from auth import require_login, is_admin

st.set_page_config(
    page_title="Los Cappers",
    page_icon="⚾",
    layout="wide"
)

inject_kc_theme()
require_login()  # blocks with a themed login screen until authenticated

# -------------------------
# Header: top-right sport tabs
# -------------------------
def _render_sport_tabs(right_align=True):
    """Render sport tabs in the header and return selected sport key or None."""
    # Layout hack: create a wide row and push tabs to the right column
    left, right = st.columns([6, 1]) if right_align else st.columns([1, 6])
    with left:
        st.markdown("")  # keep left empty
    with right:
        # Use st.radio for compact horizontal tabs; you can swap for st.tabs if preferred
        sport = st.radio(
            label="",
            options=["MLB", "NFL", "NBA", "NHL"],
            index=0,
            horizontal=True
        )
    return sport

selected_sport = _render_sport_tabs()

# -------------------------
# Pages dictionary (no sport pages here)
# -------------------------
pages = {
    "": [
        st.Page("pages/GameCard.py", title="Game Card", icon=":material/stadium:", default=True),
    ],
    "Legacy Tools": [
        st.Page("pages/Model.py", title="Model", icon=":material/monitoring:"),
        st.Page("pages/1_Pitcher_Report.py", title="Pitcher Report", icon=":material/sports_baseball:"),
        st.Page("pages/1_Pitcher_Splits.py", title="Pitcher Splits", icon=":material/split_scene:"),
        st.Page("pages/2_Pitch_Mix_Splits.py", title="Pitch Mix Splits", icon=":material/blender:"),
        st.Page("pages/2_Lineup_Analysis.py", title="Lineup Analysis", icon=":material/groups:"),
        st.Page("pages/3_Team_Tools.py", title="Team Tools", icon=":material/handyman:"),
        st.Page("pages/KC_Page.py", title="KC Lineup Dashboard", icon=":material/dashboard:"),
    ],
}

if is_admin():
    pages["Admin"] = [
        st.Page("pages/0_Debug_Roster.py", title="Debug Roster", icon=":material/bug_report:"),
    ]

# -------------------------
# Helper: load a page module by path
# -------------------------
def load_page_module(rel_path: str):
    """
    Execute a page file in-place. Uses runpy to run the file as a script.
    This mirrors how Streamlit would execute a page module; keep pages
    simple and avoid re-calling st.set_page_config inside page modules.
    """
    page_path = Path(__file__).parent / rel_path
    if not page_path.exists():
        st.error(f"Page not found: {rel_path}")
        return
    try:
        # Run the page file in its own namespace
        runpy.run_path(str(page_path), run_name="__main__")
    except Exception as e:
        st.exception(e)

# -------------------------
# If a sport tab is selected and it's not MLB, load its page directly
# -------------------------
# MLB remains the default behavior (GameCard via navigation). For other sports,
# we load the corresponding page file from app/pages/.
sport_to_page = {
    "MLB": None,  # keep default navigation behavior for MLB
    "NFL": "pages/NFL.py",
    "NBA": "pages/NBA.py",
    "NHL": "pages/NHL.py",
}

if selected_sport != "MLB":
    # Render the selected sport page directly and skip the left navigation UI
    st.experimental_rerun() if False else None  # no-op placeholder to keep flow clear
    load_page_module(sport_to_page[selected_sport])
else:
    # Render the normal navigation for MLB and legacy tools
    navigation = st.navigation(pages, expanded=True)
    navigation.run()

# -------------------------
# Optional: hide any leftover sport links in the left sidebar via CSS
# (only if you still see them and want them visually removed)
# -------------------------
hide_left_sports_css = """
<style>
/* Example: hide sidebar items that contain 'Analytics' or sport names */
[data-testid="stSidebar"] li:has(span:contains("NFL Analytics")) { display:none; }
[data-testid="stSidebar"] li:has(span:contains("NBA Analytics")) { display:none; }
[data-testid="stSidebar"] li:has(span:contains("NHL Analytics")) { display:none; }
</style>
"""
# st.markdown(hide_left_sports_css, unsafe_allow_html=True)  # enable if needed
