"""
ORC Research Dashboard - Design System
Enterprise-grade, minimalist UI with full dark/light theme support.
Call apply_styles() at the top of every page (after set_page_config).
"""

import streamlit as st

# ── Colour palette ────────────────────────────────────────────────────────────
# WCAG AA-compliant contrast in both modes; inspired by GitHub's design system.

DARK = {
    "bg":       "#0d1117",
    "surface":  "#161b22",
    "surface2": "#21262d",
    "border":   "#30363d",
    "accent":   "#2f81f7",
    "accent2":  "#a371f7",
    "success":  "#3fb950",
    "warning":  "#d29922",
    "error":    "#f85149",
    "text":     "#e6edf3",
    "text2":    "#8b949e",
    "muted":    "#6e7681",
}

LIGHT = {
    "bg":       "#ffffff",
    "surface":  "#f6f8fa",
    "surface2": "#edf2f7",
    "border":   "#d0d7de",
    "accent":   "#0969da",
    "accent2":  "#8250df",
    "success":  "#1a7f37",
    "warning":  "#9a6700",
    "error":    "#cf222e",
    "text":     "#1f2328",
    "text2":    "#656d76",
    "muted":    "#6e7781",
}

# ── Theme-aware chart helpers ─────────────────────────────────────────────────

def get_theme() -> str:
    """
    Determine the active UI theme mode from the Streamlit session.
    
    Returns:
        str: 'dark' or 'light' representing the active theme; defaults to 'dark' if no theme is set in session state.
    """
    return st.session_state.get("theme_mode", "dark")


def chart_colors() -> list:
    """
    Provide an ordered list of hex color strings for charts based on the active theme.
    
    Returns:
        colors (list): Ordered list of hex color strings — theme accent colors first, followed by a fixed set of fallback colors.
    """
    c = DARK if get_theme() == "dark" else LIGHT
    return [
        c["accent"], c["accent2"], c["success"], c["warning"],
        "#e11d48", "#0891b2", "#f97316", "#059669",
    ]


PLOTLY_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "toImageButtonOptions": {"format": "png", "filename": "orc_chart", "scale": 2},
}


def chart_layout(title: str = "", height: int = 0) -> dict:
    """
    Builds a Plotly layout dictionary configured for the current theme.
    
    Parameters:
        title (str): Optional chart title; when provided a left-aligned title block is added to the layout.
        height (int): Optional layout height in pixels; when non-zero the layout's `height` field is set.
    
    Returns:
        layout (dict): A Plotly-compatible layout dictionary with colors, fonts, axes, legend, margins, and hoverlabel styling matching the active theme.
    """
    c = DARK if get_theme() == "dark" else LIGHT
    base = {
        "plot_bgcolor":  "rgba(0,0,0,0)",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "font":   {"color": c["text"], "family": "Inter, system-ui, sans-serif", "size": 13},
        "xaxis":  {
            "gridcolor": c["border"], "linecolor": c["border"],
            "tickcolor": c["border"],
            "tickfont": {"color": c["text"], "size": 12},
            "title_font": {"color": c["text"], "size": 13},
        },
        "yaxis":  {
            "gridcolor": c["border"], "linecolor": c["border"],
            "tickcolor": c["border"],
            "tickfont": {"color": c["text"], "size": 12},
            "title_font": {"color": c["text"], "size": 13},
        },
        "legend": {"font": {"color": c["text"], "size": 12}, "bgcolor": "rgba(0,0,0,0)"},
        "margin": {"l": 8, "r": 8, "t": 36 if title else 12, "b": 8},
        "hoverlabel": {
            "bgcolor": c["surface2"], "font_color": c["text"],
            "bordercolor": c["border"],
        },
    }
    if title:
        base["title"] = {
            "text": title,
            "font": {"color": c["text"], "size": 15, "family": "Inter, sans-serif"},
            "x": 0, "xanchor": "left", "pad": {"l": 4},
        }
    if height:
        base["height"] = height
    return base


# ── Base CSS (theme-independent) ──────────────────────────────────────────────
_BASE_CSS = """
<style>
/* ── Hide Streamlit chrome ──────────────────────────── */
#MainMenu, footer, .stDeployButton          { visibility: hidden !important; display: none !important; }
[data-testid="stToolbar"]                   { display: none !important; }
[data-testid="stHeader"]                    { display: none !important; }
[data-testid="stSidebarNav"]                { display: none !important; }
[data-testid="collapsedControl"]            { display: none !important; }
[data-testid="stSidebarCollapsedControl"]   { display: none !important; }
[data-testid="stSidebarOpenButton"]         { display: none !important; }
[data-testid="stDecoration"]                { display: none !important; }
button[aria-label="Open sidebar"]           { display: none !important; }
section[data-testid="stSidebar"]            { display: none !important; }

/* ── Typography ─────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif !important; }

/* ── Layout ─────────────────────────────────────────── */
.block-container,
[data-testid="stMainBlockContainer"] { padding-top: 0.5rem !important; max-width: 1200px !important; }

/* ── Top navigation bar ─────────────────────────────── */
.orc-navbar {
    display: flex;
    align-items: center;
    gap: 0.15rem;
    padding: 0.35rem 0.75rem;
    margin: -0.5rem -1rem 1.25rem;
    border-bottom-width: 1px;
    border-bottom-style: solid;
    position: sticky;
    top: 0;
    z-index: 999;
    flex-wrap: wrap;
}
.orc-nav-logo {
    font-size: 0.88rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin-right: 0.75rem;
    padding-right: 0.75rem;
    border-right-width: 1px;
    border-right-style: solid;
    white-space: nowrap;
}
.orc-nav-item {
    text-decoration: none !important;
    padding: 0.3rem 0.6rem;
    border-radius: 5px;
    font-size: 0.8rem;
    font-weight: 500;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
}
@media (max-width: 768px) {
    .orc-navbar { gap: 0.1rem; padding: 0.3rem 0.5rem; }
    .orc-nav-logo { display: none; }
    .orc-nav-item { padding: 0.25rem 0.4rem; font-size: 0.75rem; }
}

/* ── Card ───────────────────────────────────────────── */
.orc-card {
    border-radius: 6px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.65rem;
}

/* ── Metric card ─────────────────────────────────────── */
.orc-metric {
    border-radius: 6px;
    padding: 1.4rem 1.1rem;
    text-align: center;
}
.orc-metric .orc-metric-icon { font-size: 1.3rem; margin-bottom: 0.4rem; opacity: 0.75; }
.orc-metric .orc-metric-val  {
    font-size: 1.85rem; font-weight: 700; line-height: 1.1;
    letter-spacing: -0.02em;
}
.orc-metric .orc-metric-lbl  {
    font-size: 0.68rem; font-weight: 600; margin-top: 0.3rem;
    text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.55;
}

/* ── Publication card ───────────────────────────────── */
.orc-pub {
    border-radius: 6px;
    padding: 0.9rem 1.1rem 0.9rem 1.4rem;
    margin-bottom: 0.45rem;
    border-left: 3px solid transparent;
    position: relative;
}
.orc-pub .orc-pub-title { font-size: 0.93rem; font-weight: 600; margin: 0 0 0.25rem; line-height: 1.45; }
.orc-pub .orc-pub-meta  { font-size: 0.77rem; margin: 0.1rem 0 0; opacity: 0.7; }

/* ── Badges ─────────────────────────────────────────── */
.orc-badge {
    display: inline-block;
    font-size: 0.67rem; font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
    margin-right: 0.25rem;
    text-transform: uppercase; letter-spacing: 0.04em;
    vertical-align: middle;
}

/* ── Hero ───────────────────────────────────────────── */
.orc-hero {
    border-radius: 10px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
    overflow: hidden;
}
.orc-hero h1 { font-size: 1.7rem; font-weight: 700; margin: 0 0 0.3rem; letter-spacing: -0.025em; }
.orc-hero p  { font-size: 0.875rem; margin: 0; font-weight: 400; opacity: 0.6; }

/* ── Status dot ─────────────────────────────────────── */
.orc-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 5px; vertical-align: middle;
}

/* ── Section heading ─────────────────────────────────── */
.orc-section-title {
    font-size: 0.7rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin: 1.75rem 0 0.875rem;
    padding-bottom: 0.5rem;
}

/* ── Streamlit widget overrides ─────────────────────── */
hr { margin: 1.25rem 0 !important; }
[data-testid="stChatMessage"] { border-radius: 8px !important; }
[data-testid="stExpander"]    { border-radius: 8px !important; }
.streamlit-expanderHeader { font-size: 0.85rem !important; font-weight: 600 !important; }
/* Chat input bar — prevent black bar in light mode */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stChatInputContainer"],
[data-testid="stChatInputContainer"] > div { border-radius: 8px !important; }
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important; font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important; font-weight: 600 !important;
    text-transform: uppercase; letter-spacing: 0.06em !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 0; }
.stTabs [data-baseweb="tab"] {
    font-size: 0.85rem; font-weight: 500;
    padding: 0.55rem 1rem;
    border-radius: 6px 6px 0 0;
}

/* ── Page link navigation (st.page_link) ────────────── */
[data-testid="stPageLink"] { min-width: 0; }
[data-testid="stPageLink"] a {
    text-decoration: none !important;
    padding: 0.28rem 0.5rem !important;
    border-radius: 5px !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
    display: block !important;
    text-align: center !important;
    transition: background 0.15s, color 0.15s !important;
}
/* orc-nav-logo inside column */
.orc-nav-logo {
    display: flex;
    align-items: center;
    padding: 0.35rem 0;
}

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 768px) {
    .orc-hero { padding: 1.1rem; }
    .orc-hero h1 { font-size: 1.25rem; }
    .orc-hero p  { font-size: 0.8rem; }
    .orc-metric  { padding: 0.85rem 0.6rem; }
    .orc-metric .orc-metric-val  { font-size: 1.35rem; }
    .orc-metric .orc-metric-icon { font-size: 1.05rem; }
    .orc-pub { padding: 0.75rem 0.85rem 0.75rem 1rem; }
    .block-container { padding-top: 0.75rem !important; padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
    .orc-card { padding: 0.75rem 0.9rem !important; }
    /* Wrap columns to 2-per-row on mobile */
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    [data-testid="column"] { min-width: 45% !important; flex: 1 1 45% !important; }
    /* Slightly taller buttons for tap targets */
    .stButton > button { min-height: 2.5rem !important; }
    /* Navbar compact */
    .orc-nav-item { padding: 0.3rem 0.45rem !important; font-size: 0.72rem !important; }
    [data-testid="stPageLink"] a { font-size: 0.72rem !important; padding: 0.25rem 0.3rem !important; }
}
@media (max-width: 480px) {
    .orc-hero h1 { font-size: 1.1rem; }
    .orc-section-title { font-size: 0.65rem !important; }
}
</style>
"""

# ── Dark-mode overrides ───────────────────────────────────────────────────────
_DARK_CSS = """
<style>
/* Global — covers all known Streamlit 1.x container selectors */
.stApp,
[data-testid="stApp"]                   {{ background-color: {bg} !important; color: {text} !important; }}
.stApp *, [data-testid="stApp"] *       {{ color: {text}; }}
.stApp p, .stApp span,
.stApp li, .stApp label                 {{ color: {text} !important; }}
.stApp h1,.stApp h2,.stApp h3,
.stApp h4,.stApp h5,.stApp h6           {{ color: {text} !important; }}
[data-testid="stAppViewContainer"]      {{ background-color: {bg} !important; }}
[data-testid="stMain"]                  {{ background-color: {bg} !important; }}
[data-testid="stMainBlockContainer"]    {{ background-color: {bg} !important; }}
.main, .main .block-container           {{ background-color: {bg} !important; }}
body                                    {{ background-color: {bg} !important; }}

/* Streamlit chrome */
.stMetric label                         {{ color: {text2} !important; }}
.stMetric [data-testid="stMetricValue"] {{ color: {text}  !important; }}
[data-testid="stSidebar"]               {{ background-color: {surface} !important; border-right: 1px solid {border}; }}
hr                                      {{ border-color: {border} !important; opacity: 1 !important; }}

/* Inputs */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea      {{ background: {surface2} !important; border-color: {border} !important; color: {text} !important; border-radius: 6px !important; }}
[data-baseweb="select"] > div           {{ background: {surface2} !important; color: {text}  !important; border-color: {border} !important; border-radius: 6px !important; }}
[data-baseweb="select"] li              {{ background: {surface2} !important; color: {text}  !important; }}
[data-baseweb="popover"] [role="option"] {{ background: {surface2} !important; color: {text}  !important; }}

/* Buttons */
.stButton > button                      {{ background: {surface2} !important; border: 1px solid {border} !important; color: {text} !important; font-weight: 500 !important; border-radius: 6px !important; }}
.stButton > button:hover                {{ border-color: {accent} !important; color: {accent} !important; }}
.stButton > button[kind="primary"]      {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; }}
.stButton > button[kind="primary"]:hover {{ opacity: 0.87 !important; }}
[data-testid="stFormSubmitButton"] > button {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; border-radius: 6px !important; }}

/* Download button */
[data-testid="stDownloadButton"] > button {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; border-radius: 6px !important; font-weight: 500 !important; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"]   {{ background: transparent !important; border-bottom: 1px solid {border}; }}
.stTabs [data-baseweb="tab"]        {{ color: {text2} !important; background: transparent !important; border-bottom: 2px solid transparent; margin-bottom: -1px; }}
.stTabs [aria-selected="true"]      {{ color: {accent} !important; border-bottom-color: {accent} !important; background: transparent !important; font-weight: 600 !important; }}

/* Expander */
.streamlit-expanderHeader           {{ color: {text} !important; }}
[data-testid="stExpander"]          {{ border: 1px solid {border} !important; background: {surface} !important; border-radius: 6px !important; }}

/* Cards */
.orc-card    {{ background: {surface} !important; color: {text} !important; border: 1px solid {border}; box-shadow: 0 1px 3px rgba(1,4,9,.5); }}
.orc-card *  {{ color: {text} !important; }}
.orc-metric  {{ background: {surface} !important;  border: 1px solid {border}; box-shadow: 0 1px 3px rgba(1,4,9,.5); }}
.orc-metric .orc-metric-val {{ color: {text};  }}
.orc-metric .orc-metric-lbl {{ color: {text2}; }}
.orc-pub     {{ background: {surface} !important;  border-left-color: {accent}; box-shadow: 0 1px 2px rgba(1,4,9,.3); }}
.orc-pub .orc-pub-title {{ color: {text};  }}
.orc-pub .orc-pub-meta  {{ color: {text2}; }}

/* Hero */
.orc-hero    {{ background: linear-gradient(135deg, {surface} 0%, {surface2} 100%) !important; border: 1px solid {border}; }}
.orc-hero h1 {{ color: {text} !important;  }}
.orc-hero p  {{ color: {text2} !important; }}

/* Badges */
.orc-badge-oa     {{ background: rgba(63,185,80,.12);  color: {success}; }}
.orc-badge-year   {{ background: rgba(47,129,247,.12); color: {accent};  }}
.orc-badge-cite   {{ background: rgba(163,113,247,.12);color: {accent2}; }}
.orc-badge-closed {{ background: rgba(110,118,129,.15);color: {muted};   }}

/* Section title */
.orc-section-title {{ color: {text2} !important; border-bottom: 1px solid {border}; }}

/* Alert/info boxes */
[data-testid="stAlert"]             {{ border-radius: 6px !important; }}

/* Chat input bar */
[data-testid="stBottom"]            {{ background: {bg} !important; }}
[data-testid="stBottom"] > div      {{ background: {bg} !important; }}
[data-testid="stChatInputContainer"]       {{ background: {surface} !important; border: 1px solid {border} !important; border-radius: 10px !important; }}
[data-testid="stChatInputContainer"] textarea {{ background: {surface} !important; color: {text} !important; }}

/* Chat messages */
[data-testid="stChatMessage"]       {{ background: {surface} !important; }}
[data-testid="stChatMessage"] *     {{ color: {text} !important; }}
[data-testid="stChatMessage"] code  {{ background: {surface2} !important; border-radius: 3px !important; padding: 0.1rem 0.35rem !important; }}
[data-testid="stChatMessage"] pre   {{ background: {surface2} !important; border-radius: 6px !important; padding: 0.65rem !important; }}

/* Markdown containers */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] em     {{ color: {text} !important; }}
[data-testid="stText"]                     {{ color: {text} !important; }}
[data-testid="stCaption"]                  {{ color: {text2} !important; }}

/* Dropdown popover items */
[data-baseweb="menu"]                      {{ background: {surface2} !important; }}
[data-baseweb="menu"] li,
[data-baseweb="option"]                    {{ background: {surface2} !important; color: {text} !important; }}

/* Toggle / checkbox labels */
[data-testid="stToggle"] label,
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label              {{ color: {text} !important; }}

/* Select slider value */
[data-testid="stSlider"] [data-testid="stTickBarMin"],
[data-testid="stSlider"] [data-testid="stTickBarMax"] {{ color: {text2} !important; }}

/* Navbar */
.orc-navbar  {{ background: {surface} !important; border-bottom-color: {border}; }}
.orc-nav-logo {{ color: {text} !important; border-right-color: {border}; }}
.orc-nav-item {{ color: {text2} !important; }}
.orc-nav-item:hover {{ background: {surface2} !important; color: {text} !important; }}
.orc-nav-item.active {{ background: {surface2} !important; color: {accent} !important; font-weight: 600; }}

/* Icon / emoji containers — ensure contrast */
.orc-metric .orc-metric-icon {{ filter: none; }}
.orc-dot {{ border: 1px solid rgba(255,255,255,0.1); }}

/* Toggle button override */
.stButton > button[title*="Light"],
.stButton > button[title*="Dark"] {{ min-width: 80px !important; }}

/* Page link nav (st.page_link) */
[data-testid="stPageLink"] a {{ color: {text2} !important; }}
[data-testid="stPageLink"] a:hover {{ background: {surface2} !important; color: {text} !important; }}
[data-testid="stPageLink"] a[aria-current="page"] {{
    background: {surface2} !important;
    color: {accent} !important;
    font-weight: 600 !important;
}}
</style>
"""

# ── Light-mode overrides ──────────────────────────────────────────────────────
_LIGHT_CSS = """
<style>
/* Global — covers all known Streamlit 1.x container selectors */
.stApp,
[data-testid="stApp"]                   {{ background-color: {bg} !important; color: {text} !important; }}
.stApp *, [data-testid="stApp"] *       {{ color: {text}; }}
.stApp p, .stApp span,
.stApp li, .stApp label                 {{ color: {text} !important; }}
.stApp h1,.stApp h2,.stApp h3,
.stApp h4,.stApp h5,.stApp h6           {{ color: {text} !important; }}
[data-testid="stAppViewContainer"]      {{ background-color: {bg} !important; }}
[data-testid="stMain"]                  {{ background-color: {bg} !important; }}
[data-testid="stMainBlockContainer"]    {{ background-color: {bg} !important; }}
.main, .main .block-container           {{ background-color: {bg} !important; }}
body                                    {{ background-color: {bg} !important; }}

/* Streamlit chrome */
.stMetric label                         {{ color: {text2} !important; }}
.stMetric [data-testid="stMetricValue"] {{ color: {text}  !important; }}
[data-testid="stSidebar"]               {{ background-color: {surface} !important; border-right: 1px solid {border}; }}
hr                                      {{ border-color: {border} !important; opacity: 1 !important; }}

/* Inputs */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea      {{ background: {bg}     !important; border-color: {border} !important; color: {text} !important; border-radius: 6px !important; }}
[data-baseweb="select"] > div           {{ background: {bg}     !important; color: {text}   !important; border-color: {border} !important; border-radius: 6px !important; }}
[data-baseweb="select"] li              {{ background: {surface} !important; color: {text}  !important; }}
[data-baseweb="popover"] [role="option"] {{ background: {surface} !important; color: {text} !important; }}

/* Buttons */
.stButton > button                      {{ background: {bg} !important; border: 1px solid {border} !important; color: {text} !important; font-weight: 500 !important; border-radius: 6px !important; }}
.stButton > button:hover                {{ border-color: {accent} !important; color: {accent} !important; background: {surface} !important; }}
.stButton > button[kind="primary"]      {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; }}
.stButton > button[kind="primary"]:hover {{ opacity: 0.88 !important; }}
[data-testid="stFormSubmitButton"] > button {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; border-radius: 6px !important; }}

/* Download button */
[data-testid="stDownloadButton"] > button {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; border-radius: 6px !important; font-weight: 500 !important; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"]   {{ background: transparent !important; border-bottom: 1px solid {border}; }}
.stTabs [data-baseweb="tab"]        {{ color: {text2} !important; background: transparent !important; border-bottom: 2px solid transparent; margin-bottom: -1px; }}
.stTabs [aria-selected="true"]      {{ color: {accent} !important; border-bottom-color: {accent} !important; background: transparent !important; font-weight: 600 !important; }}

/* Expander */
.streamlit-expanderHeader           {{ color: {text} !important; }}
[data-testid="stExpander"]          {{ border: 1px solid {border} !important; background: {surface} !important; border-radius: 6px !important; }}

/* Cards */
.orc-card    {{ background: {surface} !important; color: {text} !important; border: 1px solid {border}; box-shadow: 0 1px 2px rgba(31,35,40,.08); }}
.orc-card *  {{ color: {text} !important; }}
.orc-metric  {{ background: {surface} !important;  border: 1px solid {border}; box-shadow: 0 1px 2px rgba(31,35,40,.08); }}
.orc-metric .orc-metric-val {{ color: {text};  }}
.orc-metric .orc-metric-lbl {{ color: {text2}; }}
.orc-pub     {{ background: {surface} !important;  border-left-color: {accent}; box-shadow: 0 1px 2px rgba(31,35,40,.06); }}
.orc-pub .orc-pub-title {{ color: {text};  }}
.orc-pub .orc-pub-meta  {{ color: {text2}; }}

/* Hero */
.orc-hero    {{ background: linear-gradient(135deg, {surface} 0%, {surface2} 100%) !important; border: 1px solid {border}; }}
.orc-hero h1 {{ color: {text} !important;  }}
.orc-hero p  {{ color: {text2} !important; }}

/* Badges */
.orc-badge-oa     {{ background: rgba(26,127,55,.1);   color: {success}; }}
.orc-badge-year   {{ background: rgba(9,105,218,.1);   color: {accent};  }}
.orc-badge-cite   {{ background: rgba(130,80,223,.1);  color: {accent2}; }}
.orc-badge-closed {{ background: rgba(110,119,129,.1); color: {muted};   }}

/* Section title */
.orc-section-title {{ color: {text2} !important; border-bottom: 1px solid {border}; }}

/* Alert/info boxes */
[data-testid="stAlert"]             {{ border-radius: 6px !important; }}

/* Chat input bar */
[data-testid="stBottom"]            {{ background: {bg} !important; }}
[data-testid="stBottom"] > div      {{ background: {bg} !important; }}
[data-testid="stChatInputContainer"]       {{ background: {surface} !important; border: 1px solid {border} !important; border-radius: 10px !important; }}
[data-testid="stChatInputContainer"] textarea {{ background: {surface} !important; color: {text} !important; }}

/* Chat messages */
[data-testid="stChatMessage"]       {{ background: {surface} !important; }}
[data-testid="stChatMessage"] *     {{ color: {text} !important; }}
[data-testid="stChatMessage"] code  {{ background: {surface2} !important; border-radius: 3px !important; padding: 0.1rem 0.35rem !important; }}
[data-testid="stChatMessage"] pre   {{ background: {surface2} !important; border-radius: 6px !important; padding: 0.65rem !important; }}

/* Markdown containers */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] em     {{ color: {text} !important; }}
[data-testid="stText"]                     {{ color: {text} !important; }}
[data-testid="stCaption"]                  {{ color: {text2} !important; }}

/* Dropdown popover items */
[data-baseweb="menu"]                      {{ background: {surface2} !important; }}
[data-baseweb="menu"] li,
[data-baseweb="option"]                    {{ background: {surface2} !important; color: {text} !important; }}

/* Toggle / checkbox / radio labels */
[data-testid="stToggle"] label,
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label              {{ color: {text} !important; }}

/* Navbar — light mode */
.orc-navbar  {{ background: {surface} !important; border-bottom-color: {border}; }}
.orc-nav-logo {{ color: {text} !important; border-right-color: {border}; }}
.orc-nav-item {{ color: {text2} !important; }}
.orc-nav-item:hover {{ background: {surface2} !important; color: {text} !important; }}
.orc-nav-item.active {{ background: {surface2} !important; color: {accent} !important; font-weight: 600; }}

/* Icon / emoji containers — light-mode contrast */
.orc-dot {{ border: 1px solid rgba(0,0,0,0.08); }}

/* Page link nav (st.page_link) */
[data-testid="stPageLink"] a {{ color: {text2} !important; }}
[data-testid="stPageLink"] a:hover {{ background: {surface2} !important; color: {text} !important; }}
[data-testid="stPageLink"] a[aria-current="page"] {{
    background: {surface2} !important;
    color: {accent} !important;
    font-weight: 600 !important;
}}
</style>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def apply_styles():
    """
    Inject global CSS into the current page.
    Must be called on every page after set_page_config().
    Also syncs the theme from query params so the toggle propagates.
    """
    params = st.query_params
    if "theme" in params:
        st.session_state.theme_mode = params["theme"]
    elif "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "dark"

    theme  = get_theme()
    colors = DARK if theme == "dark" else LIGHT

    st.markdown(_BASE_CSS, unsafe_allow_html=True)
    st.markdown((_DARK_CSS if theme == "dark" else _LIGHT_CSS).format(**colors),
                unsafe_allow_html=True)


# ── HTML component helpers ────────────────────────────────────────────────────

def metric_card_html(icon: str, value: str, label: str) -> str:
    """
    Generate an HTML snippet for a compact metric card containing an icon, value, and label.
    
    Parameters:
        icon (str): HTML or plain text to render as the metric icon (e.g., emoji, SVG, or icon markup).
        value (str): Primary metric value to display; may include simple HTML.
        label (str): Secondary label or description for the metric; may include simple HTML.
    
    Returns:
        str: A small HTML block for an `.orc-metric` card ready to render with `unsafe_allow_html`.
    """
    return (
        f'<div class="orc-metric">'
        f'  <div class="orc-metric-icon">{icon}</div>'
        f'  <div class="orc-metric-val">{value}</div>'
        f'  <div class="orc-metric-lbl">{label}</div>'
        f'</div>'
    )


def badge_html(text: str, kind: str = "year") -> str:
    """
    Produce an HTML span element styled as a badge.
    
    Parameters:
        text (str): Visible text to place inside the badge.
        kind (str): Badge variant; one of `'oa'`, `'year'`, `'cite'`, or `'closed'`. This selects the `orc-badge-{kind}` CSS modifier.
    
    Returns:
        html (str): HTML string for a `<span>` element with classes `orc-badge` and `orc-badge-{kind}` containing `text`.
    """
    return f'<span class="orc-badge orc-badge-{kind}">{text}</span>'


def _esc(v) -> str:
    from html import escape
    return escape("" if v is None else str(v), quote=True)


def _safe_title(v) -> str:
    """Escape HTML but preserve <sub> and <sup> tags (chemical formulas, etc.)."""
    from html import escape
    safe = escape("" if v is None else str(v), quote=False)
    safe = safe.replace("&lt;sub&gt;", "<sub>").replace("&lt;/sub&gt;", "</sub>")
    safe = safe.replace("&lt;sup&gt;", "<sup>").replace("&lt;/sup&gt;", "</sup>")
    return safe


def pub_card_html(title: str, authors: list, journal: str, year,
                  citations: int, is_oa: bool, abstract: str = "") -> str:
    auth_html = ""
    if authors:
        shown = ", ".join(_esc(a) for a in authors[:3] if a)
        if len(authors) > 3:
            shown += f" +{len(authors) - 3}"
        auth_html = f'<div class="orc-pub-meta">👥 {shown}</div>'

    badges = ""
    if year:
        badges += badge_html(_esc(year), "year")
    badges += badge_html("Open Access", "oa") if is_oa else badge_html("Subscription", "closed")
    if citations:
        badges += badge_html(f"{citations:,} citations", "cite")

    abs_html = ""
    if abstract:
        snippet = _esc(abstract[:220]) + ("…" if len(abstract) > 220 else "")
        abs_html = (
            f'<div class="orc-pub-meta" style="margin-top:0.5rem;font-style:italic;opacity:0.65">'
            f'{snippet}</div>'
        )

    return (
        f'<div class="orc-pub">'
        f'  <div class="orc-pub-title">{_safe_title(title)}</div>'
        f'  {auth_html}'
        f'  <div class="orc-pub-meta" style="margin-top:0.3rem">📰 {_esc(journal)}</div>'
        f'  <div style="margin-top:0.45rem">{badges}</div>'
        f'  {abs_html}'
        f'</div>'
    )


def hero_html(title: str, subtitle: str) -> str:
    """
    Render a hero section as an HTML string containing a title and subtitle.
    
    Parameters:
        title (str): The heading text for the hero section.
        subtitle (str): The descriptive subtitle or subheading text.
    
    Returns:
        html (str): HTML markup for a `.orc-hero` block with the given title and subtitle.
    """
    return (
        f'<div class="orc-hero">'
        f'  <h1>{title}</h1>'
        f'  <p>{subtitle}</p>'
        f'</div>'
    )


def section_title_html(text: str) -> str:
    """
    Create an HTML paragraph element styled as a section title.
    
    Returns:
        An HTML string for a <p> element with class "orc-section-title" containing the provided text.
    """
    return f'<p class="orc-section-title">{text}</p>'


def theme_toggle_html() -> str:
    return "☀️ Light" if get_theme() == "dark" else "🌙 Dark"


def render_navbar(current: str = "") -> None:
    """
    Render a horizontal top navigation bar using st.page_link() for true SPA
    routing (no full page reload on navigation).
    `current` is accepted for backwards compatibility but is no longer used;
    Streamlit marks the active page automatically via aria-current="page".
    """
    _PAGES = [
        ("pages/0_Home.py",         "🏠", "Home"),
        ("pages/1_Publications.py", "📚", "Publications"),
        ("pages/2_AI_Assistant.py", "🤖", "AI"),
        ("pages/4_Analytics.py",    "📊", "Analytics"),
        ("pages/6_Settings.py",     "⚙️", "Settings"),
        ("pages/5_Bug_Report.py",   "🐛", "Report"),
        ("pages/3_Admin.py",        "🔐", "Admin"),
    ]
    logo_col, *nav_cols = st.columns([1.5] + [1] * len(_PAGES))
    with logo_col:
        st.markdown('<div class="orc-nav-logo">🔬 ORC</div>', unsafe_allow_html=True)
    for col, (path, icon, label) in zip(nav_cols, _PAGES):
        with col:
            st.page_link(path, label=f"{icon} {label}", use_container_width=True)
    st.markdown('<hr style="margin:0 0 1.25rem !important">', unsafe_allow_html=True)


def footer_html(extra: str = "") -> str:
    """
    Builds a centered footer HTML block containing product/version, an optional extra line, and a "Built by" credit link.
    
    Uses the active theme to select muted and accent colors for text and link styling.
    
    Parameters:
        extra (str): Optional HTML content rendered as an additional paragraph below the version line. If empty, no extra paragraph is included.
    
    Returns:
        html (str): An HTML string for a centered footer styled according to the current theme.
    """
    c = DARK if get_theme() == "dark" else LIGHT
    extra_line = f"<p style='margin:0.1rem 0 0'>{extra}</p>" if extra else ""
    return (
        f'<div style="text-align:center;color:{c["muted"]};font-size:0.78rem;padding:0.5rem 0 1rem">'
        f'  <p style="margin:0">ORC Research Dashboard · v1.0</p>'
        f'  {extra_line}'
        f'  <p style="margin:0.2rem 0 0">Built by '
        f'    <a href="https://www.linkedin.com/in/fahad-al-jubalie-55973926/" '
        f'       target="_blank" rel="noopener noreferrer" style="color:{c["accent"]};text-decoration:none;font-weight:500">'
        f'      Fahad Al-Jubalie</a>'
        f'  </p>'
        f'</div>'
    )
