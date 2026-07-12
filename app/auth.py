"""
Los Cappers access control.

Wraps streamlit-authenticator so every page in the app goes through one
themed login gate, and exposes role checks (admin vs subscriber) so
internal tooling like the debug page can be hidden from paying users.

This is a working v1 gate, not a full subscription platform: it proves
who someone is and what role they hold, but it doesn't handle billing.
When you're ready to charge automatically, a Stripe webhook would flip
a user's `role` (or add a `status: active/past_due`) in the same
credentials store this module reads — the login/role-check logic here
doesn't need to change.
"""
import os

import streamlit as st
import yaml
import streamlit_authenticator as stauth

from styles.kc_theme import COLOR, card_open, card_close

# auth_config.yaml is gitignored on purpose — see auth_config.example.yaml
# for the template. LC_AUTH_CONFIG_PATH lets you point at a Render "Secret
# File" mount instead of a repo-relative path in production.
CONFIG_PATH = os.environ.get(
    "LC_AUTH_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "auth_config.yaml"),
)


def _load_config():
    if not os.path.exists(CONFIG_PATH):
        st.error(
            "Auth config not found. Copy `app/auth_config.example.yaml` to "
            "`app/auth_config.yaml` (or set LC_AUTH_CONFIG_PATH) and try again."
        )
        st.stop()
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _get_authenticator():
    if "lc_authenticator" not in st.session_state:
        config = _load_config()
        st.session_state["lc_credentials"] = config["credentials"]
        st.session_state["lc_authenticator"] = stauth.Authenticate(
            config["credentials"],
            config["cookie"]["name"],
            config["cookie"]["key"],
            config["cookie"]["expiry_days"],
        )
    return st.session_state["lc_authenticator"]


def _login_screen():
    """Themed wrapper around the authenticator's login widget, plus the
    disclosures a real-money data product should show before anyone signs in."""
    from styles.kc_theme import page_header

    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        page_header("Los Cappers", "Sign in to access your research", eyebrow="MEMBERS ONLY")
        st.markdown(card_open(), unsafe_allow_html=True)
        authenticator = _get_authenticator()
        authenticator.login(location="main")
        st.markdown(card_close(), unsafe_allow_html=True)

        status = st.session_state.get("authentication_status")
        if status is False:
            st.error("Username or password is incorrect.")
        elif status is None:
            st.caption("Enter your subscriber credentials to continue.")

        st.markdown(
            f"""
            <div style="font-size:11.5px; color:#8b0000; text-align:center;
                        line-height:1.6; margin-top:22px; font-weight:600;">
            Los Cappers provides statistical models for informational and
            entertainment purposes only. No content here is a guarantee of
            outcome, and nothing on this site constitutes betting advice.
            You must be of legal betting age in your jurisdiction to use
            this data for wagering purposes. Bet responsibly.
            Problem gambling help: 1-800-GAMBLER.
            </div>
            """,
            unsafe_allow_html=True,
        )


def require_login():
    """
    Call once, at the top of the app entry point, before building navigation.
    Blocks with a themed login screen until the visitor authenticates, then
    stores their role in session_state for the rest of the run.
    """
    authenticator = _get_authenticator()

    if st.session_state.get("authentication_status") is not True:
        _login_screen()
        st.stop()

    username = st.session_state.get("username")
    creds = st.session_state.get("lc_credentials", {}).get("usernames", {})
    st.session_state["lc_role"] = creds.get(username, {}).get("role", "subscriber")


def is_admin() -> bool:
    return st.session_state.get("lc_role") == "admin"


def require_admin():
    """Call at the top of an admin-only page. Blocks non-admins."""
    if not is_admin():
        st.error("This page is restricted to administrators.")
        st.stop()


def render_account_sidebar():
    """Shows who's signed in, their role, and a logout button. Call once
    per page, typically right after inject_kc_theme()."""
    authenticator = st.session_state.get("lc_authenticator")
    name = st.session_state.get("name", "")
    role = st.session_state.get("lc_role", "subscriber")

    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding:10px 0 4px 0; border-top:1px solid {COLOR['border']}; margin-top:10px;">
                <div style="font-size:12.5px; font-weight:600; color:{COLOR['text']};">{name}</div>
                <div style="font-size:10.5px; color:{COLOR['accent']}; text-transform:uppercase; letter-spacing:0.06em;">{role}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if authenticator is not None:
            authenticator.logout("Sign out", "sidebar")
