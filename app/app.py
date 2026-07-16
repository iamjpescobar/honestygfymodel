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
import os

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
# Sport selection — the clickable sport_switcher strip renders here at
# app level, above navigation, so it exists on EVERY page and can never
# be hidden by a page that stops early (e.g. Game Card on an off-day).
# Clicking a tab sets st.session_state["lc_sport"] and reruns.
# -------------------------
selected_sport = st.session_state.get("lc_sport", "MLB")

_, _strip_col = st.columns([4, 6])
with _strip_col:
    sport_switcher(active=selected_sport)

# -------------------------
# Build the pages dict for MLB (the live product)
# -------------------------
def build_mlb_pages(include_admin: bool):
    """Return the pages dict for MLB. Admin pages are only added when
    include_admin is True."""
    pages = {
        "": [
            st.Page("pages/GameCard.py", title="Game Card", icon=":material/stadium:", default=True),
            st.Page("pages/Player_Of_The_Day.py", title="Player of the Day", icon=":material/star:"),
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

    if include_admin:
        # Admin pages are appended only when include_admin is True.
        pages["Admin"] = [
            st.Page("pages/0_Debug_Roster.py", title="Debug Roster", icon=":material/bug_report:"),
        ]

    return pages

# -------------------------
# Admin detection
# -------------------------
# Production: is_admin() should be implemented server-side and return True
# only for authenticated admin users. Do NOT rely on query params in prod.
#
# Local dev convenience: set environment variable LC_FORCE_ADMIN=true to
# simulate admin locally (useful for testing). This is optional.
force_admin_env = os.getenv("LC_FORCE_ADMIN", "").lower() in ("1", "true", "yes")

# Evaluate admin status. is_admin() is authoritative; env toggle only helps local dev.
try:
    user_is_admin = is_admin() or force_admin_env
except Exception:
    # If is_admin() raises for any reason, default to False to avoid leaking admin UI.
    user_is_admin = bool(force_admin_env)

# -------------------------
# Sport page loader (non-MLB sports)
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
# Render navigation or sport page
# -------------------------
if selected_sport == "MLB":
    # Build pages with admin pages included only when user_is_admin is True.
    navigation = st.navigation(build_mlb_pages(include_admin=user_is_admin), expanded=True)
    navigation.run()
else:
    load_page_module(SPORT_PAGES[selected_sport])
