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
    "cold":          "#5B8FC7",   # brighter steel blue (was #4a6b8a, washed out)
    "cold_dim":      "rgba(91, 143, 199, 0.16)",
    "cold_border":   "rgba(91, 143, 199, 0.45)",
    "warn":          "#F2B544",   # amber, lifted (was a muddy #E9A94B)
    "warn_dim":      "rgba(242, 181, 68, 0.14)",
    "warn_border":   "rgba(242, 181, 68, 0.4)",
    "error":         "#F2555A",   # cleaner red (was #D64545, read as brick)
    "error_dim":     "rgba(242, 85, 90, 0.14)",
    "error_border":  "rgba(214, 69, 69, 0.4)",
    # Identity colors — player names and handedness. Deliberately NOT
    # part of the red/amber/blue heatmap scale, since those are
    # reserved for the heatmap's good/mid/bad meaning. These are pure
    # identity signals, not value judgments, so a player's name or
    # handedness always reads as "information" rather than "score."
    # Near-white, not violet.
    #
    # The name is the row's ANCHOR — it's what you scan down to find
    # someone, and it should be the most legible thing in the row.
    # #9C7BFF competed with the heatmap for attention while being harder
    # to read than plain text, and a wall of violet names was the loudest
    # thing on a page whose point is the numbers. Weight and size make it
    # the anchor now; colour is reserved for values that mean something.
    "player_name":   "#F0F4F7",
    "bats_l":        "#5CCEFF",   # sky blue
    "bats_r":        "#FF8A65",   # warm coral — replaces the too-dark slate grey
    "bats_s":        "#B8860B",   # dark goldenrod (metallic gold)
    # Gold marks a SECTION HEADING and nothing else.
    #
    # It used to be described as "secondary text, labels, captions",
    # which meant it was the colour of ordinary prose in 106 places. A
    # colour that means "text" means nothing, so when something genuinely
    # was important there was no emphasis left to reach for. Labels are
    # text_muted, values are text, headings are gold. If a new use
    # doesn't fit one of those three, it doesn't need a colour.
    "gold":          "#D4AF37",   # section headings only (.pf-card-title)
    # RETIRED — zero call sites. Kept only so an old branch referencing
    # it doesn't KeyError. Delete once nothing in history needs it.
    "magenta_purple":"#D946EF",   # (unused)
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


# ---------------------------------------------------------
# TYPE — the only place font sizes should be defined
#
# There were 188 inline font-size declarations across 19 distinct
# values, drifting in half-pixel steps: 8.5, 9.5, 10.5, 11.5, 12.5,
# 13.5. Nothing was wrong with any single one; the problem was that
# "make the tables a bit denser" meant editing 188 separate strings
# spread across the views, and each edit was a fresh guess. COLOR had
# been a single source of truth since day one and type never was.
#
# Eleven steps, not the usual five or six, on purpose. This is a data
# terminal — the gap between a table cell and its sub-label is one
# pixel of real information density, and collapsing those into one step
# would flatten the hierarchy the boards depend on. Every step below
# maps to sizes already in use, so adopting them changes nothing
# visually on its own. That's the point: the sweep is safe, and the
# redesign happens afterwards by editing this dict.
# ---------------------------------------------------------
TYPE = {
    "micro":    "9px",    # dense table sub-labels, footnotes
    "tiny":     "10px",   # eyebrows, badge text, legends
    "caption":  "11px",   # captions, secondary metadata
    "small":    "12px",   # dense table cells, chips
    "body":     "13px",   # default body text and primary table text
    "body_lg":  "14px",   # emphasised body, row anchors
    "subhead":  "16px",   # card titles
    "title":    "20px",   # page and section titles
    # stat and display are deliberately NOT merged. 22px is the large
    # paired stat readout on the Game Card; 26px is the single headline
    # matchup line, the one thing on the page allowed to be the largest.
    # They read as one step apart but they are different jobs, and
    # collapsing them would silently demote the headline.
    "stat":     "22px",   # large paired stat readout
    "display":  "26px",   # the one headline per page
    "hero":     "32px",   # the page header itself (.lc-title)
}

# ---------------------------------------------------------
# SPACE — 4px grid, with a 2px half-step
#
# 103 distinct padding/margin values existed across the views, including
# 5px, 9px and 14px one-offs. The grid below covers every one of them
# within a pixel or two, which is under the threshold anyone can see and
# well under the threshold anyone can see CONSISTENTLY.
# ---------------------------------------------------------
SPACE = {
    "none": "0",
    "hair": "2px",
    "xs":   "4px",
    "sm":   "6px",
    "md":   "8px",
    "lg":   "12px",
    "xl":   "16px",
    "2xl":  "24px",
    "3xl":  "32px",
}

# ---------------------------------------------------------
# RADIUS — four size steps plus the two shape primitives.
#
# Ten different values were in use, and three of them differed from
# another only by the space after the colon.
# ---------------------------------------------------------
RADIUS = {
    "sm":     "3px",   # chips, badges, table cells
    "md":     "6px",   # buttons, inputs
    "lg":     "8px",   # panels, table containers
    "xl":     "12px",  # the raised card surface
    "pill":   "999px",
    "circle": "50%",
}


def css_variables() -> str:
    """The token dicts as CSS custom properties.

    Emitted into :root by inject_kc_theme so that raw CSS blocks and
    Python f-strings read from the SAME source. Before this, the CSS in
    this file hardcoded its own sizes while the views hardcoded theirs,
    so the two could disagree and regularly did.

    Prefixed lc- to avoid collision with Streamlit's own variables.
    """
    lines = [f"--lc-color-{k.replace('_', '-')}: {v};" for k, v in COLOR.items()]
    lines += [f"--lc-text-{k.replace('_', '-')}: {v};" for k, v in TYPE.items()]
    lines += [f"--lc-space-{k}: {v};" for k, v in SPACE.items()]
    lines += [f"--lc-radius-{k}: {v};" for k, v in RADIUS.items()]
    return ":root {\n  " + "\n  ".join(lines) + "\n}"


def inject_kc_theme():
    import streamlit as st

    st.markdown(
        f"""
        <style>
        /* ---------- Design tokens ----------
           Generated from COLOR/TYPE/SPACE/RADIUS above. Braces are
           doubled because this whole block is an f-string; css_variables()
           returns plain CSS, so it is inserted with a single {{}} pair and
           needs no escaping itself. */
        {css_variables()}

        /* ---------- Mobile / small screens ---------- */
        /* IMPORTANT: this block used to force
           `stHorizontalBlock {{ flex-wrap: wrap }}` on EVERY row of
           columns site-wide. That fought Streamlit's own built-in mobile
           behavior (columns stack to full width, one per row, below
           640px) and instead squeezed things like the Game Card's
           content/nav columns side-by-side into slivers — that was the
           main "nightmare to navigate" cause on phones. Fixed by letting
           Streamlit's native stacking do its job everywhere, and only
           opting specific rows (badge/pill rows, the game-picker
           carousel) back into horizontal scrolling where that's
           actually wanted. Those opt-ins are handled by their own
           scoped `.st-key-...` rules elsewhere in this file, not here. */
        @media (max-width: 700px) {{
            html, body {{ overflow-x: hidden !important; }}
            .stApp {{ overflow-x: hidden !important; }}

            .lc-title {{ font-size:var(--lc-text-stat) !important; }}
            .lc-subtitle {{ font-size:var(--lc-text-small) !important; }}
            .lc-eyebrow {{ font-size:var(--lc-text-tiny) !important; }}
            .block-container {{
                padding-left: 0.9rem !important;
                padding-right: 0.9rem !important;
                padding-top: 1.6rem !important;
                max-width: 100vw !important;
            }}
            .pf-card, div[class*="st-key-card_"] {{ padding:var(--lc-space-lg) var(--lc-space-lg) !important; }}
            .pf-metric-value {{ font-size:var(--lc-text-title) !important; }}

            /* Columns: let Streamlit's native full-width stacking apply.
               Just make sure nothing inside a stacked column can force
               the page wider than the viewport (long team names, wide
               badges, etc.), and give stacked rows a bit of breathing
               room between them. */
            div[data-testid="stHorizontalBlock"] {{
                gap: 0.6rem !important;
            }}
            div[data-testid="stHorizontalBlock"] > div {{
                width: 100% !important;
                min-width: 0 !important;
                max-width: 100% !important;
            }}

            /* Tables/dataframes: scroll horizontally WITHIN their own
               box instead of pushing the whole page sideways. */
            div[data-testid="stDataFrame"], div[data-testid="stTable"] {{
                font-size:var(--lc-text-caption) !important;
                max-width: 100% !important;
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch;
            }}

            /* Buttons, pills, and the view-nav radio need real touch
               targets on mobile — the desktop sizing (0.5rem padding)
               is too small to reliably tap. */
            .stButton > button, .stDownloadButton > button {{
                min-height: 40px !important;
                padding: 0.55rem 1rem !important;
                font-size:var(--lc-text-body-lg) !important;
            }}
            div[data-testid="stButtonGroup"] button {{
                min-height: 38px !important;
                font-size:var(--lc-text-body) !important;
            }}
            .st-key-gc_view_nav label {{
                padding:var(--lc-space-lg) var(--lc-space-lg) !important;
            }}
            .st-key-gc_view_nav label div[data-testid="stMarkdownContainer"] p {{
                font-size:var(--lc-text-body-lg) !important;
            }}

            /* Sidebar: full-width and comfortably tappable when open. */
            section[data-testid="stSidebar"] {{ min-width: 82vw !important; }}

            /* Long unbroken strings (team/venue names inside badges,
               wordmark, etc.) wrap instead of forcing horizontal scroll. */
            .pf-badge, .pf-card-title, .pf-card-subtitle {{
                white-space: normal !important;
                word-break: break-word !important;
            }}
        }}

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
            font-size:var(--lc-text-small);
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {{
            color: {COLOR["text"]} !important;
            font-size:var(--lc-text-body) !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            border-left: 2px solid {COLOR["accent"]};
            padding-left:var(--lc-space-md);
            margin-top: 1.4rem !important;
            margin-bottom: 0.6rem !important;
        }}

        /* ---------------- PAGE HEADER ---------------- */
        .lc-eyebrow {{
            /* Left-aligned, not centred. The nav row and the Sync button
               under this header are left-aligned, so a centred title put
               two competing axes on one screen — which is what made the
               top of every page feel unsettled even after the ordering
               bug was fixed. One axis, top to bottom. */
            text-align: left;
            font-size:var(--lc-text-caption);
            font-weight: 700;
            color: {COLOR["accent"]};
            text-transform: uppercase;
            letter-spacing: 0.18em;
            margin-bottom:var(--lc-space-sm);
        }}
        .lc-title {{
            text-align: left;
            font-size:var(--lc-text-hero);
            font-weight: 800;
            letter-spacing: -0.01em;
            color: {COLOR["text"]};
            margin-bottom:var(--lc-space-xs);
        }}
        .lc-subtitle {{
            text-align: left;
            font-size:var(--lc-text-body);
            font-weight: 500;
            color: {COLOR["text_muted"]};
            margin-bottom: 1.6rem;
        }}
        .lc-rule {{
            width: 64px;
            height: 2px;
            background: {COLOR["accent"]};
            /* was `auto` both sides to centre under a centred title; the
               title is left-aligned now, so the rule anchors to the same
               left edge instead of floating mid-page. */
            margin: 14px auto 1.6rem 0;
        }}

        /* Section labels — replaces default h3/subheader look everywhere */
        h3 {{
            color: {COLOR["text"]} !important;
            font-size:var(--lc-text-body-lg) !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-left: 3px solid {COLOR["accent"]};
            padding-left:var(--lc-space-md);
            margin-top: 1.6rem !important;
        }}
        h1, h2 {{ color: {COLOR["text"]} !important; }}

        /* ---------------- CARDS ---------------- */
        /* Real container-based cards (see card() in this file) \u2014 matches
           any st.container(key="card_...") so every card gets this
           styling with no per-card CSS needed. */
        /* THIS is the rule that actually draws every card on the page.
           card() returns a Streamlit container keyed st-key-card_*, so
           .pf-card above only covers the handful of raw-HTML cards —
           restyling that one alone changed nothing visible.

           No border, no 3px top bar. The old card was outlined in teal
           with a bright bar across the top, which drew a hard rectangle
           around every panel and made the page read as a grid of boxes.
           Separation now comes from a slightly lifted surface and a
           shadow, so panels read as depth rather than as frames. */
        div[class*="st-key-card_"] {{
            background: linear-gradient(165deg, {COLOR["surface_raised"]} 0%, {COLOR["surface"]} 100%) !important;
            border: none !important;
            border-radius:var(--lc-radius-xl) !important;
            padding:var(--lc-space-xl) var(--lc-space-xl) !important;
            margin-bottom:var(--lc-space-lg) !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.4),
                        0 10px 30px -14px rgba(0,0,0,0.55) !important;
        }}

        /* Glossary gets its own accent — real bloody red instead of the
           page's default cyan, so it reads as a distinct reference
           section rather than another stat card. */
        div[class*="st-key-card_glossary"] {{
            /* Still distinct from a stat card, but by TINT rather than by
               an outline — same reasoning as the rule above. */
            background: linear-gradient(165deg, {COLOR["error_dim"]}, {COLOR["surface"]} 70%) !important;
            border: none !important;
        }}

        .pf-card {{
            /* Soft raised surface, not a boxed frame.
               The old card had a 1px teal border AND a 3px teal bar
               across the top, which drew a hard rectangle around every
               panel and made the page read as a stack of boxes. Depth
               now comes from a lifted background and a shadow — the same
               language as the score bars — so the panel reads as a
               surface rather than an outline. */
            background: linear-gradient(165deg, {COLOR["surface_raised"]} 0%, {COLOR["surface"]} 100%);
            border: 1px solid {COLOR["border_soft"]};
            border-radius:var(--lc-radius-xl);
            padding:var(--lc-space-xl) var(--lc-space-xl);
            margin-bottom:var(--lc-space-lg);
            box-shadow: 0 1px 3px rgba(0,0,0,0.35),
                        0 8px 24px -12px rgba(0,0,0,0.5);
        }}
        .pf-card-title {{
            font-weight: 700;
            font-size:var(--lc-text-body-lg);
            color: {COLOR["text"]};
            margin-bottom:var(--lc-space-xs);
            letter-spacing: 0.01em;
        }}
        .pf-card-subtitle {{
            font-size:var(--lc-text-small);
            color: {COLOR["text_muted"]};
            margin-bottom:var(--lc-space-lg);
        }}

        /* ---------------- BADGES ---------------- */
        .pf-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding:var(--lc-space-xs) var(--lc-space-lg);
            border-radius:var(--lc-radius-sm);
            font-size:var(--lc-text-small);
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
            margin-right:var(--lc-space-md);
            margin-bottom:var(--lc-space-sm);
        }}
        .pf-badge-accent  {{ background: {COLOR["stat_high_dim"]}; color: {COLOR["stat_high"]};    border: 1px solid {COLOR["stat_high_border"]}; }}
        .pf-badge-good    {{ background: {COLOR["stat_high_dim"]}; color: {COLOR["stat_high"]};    border: 1px solid {COLOR["stat_high_border"]}; }}
        .pf-badge-bad     {{ background: {COLOR["stat_low_dim"]};  color: {COLOR["stat_low_text"]}; border: 1px solid {COLOR["stat_low_border"]}; }}
        .pf-badge-neutral {{ background: {COLOR["stat_mid_dim"]};  color: {COLOR["stat_mid_text"]}; border: 1px solid {COLOR["stat_mid_border"]}; }}

        /* ---------------- DATAFRAMES / TABLES ---------------- */
        div[data-testid="stDataFrame"], div[data-testid="stTable"] {{
            border-radius:var(--lc-radius-md);
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
            padding:var(--lc-space-sm) var(--lc-space-lg);
            border-bottom: 1px solid {COLOR["border_soft"]};
            font-size:var(--lc-text-small);
        }}
        div[data-testid="stDataFrame"] table th, div[data-testid="stTable"] table th {{
            color: {COLOR["text_muted"]};
            text-transform: uppercase;
            font-size:var(--lc-text-tiny);
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
            font-size:var(--lc-text-body);
            padding:var(--lc-space-md) var(--lc-space-xs);
        }}
        .stTabs [aria-selected="true"] {{
            color: {COLOR["accent"]} !important;
            border-bottom: 2px solid {COLOR["accent"]} !important;
        }}

        /* Streamlit adds ~1rem of margin between every single element by
           default \u2014 on a page with this many stacked widgets/cards that
           adds up to real, unnecessary scroll. Tighten it globally. */
        div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] {{
            margin-bottom:var(--lc-space-xs) !important;
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
            border-radius:var(--lc-radius-md) !important;
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
            padding-bottom:var(--lc-space-md);
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
            font-size:var(--lc-text-body);
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
            padding:var(--lc-space-md) var(--lc-space-lg) !important;
            margin:var(--lc-space-none) !important;
            width: 100%;
        }}
        .st-key-gc_view_nav label:hover {{
            background: {COLOR["surface_raised"]} !important;
        }}
        .st-key-gc_view_nav label div[data-testid="stMarkdownContainer"] p {{
            color: {COLOR["text_muted"]};
            font-size:var(--lc-text-body);
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
            border-radius:var(--lc-radius-md);
            font-weight: 600;
            font-size:var(--lc-text-body);
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
            border-radius:var(--lc-radius-md) !important;
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
            font-size:var(--lc-text-display);
            font-weight: 700;
            color: {COLOR["stat_high"]};
        }}
        .pf-metric-label {{
            font-size:var(--lc-text-caption);
            color: {COLOR["text_muted"]};
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-top:var(--lc-space-hair);
        }}
        div[data-testid="stMetric"] {{
            background: {COLOR["surface"]};
            border: 1px solid {COLOR["border"]};
            border-radius:var(--lc-radius-lg);
            padding:var(--lc-space-lg) var(--lc-space-xl);
        }}
        div[data-testid="stMetricValue"] {{
            font-family: 'JetBrains Mono', monospace !important;
            color: {COLOR["stat_high"]} !important;
        }}

        /* ---------------- STATUS BANNERS ---------------- */
        .pf-status {{
            border-radius:var(--lc-radius-lg);
            padding:var(--lc-space-lg) var(--lc-space-xl);
            margin-bottom:var(--lc-space-lg);
            font-size:var(--lc-text-body);
            font-weight: 500;
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }}
        .pf-status-icon {{ font-size:var(--lc-text-body-lg); line-height: 1.4; }}
        .pf-status-error   {{ background: {COLOR["error_dim"]}; border: 1px solid {COLOR["error_border"]}; color: #f0a6b0; }}
        .pf-status-warning {{ background: {COLOR["warn_dim"]};  border: 1px solid {COLOR["warn_border"]};  color: #e8c47f; }}
        .pf-status-info    {{ background: {COLOR["cold_dim"]};  border: 1px solid {COLOR["cold_border"]};  color: #9db8cf; }}

        /* Restyle Streamlit's native alerts for anything not yet converted */
        div[data-testid="stAlert"] {{
            background: {COLOR["surface"]} !important;
            border: 1px solid {COLOR["border"]} !important;
            border-radius:var(--lc-radius-lg) !important;
            color: {COLOR["text"]} !important;
        }}
        div[data-testid="stExpander"] {{
            background: {COLOR["surface"]};
            border: 1px solid {COLOR["border"]};
            border-radius:var(--lc-radius-lg);
        }}

        /* Divider */
        hr {{ border-color: {COLOR["border"]} !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


SPORT_ACCENTS = {
    "MLB": None,             # MLB keeps the house style
    "KBO": "#4FA3FF",
    "NPB": "#E4573D",
    "WNBA": "#FF7A00",
    "NBA": "#E03A3E",
    "NHL": "#9BB0C1",
    "NFL": "#3B82F6",
}


def page_header(title: str, subtitle: str = "", eyebrow: str = "LOS CAPPERS",
                accent: str = None, align: str = "center"):
    """
    Renders the shared page header — eyebrow label, title, subtitle, accent
    rule. Use this on every page instead of st.title()/emoji headers so the
    whole app reads as one product.

    accent: hex color for the title/eyebrow/rule. If not given, it's
    auto-detected from the title's first word (see SPORT_ACCENTS), so each
    sport's pages carry their own identity with zero per-page changes.
    """
    import streamlit as st

    if accent is None:
        accent = SPORT_ACCENTS.get((title.split() or [""])[0])

    # align: "center" (default, unchanged for every existing page) or
    # "left". Left-aligning puts the title on the SAME vertical axis as
    # the nav and content below it; centred titles over left-aligned
    # controls are what makes a page top feel unsettled. Opt-in per page
    # rather than a global flip, so adopting it anywhere is a one-word
    # change and adopting it nowhere costs nothing.
    _left = align == "left"
    _al = "text-align:left;" if _left else ""
    _rule_al = "margin-left:0;margin-right:auto;" if _left else ""

    eb_style = f' style="{_al}color:{accent};"' if accent else (f' style="{_al}"' if _left else "")
    ti_style = f' style="{_al}color:{accent};"' if accent else (f' style="{_al}"' if _left else "")
    sub_style = f' style="{_al}"' if _left else ""
    rule_style = (f' style="{_rule_al}background:{accent};"' if accent
                  else (f' style="{_rule_al}"' if _left else ""))

    html = (f'<div class="lc-eyebrow"{eb_style}>{eyebrow}</div>'
            f'<h1 class="lc-title"{ti_style}>{title}</h1>')
    if subtitle:
        html += f'<div class="lc-subtitle"{sub_style}>{subtitle}</div>'
    html += f'<div class="lc-rule"{rule_style}></div>'
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

    sports = ["MLB", "KBO", "NPB", "WNBA", "NBA", "NHL", "NFL"]
    st.session_state.setdefault("lc_sport", "MLB")

    choice = st.segmented_control(
        "Sport",
        sports,
        default=active if active in sports else "MLB",
        key="lc_sport_seg",
        label_visibility="collapsed",
    )
    st.markdown(
        f'<div style="text-align:center; font-size:var(--lc-text-micro); font-weight:700; '
        f'letter-spacing:0.14em; color:{COLOR["text_faint"]}; opacity:0.75; '
        f'margin-top:var(--lc-space-hair); text-transform:uppercase;">'
        f'MLB · KBO · NPB · WNBA live — NBA / NHL / NFL soon</div>',
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
        f'<span style="display:inline-block; padding:var(--lc-space-xs) var(--lc-space-md); border-radius:var(--lc-radius-sm); '
        f'background:{bg}; color:{fg}; border:1px solid {border}; font-size:var(--lc-text-small); '
        f'font-weight:600; font-family:\'JetBrains Mono\',monospace;">{label}</span>'
    )


def coming_soon_page(sport: str, emoji: str, blurb_tail: str, planned):
    """The whole body of a not-yet-built sport page.

    NFL.py, NBA.py and NHL.py were three 51-line files differing only by
    a sport name, an emoji, and three title/description pairs — about 150
    lines to say the same thing three times. Any copy edit to the shared
    promise ("no placeholders, no estimates, no filler") had to be made
    in three places or the pages quietly disagreed with each other, which
    is a bad look on the one line that IS the site's pitch.

    `planned` is a list of (title, description) pairs, rendered in order.

    Each page draws its own SPORT_ACCENTS colour, so a visitor landing on
    NHL sees the same identity system the live pages use rather than the
    MLB house style on a page that isn't MLB.
    """
    import streamlit as st

    accent = SPORT_ACCENTS.get(sport) or COLOR["accent"]

    page_header(f"{sport} Analytics",
                "In development \u2014 built on real data or not at all",
                eyebrow="COMING SOON")

    st.markdown(card_open(f"{emoji} {sport} is on the roadmap"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-body-lg); '
        f'line-height:1.7;">'
        f'{sport} tools are being built on the same standard as the MLB engine: '
        f'every number traced to a real, verifiable source \u2014 no placeholders, '
        f'no estimates, no filler. {blurb_tail}'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(card_close(), unsafe_allow_html=True)

    st.markdown(card_open("What's planned"), unsafe_allow_html=True)
    for title, desc in planned:
        st.markdown(
            f'<div style="margin-bottom:var(--lc-space-lg);">'
            f'<div style="font-weight:700; color:{COLOR["text"]}; '
            f'font-size:var(--lc-text-body);">{title}</div>'
            f'<div style="color:{COLOR["text_muted"]}; '
            f'font-size:var(--lc-text-small);">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown(card_close(), unsafe_allow_html=True)

    st.markdown(
        badge("MLB \u2014 live now", "good")
        + badge(f'{sport} \u2014 in development', "neutral"),
        unsafe_allow_html=True,
    )
    footer()


def footer():
    """Shared site footer — disclosure + build identity. Call once at the
    bottom of every page so the legal/responsible-gambling language is
    never accidentally left off a page."""
    import streamlit as st

    st.markdown(
        f"""
        <div style="margin-top:2.5rem; padding-top:var(--lc-space-xl); border-top:1px solid {COLOR["border"]};
                    font-size:var(--lc-text-caption); color:{COLOR["text_faint"]}; line-height:1.7;">
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
        f'font-size:var(--lc-text-caption); color:{COLOR["text_faint"]}; margin-top:-10px; margin-bottom:1.4rem;">'
        f'{label}: {now}</div>',
        unsafe_allow_html=True,
    )
