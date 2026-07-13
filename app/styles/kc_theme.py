"""
Los Cappers — "Steel Line" theme.

A single design system applied to every page: graphite background,
one cyan signal accent reserved for what matters (danger-zone heat,
active states), monospace for every number so the app reads like a
data terminal rather than a dashboard demo. No emoji, no gradients,
no glow. Import inject_kc_theme() + page_header() at the top of every
page — that's what keeps the app looking like one product instead of
five different prototypes stitched together.
"""

# ---------------------------------------------------------
# TOKENS — the only place colors should be defined
# ---------------------------------------------------------
COLOR = {
    "bg":            "#0a0d10",
    "surface":       "#12161a",
    "surface_raised":"#161b20",
    "border":        "#232b31",
    "border_soft":   "#1a2025",
    "text":          "#e6edf0",
    "text_muted":    "#7c8791",
    "text_faint":    "#4d565d",
    "accent":        "#34d7c8",   # signal cyan — heat, active states, primary data
    "accent_dim":    "rgba(52, 215, 200, 0.14)",
    "accent_border": "rgba(52, 215, 200, 0.45)",
    "cold":          "#4a6b8a",   # unfavorable / low value
    "cold_dim":      "rgba(74, 107, 138, 0.16)",
    "cold_border":   "rgba(74, 107, 138, 0.45)",
    "warn":          "#E9A94B",
    "warn_dim":      "rgba(233, 169, 75, 0.14)",
    "warn_border":   "rgba(233, 169, 75, 0.4)",
    "error":         "#D64545",
    "error_dim":     "rgba(214, 69, 69, 0.14)",
    "error_border":  "rgba(214, 69, 69, 0.4)",
    # Identity colors — player names and handedness. Deliberately NOT
    # part of the red/amber/blue heatmap scale, since those are
    # reserved for the heatmap's good/mid/bad meaning. These are pure
    # identity signals, not value judgments, so a player's name or
    # handedness always reads as "information" rather than "score."
    "player_name":   "#9C7BFF",   # violet
    "bats_l":        "#5CCEFF",   # sky blue
    "bats_r":        "#FF8A65",   # warm coral — replaces the too-dark slate grey
    "bats_s":        "#B8860B",   # dark goldenrod (metallic gold)
    "gold":          "#D4AF37",   # general "important text" gold — secondary text, labels, captions
    "magenta_purple":"#D946EF",   # card titles for the Top Plays panel + team names — distinct from player_name's softer violet
    "headline":      "#22C55E",   # vibrant emerald — reserved for the single biggest matchup headline, distinct from every other color on the page so it reads as THE main event
    # Stat/table tier colors — exact palette: heatmap cells use these
    # literally. Badges use the same hues lightened just enough to read
    # as text against a near-black background (Low as-is would be
    # invisible as text).
    "stat_high":       "#3BB8FF",
    "stat_high_dim":   "rgba(59, 184, 255, 0.16)",
    "stat_high_border":"rgba(59, 184, 255, 0.45)",
    "stat_mid":        "#0E7C86",
    "stat_mid_text":   "#4fc4cf",   # lightened Mid, for badge legibility
    "stat_mid_dim":    "rgba(14, 124, 134, 0.22)",
    "stat_mid_border": "rgba(14, 124, 134, 0.55)",
    "stat_low":        "#0A1F26",
    "stat_low_text":   "#4a7a87",   # lightened Low, for badge legibility
    "stat_low_dim":    "rgba(10, 31, 38, 0.55)",
    "stat_low_border": "rgba(74, 122, 135, 0.4)",
}


def inject_kc_theme():
    import streamlit as st

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

        :root {{
            --lc-bg: {COLOR["bg"]};
            --lc-surface: {COLOR["surface"]};
            --lc-border: {COLOR["border"]};
            --lc-text: {COLOR["text"]};
            --lc-muted: {COLOR["text_muted"]};
            --lc-accent: {COLOR["accent"]};
        }}

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        /* Any numeric / tabular content reads as monospace — the "terminal" cue */
        div[data-testid="stDataFrame"], div[data-testid="stTable"],
        .lc-mono, code {{
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace !important;
        }}

        .stApp {{
            background-color: {COLOR["bg"]};
            color: {COLOR["text"]};
        }}

        #MainMenu, footer, header {{visibility: hidden;}}

        /* ---------------- SIDEBAR ---------------- */
        section[data-testid="stSidebar"] {{
            background-color: {COLOR["surface"]};
            border-right: 1px solid {COLOR["border"]};
        }}
        section[data-testid="stSidebar"] label {{
            color: {COLOR["text_muted"]} !important;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {{
            color: {COLOR["text"]} !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            border-left: 2px solid {COLOR["accent"]};
            padding-left: 9px;
            margin-top: 1.4rem !important;
            margin-bottom: 0.6rem !important;
        }}

        /* ---------------- PAGE HEADER ---------------- */
        .lc-eyebrow {{
            text-align: center;
            font-size: 11px;
            font-weight: 700;
            color: {COLOR["accent"]};
            text-transform: uppercase;
            letter-spacing: 0.18em;
            margin-bottom: 6px;
        }}
        .lc-title {{
            text-align: center;
            font-size: 32px;
            font-weight: 800;
            letter-spacing: -0.01em;
            color: {COLOR["text"]};
            margin-bottom: 4px;
        }}
        .lc-subtitle {{
            text-align: center;
            font-size: 13px;
            font-weight: 500;
            color: {COLOR["text_muted"]};
            margin-bottom: 1.6rem;
        }}
        .lc-rule {{
            width: 64px;
            height: 2px;
            background: {COLOR["accent"]};
            margin: 14px auto 1.6rem auto;
        }}

        /* Section labels — replaces default h3/subheader look everywhere */
        h3 {{
            color: {COLOR["text"]} !important;
            font-size: 14px !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-left: 3px solid {COLOR["accent"]};
            padding-left: 10px;
            margin-top: 1.6rem !important;
        }}
        h1, h2 {{ color: {COLOR["text"]} !important; }}

        /* ---------------- CARDS ---------------- */
        /* Real container-based cards (see card() in this file) \u2014 matches
           any st.container(key="card_...") so every card gets this
           styling with no per-card CSS needed. */
        div[class*="st-key-card_"] {{
            background: linear-gradient(160deg, {COLOR["stat_high_dim"]}, {COLOR["surface"]} 70%) !important;
            border: 1px solid {COLOR["stat_high_border"]} !important;
            border-top: 3px solid {COLOR["stat_high"]} !important;
            border-radius: 8px !important;
            padding: 14px 16px !important;
            margin-bottom: 10px !important;
        }}

        /* Glossary gets its own accent — real bloody red instead of the
           page's default cyan, so it reads as a distinct reference
           section rather than another stat card. */
        div[class*="st-key-card_glossary"] {{
            background: linear-gradient(160deg, {COLOR["error_dim"]}, {COLOR["surface"]} 70%) !important;
            border: 1px solid {COLOR["error_border"]} !important;
            border-top: 3px solid {COLOR["error"]} !important;
        }}

        .pf-card {{
            background: linear-gradient(160deg, {COLOR["stat_high_dim"]}, {COLOR["surface"]} 70%);
            border: 1px solid {COLOR["stat_high_border"]};
            border-top: 3px solid {COLOR["stat_high"]};
            border-radius: 8px;
            padding: 14px 16px;
            margin-bottom: 10px;
        }}
        .pf-card-title {{
            font-weight: 700;
            font-size: 15px;
            color: {COLOR["text"]};
            margin-bottom: 4px;
            letter-spacing: 0.01em;
        }}
        .pf-card-subtitle {{
            font-size: 12.5px;
            color: {COLOR["text_muted"]};
            margin-bottom: 12px;
        }}

        /* ---------------- BADGES ---------------- */
        .pf-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 13px;
            border-radius: 4px;
            font-size: 12.5px;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
            margin-right: 8px;
            margin-bottom: 6px;
        }}
        .pf-badge-accent  {{ background: {COLOR["stat_high_dim"]}; color: {COLOR["stat_high"]};    border: 1px solid {COLOR["stat_high_border"]}; }}
        .pf-badge-good    {{ background: {COLOR["stat_high_dim"]}; color: {COLOR["stat_high"]};    border: 1px solid {COLOR["stat_high_border"]}; }}
        .pf-badge-bad     {{ background: {COLOR["stat_low_dim"]};  color: {COLOR["stat_low_text"]}; border: 1px solid {COLOR["stat_low_border"]}; }}
        .pf-badge-neutral {{ background: {COLOR["stat_mid_dim"]};  color: {COLOR["stat_mid_text"]}; border: 1px solid {COLOR["stat_mid_border"]}; }}

        /* ---------------- DATAFRAMES / TABLES ---------------- */
        div[data-testid="stDataFrame"], div[data-testid="stTable"] {{
            border-radius: 6px;
            overflow: hidden;
            border: none;
            background-color: transparent !important;
        }}
        /* The hover toolbar (search/download/fullscreen icons) is a
           separate Streamlit chrome layer on top of the grid, not
           covered by Styler cell rules \u2014 it defaults to a light
           background unless targeted directly. */
        div[data-testid="stElementToolbar"],
        div[data-testid="stElementToolbarButton"] {{
            background-color: {COLOR["surface_raised"]} !important;
            color: {COLOR["text"]} !important;
        }}
        div[data-testid="stElementToolbar"] button svg {{
            fill: {COLOR["text_muted"]} !important;
        }}
        div[data-testid="stDataFrame"] table, div[data-testid="stTable"] table {{
            background-color: {COLOR["surface"]};
            border-collapse: collapse;
        }}
        div[data-testid="stDataFrame"] table td, div[data-testid="stTable"] table td,
        div[data-testid="stDataFrame"] table th, div[data-testid="stTable"] table th {{
            padding: 7px 12px;
            border-bottom: 1px solid {COLOR["border_soft"]};
            font-size: 12.5px;
        }}
        div[data-testid="stDataFrame"] table th, div[data-testid="stTable"] table th {{
            color: {COLOR["text_muted"]};
            text-transform: uppercase;
            font-size: 10.5px;
            letter-spacing: 0.06em;
            background-color: {COLOR["surface_raised"]};
        }}

        /* ---------------- TABS ---------------- */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
            border-bottom: 1px solid {COLOR["border"]};
        }}
        .stTabs [data-baseweb="tab"] {{
            color: {COLOR["text_muted"]};
            font-weight: 600;
            font-size: 13px;
            padding: 10px 4px;
        }}
        .stTabs [aria-selected="true"] {{
            color: {COLOR["accent"]} !important;
            border-bottom: 2px solid {COLOR["accent"]} !important;
        }}

        /* Streamlit adds ~1rem of margin between every single element by
           default \u2014 on a page with this many stacked widgets/cards that
           adds up to real, unnecessary scroll. Tighten it globally. */
        div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] {{
            margin-bottom: 4px !important;
        }}
        .block-container {{
            padding-top: 1.5rem !important;
            padding-bottom: 1.5rem !important;
        }}

        /* Subtle icon motion \u2014 tasteful, not distracting on a data product */
        @keyframes lc-float {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-3px); }}
        }}
        @keyframes lc-drift {{
            0%, 100% {{ transform: translateX(0); opacity: 0.85; }}
            50% {{ transform: translateX(3px); opacity: 1; }}
        }}
        .lc-weather-icon {{ animation: lc-float 3s ease-in-out infinite; display: inline-block; }}
        .lc-wind-icon {{ animation: lc-drift 2.2s ease-in-out infinite; display: inline-block; }}

        /* Streamlit's default caption color is quite dim against our
           dark background \u2014 boost contrast globally. */
        [data-testid="stCaptionContainer"] p {{
            color: {COLOR["text_muted"]} !important;
        }}

        /* ---------------- PILLS / SEGMENTED CONTROL ---------------- */
        /* st.pills and st.segmented_control share this underlying widget.
           Default Streamlit styling renders plain white text on a flat
           background here, which clashes with the dark theme \u2014 give it
           the same card/accent treatment as everything else. */
        div[data-testid="stButtonGroup"] button {{
            background-color: {COLOR["surface_raised"]} !important;
            color: {COLOR["text"]} !important;
            border: 1px solid {COLOR["border"]} !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
        }}
        div[data-testid="stButtonGroup"] button:hover {{
            border-color: {COLOR["stat_high"]} !important;
            color: {COLOR["stat_high"]} !important;
        }}
        div[data-testid="stButtonGroup"] button[aria-checked="true"],
        div[data-testid="stButtonGroup"] button[aria-pressed="true"] {{
            background-color: {COLOR["stat_high_dim"]} !important;
            border-color: {COLOR["stat_high"]} !important;
            color: {COLOR["stat_high"]} !important;
        }}

        /* Game picker specifically: force a single scrollable row instead
           of wrapping into a cluttered grid when there are many games. */
        .st-key-game_picker div[data-testid="stButtonGroup"] {{
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            padding-bottom: 8px;
            scrollbar-width: thin;
            scrollbar-color: {COLOR["border"]} transparent;
        }}
        .st-key-game_picker div[data-testid="stButtonGroup"] button {{
            flex-shrink: 0 !important;
            white-space: nowrap !important;
        }}

        /* Radio button labels (e.g. "Select Pitcher") were using
           Streamlit's default text color, which reads poorly against
           our dark background. */
        div[data-testid="stRadio"] label div[data-testid="stMarkdownContainer"] p {{
            color: {COLOR["text"]} !important;
            font-size: 13.5px;
        }}
        div[data-testid="stRadio"] > div[data-testid="stWidgetLabel"] p {{
            color: {COLOR["text_muted"]} !important;
        }}

        /* ---------------- INTERNAL VIEW NAV (radio-based, styled as a sidebar list) ---------------- */
        .st-key-gc_view_nav div[role="radiogroup"] {{
            flex-direction: column;
            gap: 2px;
        }}
        .st-key-gc_view_nav label {{
            background: transparent !important;
            border: none !important;
            border-left: 2px solid transparent !important;
            border-radius: 0 6px 6px 0 !important;
            padding: 9px 12px !important;
            margin: 0 !important;
            width: 100%;
        }}
        .st-key-gc_view_nav label:hover {{
            background: {COLOR["surface_raised"]} !important;
        }}
        .st-key-gc_view_nav label div[data-testid="stMarkdownContainer"] p {{
            color: {COLOR["text_muted"]};
            font-size: 13px;
            font-weight: 600;
        }}
        .st-key-gc_view_nav label input:checked ~ div {{
            color: {COLOR["stat_high"]} !important;
        }}
        .st-key-gc_view_nav label:has(input:checked) {{
            border-left: 2px solid {COLOR["stat_high"]} !important;
            background: {COLOR["stat_high_dim"]} !important;
        }}
        .st-key-gc_view_nav label:has(input:checked) div[data-testid="stMarkdownContainer"] p {{
            color: {COLOR["stat_high"]} !important;
        }}

        /* ---------------- BUTTONS ---------------- */
        .stButton > button, .stDownloadButton > button {{
            background-color: {COLOR["surface_raised"]};
            color: {COLOR["text"]};
            border: 1px solid {COLOR["border"]};
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
            padding: 0.5rem 1.1rem;
            transition: border-color 0.15s ease, color 0.15s ease;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            border-color: {COLOR["accent"]};
            color: {COLOR["accent"]};
            background-color: {COLOR["surface_raised"]};
        }}
        .stButton > button:focus:not(:active) {{
            border-color: {COLOR["accent"]};
            color: {COLOR["accent"]};
        }}
        /* primary (type="primary") buttons */
        .stButton > button[kind="primary"] {{
            background-color: {COLOR["accent"]};
            color: #06110f;
            border: 1px solid {COLOR["accent"]};
        }}
        .stButton > button[kind="primary"]:hover {{
            background-color: {COLOR["accent"]};
            color: #06110f;
            opacity: 0.9;
        }}

        /* ---------------- INPUTS / SELECTS ---------------- */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stTextInput > div > div,
        .stNumberInput > div > div {{
            background-color: {COLOR["surface_raised"]} !important;
            border: 1px solid {COLOR["border"]} !important;
            border-radius: 6px !important;
            color: {COLOR["text"]} !important;
        }}
        /* The selected value text sits in a deeply nested BaseWeb element
           that sets its own color, bypassing the container rule above.
           Catch every descendant explicitly so the selected value is
           never invisible against our dark background. */
        div[data-baseweb="select"] div, div[data-baseweb="select"] span {{
            color: {COLOR["text"]} !important;
        }}
        div[data-baseweb="select"] > div:focus-within,
        .stTextInput > div > div:focus-within {{
            border-color: {COLOR["stat_high"]} !important;
            box-shadow: 0 0 0 1px {COLOR["stat_high"]} !important;
        }}
        input, textarea {{
            color: {COLOR["text"]} !important;
            font-family: 'JetBrains Mono', monospace !important;
        }}

        /* ---------------- METRICS ---------------- */
        .pf-metric-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 26px;
            font-weight: 700;
            color: {COLOR["stat_high"]};
        }}
        .pf-metric-label {{
            font-size: 11px;
            color: {COLOR["text_muted"]};
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-top: 2px;
        }}
        div[data-testid="stMetric"] {{
            background: {COLOR["surface"]};
            border: 1px solid {COLOR["border"]};
            border-radius: 8px;
            padding: 14px 16px;
        }}
        div[data-testid="stMetricValue"] {{
            font-family: 'JetBrains Mono', monospace !important;
            color: {COLOR["stat_high"]} !important;
        }}

        /* ---------------- STATUS BANNERS ---------------- */
        .pf-status {{
            border-radius: 8px;
            padding: 13px 16px;
            margin-bottom: 14px;
            font-size: 13.5px;
            font-weight: 500;
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }}
        .pf-status-icon {{ font-size: 15px; line-height: 1.4; }}
        .pf-status-error   {{ background: {COLOR["error_dim"]}; border: 1px solid {COLOR["error_border"]}; color: #f0a6b0; }}
        .pf-status-warning {{ background: {COLOR["warn_dim"]};  border: 1px solid {COLOR["warn_border"]};  color: #e8c47f; }}
        .pf-status-info    {{ background: {COLOR["cold_dim"]};  border: 1px solid {COLOR["cold_border"]};  color: #9db8cf; }}

        /* Restyle Streamlit's native alerts for anything not yet converted */
        div[data-testid="stAlert"] {{
            background: {COLOR["surface"]} !important;
            border: 1px solid {COLOR["border"]} !important;
            border-radius: 8px !important;
            color: {COLOR["text"]} !important;
        }}
        div[data-testid="stExpander"] {{
            background: {COLOR["surface"]};
            border: 1px solid {COLOR["border"]};
            border-radius: 8px;
        }}

        /* Divider */
        hr {{ border-color: {COLOR["border"]} !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "", eyebrow: str = "LOS CAPPERS"):
    """
    Renders the shared page header — eyebrow label, title, subtitle, accent
    rule. Use this on every page instead of st.title()/emoji headers so the
    whole app reads as one product.
    """
    import streamlit as st

    html = f'<div class="lc-eyebrow">{eyebrow}</div><h1 class="lc-title">{title}</h1>'
    if subtitle:
        html += f'<div class="lc-subtitle">{subtitle}</div>'
    html += '<div class="lc-rule"></div>'
    st.markdown(html, unsafe_allow_html=True)


def status_banner(kind: str, message: str, details: str = None):
    """
    Renders a clean, themed status banner instead of Streamlit's default
    bright st.error/st.warning boxes.
    kind: 'error', 'warning', or 'info'
    message: short, plain-language summary a non-technical user can read
    details: optional raw technical detail (exception text etc.), shown
             only inside a collapsed expander so it doesn't clutter the UI
    """
    import streamlit as st

    icon = {"error": "!", "warning": "!", "info": "i"}.get(kind, "i")
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
    style options: 'accent' / 'good' (signal cyan), 'bad' (cold steel), 'neutral'
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


def sport_switcher(active: str = "MLB"):
    """
    Clickable sport tab strip — rendered once, at app level (app.py),
    so it exists on every page. Uses st.segmented_control (the same
    native component the Game Card's pitcher picker uses) so it renders
    compact and consistent on any Streamlit version, with no CSS hacks.
    Only MLB is wired to real data; the other sports lead to their own
    "coming soon" pages rather than pretending to be live.
    Clicking sets st.session_state["lc_sport"] and reruns; app.py reads
    that to decide whether to render MLB navigation or a sport page.
    """
    import streamlit as st

    sports = ["MLB", "KBO", "NPB", "NBA", "NHL", "NFL"]
    st.session_state.setdefault("lc_sport", "MLB")

    choice = st.segmented_control(
        "Sport",
        sports,
        default=active if active in sports else "MLB",
        key="lc_sport_seg",
        label_visibility="collapsed",
    )
    st.markdown(
        f'<div style="text-align:center; font-size:8.5px; font-weight:700; '
        f'letter-spacing:0.14em; color:{COLOR["text_faint"]}; opacity:0.75; '
        f'margin-top:2px; text-transform:uppercase;">'
        f'MLB live · NBA / NHL / NFL soon</div>',
        unsafe_allow_html=True,
    )

    if choice and choice != active:
        st.session_state["lc_sport"] = choice
        st.rerun()


def card(key: str):
    """
    Real bordered card \u2014 use as `with card("my_key"):` and everything
    inside genuinely nests in one box.

    This replaces the old card_open()/card_close() raw-HTML pattern for
    any card that holds more than just a title: card_open() returns an
    unclosed <div>, but each st.markdown()/st.dataframe() call after it
    renders as its own sealed fragment in the browser \u2014 the div never
    actually stays open across calls, so anything past the title was
    silently escaping the card. st.container() is a genuine DOM
    container, so this doesn't have that problem.
    """
    import streamlit as st
    return st.container(key=f"card_{key}", border=False)


def card_close() -> str:
    return "</div>"


# Real sabermetric convention: each pitch type gets a fixed color
# (matches Baseball Savant's own pitch-type coloring), not a random
# rainbow \u2014 this makes pitch mix instantly recognizable to anyone
# who's used other baseball data tools.
PITCH_COLORS = {
    "FF": "#e5484d", "FA": "#e5484d",          # four-seam \u2014 red
    "SI": "#e8823c", "FT": "#e8823c",          # sinker \u2014 orange
    "FC": "#e8a23c",                            # cutter \u2014 amber
    "SL": "#e8c247",                            # slider \u2014 yellow
    "ST": "#30a46c",                            # sweeper \u2014 green
    "CU": "#4a6fa5", "KC": "#4a6fa5", "CS": "#4a6fa5",  # curveball family \u2014 blue
    "CH": "#00E5FF",                             # changeup \u2014 cyan
    "FS": "#8a63d2", "SV": "#8a63d2",            # splitter/screwball \u2014 purple
    "KN": "#9aa3ad",                             # knuckleball \u2014 gray
}
PITCH_NAMES = {
    "FF": "4-Seam", "FA": "Fastball", "SI": "Sinker", "FT": "2-Seam",
    "FC": "Cutter", "SL": "Slider", "ST": "Sweeper", "CU": "Curveball",
    "KC": "Knuckle Curve", "CS": "Slow Curve", "CH": "Changeup",
    "FS": "Splitter", "SV": "Screwball", "KN": "Knuckleball",
}


def pitch_color(pitch_type: str) -> str:
    return PITCH_COLORS.get(pitch_type, COLOR["text_faint"])


def pitch_color_by_name(name: str) -> str:
    """Same real pitch colors, looked up by the READABLE name (e.g.
    "4-Seam") instead of the raw Statcast code (e.g. "FF") — for
    tables that display the friendly name rather than the code."""
    for code, n in PITCH_NAMES.items():
        if n == name and code in PITCH_COLORS:
            return PITCH_COLORS[code]
    return COLOR["text_faint"]


def pitch_name(pitch_type: str) -> str:
    return PITCH_NAMES.get(pitch_type, pitch_type)


def internal_nav(items: list, active: str, key: str) -> str:
    """
    Vertical icon-strip-style nav rendered as a themed radio group \u2014
    used for switching between views WITHIN one page (Matchup / Top
    Plays / etc.) so the selected game context never resets. This is
    deliberately NOT Streamlit's page-level st.navigation \u2014 that would
    force a full page reload and lose the selected game, exactly the
    friction this redesign was meant to remove.
    """
    import streamlit as st
    return st.radio(key, items, index=items.index(active) if active in items else 0,
                     key=key, label_visibility="collapsed")


def edge_tag(label: str, tier: str) -> str:
    """
    Colored edge/opportunity tag for the Top Plays table.
    tier: 'strong' (teal, our brand positive), 'good' (amber, positive
    but softer), 'neutral' (gray), 'risk' (red \u2014 the one place in this
    app that intentionally breaks from the teal-only palette, because
    "this is a risk" needs to read as unambiguous as a stop sign).
    """
    colors = {
        "strong": (COLOR["stat_high_dim"], COLOR["stat_high"], COLOR["stat_high_border"]),
        "good":   (COLOR["warn_dim"], COLOR["warn"], COLOR["warn_border"]),
        "neutral":(COLOR["stat_mid_dim"], COLOR["stat_mid_text"], COLOR["stat_mid_border"]),
        "risk":   (COLOR["error_dim"], COLOR["error"], COLOR["error_border"]),
    }
    bg, fg, border = colors.get(tier, colors["neutral"])
    return (
        f'<span style="display:inline-block; padding:4px 10px; border-radius:4px; '
        f'background:{bg}; color:{fg}; border:1px solid {border}; font-size:12px; '
        f'font-weight:600; font-family:\'JetBrains Mono\',monospace;">{label}</span>'
    )


def footer():
    """Shared site footer — disclosure + build identity. Call once at the
    bottom of every page so the legal/responsible-gambling language is
    never accidentally left off a page."""
    import streamlit as st

    st.markdown(
        f"""
        <div style="margin-top:2.5rem; padding-top:16px; border-top:1px solid {COLOR["border"]};
                    font-size:11px; color:{COLOR["text_faint"]}; line-height:1.7;">
        Los Cappers provides statistical models for informational and entertainment
        purposes only. Nothing on this site is betting advice or a guarantee of
        outcome. You must be of legal betting age in your jurisdiction. Problem
        gambling help: 1-800-GAMBLER.
        </div>
        """,
        unsafe_allow_html=True,
    )


def data_timestamp(label: str = "Data refreshed"):
    """Renders a small monospace 'as-of' timestamp. Call right under a page
    header on any page that pulls live data — on a paid data product, users
    should always be able to see how fresh what they're looking at is."""
    import streamlit as st
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    st.markdown(
        f'<div style="text-align:center; font-family:\'JetBrains Mono\',monospace; '
        f'font-size:11px; color:{COLOR["text_faint"]}; margin-top:-10px; margin-bottom:1.4rem;">'
        f'{label}: {now}</div>',
        unsafe_allow_html=True,
    )