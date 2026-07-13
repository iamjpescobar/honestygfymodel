"""
Los Cappers — entry point.

This file's only jobs are: set page config once, gate access behind
login, and build the navigation. The actual pages live in app/pages/.
Debug Roster only appears in the nav for admins — subscribers never
see it exists.

Brand note: this used to be titled "Los Cappers MLB Model." Dropped the
MLB-specific title since the product is moving toward multi-sport
(MLB/NBA/NHL/NFL) — see styles/kc_theme.py's sport_switcher(). Only MLB
has real data behind it right now; the others are placeholders, not
live features, until their own data engines are built the same way
MLB's were.
"""
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

    # -----------------------------
    # NEW MULTI-SPORT SECTIONS
    # -----------------------------
    "NFL": [
        st.Page("pages/NFL.py", title="NFL Analytics", icon=":material/sports_football:")
    ],

    "NBA": [
        st.Page("pages/NBA.py", title="NBA Analytics", icon=":material/sports_basketball:")
    ],

    "NHL": [
        st.Page("pages/NHL.py", title="NHL Analytics", icon=":material/sports_hockey:")
    ],
}

if is_admin():
    pages["Admin"] = [
        st.Page("pages/0_Debug_Roster.py", title="Debug Roster", icon=":material/bug_report:"),
    ]

navigation = st.navigation(pages, expanded=True)
navigation.run()
