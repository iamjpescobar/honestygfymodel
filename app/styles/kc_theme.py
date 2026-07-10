def inject_kc_theme():
    import streamlit as st

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        .stApp {
            background-color: #0a0a0d;
            color: #e8e8ec;
        }

        #MainMenu, footer, header {visibility: hidden;}

        section[data-testid="stSidebar"] {
            background-color: #101014;
            border-right: 1px solid #232329;
        }

        .main-header {
            text-align: center;
            font-size: 34px;
            font-weight: 800;
            letter-spacing: 0.02em;
            margin-bottom: 0.15rem;
            color: #f5f5f7;
        }
        .sub-header {
            text-align: center;
            font-size: 15px;
            font-weight: 500;
            color: #ef4444;
            margin-bottom: 1.75rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        h3 {
            color: #f0f0f3 !important;
            font-size: 15px !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-left: 3px solid #8b0000;
            padding-left: 10px;
            margin-top: 1.6rem !important;
        }

        .pf-card {
            background: #131318;
            border: 1px solid #232329;
            border-radius: 14px;
            padding: 20px 22px;
            margin-bottom: 18px;
        }
        .pf-card-title {
            font-weight: 700;
            font-size: 16px;
            color: #f0f0f3;
            margin-bottom: 4px;
        }
        .pf-card-subtitle {
            font-size: 13px;
            color: #9797a5;
            margin-bottom: 10px;
        }

        .pf-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 600;
            margin-right: 8px;
            margin-bottom: 6px;
        }
        .pf-badge-accent  { background: rgba(139, 0, 0, 0.22);    color: #f87171; border: 1px solid rgba(139,0,0,0.55); }
        .pf-badge-good    { background: rgba(212, 175, 55, 0.16); color: #e8c766; border: 1px solid rgba(212,175,55,0.45); }
        .pf-badge-bad     { background: rgba(30, 58, 95, 0.30);   color: #7ba3d0; border: 1px solid rgba(30,58,95,0.6); }
        .pf-badge-neutral { background: rgba(148, 163, 184, 0.12); color: #cbd5e1; border: 1px solid rgba(148,163,184,0.3); }

        div[data-testid="stDataFrame"] {
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid #232329;
        }
        div[data-testid="stDataFrame"] table {
            background-color: #131318;
            border-collapse: collapse;
        }
        div[data-testid="stDataFrame"] table td,
        div[data-testid="stDataFrame"] table th {
            padding: 6px 10px;
            border-bottom: 1px solid #1d1d24;
            font-size: 12.5px;
        }
        div[data-testid="stDataFrame"] table th {
            color: #9797a5;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.05em;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            border-bottom: 1px solid #232329;
        }
        .stTabs [data-baseweb="tab"] {
            color: #9797a5;
            font-weight: 600;
            font-size: 14px;
            padding: 10px 4px;
        }
        .stTabs [aria-selected="true"] {
            color: #f87171 !important;
            border-bottom: 2px solid #8b0000 !important;
        }

        section[data-testid="stSidebar"] label {
            color: #cbd5e1 !important;
            font-weight: 600;
            font-size: 13px;
        }

        .pf-metric-value {
            font-size: 22px;
            font-weight: 800;
            color: #f5f5f7;
        }
        .pf-metric-label {
            font-size: 12px;
            color: #9797a5;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .pf-status {
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 14px;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }
        .pf-status-icon { font-size: 16px; line-height: 1.4; }
        .pf-status-error {
            background: rgba(139, 0, 0, 0.14);
            border: 1px solid rgba(139, 0, 0, 0.4);
            color: #f5b8b8;
        }
        .pf-status-warning {
            background: rgba(161, 122, 24, 0.14);
            border: 1px solid rgba(161, 122, 24, 0.4);
            color: #e8c766;
        }
        .pf-status-info {
            background: rgba(148, 163, 184, 0.10);
            border: 1px solid rgba(148, 163, 184, 0.3);
            color: #cbd5e1;
        }

        div[data-testid="stAlert"] {
            background: #131318 !important;
            border: 1px solid #232329 !important;
            border-radius: 12px !important;
            color: #e8e8ec !important;
        }
        div[data-testid="stExpander"] {
            background: #131318;
            border: 1px solid #232329;
            border-radius: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_banner(kind: str, message: str, details: str = None):
    """
    Renders a clean, dark-themed status banner instead of Streamlit's
    default bright st.error/st.warning boxes.
    kind: 'error', 'warning', or 'info'
    message: short, plain-language summary a non-technical user can read
    details: optional raw technical detail (exception text etc.), shown
             only inside a collapsed expander so it doesn't clutter the UI
    """
    import streamlit as st

    icon = {"error": "⚠️", "warning": "⚠️", "info": "ℹ️"}.get(kind, "ℹ️")
    st.markdown(
        f'<div class="pf-status pf-status-{kind}">'
        f'<span class="pf-status-icon">{icon}</span><span>{message}</span>'
        f'</div>',
        unsafe_allow_html=True
    )
    if details:
        with st.expander("Technical details"):
            st.code(details, language=None)


def badge(text: str, style: str = "neutral") -> str:
    """
    Returns an HTML pill/badge string, e.g. badge("vs RHB 0.83", "bad").
    style options: 'accent' (blood red), 'good' (gold), 'bad' (dark blue), 'neutral'
    """
    return f'<span class="pf-badge pf-badge-{style}">{text}</span>'


def card_open(title: str = "", subtitle: str = "") -> str:
    """Returns the opening HTML for a styled card. Pair with card_close()."""
    html = '<div class="pf-card">'
    if title:
        html += f'<div class="pf-card-title">{title}</div>'
    if subtitle:
        html += f'<div class="pf-card-subtitle">{subtitle}</div>'
    return html


def card_close() -> str:
    return "</div>"