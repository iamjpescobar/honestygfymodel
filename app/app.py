"""
Los Cappers — entry point (multi-sport header tabs).

Sets page config once, gates access behind login, renders the top-right
sport tab bar, and builds the navigation. MLB is the live product and
keeps the full left navigation; the other sports load their own
"coming soon" pages — clearly labeled as in development, never showing
placeholder data, per the same real-data standard the MLB engines hold.
"""
import runpy
from pathlib import Path

import streamlit as st

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
# Sport selection — driven by the clickable sport_switcher strip that
# pages render in place (see styles/kc_theme.py). Clicking a tab there
# sets this session key and reruns; no separate header radio needed.
# -------------------------
selected_sport = st.session_state.get("lc_sport", "MLB")

# -------------------------
# MLB navigation (the live product)
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
# Sport page loader (non-MLB sports)
# -------------------------
SPORT_PAGES = {
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


if selected_sport == "MLB":
    navigation = st.navigation(pages, expanded=True)
    navigation.run()
else:
    load_page_module(SPORT_PAGES[selected_sport])